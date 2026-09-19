"""Packaging (tar.gz), cifratura GPG, hashing e retention dell'evidenza
del test continuo. Stile GPG coerente con src/testauth._run_gpg: sempre il
binario di sistema via subprocess, mai una libreria python-gnupg, sempre
un GNUPGHOME temporaneo isolato e distrutto a fine funzione."""
import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timedelta

from . import constants, gpgtrust

TIMESTAMP_DIR_RE = re.compile(r"^\d{14}$")  # yyyymmddhhmmss


class EvidenceError(Exception):
    pass


def timestamp_now():
    return datetime.now().strftime("%Y%m%d%H%M%S")


def should_keep_full_evidence(manifest):
    """Regola: se il test e' OK, non ci sono warning/errori diag (vedi
    "diagWarn"/"diagError" nel manifest, calcolati da mdtcap con
    compute_diag_warn_count()/compute_diag_error_count() sul log di
    qcsuper) e (non --extra o extraLevel=='I'), basta conservare/inviare
    manifest.json. Altrimenti tutta l'evidenza. Un diagError puo'
    significare un'intera categoria di traffico mancante dal .dlf senza
    che OK/hasMDT/hasRRC se ne accorgano (vedi doc/GUIDA_MDTCAP.md):
    merita comunque l'evidenza completa, per poterlo diagnosticare in un
    secondo momento."""
    if not manifest.get("OK", False):
        return True
    if manifest.get("diagWarn", 0) or manifest.get("diagError", 0):
        return True
    if manifest.get("extended") and manifest.get("extraLevel", "I") != "I":
        return True
    return False


def package_dir(src_dir, only_manifest, dest_path=None):
    """Crea un tar.gz da src_dir (l'intera directory, oppure solo
    manifest.json se only_manifest e' vero) e ritorna il percorso creato."""
    name = os.path.basename(os.path.normpath(src_dir))
    if dest_path is None:
        dest_path = tempfile.mktemp(prefix=f"mdtmain-{name}-", suffix=".tar.gz")
    with tarfile.open(dest_path, "w:gz") as tar:
        if only_manifest:
            manifest_path = os.path.join(src_dir, "manifest.json")
            if not os.path.isfile(manifest_path):
                raise EvidenceError(f"manifest.json non trovato in {src_dir}")
            tar.add(manifest_path, arcname=os.path.join(name, "manifest.json"))
        else:
            tar.add(src_dir, arcname=name)
    return dest_path


def gpg_encrypt(path_in, pubkey_files=None, path_out=None):
    """Cifra path_in verso i destinatari di TUTTI i pubkey_files (default:
    la chiave radice src/res/auth.pub e la chiave dati main_configs/
    data.pub — vedi gpgtrust.verify_evidence_keys, chiamata separatamente
    all'avvio di mdtmain per validare che queste due chiavi siano davvero
    in relazione di fiducia). Se due file coincidono (stessa chiave),
    gpg deduplica da solo il destinatario: nessun caso speciale serve
    qui per il caso "solo chiave master" (stessa chiave in entrambi i
    file)."""
    pubkey_files = pubkey_files or [constants.AUTH_PUBKEY_FILE, constants.DATA_PUBKEY_FILE]
    for f in pubkey_files:
        if not os.path.isfile(f):
            raise EvidenceError(f"chiave pubblica non trovata: {f}")
    path_out = path_out or (path_in + ".gpg")
    try:
        with tempfile.TemporaryDirectory(prefix="mdtmain-gnupg-") as gnupghome:
            os.chmod(gnupghome, 0o700)
            fprs = []
            for f in pubkey_files:
                with open(f, "rb") as fh:
                    key_bytes = fh.read()
                fpr = gpgtrust.key_fingerprint(key_bytes)
                if fpr is None:
                    raise EvidenceError(f"impossibile ricavare il fingerprint da {f}")
                gpgtrust.import_key(gnupghome, key_bytes)
                if fpr not in fprs:
                    fprs.append(fpr)
            env = os.environ.copy()
            env["GNUPGHOME"] = gnupghome
            recipient_args = []
            for fpr in fprs:
                recipient_args += ["--recipient", fpr]
            proc = subprocess.run(
                ["gpg", "--batch", "--yes", "--no-tty", "--trust-model", "always",
                 *recipient_args, "--output", path_out, "--encrypt", path_in],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            )
            if proc.returncode != 0:
                raise EvidenceError("cifratura GPG fallita: " + proc.stderr.decode(errors="replace").strip())
    except gpgtrust.GpgTrustError as e:
        raise EvidenceError(str(e))
    return path_out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pick_persistent_dir():
    """Directory di lavoro persistente per il test continuo: la chiavetta
    USB se gia' montata (stessa convenzione di usbmount), altrimenti la
    directory locale di fallback dentro il repo."""
    if os.path.ismount(constants.USB_MOUNTPOINT):
        base = os.path.join(constants.USB_MOUNTPOINT, "Evidenze_MDT_Continuo")
    else:
        base = constants.CONTINUOUS_LOCAL_DIR
    os.makedirs(base, exist_ok=True)
    return base


def cleanup_old_evidence(base_dir, days=constants.RETENTION_DAYS):
    if not os.path.isdir(base_dir):
        return
    cutoff = datetime.now() - timedelta(days=days)
    for name in os.listdir(base_dir):
        if not TIMESTAMP_DIR_RE.match(name):
            continue
        try:
            when = datetime.strptime(name, "%Y%m%d%H%M%S")
        except ValueError:
            continue
        if when < cutoff:
            shutil.rmtree(os.path.join(base_dir, name), ignore_errors=True)


def wipe_tmpfs(path):
    shutil.rmtree(path, ignore_errors=True)


# ---- spool di invio (log/spool) --------------------------------------------
# L'evidenza gia' pronta per l'upload (tar.gz cifrato GPG) vive qui, non in
# un file temporaneo: cosi' un invio immediato fallito (server
# irraggiungibile, errore di rete, ...) non perde il lavoro gia' fatto —
# resta in attesa di un tentativo successivo (scheduler.flush_spool(), o
# un invio manuale, vedi app.screen_send_spool_manually()) finche' non
# viene rimosso ESPLICITAMENTE, e solo a invio riuscito.

SPOOL_SUFFIX = ".tar.gz.gpg"


def spool_dir():
    os.makedirs(constants.SPOOL_DIR, exist_ok=True)
    return constants.SPOOL_DIR


def list_spool_files():
    """Percorsi dei file di evidenza in attesa di invio in log/spool, dal
    piu' vecchio al piu' recente (stesso ordine, FIFO, in cui vanno
    inviati)."""
    d = spool_dir()
    names = sorted(
        (n for n in os.listdir(d) if n.endswith(SPOOL_SUFFIX)),
        key=lambda n: os.path.getmtime(os.path.join(d, n)),
    )
    return [os.path.join(d, n) for n in names]


def spool_dirname(spool_path):
    """Il nome della directory di evidenza originale (es.
    "20260910023134", vedi evidence.timestamp_now()) da cui e' stato
    creato il file di spool indicato — il valore da passare come
    "nomeDirectory" a httpclient.push_evidence()."""
    name = os.path.basename(spool_path)
    if name.endswith(SPOOL_SUFFIX):
        name = name[:-len(SPOOL_SUFFIX)]
    for kind in (".full", ".json"):
        if name.endswith(kind):
            return name[:-len(kind)]
    return name


def spool_is_full(spool_path):
    """True se il file di spool indicato e' evidenza COMPLETA (non solo
    manifest.json) — vedi l'infisso ".full"/".json" aggiunto da
    prepare_for_upload, usato per contare correttamente E_POS
    (alarmstate.record_evidence_sent) anche per un invio ritardato
    (flush_spool), quando il manifest originale non e' piu'
    disponibile."""
    return os.path.basename(spool_path).endswith(".full" + SPOOL_SUFFIX)


def prepare_for_upload(outdir, manifest):
    """Impacchetta (tar.gz, solo manifest.json se should_keep_full_evidence
    dice di no) e cifra (GPG) l'evidenza di outdir, salvando il risultato
    DIRETTAMENTE in log/spool/ (mai un file temporaneo: vedi il commento
    di modulo sopra). Ritorna il percorso del file .tar.gz.gpg creato."""
    name = os.path.basename(os.path.normpath(outdir))
    only_manifest = not should_keep_full_evidence(manifest)
    kind = "json" if only_manifest else "full"
    dest = os.path.join(spool_dir(), f"{name}.{kind}.tar.gz")
    pkg = package_dir(outdir, only_manifest=only_manifest, dest_path=dest)
    try:
        return gpg_encrypt(pkg, path_out=pkg + ".gpg")
    finally:
        # Il tar.gz in chiaro non deve mai restare in log/spool: solo il
        # .gpg cifrato e' pensato per starci in attesa di invio.
        try:
            os.remove(pkg)
        except OSError:
            pass


def remove_from_spool(spool_path):
    try:
        os.remove(spool_path)
    except OSError:
        pass
