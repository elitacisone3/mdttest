"""Singola istanza della modalita' --edge-mode (vedi mdtmain --help) e
arresto pulito su SIGTERM.

Ogni avvio VERO di mdtmain (qualunque modalita', non solo --edge-mode:
vedi mdtmain --edge-mode) chiama stop_running_instance() prima di fare
qualunque altra cosa: se un'istanza --edge-mode precedente e' ancora in
esecuzione (file EDGE_MODE_PID_FILE con un pid vivo), viene terminata —
cosi' un uso interattivo (es. un tecnico collegato via SSH/schermo, o un
riavvio del servizio) non deve mai competere con il servizio automatico
per lo stesso modem/la stessa porta USB. Solo --edge-mode stesso scrive
il proprio pid (write_pid_file), DOPO il fork di screenmode.activate()
(altrimenti il pid registrato sarebbe quello del processo padre, che
esce subito): un'istanza avviata senza --edge-mode non scrive mai questo
file."""
import os
import signal
import time

from . import constants, runner, syslog_log

_GRACE_SECONDS = 5.0
_POLL_SECONDS = 0.1


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _remove_pid_file():
    try:
        os.remove(constants.EDGE_MODE_PID_FILE)
    except OSError:
        pass


def stop_running_instance():
    """No-op silenzioso se il file pid non esiste, e' illeggibile, o
    punta a un processo non piu' vivo (rimosso comunque in
    quest'ultimo caso: residuo di un'esecuzione precedente terminata
    senza pulizia, es. SIGKILL). Non termina mai il processo CORRENTE
    (confronto esplicito col proprio pid): rilevante solo se
    --edge-mode viene rilanciato dallo stesso pid, il che non accade in
    pratica, ma rende la funzione sicura da chiamare incondizionatamente."""
    try:
        with open(constants.EDGE_MODE_PID_FILE, "r") as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return
    if pid == os.getpid():
        return
    if not _pid_alive(pid):
        _remove_pid_file()
        return

    syslog_log.info(f"mdtmain: chiudo l'istanza --edge-mode precedente (pid {pid}).")
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        _remove_pid_file()
        return

    deadline = time.monotonic() + _GRACE_SECONDS
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            break
        time.sleep(_POLL_SECONDS)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    _remove_pid_file()


def write_pid_file():
    os.makedirs(os.path.dirname(constants.EDGE_MODE_PID_FILE), exist_ok=True)
    with open(constants.EDGE_MODE_PID_FILE, "w") as f:
        f.write(str(os.getpid()))


stop_requested = False


def _on_sigterm(_signum, _frame):
    global stop_requested
    stop_requested = True
    syslog_log.info("mdtmain: --edge-mode ricevuto segnale di arresto.")
    # Sveglia subito un'eventuale cattura mdtcap in corso (stesso
    # meccanismo di runner.signal_stop, usato da mdtcap stesso per
    # riconoscere una richiesta di interruzione — vedi mdtcap --help,
    # sezione "--shm DIR"): innocuo se non c'e' nessuna cattura in
    # corso in questo momento (directory --shm non ancora creata, es.
    # durante l'attesa della prossima finestra di schedulazione).
    try:
        runner.signal_stop(constants.CONTINUOUS_SHM)
    except OSError:
        pass


def install_sigterm_handler():
    global stop_requested
    stop_requested = False
    signal.signal(signal.SIGTERM, _on_sigterm)


def should_stop():
    return stop_requested
