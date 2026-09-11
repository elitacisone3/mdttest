"""Log su syslog per la modalita' --edge-mode: no-op silenzioso finche'
enable() non e' stata chiamata (stesso stile di sound.py), cosi' il
resto di mdtmain puo' chiamare info()/warning()/error() incondizionatamente
per segnalare eventi significativi (avvio/fine test, allarme, evidenza
inviata, errore/blocco) senza dover controllare ogni volta se e' in corso
--edge-mode — nell'uso interattivo normale (dialog) questi eventi restano
visibili a schermo come sempre, e queste chiamate non fanno nulla.

Usa il modulo "syslog" della libreria standard (voce di logging di
sistema, letta da journalctl su qualunque distribuzione con systemd,
senza scrivere nulla su stdout/stderr — nessun output nel senso richiesto
da un servizio systemd silenzioso)."""
import syslog

_enabled = False


def enable():
    global _enabled
    if _enabled:
        return
    syslog.openlog(ident="mdtmain", logoption=syslog.LOG_PID, facility=syslog.LOG_DAEMON)
    _enabled = True


def info(message):
    if _enabled:
        syslog.syslog(syslog.LOG_INFO, message)


def warning(message):
    if _enabled:
        syslog.syslog(syslog.LOG_WARNING, message)


def error(message):
    if _enabled:
        syslog.syslog(syslog.LOG_ERR, message)
