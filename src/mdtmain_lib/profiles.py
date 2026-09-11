"""Parsing dei due sistemi di 'profilo' distinti:

- mdt_configs/profile/*.conf: un argomento mdtcap per riga (per la
  selezione profilo comune a test locale/USB/continuo).
- main_configs/profile/*.conf: DSL di schedulazione del test continuo
  (comandi START/IN/EVERY/CHECKPOINT, uno per riga — vedi ScheduleLine
  e scheduler.run_continuous per come vengono eseguiti):

    START [argomenti mdtcap...]
    IN HH:MM HH:MM [argomenti mdtcap...]
    EVERY N [MAX M] PAUSE P IN HH:MM HH:MM [argomenti mdtcap...]
    CHECKPOINT HH:MM HH:MM

  Righe vuote o che iniziano con '#' sono ignorate; qualunque altra riga
  malformata solleva ScheduleSyntaxError (MAI ignorata silenziosamente:
  una riga malformata potrebbe altrimenti lasciare ore di giornata senza
  nessuna finestra attiva senza che nessuno se ne accorga).
"""
import glob
import os
import shlex
from collections import namedtuple
from datetime import datetime

from . import constants

# Struttura unica "a unione taggata" per le 4 righe della DSL (piu'
# semplice di 4 tipi separati, dato che condividono quasi tutti i
# campi): every_minutes/max_cycles/pause_minutes sono None per
# START/IN/CHECKPOINT, valorizzati (max_cycles puo' restare None: nessun
# tetto) solo per EVERY. start/end sono None solo per START.
ScheduleLine = namedtuple("ScheduleLine", [
    "kind",           # "START" | "IN" | "EVERY" | "CHECKPOINT"
    "start", "end",   # datetime.time, None per START
    "args",           # list[str], [] per CHECKPOINT
    "every_minutes",  # int, solo per EVERY
    "max_cycles",     # int o None, solo per EVERY (None = nessun tetto)
    "pause_minutes",  # int, solo per EVERY
])


class ScheduleSyntaxError(Exception):
    """path:lineno: messaggio. Sollevata da parse_schedule per QUALUNQUE
    riga che non sia vuota/di commento e non corrisponda alla DSL —
    strumento probatorio/di conformita': meglio fermarsi con un errore
    chiaro che proseguire silenziosamente con una schedulazione
    incompleta."""

    def __init__(self, path, lineno, message):
        super().__init__(f"{path}:{lineno}: {message}")


def _list_conf_names(directory):
    names = []
    for path in sorted(glob.glob(os.path.join(directory, "*.conf"))):
        names.append(os.path.splitext(os.path.basename(path))[0])
    return names


def list_mdtcap_profiles():
    return _list_conf_names(constants.MDTCAP_PROFILE_DIR)


def list_continuous_schedules():
    return _list_conf_names(constants.CONTINUOUS_SCHEDULE_DIR)


def parse_hhmm(value):
    return datetime.strptime(value, "%H:%M").time()


def _need_hhmm(tokens, i_start, i_end, path, lineno):
    try:
        return parse_hhmm(tokens[i_start]), parse_hhmm(tokens[i_end])
    except (IndexError, ValueError) as e:
        raise ScheduleSyntaxError(path, lineno, f"orario HH:MM non valido: {e}")


def _need_int(tokens, i, label, path, lineno):
    try:
        return int(tokens[i])
    except IndexError:
        raise ScheduleSyntaxError(path, lineno, f"atteso un numero dopo {label}")
    except ValueError:
        raise ScheduleSyntaxError(path, lineno, f"{label}: valore non numerico: {tokens[i]!r}")


def _parse_line(tokens, path, lineno):
    kw = tokens[0].upper()
    if kw == "START":
        return ScheduleLine("START", None, None, tokens[1:], None, None, None)
    if kw == "IN":
        start, end = _need_hhmm(tokens, 1, 2, path, lineno)
        return ScheduleLine("IN", start, end, tokens[3:], None, None, None)
    if kw == "CHECKPOINT":
        start, end = _need_hhmm(tokens, 1, 2, path, lineno)
        if len(tokens) > 3:
            raise ScheduleSyntaxError(path, lineno, "CHECKPOINT non accetta argomenti mdtcap")
        return ScheduleLine("CHECKPOINT", start, end, [], None, None, None)
    if kw == "EVERY":
        i = 1
        every_minutes = _need_int(tokens, i, "EVERY", path, lineno)
        i += 1
        max_cycles = None
        if i < len(tokens) and tokens[i].upper() == "MAX":
            max_cycles = _need_int(tokens, i + 1, "MAX", path, lineno)
            i += 2
        if i >= len(tokens) or tokens[i].upper() != "PAUSE":
            raise ScheduleSyntaxError(path, lineno, "atteso PAUSE dopo EVERY [MAX]")
        pause_minutes = _need_int(tokens, i + 1, "PAUSE", path, lineno)
        i += 2
        if i >= len(tokens) or tokens[i].upper() != "IN":
            raise ScheduleSyntaxError(path, lineno, "atteso IN dopo EVERY ... PAUSE")
        start, end = _need_hhmm(tokens, i + 1, i + 2, path, lineno)
        i += 3
        return ScheduleLine("EVERY", start, end, tokens[i:], every_minutes, max_cycles, pause_minutes)
    raise ScheduleSyntaxError(path, lineno, f"comando sconosciuto: {kw!r}")


def parse_schedule(path):
    """Un comando per riga (righe vuote/# ignorate). Ordine keyword di
    EVERY fissato ('EVERY N [MAX M] PAUSE P IN HH:MM HH:MM [args]'):
    coerente con tutti gli esempi noti, piu' semplice da parsare/
    documentare di un ordine libero, e da' errori precisi invece di
    dover indovinare l'intento. Piu' righe START sono ammesse: eseguono
    in sequenza all'avvio, nell'ordine del file (vedi
    scheduler.run_continuous)."""
    lines = []
    with open(path, "r") as f:
        for lineno, raw in enumerate(f, start=1):
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            tokens = shlex.split(s)
            if not tokens:
                continue
            lines.append(_parse_line(tokens, path, lineno))
    return lines


def in_window(line, at):
    return line.start is not None and line.start <= at < line.end


def active_index(lines, at, kinds=None):
    """Indice (non l'oggetto: serve al chiamante per tenere stato
    per-riga, es. cicli EVERY fatti oggi) della prima riga il cui
    [start,end) contiene 'at', filtrando per kind se specificato. None
    se nessuna."""
    for i, line in enumerate(lines):
        if kinds is not None and line.kind not in kinds:
            continue
        if in_window(line, at):
            return i
    return None


def next_window_start(lines, at, kinds=None):
    candidates = [l.start for l in lines if l.start is not None and (kinds is None or l.kind in kinds)]
    if not candidates:
        return None
    upcoming = [t for t in candidates if t > at]
    return min(upcoming) if upcoming else min(candidates)
