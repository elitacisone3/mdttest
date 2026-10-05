"""Classificazione della mobilita' del dispositivo durante una cattura, a
partire da periodic_cell_gps_decoded.csv (scritto da mdtcap nella cartella
di evidenza). Condiviso da src/extra_scan (gruppo --full-scan, euristica
MeasCfg) e src/coverage_report.py.

Esiti: "ferma", "in_movimento", "sconosciuta". Con GPS si usa lo
spostamento massimo dal primo fix; senza GPS ci si limita alla cella
servente (una sola cella per tutta la cattura -> "ferma", ma con una
nota: e' un'indicazione piu' debole)."""
import csv
import math
import os

# Sotto STATIONARY_M di spostamento massimo il dispositivo e' considerato
# fermo; sopra MOVING_M in movimento; in mezzo resta "sconosciuta" (rumore
# del fix GPS, piccoli spostamenti a piedi).
STATIONARY_M = 100.0
MOVING_M = 500.0


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def read_samples(csv_path):
    """Righe di periodic_cell_gps_decoded.csv come dict (lista vuota se il
    file manca, es. in modalita' replay)."""
    if not csv_path or not os.path.isfile(csv_path):
        return []
    try:
        with open(csv_path, newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def classify(csv_path):
    """Ritorna (esito, dettaglio, info) con info = dict con
    gps_fixes, max_displacement_m, cells (set di (cell_id, pci))."""
    rows = read_samples(csv_path)
    fixes = []
    cells = set()
    for r in rows:
        if r.get("cell_id"):
            cells.add((r.get("cell_id", ""), r.get("pci", "")))
        if r.get("gps_fix") != "1":
            continue
        try:
            lat, lon = float(r["gps_lat"]), float(r["gps_lon"])
        except (KeyError, ValueError, TypeError):
            continue
        if lat == 0 and lon == 0:
            continue
        fixes.append((lat, lon))

    info = {"gps_fixes": len(fixes), "max_displacement_m": None, "cells": cells}
    if len(fixes) >= 2:
        lat0, lon0 = fixes[0]
        disp = max(haversine_m(lat0, lon0, lat, lon) for lat, lon in fixes)
        info["max_displacement_m"] = round(disp)
        if disp < STATIONARY_M:
            return "ferma", f"spostamento GPS massimo {disp:.0f} m", info
        if disp > MOVING_M:
            return "in_movimento", f"spostamento GPS massimo {disp:.0f} m", info
        return "sconosciuta", f"spostamento GPS massimo {disp:.0f} m (fra le soglie)", info
    if not rows:
        return "sconosciuta", "nessun campione periodico cella/GPS (es. analisi di un .dlf)", info
    if len(cells) == 1:
        return "ferma", "nessun fix GPS, una sola cella servente per tutta la cattura", info
    if len(cells) > 1:
        return "sconosciuta", f"nessun fix GPS, {len(cells)} celle servanti diverse", info
    return "sconosciuta", "nessun fix GPS ne' cella servente nei campioni", info
