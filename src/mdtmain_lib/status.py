"""Mapping dei file --shm/manifest.json ai 4 pallini di stato del test
continuo (Tracciamento/Campionamento/Test extra/Invio dati), con la
regola 'una volta rosso resta rosso fino a mezzanotte' per Tracciamento
ed Extra."""
from datetime import datetime

GREEN, ORANGE, RED, GRAY = "green", "orange", "red", "gray"

_DOT_CHAR = {GREEN: "\x1b[32m●\x1b[0m", ORANGE: "\x1b[33m●\x1b[0m",
             RED: "\x1b[31m●\x1b[0m", GRAY: "\x1b[90m●\x1b[0m"}


def _b(shm, field):
    return shm.get(field) == "1"


def _i(shm, field, default=0):
    try:
        return int(shm.get(field, default))
    except (TypeError, ValueError):
        return default


class DayState:
    """Fonte unica di verita' per tutto lo stato "quante volte/fino a
    quando oggi" dello scheduler (test continuo): i 2 lock rosso-fino-a-
    mezzanotte di sempre, PIU' (per la DSL IN/EVERY/CHECKPOINT, vedi
    scheduler.run_continuous) i cicli EVERY fatti oggi, la pausa EVERY
    corrente, le finestre "consumate" per oggi, e i CHECKPOINT gia'
    scattati oggi — mai un tracker separato con una propria logica di
    cambio giorno indipendente. now_fn (mockabile per --mock-time, vedi
    scheduler.py) e' l'unica fonte dell'orologio usata qui."""

    def __init__(self, day=None, now_fn=None):
        self._now_fn = now_fn or datetime.now
        self.day = day or self._now_fn().date()
        self.tracciamento_locked_red = False
        self.extra_locked_red = False
        self.last_invio = "pending"  # "ok" | "fail" | "warn" | "pending"
        self.alarm_played_today = False  # sirena.wav (modalita' --screen): al piu' una volta al giorno
        self.checkpoint_fired = {}        # {indice riga CHECKPOINT: True}
        self.every_cycles_done = {}       # {indice riga EVERY: int}
        self.every_pause_until = {}       # {indice riga EVERY: time}
        self.window_consumed_until = {}   # {indice riga IN/EVERY: time} - "fatta per oggi"

    @classmethod
    def new(cls, now_fn=None):
        return cls(now_fn=now_fn)

    def refresh_day(self):
        if self._now_fn().date() != self.day:
            self.__init__(now_fn=self._now_fn)  # now_fn sopravvive al reset


def dot_color_tracciamento(shm, manifest, day_state):
    if day_state.tracciamento_locked_red:
        return RED
    extra_level = (manifest or {}).get("extraLevel") or shm.get("extraLevel")
    red = _b(shm, "mdt") or _b(shm, "rrc") or extra_level == "A"
    if red:
        day_state.tracciamento_locked_red = True
        return RED
    if extra_level in ("W", "C"):
        return ORANGE
    return GREEN


def dot_color_campionamento(shm, manifest, proc_alive, elapsed_seconds):
    if manifest is not None and not manifest.get("OK", True):
        return RED
    if not proc_alive and manifest is None:
        return RED
    diag_warn = _i(shm, "diagWarn")
    warn_sum = diag_warn + _i(shm, "warnPosD") + _i(shm, "warnPosL") + _i(shm, "warnMDTD") + _i(shm, "warnMDTL")
    if not _b(shm, "lte") and elapsed_seconds is not None and elapsed_seconds > 60:
        return RED
    if warn_sum > 0:
        return ORANGE
    return GREEN


def dot_color_extra(shm, manifest, extra_active, day_state):
    if not extra_active:
        return GRAY
    if day_state.extra_locked_red:
        return RED
    level = (manifest or {}).get("extraLevel") or shm.get("extraLevel") or "I"
    if level == "A" or level == "C":
        day_state.extra_locked_red = True
        return RED
    if level == "W":
        return ORANGE
    return GREEN


def dot_color_invio(push_state):
    return {"ok": GREEN, "fail": RED, "warn": ORANGE, "pending": ORANGE}.get(push_state, ORANGE)


def record_push_result(day_state, ok, had_retry=False):
    day_state.last_invio = "ok" if ok else ("warn" if had_retry else "fail")


def update_day_state_from_manifest(day_state, manifest, extra_active):
    """Applica il lock 'rosso fino a mezzanotte' usando il manifest finale
    di un'esecuzione appena conclusa (piu' affidabile dei file --shm, che
    mdtcap ripulisce ad ogni run successivo)."""
    day_state.refresh_day()
    if manifest is None:
        return
    if manifest.get("hasMDT") or manifest.get("hasRRC"):
        day_state.tracciamento_locked_red = True
    if extra_active and manifest.get("extraLevel") == "A":
        day_state.tracciamento_locked_red = True
    if extra_active and manifest.get("extraLevel") in ("A", "C"):
        day_state.extra_locked_red = True


def render_dots(shm, manifest=None, extra_active=False, day_state=None,
                 proc_alive=True, elapsed_seconds=None):
    day_state = day_state or DayState.new()
    day_state.refresh_day()
    tracc = dot_color_tracciamento(shm, manifest, day_state)
    camp = dot_color_campionamento(shm, manifest, proc_alive, elapsed_seconds)
    extra = dot_color_extra(shm, manifest, extra_active, day_state)
    invio = dot_color_invio(day_state.last_invio)

    lines = ["Generale:"]
    lines.append(f"{_DOT_CHAR[tracc]} Tracciamento")
    lines.append(f"{_DOT_CHAR[camp]} Campionamento")
    if extra_active:
        level = (manifest or {}).get("extraLevel") or shm.get("extraLevel") or "I"
        lines.append(f"{_DOT_CHAR[extra]} Test extra (livello {level})")
    else:
        lines.append(f"{_DOT_CHAR[extra]} Test extra (non attivo)")
    lines.append(f"{_DOT_CHAR[invio]} Invio dati")
    return "\n".join(lines)
