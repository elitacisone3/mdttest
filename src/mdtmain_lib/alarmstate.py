"""Stato persistente dell'ultimo test/allarme del test continuato:
log/lastAlarm (testo semplice, per la riga in basso della schermata
principale) e log/lastAlarm.conf (key=value, per consumo automatico).
Sopravvive a un riavvio dello scheduler/di --edge-mode, a differenza di
status.DayState (in memoria, per singola esecuzione). Il flag di
allarme pendente (ALARM_DL) e' condiviso da DUE meccanismi indipendenti
che possono far suonare la sirena: l'allarme immediato
(scheduler._maybe_play_alarm, subito dopo un test, nella finestra
minAlarmHour/maxAlarmHour) e il comando CHECKPOINT dello scheduler
(vedi profiles.py/scheduler.py) — qualunque dei due suona per primo
consuma il flag per l'altro.

Ogni funzione riceve "now_fn" esplicitamente (mai una variabile globale
mutabile): chi chiama in produzione passa datetime.now, chi collauda lo
scheduler con --mock-time passa un now_fn mockato (vedi
scheduler.run_continuous/app.run_continuous_headless).

log/lastAlarm.conf, i campi MDT=/RRC= riflettono SOLO il caso "con
posizione/GPS" (equivalgono a MDT_GPS/RRC_GPS nel testo di
log/lastAlarm, non alle keyword semplici MDT/RRC) — scelta esplicita.
Per non perdere l'informazione necessaria a ricostruire log/lastAlarm
(che invece distingue le 4 keyword MDT/MDT_GPS/RRC/RRC_GPS), il .conf
include anche MDT_PLAIN=/RRC_PLAIN= (evidenza vista SENZA posizione)."""
import os
from datetime import datetime

from . import constants

FLAG_LIFETIME_SECONDS = 24 * 3600

_KEYS = ["MDT", "RRC", "MDT_PLAIN", "RRC_PLAIN", "EXTRA", "LAST", "ALARM",
         "E_NUM", "E_POS", "E_ERR", "ALARM_DL"]
_DEFAULTS = {k: "0" for k in _KEYS}
_DEFAULTS["EXTRA"] = ""
_EXTRA_ORDER = {"": -1, "I": 0, "W": 1, "C": 2, "A": 3}


def evidence_qualifies(manifest):
    """Stessa soglia di sempre (vedi scheduler._maybe_play_alarm): hasMDT
    o hasRRCPos o extraLevel=='A'. Funzione a parte, riusabile, invece
    di ripeterla inline in piu' punti."""
    if not manifest:
        return False
    return bool(manifest.get("hasMDT") or manifest.get("hasRRCPos") or manifest.get("extraLevel") == "A")


def _load():
    values = {}
    try:
        with open(constants.LAST_ALARM_CONF_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                values[k.strip()] = v.strip()
    except OSError:
        pass
    for k in _KEYS:
        values.setdefault(k, _DEFAULTS[k])
    return values


def _int(values, key, default=0):
    try:
        return int(values[key])
    except (KeyError, ValueError):
        return default


def _expired(values, now_fn):
    dl = _int(values, "ALARM_DL")
    return dl > 0 and now_fn().timestamp() >= dl


def _fmt_ts(unix_ts):
    if not unix_ts:
        return "----/--/-- --:--"
    return datetime.fromtimestamp(int(unix_ts)).strftime("%d/%m/%Y %H:%M")


def _write_text_file(values):
    flags = []
    if _int(values, "MDT"):
        flags.append("MDT_GPS")
    elif _int(values, "MDT_PLAIN"):
        flags.append("MDT")
    if _int(values, "RRC"):
        flags.append("RRC_GPS")
    elif _int(values, "RRC_PLAIN"):
        flags.append("RRC")
    line = f"{_fmt_ts(_int(values, 'LAST'))} {_fmt_ts(_int(values, 'ALARM'))}"
    if flags:
        line += " " + " ".join(flags)
    extra = values.get("EXTRA", "")
    if extra:
        line += f" Extra: {extra}"
    os.makedirs(os.path.dirname(constants.LAST_ALARM_TEXT_FILE), exist_ok=True)
    with open(constants.LAST_ALARM_TEXT_FILE, "w") as f:
        f.write(line + "\n")


def _save(values):
    os.makedirs(os.path.dirname(constants.LAST_ALARM_CONF_FILE), exist_ok=True)
    with open(constants.LAST_ALARM_CONF_FILE, "w") as f:
        f.write("\n".join(f"{k}={values[k]}" for k in _KEYS) + "\n")
    _write_text_file(values)


def record_test_result(manifest, now_fn):
    """Da chiamare dopo OGNI cattura completata (IN/EVERY/START), col
    manifest risultante (None se la cattura non ha prodotto un
    manifest.json: aggiorna solo LAST). Imposta il flag (ALARM_DL) la
    prima volta che un test e' "alarm-worthy" (evidence_qualifies
    sopra); mentre il flag e' pendente, accumula le keyword
    MDT/MDT_PLAIN/RRC/RRC_PLAIN e il livello extra piu' alto visti — se
    il flag era scaduto (24h passate senza sirena), riparte da zero
    invece di continuare ad accumulare sul vecchio ciclo."""
    values = _load()
    if _expired(values, now_fn):
        values.update(ALARM_DL="0", MDT="0", RRC="0", MDT_PLAIN="0", RRC_PLAIN="0", EXTRA="")
    now_ts = int(now_fn().timestamp())
    values["LAST"] = str(now_ts)
    if manifest is None:
        _save(values)
        return

    has_mdt = bool(manifest.get("hasMDT"))
    mdt_gps = has_mdt and bool(manifest.get("reqMDTPos") or manifest.get("reqMDTGPS"))
    has_rrc = bool(manifest.get("hasRRC"))
    rrc_gps = has_rrc and bool(manifest.get("hasRRCPos"))
    extra_level = manifest.get("extraLevel") if manifest.get("extended") else ""

    pending = _int(values, "ALARM_DL") > 0
    if evidence_qualifies(manifest) and not pending:
        values["ALARM_DL"] = str(now_ts + FLAG_LIFETIME_SECONDS)
        pending = True

    if pending:
        if mdt_gps:
            values["MDT"] = "1"
        elif has_mdt:
            values["MDT_PLAIN"] = "1"
        if rrc_gps:
            values["RRC"] = "1"
        elif has_rrc:
            values["RRC_PLAIN"] = "1"
        if _EXTRA_ORDER.get(extra_level, -1) > _EXTRA_ORDER.get(values.get("EXTRA", ""), -1):
            values["EXTRA"] = extra_level

    _save(values)


def is_alarm_pending(now_fn):
    """Query pura: NON riscrive il file se il flag risulta scaduto (una
    funzione con nome/aspetto da getter non deve avere effetti
    collaterali a sorpresa) — il prossimo record_test_result() lo
    ripulisce comunque da solo quando arriva nuova evidenza."""
    values = _load()
    if _expired(values, now_fn):
        return False
    return _int(values, "ALARM_DL") > 0


def mark_alarm_played(now_fn):
    """Chiamata da ENTRAMBI i meccanismi (_maybe_play_alarm e la
    valutazione di CHECKPOINT) quando fanno suonare davvero la
    sirena."""
    values = _load()
    values["ALARM"] = str(int(now_fn().timestamp()))
    values["ALARM_DL"] = "0"
    for k in ("MDT", "RRC", "MDT_PLAIN", "RRC_PLAIN"):
        values[k] = "0"
    values["EXTRA"] = ""
    _save(values)


def read_last_alarm_text():
    """Contenuto di log/lastAlarm (una riga, senza newline finale), o ""
    se il file manca/e' vuoto — usato da ui.current_net_status_text per
    comporlo nella scritta in alto a destra (mai durante un test in
    corso: vedi ui.draw_test_header, sarebbe fuorviante mostrare
    l'ultimo allarme mentre un test nuovo e' gia' iniziato)."""
    try:
        with open(constants.LAST_ALARM_TEXT_FILE, "r") as f:
            return f.read().strip()
    except OSError:
        return ""


def record_evidence_sent(ok, positive):
    """Da chiamare da scheduler.upload_one dopo ogni tentativo di invio:
    E_NUM/E_POS sui successi (E_POS solo se "positive", cioe' evidenza
    COMPLETA non solo manifest.json), E_ERR sui fallimenti. Nessun
    now_fn: non scrive nessun timestamp, solo contatori."""
    values = _load()
    if ok:
        values["E_NUM"] = str(_int(values, "E_NUM") + 1)
        if positive:
            values["E_POS"] = str(_int(values, "E_POS") + 1)
    else:
        values["E_ERR"] = str(_int(values, "E_ERR") + 1)
    _save(values)
