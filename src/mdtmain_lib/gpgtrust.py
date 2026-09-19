"""Verifica della catena di fiducia fra la chiave GPG radice/master
(src/res/auth.pub) e la chiave usata come destinatario per cifrare le
evidenze (main_configs/data.pub) — vedi verify_evidence_keys().

Le funzioni GPG di base (_run_gpg/key_fingerprint/import_key/
is_signed_by) sono la STESSA logica di src/testauth (stesso stile: solo
il binario gpg via subprocess, mai python-gnupg, sempre un GNUPGHOME
temporaneo isolato), duplicata qui VOLUTAMENTE invece di essere
condivisa per import: src/testauth e' un tool a se stante e di sicurezza
critica (autorizzazione al cambio IMEI, porta anche il corrispettivo PHP
tool/mkimei sul server) e non deve dipendere da mdtmain_lib ne' rischiare
regressioni per un refactor cross-uso."""
import os
import subprocess
import tempfile


class GpgTrustError(Exception):
    pass


def _run_gpg(args, gnupghome=None, input_bytes=None):
    env = os.environ.copy()
    if gnupghome is not None:
        env["GNUPGHOME"] = gnupghome
    return subprocess.run(
        ["gpg", "--batch", "--yes", "--no-tty", "--pinentry-mode", "loopback", *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def key_fingerprint(key_bytes):
    """Ricava l'impronta di una chiave GPG SENZA importarla in nessun
    portachiavi ("--dry-run --import-options show-only"). Ritorna None
    se key_bytes non contiene una chiave GPG valida."""
    proc = _run_gpg(["--with-colons", "--import-options", "show-only", "--dry-run", "--import"],
                     input_bytes=key_bytes)
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        fields = line.split(":")
        if fields[0] == "fpr" and len(fields) > 9 and fields[9]:
            return fields[9].upper()
    return None


def import_key(gnupghome, key_bytes):
    proc = _run_gpg(["--import"], gnupghome=gnupghome, input_bytes=key_bytes)
    if proc.returncode != 0:
        raise GpgTrustError("import della chiave GPG fallito: " + proc.stderr.decode("utf-8", "replace").strip())


def is_signed_by(gnupghome, target_fpr, issuer_fpr):
    """True se, nel GNUPGHOME indicato (target_fpr e issuer_fpr gia'
    importate), la chiave target_fpr porta una firma VALIDA
    (crittograficamente verificata da gpg, non solo presente) della
    chiave issuer_fpr. Usa "--check-sigs" (verifica le firme) e non
    "--list-sigs" (le elencherebbe soltanto, senza verificarle) — vedi la
    colonna di validita' ('!') nell'output --with-colons.

    "--allow-weak-key-signatures" e' necessario per chiavi radice DSA
    (come src/res/auth.pub, dsa1024): DSA si accoppia naturalmente con
    SHA-1 e senza questo flag GnuPG >= 2.2.31 rifiuta a priori qualunque
    firma di terze parti fatta con SHA-1, riportando validita' '%'
    invece di '!' — verificato empiricamente con la vera
    src/res/auth.pub. Stessa logica di src/testauth.is_signed_by()."""
    proc = _run_gpg(["--with-colons", "--check-sigs", "--allow-weak-key-signatures", target_fpr],
                     gnupghome=gnupghome)
    issuer_tail = issuer_fpr[-16:].upper()
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        fields = line.split(":")
        if fields[0] != "sig" or len(fields) < 5:
            continue
        validity = fields[1]
        issuer_keyid = fields[4].upper()
        issuer_fpr_field = fields[12].upper() if len(fields) > 12 else ""
        if validity == "!" and (issuer_keyid == issuer_tail or issuer_fpr_field == issuer_fpr):
            return True
    return False


def verify_evidence_keys(auth_pubkey_file, data_pubkey_file):
    """Verifica che auth_pubkey_file e data_pubkey_file esistano e
    contengano chiavi GPG valide, e che data_pubkey_file sia valida come
    destinatario delle evidenze: o e' la STESSA chiave di
    auth_pubkey_file, o e' firmata da essa (is_signed_by). Ritorna la
    lista dei fingerprint dei due file (uno o due, senza deduplicare: la
    deduplicazione dei destinatari identici la fa gia' gpg in
    evidence.gpg_encrypt). Solleva GpgTrustError, con un messaggio
    descrittivo in italiano adatto a essere mostrato in una msgbox, al
    primo problema incontrato."""
    if not os.path.isfile(auth_pubkey_file):
        raise GpgTrustError(f"chiave radice non trovata: {auth_pubkey_file}")
    if not os.path.isfile(data_pubkey_file):
        raise GpgTrustError(f"chiave dati non trovata: {data_pubkey_file}")

    with open(auth_pubkey_file, "rb") as f:
        auth_bytes = f.read()
    with open(data_pubkey_file, "rb") as f:
        data_bytes = f.read()

    auth_fpr = key_fingerprint(auth_bytes)
    if auth_fpr is None:
        raise GpgTrustError(f"{auth_pubkey_file}: chiave GPG non valida")
    data_fpr = key_fingerprint(data_bytes)
    if data_fpr is None:
        raise GpgTrustError(f"{data_pubkey_file}: chiave GPG non valida")

    if data_fpr == auth_fpr:
        return [auth_fpr]

    with tempfile.TemporaryDirectory(prefix="mdtmain-gpgtrust-") as gnupghome:
        os.chmod(gnupghome, 0o700)
        import_key(gnupghome, auth_bytes)
        import_key(gnupghome, data_bytes)
        if not is_signed_by(gnupghome, data_fpr, auth_fpr):
            raise GpgTrustError(
                f"la chiave in {data_pubkey_file} non e' firmata dalla chiave radice "
                f"{auth_pubkey_file}")
    return [auth_fpr, data_fpr]
