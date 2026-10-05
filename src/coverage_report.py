#!/usr/bin/env python3
"""
Esito della sessione e report di copertura di mdtcap (sempre attivo,
chiamato da run_analysis_and_report() dopo compute_full_scan).

Distingue "la rete non ha chiesto nulla" da "il test non era in grado di
vederlo". Legge il .dlf (log code ricevuti, intervalli senza record), il
pcap (stati RRC, SIB1, UECapability), qcsuper.log (frame scartati, errori,
timeout di DIAG_LOG_CONFIG_F) e periodic_cell_gps_decoded.csv (RAT, celle,
mobilita'). Scrive coverage_report.txt nell'outdir e stampa su stdout una
sola riga JSON:

    {"esito": "rilevato"|"non_rilevato"|"non_verificabile",
     "esitoMotivi": [...], "sintesi": [...], "coverage": {...}}

Esito:
  rilevato          almeno un indicatore forte, passato da mdtcap con
                    --indicator (metriche MDT esistenti, MDTExt/LPP ad A
                    con --full-scan). Vale anche se la cattura era in parte
                    cieca: quello che si e' visto resta visto.
  non_verificabile  nessun indicatore e cattura "cieca": nessun record LTE
                    RRC OTA (0xB0C0) o NAS OTA, log non abilitati (timeout
                    di DIAG_LOG_CONFIG_F), self-test fallito, durata sotto
                    il minimo, nessuna connessione RRC osservata.
  non_rilevato      tutto il resto.

Limitazioni elencate senza cambiare l'esito: nessun ciclo idle completo,
frame DIAG scartati, mobilita' sconosciuta, UE che non dichiara il Logged
MDT (o che non ha inviato la UECapabilityInformation).

Uso (da mdtcap):
    coverage_report.py --out DIR [--dlf FILE] [--pcap FILE]
        [--qcsuper-log FILE] [--periodic-csv FILE] [--duration S]
        [--self-test ok|fail|off] [--gnss on|off|unknown]
        [--indicator TESTO ...] [--min-duration S] [--gap S]
"""
import argparse
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import mdt_mobility  # noqa: E402  (src/mdt_mobility.py)


def _load_extra_scan():
    """src/extra_scan e' un eseguibile senza estensione .py: lo si carica
    come modulo per riusarne gli helper tshark/DLF (run_tshark_fields,
    frame_count, iter_dlf_records, decode_dlf_timestamp,
    ue_capability_summary) invece di duplicarli."""
    path = os.path.join(SCRIPT_DIR, "extra_scan")
    loader = importlib.machinery.SourceFileLoader("extra_scan", path)
    spec = importlib.util.spec_from_loader("extra_scan", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


xs = _load_extra_scan()

ESITI = ("rilevato", "non_rilevato", "non_verificabile")

# Log code di protocollo rilevanti per le analisi di mdtcap (sottoinsieme
# della maschera ridotta di src/qcsuper_run.py).
LOG_CODES = {
    0xB0C0: "LTE RRC OTA",
    0xB0EC: "NAS EMM OTA (rete -> UE)",
    0xB0ED: "NAS EMM OTA (UE -> rete)",
    0xB0E2: "NAS ESM OTA (rete -> UE)",
    0xB0E3: "NAS ESM OTA (UE -> rete)",
}
NAS_CODES = (0xB0EC, 0xB0ED, 0xB0E2, 0xB0E3)

# Stesso intervallo di validita' di qcsuper/inputs/dlf_read.py: fuori da
# qui il timestamp del record non e' affidabile e viene ignorato.
TS_MIN = datetime(2010, 1, 1, tzinfo=timezone.utc).timestamp()
TS_MAX = datetime(2050, 1, 1, tzinfo=timezone.utc).timestamp()

MIN_DURATION_S = 120
GAP_S = 60
MAX_GAPS_LISTED = 10

LOG_CONFIG_TIMEOUT_RE = re.compile(r"DIAG_LOG_CONFIG_F.*timed out")
WRONG_CRC_RE = re.compile(r"Wrong CRC")
ERROR_RE = re.compile(r"\| ERROR @ ")

RRC_EVENTS_FILTER = ("lte-rrc.rrcConnectionSetup_element or lte-rrc.rrcConnectionRelease_element"
                     " or lte-rrc.rrcConnectionReestablishment_element")
DCCH_FILTER = "lte-rrc.UL_DCCH_Message_element or lte-rrc.DL_DCCH_Message_element"
SIB1_FILTER = "lte-rrc.systemInformationBlockType1_element"
# l'UE ha misure Logged MDT registrate in idle da consegnare
LOG_MEAS_AVAILABLE_FILTER = "lte-rrc.logMeasAvailable_r10 or lte-rrc.logMeasAvailable_r13"


def iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_int(s, default=0):
    try:
        return int(s)
    except (TypeError, ValueError):
        return default


def to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------
# .dlf: log code ricevuti e intervalli senza record
# ---------------------------------------------------------------------

def scan_dlf(dlf_path, gap_s):
    """None se il .dlf manca (es. --analyze-pcap)."""
    if not dlf_path or not os.path.isfile(dlf_path):
        return None
    with open(dlf_path, "rb") as f:
        data = f.read()
    counts = Counter()
    times = []
    for log_type, log_time, _payload in xs.iter_dlf_records(data):
        counts[log_type] += 1
        ts = xs.decode_dlf_timestamp(log_time)
        if TS_MIN <= ts <= TS_MAX:
            times.append(ts)
    times.sort()
    gaps = []
    for a, b in zip(times, times[1:]):
        if b - a > gap_s:
            gaps.append({"from": iso(a), "to": iso(b), "s": round(b - a)})
    return {
        "records": sum(counts.values()),
        "logCodes": {f"0x{code:04X}": counts.get(code, 0) for code in LOG_CODES},
        "otherRecords": sum(n for code, n in counts.items() if code not in LOG_CODES),
        "first": iso(times[0]) if times else "",
        "last": iso(times[-1]) if times else "",
        "spanS": round(times[-1] - times[0]) if times else 0,
        "gapThresholdS": gap_s,
        "gaps": sorted(gaps, key=lambda g: -g["s"])[:MAX_GAPS_LISTED],
        "gapsCount": len(gaps),
    }


# ---------------------------------------------------------------------
# qcsuper.log: frame scartati, errori, timeout di DIAG_LOG_CONFIG_F
# ---------------------------------------------------------------------

def scan_qcsuper_log(path):
    """None se qcsuper.log manca (modalita' replay)."""
    if not path or not os.path.isfile(path):
        return None
    dropped = errors = timeouts = 0
    with open(path, "r", errors="replace") as f:
        for line in f:
            if WRONG_CRC_RE.search(line):
                dropped += 1
            if ERROR_RE.search(line):
                errors += 1
                if LOG_CONFIG_TIMEOUT_RE.search(line):
                    timeouts += 1
    return {"droppedFrames": dropped, "errors": errors, "logConfigTimeouts": timeouts}


# ---------------------------------------------------------------------
# pcap: stati RRC, SIB1
# ---------------------------------------------------------------------

def rrc_states(pcap):
    """Ricostruisce le transizioni connected/idle da RRCConnectionSetup e
    RRCConnectionRelease, in ordine di frame. Un ciclo completo e' un
    Setup preceduto da un Release (connected -> idle -> connected). Le
    durate idle si calcolano solo fra frame con timestamp valido: qcsuper
    scrive epoch 0 per i primi frame di una sessione live (vedi
    capture_time_bounds() in src/extra_scan)."""
    rows = xs.run_tshark_fields(pcap, RRC_EVENTS_FILTER, [
        "frame.number", "frame.time_epoch", "lte-rrc.rrcConnectionSetup_element",
        "lte-rrc.rrcConnectionReestablishment_element", "lte-rrc.rrcConnectionRelease_element"])
    rows.sort(key=lambda r: to_int(r["frame.number"]))
    setups = reestablishments = releases = cycles = 0
    idle_phases = []
    last_release_ts = None
    seen_release = False
    for r in rows:
        ts = to_float(r["frame.time_epoch"])
        if r["lte-rrc.rrcConnectionSetup_element"]:
            setups += 1
            if seen_release:
                cycles += 1
                if last_release_ts and ts > 0:
                    idle_phases.append(round(ts - last_release_ts))
            seen_release = False
        elif r["lte-rrc.rrcConnectionReestablishment_element"]:
            reestablishments += 1
        elif r["lte-rrc.rrcConnectionRelease_element"]:
            releases += 1
            seen_release = True
            last_release_ts = ts if ts > 0 else None
    return {
        "setups": setups,
        "reestablishments": reestablishments,
        "releases": releases,
        "idleCycles": cycles,
        "idlePhasesS": idle_phases,
        "dcchFrames": xs.frame_count(pcap, DCCH_FILTER),
        "logMeasAvailable": xs.frame_count(pcap, LOG_MEAS_AVAILABLE_FILTER),
    }


def sib1_cells(pcap):
    """Celle annunciate dalle SIB1: cellIdentity (28 bit), TAC, PLMN."""
    cmd_fields = ["lte-rrc.cellIdentity", "lte-rrc.trackingAreaCode", "lte-rrc.MCC_MNC_Digit"]
    try:
        out = subprocess.run(["tshark", "-r", pcap, "-Y", SIB1_FILTER, "-T", "fields",
                              "-E", "separator=\t", "-E", "occurrence=a", "-E", "aggregator=,"]
                             + [x for f in cmd_fields for x in ("-e", f)],
                             capture_output=True, text=True, timeout=120)
        rows = [line.split("\t") for line in out.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []
    cells = {}
    for parts in rows:
        parts += [""] * (3 - len(parts))
        cell_hex = parts[0].split(",")[0].replace(":", "")
        tac_hex = parts[1].split(",")[0].replace(":", "")
        digits = [d for d in parts[2].split(",") if d]
        try:
            cell_id = int(cell_hex, 16) >> 4 if cell_hex else None
        except ValueError:
            cell_id = None
        # un solo PLMN nella SIB1: 3 cifre di MCC + 2 o 3 di MNC
        plmn = ""
        if len(digits) in (5, 6):
            plmn = "".join(digits[:3]) + "-" + "".join(digits[3:])
        elif digits:
            plmn = "multiplo"
        key = (plmn, tac_hex.upper(), cell_id)
        cells[key] = cells.get(key, 0) + 1
    return [{"plmn": k[0], "tac": k[1], "cellIdentity": k[2], "sib1": n}
            for k, n in sorted(cells.items(), key=lambda kv: -kv[1])]


# ---------------------------------------------------------------------
# periodic_cell_gps_decoded.csv: RAT e celle servanti
# ---------------------------------------------------------------------

def periodic_cells(csv_path):
    rows = mdt_mobility.read_samples(csv_path)
    rat = Counter(r.get("net_mode", "") or "?" for r in rows)
    cells = {}
    for r in rows:
        if not r.get("cell_id"):
            continue
        key = (r.get("mcc", ""), r.get("mnc", ""), r.get("tac_hex", ""), r.get("cell_id", ""),
               r.get("pci", ""), r.get("band", ""), r.get("earfcn", ""))
        cells[key] = cells.get(key, 0) + 1
    return {
        "samples": len(rows),
        "rat": dict(rat),
        "cells": [{"mcc": k[0], "mnc": k[1], "tac": k[2], "cellId": k[3], "pci": k[4],
                   "band": k[5], "earfcn": k[6], "samples": n}
                  for k, n in sorted(cells.items(), key=lambda kv: -kv[1])],
    }


# ---------------------------------------------------------------------
# esito
# ---------------------------------------------------------------------

def decide(args, cov):
    blind = []
    dlf, qlog, rrc = cov["diag"], cov["qcsuper"], cov["rrc"]

    if dlf is not None:
        if dlf["logCodes"]["0xB0C0"] == 0:
            blind.append("nessun record LTE RRC OTA (0xB0C0) nel .dlf")
        if sum(dlf["logCodes"][f"0x{c:04X}"] for c in NAS_CODES) == 0:
            blind.append("nessun messaggio NAS OTA (0xB0EC/ED/E2/E3) nel .dlf")
    else:
        # --analyze-pcap: nessun .dlf, si contano i frame decodificati
        if cov["pcapFrames"]["lteRrc"] == 0:
            blind.append("nessun messaggio LTE RRC nel pcap")
        if cov["pcapFrames"]["nas"] == 0:
            blind.append("nessun messaggio NAS nel pcap")
    if qlog is not None and qlog["logConfigTimeouts"] > 0:
        blind.append(f"abilitazione dei log non riuscita: {qlog['logConfigTimeouts']} timeout di "
                     "DIAG_LOG_CONFIG_F in qcsuper.log")
    if args.self_test == "fail":
        blind.append("self-test dei log fallito")
    if cov["durationS"] < args.min_duration:
        blind.append(f"durata {cov['durationS']}s sotto il minimo di {args.min_duration}s")
    if rrc["setups"] == 0 and rrc["dcchFrames"] == 0:
        blind.append("nessuna connessione RRC osservata (nessun RRCConnectionSetup "
                     "ne' messaggio DCCH)")

    limits = []
    if rrc["idleCycles"] == 0:
        limits.append("nessun ciclo idle completo (connected -> idle -> connected): il Logged MDT "
                      "si misura in idle e viene recuperato alla riconnessione")
    if qlog is not None and qlog["droppedFrames"] > 0:
        limits.append(f"{qlog['droppedFrames']} frame DIAG scartati per CRC errato")
    if cov["mobility"]["esito"] == "sconosciuta":
        limits.append(f"mobilita' sconosciuta ({cov['mobility']['dettaglio']})")
    cap = cov["capability"]
    if cap is None:
        limits.append("l'UE non ha inviato la UECapabilityInformation: non si sa se supporta il Logged MDT")
    elif not cap["loggedMeasurementsIdle"]:
        limits.append("l'UE non dichiara il Logged MDT (loggedMeasurementsIdle assente)")

    if args.indicator:
        esito, motivi = "rilevato", list(args.indicator)
        limits = blind + limits
    elif blind:
        esito, motivi = "non_verificabile", blind
    else:
        esito, motivi = "non_rilevato", ["nessun indicatore forte in una cattura in grado di vederlo"]
    return esito, motivi, limits


def collect(args):
    dlf = scan_dlf(args.dlf, args.gap)
    qlog = scan_qcsuper_log(args.qcsuper_log)
    pcap_ok = bool(args.pcap) and os.path.isfile(args.pcap)
    rrc = rrc_states(args.pcap) if pcap_ok else {
        "setups": 0, "reestablishments": 0, "releases": 0, "idleCycles": 0, "idlePhasesS": [],
        "dcchFrames": 0, "logMeasAvailable": 0}
    mob, mob_detail, _info = mdt_mobility.classify(args.periodic_csv)
    cap = xs.ue_capability_summary(args.pcap) if pcap_ok else None

    # Durata: quella effettiva della cattura live se passata da mdtcap,
    # altrimenti l'arco coperto dai record del .dlf o dai frame del pcap.
    duration, duration_src = args.duration, "cattura"
    if duration <= 0 and dlf is not None and dlf["spanS"] > 0:
        duration, duration_src = dlf["spanS"], "arco dei record del .dlf"
    if duration <= 0 and pcap_ok:
        lo, hi = xs.capture_time_bounds(args.pcap)
        if lo is not None:
            duration, duration_src = round(hi - lo), "arco dei frame del pcap"

    return {
        "durationS": max(0, int(duration)),
        "durationSource": duration_src,
        "minDurationS": args.min_duration,
        "diag": dlf,
        "qcsuper": qlog,
        "pcapFrames": {
            "lteRrc": xs.frame_count(args.pcap, "lte_rrc") if pcap_ok else 0,
            "nas": xs.frame_count(args.pcap, "nas-eps") if pcap_ok else 0,
        },
        "rrc": rrc,
        "periodic": periodic_cells(args.periodic_csv),
        "sib1Cells": sib1_cells(args.pcap) if pcap_ok else [],
        "capability": None if cap is None else {
            "loggedMeasurementsIdle": cap["flags"]["loggedMeasurementsIdle"],
            "standaloneGNSS": cap["flags"]["standaloneGNSS"],
            "ueBasedNetwPerfMeas": cap["flags"]["ueBasedNetwPerfMeas"],
            "releases": cap["releases"],
            "fingerprint": cap["fingerprint"],
        },
        "gnss": args.gnss or "unknown",
        "mobility": {"esito": mob, "dettaglio": mob_detail},
        "selfTest": args.self_test,
    }


# ---------------------------------------------------------------------
# output
# ---------------------------------------------------------------------

def yn(v):
    return "si'" if v else "no"


def summary_lines(cov):
    """Righe brevi per la sezione "Copertura" di report_finale.txt."""
    out = [f"Durata: {cov['durationS']}s ({cov['durationSource']}, minimo {cov['minDurationS']}s)"]
    dlf = cov["diag"]
    if dlf is not None:
        codes = ", ".join(f"{k}={v}" for k, v in dlf["logCodes"].items())
        out.append(f"Log code ricevuti: {codes} (altri: {dlf['otherRecords']})")
        out.append(f"Intervalli senza record DIAG > {dlf['gapThresholdS']}s: {dlf['gapsCount']}")
    else:
        pf = cov["pcapFrames"]
        out.append(f"Log code: N/D (nessun .dlf); frame nel pcap: LTE RRC={pf['lteRrc']}, NAS={pf['nas']}")
    q = cov["qcsuper"]
    if q is not None:
        out.append(f"qcsuper.log: {q['droppedFrames']} frame scartati (CRC), {q['errors']} errori, "
                   f"{q['logConfigTimeouts']} timeout DIAG_LOG_CONFIG_F")
    r = cov["rrc"]
    idle = f", fasi idle {', '.join(str(s) + 's' for s in r['idlePhasesS'])}" if r["idlePhasesS"] else ""
    out.append(f"RRC: {r['setups']} connessioni, {r['releases']} rilasci, {r['idleCycles']} cicli "
               f"connected -> idle -> connected{idle}, logMeasAvailable {r['logMeasAvailable']}")
    p = cov["periodic"]
    if p["samples"]:
        rat = ", ".join(f"{k}={v}" for k, v in p["rat"].items())
        out.append(f"RAT (campioni periodici): {rat}; celle servanti: {len(p['cells'])}")
    if cov["sib1Cells"]:
        cells = "; ".join(f"PLMN {c['plmn'] or '?'} TAC {c['tac'] or '?'} cella {c['cellIdentity']}"
                          for c in cov["sib1Cells"][:3])
        out.append(f"Celle da SIB1: {cells}")
    cap = cov["capability"]
    if cap is None:
        out.append("UECapability: non inviata durante la cattura")
    else:
        out.append(f"UECapability: Logged MDT {yn(cap['loggedMeasurementsIdle'])}, "
                   f"GNSS autonomo {yn(cap['standaloneGNSS'])}")
    out.append(f"GNSS: {cov['gnss']}; mobilita': {cov['mobility']['esito']}; self-test: {cov['selfTest']}")
    return out


def write_text_report(path, esito, motivi, limits, cov):
    lines = [
        "Report di copertura mdtcap",
        "==========================",
        "",
        f"Esito: {esito}",
    ]
    lines += [f"  - {m}" for m in motivi]
    if limits:
        lines += ["", "Limitazioni (non cambiano l'esito):"]
        lines += [f"  - {m}" for m in limits]
    lines += ["", "Sintesi:"]
    lines += [f"  {s}" for s in summary_lines(cov)]

    dlf = cov["diag"]
    if dlf is not None:
        lines += ["", "Log code ricevuti (.dlf):"]
        for code, name in LOG_CODES.items():
            lines.append(f"  0x{code:04X} {name:<28} {dlf['logCodes'][f'0x{code:04X}']}")
        lines.append(f"  altri log code                    {dlf['otherRecords']}")
        lines.append(f"  totale record: {dlf['records']}, dal {dlf['first'] or '?'} al {dlf['last'] or '?'}")
        lines += ["", f"Intervalli senza record DIAG piu' lunghi di {dlf['gapThresholdS']}s: {dlf['gapsCount']}"]
        for g in dlf["gaps"]:
            lines.append(f"  {g['from']} -> {g['to']} ({g['s']}s)")
        if dlf["gapsCount"]:
            lines.append("  (con la maschera DIAG ridotta, in idle senza traffico intervalli lunghi possono")
            lines.append("  essere normali: e' un'informazione da confrontare con gli stati RRC, non un errore)")

    r = cov["rrc"]
    lines += ["", "Stati RRC (dal pcap):",
              f"  RRCConnectionSetup: {r['setups']}",
              f"  RRCConnectionReestablishment: {r['reestablishments']}",
              f"  RRCConnectionRelease: {r['releases']}",
              f"  messaggi DCCH (connected): {r['dcchFrames']}",
              f"  cicli completi connected -> idle -> connected: {r['idleCycles']}",
              f"  logMeasAvailable (l'UE ha misure Logged MDT da consegnare): {r['logMeasAvailable']}"]
    if r["idlePhasesS"]:
        lines.append(f"  durata delle fasi idle: {', '.join(str(s) + 's' for s in r['idlePhasesS'])}")

    p = cov["periodic"]
    lines += ["", f"RAT e celle servanti (periodic_cell_gps_decoded.csv, {p['samples']} campioni):"]
    for k, v in p["rat"].items():
        lines.append(f"  RAT {k}: {v} campioni")
    for c in p["cells"]:
        lines.append(f"  MCC {c['mcc']} MNC {c['mnc']} TAC {c['tac']} cella {c['cellId']} PCI {c['pci']} "
                     f"banda {c['band']} EARFCN {c['earfcn']}: {c['samples']} campioni")
    lines += ["", "Celle annunciate dalle SIB1:"]
    if not cov["sib1Cells"]:
        lines.append("  nessuna SIB1 decodificata")
    for c in cov["sib1Cells"]:
        lines.append(f"  PLMN {c['plmn'] or '?'} TAC {c['tac'] or '?'} cellIdentity {c['cellIdentity']}: "
                     f"{c['sib1']} SIB1")

    cap = cov["capability"]
    lines += ["", "Capability dichiarate dall'UE:"]
    if cap is None:
        lines.append("  nessuna UECapabilityInformation nella cattura")
    else:
        lines.append(f"  loggedMeasurementsIdle (Logged MDT): {yn(cap['loggedMeasurementsIdle'])}")
        lines.append(f"  standaloneGNSS-Location: {yn(cap['standaloneGNSS'])}")
        lines.append(f"  ue-BasedNetwPerfMeasParameters: {yn(cap['ueBasedNetwPerfMeas'])}")
        lines.append(f"  accessStratumRelease: {', '.join(cap['releases']) or '?'}")

    lines += ["", "Contesto:",
              f"  GNSS: {cov['gnss']}",
              f"  mobilita': {cov['mobility']['esito']} ({cov['mobility']['dettaglio']})",
              f"  self-test: {cov['selfTest']}",
              "",
              "Un esito non_rilevato significa che la cattura era in grado di vedere le richieste",
              "della rete e non ne ha viste: resta un dato di questa sessione, non una garanzia."]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def parse_args(argv):
    ap = argparse.ArgumentParser(description="Esito della sessione e report di copertura di mdtcap")
    ap.add_argument("--out", required=True, help="outdir della sessione (vi scrive coverage_report.txt)")
    ap.add_argument("--dlf", default="")
    ap.add_argument("--pcap", default="")
    ap.add_argument("--qcsuper-log", default="")
    ap.add_argument("--periodic-csv", default="")
    ap.add_argument("--duration", type=int, default=0, help="durata effettiva della cattura live, secondi")
    ap.add_argument("--self-test", choices=("ok", "fail", "off"), default="off")
    ap.add_argument("--gnss", default="")
    ap.add_argument("--indicator", action="append", default=[],
                    help="indicatore forte trovato da mdtcap (ripetibile): l'esito diventa 'rilevato'")
    ap.add_argument("--min-duration", type=int, default=MIN_DURATION_S)
    ap.add_argument("--gap", type=int, default=GAP_S, help="soglia degli intervalli senza record DIAG, secondi")
    return ap.parse_args(argv)


def main():
    args = parse_args(sys.argv[1:])
    try:
        cov = collect(args)
        esito, motivi, limits = decide(args, cov)
        cov["limitazioni"] = limits
        write_text_report(os.path.join(args.out, "coverage_report.txt"), esito, motivi, limits, cov)
        result = {"esito": esito, "esitoMotivi": motivi, "sintesi": summary_lines(cov), "coverage": cov}
    except Exception as exc:  # fail-soft: mdtcap riceve comunque un esito
        print(f"coverage_report: errore interno non gestito: {exc}", file=sys.stderr)
        if args.indicator:
            esito, motivi = "rilevato", list(args.indicator)
        else:
            esito, motivi = "non_verificabile", [f"report di copertura non calcolabile: {exc}"]
        result = {"esito": esito, "esitoMotivi": motivi, "sintesi": [], "coverage": {}}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
