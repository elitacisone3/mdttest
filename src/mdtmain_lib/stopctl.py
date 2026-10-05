"""Arresto pulito di mdtmain su SIGTERM (--edge-mode e --screen, vedi
mdtmain --stop ed edgemode.py per i file pid).

L'handler SIGTERM non interrompe mai mdtmain in un punto qualunque (es.
a meta' di un invio di rete, di una cifratura o di una scrittura di
configurazione): imposta solo stop_requested e poi, a seconda di cosa
sta facendo il processo in quel momento:
  - cattura mdtcap in corso (set_active_capture, vedi
    runner.run_foreground_with_keypress_stop): chiede a mdtcap di
    fermarsi (mdtStop in --shm, stesso meccanismo di un tasto premuto) e
    lascia che il chiamante gestisca normalmente l'evidenza della
    cattura interrotta (stop_reason "signal");
  - fermo in attesa dell'utente (dialog, schermata di pausa: blocco
    interruptible(), vedi ui.py): solleva subito StopRequested;
  - altrimenti nulla: il flag viene raccolto al prossimo interruptible()
    o should_stop().
StopRequested risale fino a mdtmain, che esce in modo ordinato (atexit:
ripristino console/getty, rimozione del file pid)."""
import contextlib
import signal

from . import syslog_log


class StopRequested(BaseException):
    """BaseException (come KeyboardInterrupt), non Exception: non deve
    essere intercettata dai vari "except Exception" di app.py (es. gli
    errori imprevisti di run_edge_mode), ma arrivare fino a mdtmain."""


stop_requested = False
_active_capture_stop = None
_interruptible_depth = 0


def _on_sigterm(_signum, _frame):
    global stop_requested
    stop_requested = True
    syslog_log.info("mdtmain: ricevuto segnale di arresto.")
    if _active_capture_stop is not None:
        try:
            _active_capture_stop()
        except OSError:
            pass
        return
    if _interruptible_depth > 0:
        raise StopRequested()


def install_sigterm_handler():
    global stop_requested
    stop_requested = False
    signal.signal(signal.SIGTERM, _on_sigterm)


def should_stop():
    return stop_requested


def check():
    """Solleva StopRequested se l'arresto e' gia' stato chiesto."""
    if stop_requested:
        raise StopRequested()


def set_active_capture(stop_fn):
    global _active_capture_stop
    _active_capture_stop = stop_fn


def clear_active_capture():
    global _active_capture_stop
    _active_capture_stop = None


@contextlib.contextmanager
def interruptible():
    """Blocco in cui mdtmain e' solo in attesa dell'utente (nessuno stato
    a meta'): un SIGTERM qui dentro solleva subito StopRequested. Solleva
    StopRequested anche all'ingresso se l'arresto era gia' stato chiesto
    (es. il riepilogo mostrato subito dopo una cattura interrotta)."""
    global _interruptible_depth
    check()
    _interruptible_depth += 1
    try:
        yield
    finally:
        _interruptible_depth -= 1
