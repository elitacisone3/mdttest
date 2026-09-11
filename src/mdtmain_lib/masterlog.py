"""Output ndjson di src/scanlogs: log/masterSpool.ndjson (buffer di invio
pendente verso /api/masterLog, svuotato a invio riuscito O a errore HTTP
400 — mai altrimenti) e log/master.ndjson (copia storica permanente, mai
troncata). Stile "spool" analogo a evidence.py (vedi le sue funzioni
spool_dir/list_spool_files/ecc.) ma per un flat file append-only invece
di file .tar.gz.gpg individuali per ogni evidenza — modulo separato
perche' evidence.py si dichiara esplicitamente scoperto a "packaging
tar.gz/GPG/hashing/retention" di quell'artefatto binario, concettualmente
diverso da questo.

fcntl.flock: log/masterSpool.ndjson puo' essere toccato da due processi
mdtmain indipendenti (es. uno --edge-mode con test continuato in corso e
un invio manuale avviato da un'altra sessione nello stesso momento) - una
sezione critica minima evita che un invio in corso (lettura+troncamento)
perda un'aggiunta concorrente."""
import fcntl
import os
import subprocess

from . import constants, httpclient, syslog_log


class ScanlogsError(Exception):
    pass


def run_scanlogs(outdir, timeout=120):
    """Esegue src/scanlogs <outdir> e ritorna il suo stdout (ndjson, puo'
    essere vuoto: "nessuna evidenza", non un errore). Solleva
    ScanlogsError SOLO se lo script stesso fallisce (exit non zero, non
    trovato, timeout)."""
    try:
        proc = subprocess.run(
            [constants.SCANLOGS_SCRIPT, outdir],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise ScanlogsError(str(e))
    if proc.returncode != 0:
        raise ScanlogsError(proc.stderr.strip() or f"scanlogs: exit {proc.returncode}")
    return proc.stdout


def append_scan_output(ndjson_text):
    """Aggiunge ndjson_text (stdout gia' prodotto da src/scanlogs) sia a
    log/masterSpool.ndjson (buffer di invio) sia a log/master.ndjson
    (storico permanente, MAI troncato) — no-op se ndjson_text e' vuoto
    (nessuna evidenza rilevante in questo test)."""
    if not ndjson_text:
        return
    text = ndjson_text if ndjson_text.endswith("\n") else ndjson_text + "\n"
    os.makedirs(os.path.dirname(constants.MASTER_SPOOL_FILE), exist_ok=True)
    with open(constants.MASTER_SPOOL_FILE, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(text)
    with open(constants.MASTER_LOG_FILE, "a") as f:
        f.write(text)


def flush_masterlog(host):
    """Se log/masterSpool.ndjson non e' vuoto, ne invia il contenuto
    ATTUALE (non solo l'ultima aggiunta: puo' contenere il residuo di
    tentativi falliti precedenti) a POST {host}/api/masterLog. Risposta
    200 o 400 -> tronca masterSpool.ndjson a vuoto (400 = almeno una
    riga non valida, ma il server ha comunque "gestito" l'invio, quindi
    lo spool si svuota comunque, come da specifica). Qualunque altro
    esito (errore di rete/altro status HTTP) -> lo lascia INVARIATO per
    un tentativo successivo. Ritorna True se il file e' stato
    troncato, False altrimenti (incluso il caso "niente da inviare")."""
    path = constants.MASTER_SPOOL_FILE
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return False
    with open(path, "r+b") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        data = f.read()
        if not data:
            return False
        try:
            resp = httpclient.push_masterlog(host, data)
        except httpclient.ServerError as e:
            syslog_log.error(f"mdtmain: invio masterLog fallito (rete: {e}).")
            return False
        status = getattr(resp, "status", getattr(resp, "code", None))
        if status in (200, 400):
            f.seek(0)
            f.truncate()
            if status == 200:
                syslog_log.info("mdtmain: masterLog inviato al server.")
            else:
                syslog_log.warning("mdtmain: masterLog: risposta HTTP 400 (righe scartate), svuotato comunque.")
            return True
        syslog_log.error(f"mdtmain: invio masterLog fallito (risposta HTTP {status}).")
        return False
