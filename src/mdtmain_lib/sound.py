"""Riproduzione suoni per la modalita' --screen (vedi screenmode.py):
no-op silenzioso finche' enable() non e' stata chiamata, cosi' il resto
di mdtmain puo' chiamare beep()/siren()/mdt_found() incondizionatamente
senza controllare ogni volta se --screen e' attivo."""
import subprocess

from . import constants

_ENABLED = False


def enable():
    global _ENABLED
    _ENABLED = True


def _play(path):
    if not _ENABLED:
        return
    try:
        subprocess.Popen(["aplay", "-q", path],
                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)
    except OSError:
        pass  # aplay non installato/eseguibile: nessun suono, non bloccante


def beep():
    """Sostituisce il carattere BEL (--beep di mdtcap) in modalita'
    --screen, dove potrebbe non produrre alcun suono udibile."""
    _play(constants.BEEP_WAV)


def siren():
    """Allarme test continuato (MDT/RRC con posizione/livello extra "A"),
    al piu' una volta al giorno — la logica "una volta al giorno" e la
    finestra oraria/disableAlarm sono decise dal chiamante (vedi
    status.DayState in scheduler.py), non qui."""
    _play(constants.SIRENA_WAV)


def mdt_found():
    """Fine di un test locale/USB (non il continuato) con evidenza
    (hasMDT/hasRRCPos) nel manifest."""
    _play(constants.MDT_WAV)
