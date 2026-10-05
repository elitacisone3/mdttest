"""Gestione dei file pid di mdtmain (--edge-mode e --screen) e arresto
delle istanze registrate (l'arresto pulito su SIGTERM, lato istanza che
lo riceve, e' in stopctl.py).

Ogni avvio VERO di mdtmain (qualunque modalita', non solo --edge-mode:
vedi mdtmain --edge-mode) chiama stop_running_instance() prima di fare
qualunque altra cosa: se un'istanza --edge-mode precedente e' ancora in
esecuzione (file EDGE_MODE_PID_FILE con un pid vivo), viene terminata —
cosi' un uso interattivo (es. un tecnico collegato via SSH/schermo, o un
riavvio del servizio) non deve mai competere con il servizio automatico
per lo stesso modem/la stessa porta USB. Un'istanza --screen registra il
proprio pid in SCREEN_MODE_PID_FILE, che NON viene toccato da un nuovo
avvio, ma solo da mdtmain --stop (stop_instances), che ferma entrambe.
Il pid e' scritto (write_pid_file) DOPO il fork di screenmode.activate()
(altrimenti il pid registrato sarebbe quello del processo padre, che
esce subito)."""
import atexit
import os
import signal
import time

from . import constants, syslog_log

_GRACE_SECONDS = 5.0
_POLL_SECONDS = 0.1


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _is_mdtmain(pid):
    """Protezione da pid riciclati: un pid letto da un file pid viene
    segnalato solo se e' davvero un processo mdtmain."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            argv = f.read().split(b"\0")
    except OSError:
        return False
    return any(os.path.basename(a) == b"mdtmain" for a in argv)


def _read_pid(pid_file):
    try:
        with open(pid_file, "r") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _remove_pid_file(pid_file):
    try:
        os.remove(pid_file)
    except OSError:
        pass


def _live_instance(pid_file):
    """Pid dell'istanza mdtmain registrata in pid_file, o None (file
    assente/illeggibile, processo morto o non mdtmain: il file residuo
    viene rimosso). Mai il processo CORRENTE."""
    pid = _read_pid(pid_file)
    if pid is None or pid == os.getpid():
        return None
    if not _pid_alive(pid) or not _is_mdtmain(pid):
        _remove_pid_file(pid_file)
        return None
    return pid


def stop_instances(pid_files, grace_seconds, log_fn=None):
    """SIGTERM a ogni istanza viva registrata in pid_files, poi attende
    fino a grace_seconds che terminino (un'eventuale cattura mdtcap in
    corso viene chiusa in modo pulito, vedi stopctl.py); le istanze
    ancora vive allo scadere vengono uccise con SIGKILL insieme al loro
    gruppo di processi (mdtcap/dialog figli inclusi). Ritorna
    (pid fermati, pid uccisi con SIGKILL)."""
    log_fn = log_fn or (lambda _msg: None)
    targets = {}
    for pid_file in pid_files:
        pid = _live_instance(pid_file)
        if pid is None:
            continue
        log_fn(f"Fermo mdtmain (pid {pid})...")
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            _remove_pid_file(pid_file)
            continue
        targets[pid] = pid_file
    if not targets:
        return [], []

    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline and any(_pid_alive(p) for p in targets):
        time.sleep(_POLL_SECONDS)

    killed = []
    for pid, pid_file in targets.items():
        if _pid_alive(pid):
            killed.append(pid)
            try:
                os.killpg(pid, signal.SIGKILL)
            except OSError:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        _remove_pid_file(pid_file)
    return list(targets), killed


def stop_running_instance():
    """Chiude un'eventuale istanza --edge-mode ancora in esecuzione (vedi
    docstring del modulo). No-op silenzioso se non ce n'e' nessuna."""
    pid = _live_instance(constants.EDGE_MODE_PID_FILE)
    if pid is None:
        return
    syslog_log.info(f"mdtmain: chiudo l'istanza --edge-mode precedente (pid {pid}).")
    stop_instances([constants.EDGE_MODE_PID_FILE], _GRACE_SECONDS)


def write_pid_file(pid_file):
    """Registra il pid corrente; il file viene rimosso all'uscita (solo
    se contiene ancora questo pid)."""
    os.makedirs(os.path.dirname(pid_file), exist_ok=True)
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))
    my_pid = os.getpid()

    def _cleanup():
        if _read_pid(pid_file) == my_pid:
            _remove_pid_file(pid_file)
    atexit.register(_cleanup)
