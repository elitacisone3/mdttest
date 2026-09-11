#!/usr/bin/env python3
"""
Scansione euristica a livello di BIT del file .dlf grezzo (e dei frame diag
scartati per CRC errato, recuperati dal testo di qcsuper.log), per cercare
segnali di posizione GPS (Ellipsoid-Point) o di setup MDT
(loggedMeasurementConfiguration) che potrebbero essere sfuggiti alla catena
normale qcsuper -> pcap -> tshark -> mdtcap.

Perche' serve un secondo livello, indipendente da tshark/qcsuper
------------------------------------------------------------------
mdtcap conta gia' gli avvisi WARNING di qcsuper (vedi "diagWarn" nel
manifest.json e compute_diag_warn_count() in mdtcap) — quasi sempre frame
HDLC scartati per CRC errato (_hdlc_mixin.py di qcsuper). Quando questo
capita, il frame scartato NON finisce mai nel .dlf: nessuna rilettura del
.dlf (nemmeno con --dlf-read) puo' recuperarlo. L'UNICA traccia che
resta e' il testo del messaggio WARNING stesso in qcsuper.log, che include
il repr() Python dei byte del frame (gia' de-escapato HDLC, CRC finale
escluso) — vedi hdlc_decapsulate() in qcsuper/inputs/_hdlc_mixin.py:
    warning('Ignoring (partial?) frame: Wrong CRC: %s (is: %02x, should be: %02x)'
            % (repr(payload[:-2]), ...))
Questo script prova quindi DUE riletture indipendenti (mai il pcap/tshark):
  D (Diag)   = il .dlf gia' scritto, riletto con un parser proprio (stessa
               logica di qcsuper/modules/pcap_dump.py, riportata qui sotto,
               ma completamente indipendente dal dissector lte-rrc di
               Wireshark: serve da "secondo parere" anche per i record che
               NON hanno avuto problemi di CRC, nel caso il filtro/
               dissector standard avesse un buco - e' successo in passato,
               vedi lo scenario "r17-only" di synthetic_test).
  L (Log)    = i frame SCARTATI per CRC errato, ricostruiti dal testo di
               qcsuper.log: unica fonte possibile per quei dati, per
               definizione MAI verificata (il CRC e' fallito, non sappiamo
               QUALE byte sia sbagliato) - risultati sempre da trattare
               come indizi da controllare a mano, mai come certezze.

Cosa NON e' byte-allineato (e quindi NON si presta a una regex sui byte)
-------------------------------------------------------------------------
I PDU RRC sono codificati UPER (Unaligned PER, ITU-T X.691): a differenza
di ALIGNED PER, i campi ordinari NON sono allineati a un confine di
ottetto. Verificato empiricamente: codificando un Ellipsoid-Point noto con
synthetic_test/gen_mdt_dlf.py e cercandone i 6 byte esatti nel .dlf
risultante, NON si trova nulla — il campo cade a un offset in bit
qualunque (es. bit 163 nello scenario "full", bit 38 in "r17-only"). Una
regex/grep sui byte non lo trovera' mai in modo affidabile: serve uno
scan bit-a-bit con un filtro di plausibilita' (bounding box), non un
pattern di byte in senso stretto.

Uso
---
    mdt_bitscan.py --dlf capture.dlf --qcsuper-log qcsuper.log \\
        --gps-csv periodic_cell_gps_decoded.csv \\
        --mcc 222 --mnc 01 --bbox-dir mdt_configs/gpsBoundingBox \\
        --report mdt_bitscan_report.txt

Stampa su stdout, come ultima cosa, esattamente 4 righe "chiave=valore"
(warnPosD/warnPosL/warnMDTD/warnMDTL) pensate per essere lette da uno
script di shell via command substitution; tutto il resto (dettaglio dei
candidati, note, avvisi) va nel file --report e su stderr.
"""
import argparse
import ast
import csv
import json
import os
import re
import struct
import sys
from struct import calcsize, unpack, unpack_from

LOG_LTE_RRC_OTA_MSG_LOG_C = 0xB0C0
DIAG_LOG_F = 0x10

# Tabelle canale->direzione per i due gruppi di versione dell'header esteso
# LOG_LTE_RRC_OTA_MSG_LOG_C effettivamente rilevanti per questo progetto:
#   - v0: quella usata da synthetic_test/gen_mdt_dlf.py (e da modem/
#     firmware piu' vecchi)
#   - v14: quella usata DAVVERO dal modem di questo rig (SIM7600E-H,
#     verificato leggendo ext_header_ver=20 nei .dlf reali gia' raccolti —
#     qcsuper applica la tabella "v14" anche per ext_header_ver in
#     (14,15,16,20,24,25), vedi pcap_dump.py)
# Altri gruppi di versione (9, 12, 19, >=25 post-NR) esistono in qcsuper
# ma non sono mai stati osservati su questo modem: quando capitano, questo
# script si limita a saltare il record (vedi classify_channel), invece di
# rischiare di interpretare male l'header e produrre falsi risultati.
CHANNEL_TABLES = {
    "v0": {"dl": (5, 6), "ul": (7, 8)},
    "v14": {"dl": (6, 7), "ul": (8, 9)},
}


def channel_group(ext_header_ver: int):
    if ext_header_ver in (14, 15, 16, 20, 24, 25):
        return "v14"
    if ext_header_ver in (9, 12, 19) or ext_header_ver >= 25:
        return None  # non replicato qui, vedi commento sopra
    return "v0"


def classify_channel(ext_header_ver: int, channel_type: int):
    group = channel_group(ext_header_ver)
    if group is None:
        return None
    table = CHANNEL_TABLES[group]
    if channel_type in table["dl"]:
        return "dl"
    if channel_type in table["ul"]:
        return "ul"
    return None


def parse_rrc_ota_envelope(log_payload: bytes):
    """
    Porta fedele (solo la parte che ci serve: individuare channel_type e
    isolare il PDU RRC vero e proprio) di qcsuper/modules/pcap_dump.py,
    ramo "elif log_type == LOG_LTE_RRC_OTA_MSG_LOG_C". Ritorna
    (ext_header_ver, channel_type, pdu_bytes) o None se il payload e'
    troppo corto/malformato per essere interpretato con sicurezza.
    """
    if len(log_payload) < 6:
        return None
    try:
        (ext_header_ver, rrc_rel, rrc_ver, bearer_id, phy_cellid) = unpack_from(
            "<BBBBH", log_payload, 0
        )
        ext_header = log_payload[6:]

        if ext_header_ver >= 25:
            if len(log_payload) < 8:
                return None
            (ext_header_ver, rrc_rel, rrc_ver, nc_rrc_rel, bearer_id, phy_cellid) = (
                unpack_from("<BBBHBH", log_payload, 0)
            )
            ext_header = log_payload[8:]

        freq_type = "H" if ext_header_ver < 8 else "I"
        header_spec = "<" + freq_type + "HBH"
        base_size = calcsize(header_spec)

        if len(ext_header) < base_size:
            return None

        if unpack_from("<H", ext_header, base_size - 2)[0] != len(ext_header) - base_size:
            header_spec = "<" + freq_type + "HB4xH"
            base_size = calcsize(header_spec)
            if len(ext_header) < base_size:
                return None

        (freq, sfn, channel_type, length) = unpack_from(header_spec, ext_header, 0)
        pdu = ext_header[base_size : base_size + length]
        if len(pdu) < length:
            return None  # troncato: non ci si affida a un PDU incompleto

        return ext_header_ver, channel_type, pdu
    except struct.error:
        return None


def iter_dlf_records(data: bytes):
    """
    Stesso formato di qcsuper/inputs/dlf_read.py: record consecutivi
    (log_length u16, log_type u16, log_time u64) + payload. Si ferma in
    modo silenzioso su una coda troncata (es. cattura interrotta a meta'),
    invece di sollevare un'eccezione.
    """
    off = 0
    n = len(data)
    while off + 12 <= n:
        log_length, log_type, log_time = unpack_from("<HHQ", data, off)
        if log_length < 12 or off + log_length > n:
            break
        yield log_type, data[off + 12 : off + log_length]
        off += log_length


WRONG_CRC_RE = re.compile(
    r"Ignoring \(partial\?\) frame: Wrong CRC: (?P<repr>b['\"].*) "
    r"\(is: [0-9a-f]+, should be: [0-9a-f]+\)\s*$"
)


def iter_dropped_frames(qcsuper_log_path: str):
    """
    Rilegge qcsuper.log e ricostruisce i byte grezzi di ogni frame
    scartato per CRC errato (repr() Python nel testo del WARNING, vedi
    hdlc_decapsulate() in qcsuper/inputs/_hdlc_mixin.py). ast.literal_eval
    e' sicuro (nessuna esecuzione di codice): il repr() di un oggetto
    bytes e' sempre un letterale bytes valido.
    """
    try:
        f = open(qcsuper_log_path, "r", errors="replace")
    except OSError:
        return
    with f:
        for line in f:
            m = WRONG_CRC_RE.search(line)
            if not m:
                continue
            try:
                frame = ast.literal_eval(m.group("repr"))
            except (SyntaxError, ValueError):
                continue
            if isinstance(frame, (bytes, bytearray)):
                yield bytes(frame)


def extract_log_from_dropped_frame(frame: bytes):
    """
    Rispecchia dispatch_received_diag_packet() in
    qcsuper/inputs/_base_input.py per opcode == DIAG_LOG_F: i byte
    recuperati da un WARNING "Wrong CRC" sono esattamente il contenuto
    che quella funzione avrebbe ricevuto come "unframed_diag_packet" se
    il CRC fosse stato corretto. NESSUNA garanzia che il contenuto sia
    integro (e' proprio perche' il CRC e' fallito che siamo qui): un
    singolo byte sbagliato ovunque nel frame puo' rendere questa
    interpretazione completamente sbagliata - e' un'euristica, non una
    decodifica verificata.
    """
    if len(frame) < 1 or frame[0] != DIAG_LOG_F:
        return None
    header_size = 1 + calcsize("<BH") + calcsize("<HHQ")
    if len(frame) < header_size:
        return None
    payload = frame[1:]
    pending_msgs, log_outer_length = unpack_from("<BH", payload, 0)
    inner = payload[calcsize("<BH") :]
    log_inner_length, log_type, log_time = unpack_from("<HHQ", inner, 0)
    log_payload = inner[calcsize("<HHQ") :]
    return log_type, log_payload


def decode_ellipsoid_window(bits48: int):
    """
    Stessa formula di decode_ellipsoid_point() in src/decode_mdt_location.py
    (verificata a suo tempo contro epan/dissectors/asn1/lte-rrc/lte-rrc.cnf
    e lpp/LPP-PDU-Definitions.asn di Wireshark), qui applicata a una
    finestra di 48 bit qualunque invece che ai primi 6 byte di un OCTET
    STRING gia' isolato da tshark.
    """
    lat_sign = (bits48 >> 47) & 1
    lat_val = (bits48 >> 24) & 0x7FFFFF
    lon_val = bits48 & 0xFFFFFF
    lat = (lat_val / (1 << 23)) * 90.0
    if lat_sign:
        lat = -lat
    lon = ((lon_val - (1 << 23)) / (1 << 24)) * 360.0
    return lat, lon


def scan_position_candidates(pdu: bytes, bbox):
    """
    Fa scorrere una finestra di 48 bit su OGNI offset in bit (non solo gli
    8 shift di byte: l'UPER non allinea il campo, vedi docstring del
    modulo) e tiene solo le finestre il cui (lat, lon) decodificato cade
    dentro bbox = (min_lat, min_lon, max_lat, max_lon). Ritorna la lista
    di (bit_offset, lat, lon); tipicamente se ne usa solo la lunghezza
    (un record con >=1 candidato viene contato una volta sola dal
    chiamante), i dettagli servono per il report.
    """
    if bbox is None or len(pdu) < 6:
        return []
    min_lat, min_lon, max_lat, max_lon = bbox
    value = int.from_bytes(pdu, "big")
    nbits = len(pdu) * 8
    hits = []
    for start in range(0, nbits - 48 + 1):
        window = (value >> (nbits - start - 48)) & ((1 << 48) - 1)
        lat, lon = decode_ellipsoid_window(window)
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            hits.append((start, lat, lon))
    return hits


def plmn_bit_pattern(mcc: str, mnc: str) -> str:
    """
    Codifica UPER (a mano, stringa di bit) del tipo PLMN-Identity di
    TS 36.331 quando il campo opzionale "mcc" e' presente:
      1 bit  optional-mcc-presente (sempre 1: qui cerchiamo un match
             ESPLICITO del nostro MCC, non il caso "mcc assente")
      3x4 bit  MCC-MNC-Digit (INTEGER(0..9), 4 bit ciascuno, PER vincolato)
      1 bit  selettore size MNC (0 = 2 cifre, 1 = 3 cifre; SIZE(2..3))
      2x4 o 3x4 bit  cifre MNC
    E' il campo traceReference-r10.plmn-Identity-r10 dentro
    loggedMeasurementConfiguration-r10 (vedi
    build_logged_measurement_configuration() in
    synthetic_test/gen_mdt_dlf.py) - ma PLMN-Identity compare anche in
    altri IE RRC, quindi un match qui e' un INDIZIO di un messaggio che
    nomina la nostra rete, non la prova di un setup MDT specifico
    ("se si riesce": e' deliberatamente un'euristica best-effort).
    """
    bits = "1"
    for d in mcc:
        bits += format(int(d), "04b")
    bits += "0" if len(mnc) == 2 else "1"
    for d in mnc:
        bits += format(int(d), "04b")
    return bits


def scan_mdt_candidates(pdu: bytes, plmn_pattern: str):
    """
    Cerca plmn_pattern in OGNI posizione di bit del PDU (stessa tecnica di
    scan_position_candidates, ma pattern esatto invece di un filtro di
    plausibilita', dato che qui il "bersaglio" e' un valore noto - il
    nostro MCC/MNC - non un intervallo). Ritorna gli offset di bit.
    """
    if not plmn_pattern or len(pdu) * 8 < len(plmn_pattern):
        return []
    bits = "".join(f"{byte:08b}" for byte in pdu)
    hits = []
    start = 0
    while True:
        idx = bits.find(plmn_pattern, start)
        if idx < 0:
            break
        hits.append(idx)
        start = idx + 1
    return hits


def load_bbox_from_gps_csv(path: str, lat_margin: float, lon_margin: float):
    if not path or not os.path.isfile(path):
        return None
    lats, lons = [], []
    try:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("gps_fix") != "1":
                    continue
                try:
                    lat = float(row["gps_lat"])
                    lon = float(row["gps_lon"])
                except (KeyError, TypeError, ValueError):
                    continue
                lats.append(lat)
                lons.append(lon)
    except OSError:
        return None
    if not lats:
        return None
    return (
        min(lats) - lat_margin,
        min(lons) - lon_margin,
        max(lats) + lat_margin,
        max(lons) + lon_margin,
    )


def load_bbox_from_mcc_file(bbox_dir: str, mcc: str, lat_margin: float, lon_margin: float):
    if not bbox_dir or not mcc:
        return None
    path = os.path.join(bbox_dir, f"{mcc}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            values = json.load(f)
        min_lat, min_lon, max_lat, max_lon = (float(v) for v in values)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return (min_lat - lat_margin, min_lon - lon_margin, max_lat + lat_margin, max_lon + lon_margin)


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dlf", help="file .dlf della cattura (metodo D)")
    ap.add_argument("--qcsuper-log", help="qcsuper.log della cattura (metodo L)")
    ap.add_argument("--gps-csv", help="periodic_cell_gps_decoded.csv della cattura, per il bounding box")
    ap.add_argument("--lat-margin", type=float, default=0.02, help="margine di tolleranza in gradi (default 0.02)")
    ap.add_argument("--lon-margin", type=float, default=0.02, help="margine di tolleranza in gradi (default 0.02)")
    ap.add_argument("--mcc", default="", help="MCC di rete (fallback bounding box + pattern PLMN)")
    ap.add_argument("--mnc", default="", help="MNC di rete (pattern PLMN)")
    ap.add_argument("--bbox-dir", default="", help="directory mdt_configs/gpsBoundingBox")
    ap.add_argument("--report", default="", help="file di dettaglio (candidati, note) da scrivere")
    return ap.parse_args()


def main():
    args = parse_args()
    report_lines = []

    bbox = load_bbox_from_gps_csv(args.gps_csv, args.lat_margin, args.lon_margin)
    bbox_source = "GPS di questa cattura"
    if bbox is None:
        bbox = load_bbox_from_mcc_file(args.bbox_dir, args.mcc, args.lat_margin, args.lon_margin)
        bbox_source = f"mdt_configs/gpsBoundingBox/{args.mcc}.json"
    if bbox is None:
        report_lines.append(
            "Nessun bounding box disponibile (niente fix GPS in questa cattura, "
            f"e nessun file {args.mcc or '<mcc?>'}.json in {args.bbox_dir or '?'}): "
            "scansione posizione (warnPosD/warnPosL) saltata, resta 0/0."
        )
    else:
        report_lines.append(
            "Bounding box (%s, margine %.4f/%.4f gradi): lat [%.6f, %.6f], lon [%.6f, %.6f]"
            % (bbox_source, args.lat_margin, args.lon_margin, bbox[0], bbox[2], bbox[1], bbox[3])
        )

    plmn_pattern = ""
    if args.mcc and args.mnc:
        plmn_pattern = plmn_bit_pattern(args.mcc, args.mnc)
        report_lines.append(f"Pattern PLMN cercato (MCC={args.mcc} MNC={args.mnc}): {plmn_pattern}")
    else:
        report_lines.append("MCC/MNC di rete non disponibili: scansione MDT (warnMDTD/warnMDTL) saltata, resta 0/0.")

    warn_pos_d = warn_pos_l = warn_mdt_d = warn_mdt_l = 0

    # --- metodo D: .dlf gia' scritto, riletto con parser indipendente ---
    if args.dlf and os.path.isfile(args.dlf):
        with open(args.dlf, "rb") as f:
            dlf_data = f.read()
        n_records = 0
        for log_type, payload in iter_dlf_records(dlf_data):
            if log_type != LOG_LTE_RRC_OTA_MSG_LOG_C:
                continue
            parsed = parse_rrc_ota_envelope(payload)
            if parsed is None:
                continue
            ver, ch, pdu = parsed
            direction = classify_channel(ver, ch)
            n_records += 1
            if direction == "ul" and bbox is not None:
                hits = scan_position_candidates(pdu, bbox)
                if hits:
                    warn_pos_d += 1
                    off, lat, lon = hits[0]
                    report_lines.append(
                        f"[D][pos] record RRC-OTA uplink: candidato a bit {off}, "
                        f"lat={lat:.6f} lon={lon:.6f} ({len(hits)} finestre totali nel record)"
                    )
            elif direction == "dl" and plmn_pattern:
                hits = scan_mdt_candidates(pdu, plmn_pattern)
                if hits:
                    warn_mdt_d += 1
                    report_lines.append(
                        f"[D][mdt] record RRC-OTA downlink: pattern PLMN trovato a bit {hits[0]} "
                        f"({len(hits)} occorrenze nel record)"
                    )
        report_lines.append(f"Metodo D: {n_records} record RRC-OTA (0xb0c0) analizzati nel .dlf")
    else:
        report_lines.append("Metodo D saltato: file .dlf non indicato o non trovato")

    # --- metodo L: frame scartati per CRC errato, dal testo di qcsuper.log ---
    if args.qcsuper_log and os.path.isfile(args.qcsuper_log):
        n_dropped = n_rrc = 0
        for frame in iter_dropped_frames(args.qcsuper_log):
            n_dropped += 1
            extracted = extract_log_from_dropped_frame(frame)
            if extracted is None:
                continue
            log_type, log_payload = extracted
            if log_type != LOG_LTE_RRC_OTA_MSG_LOG_C:
                continue
            parsed = parse_rrc_ota_envelope(log_payload)
            if parsed is None:
                continue
            ver, ch, pdu = parsed
            direction = classify_channel(ver, ch)
            n_rrc += 1
            if direction == "ul" and bbox is not None:
                hits = scan_position_candidates(pdu, bbox)
                if hits:
                    warn_pos_l += 1
                    off, lat, lon = hits[0]
                    report_lines.append(
                        f"[L][pos] frame CRC scartato, NON VERIFICATO: candidato a bit {off}, "
                        f"lat={lat:.6f} lon={lon:.6f} ({len(hits)} finestre totali)"
                    )
            elif direction == "dl" and plmn_pattern:
                hits = scan_mdt_candidates(pdu, plmn_pattern)
                if hits:
                    warn_mdt_l += 1
                    report_lines.append(
                        f"[L][mdt] frame CRC scartato, NON VERIFICATO: pattern PLMN a bit {hits[0]} "
                        f"({len(hits)} occorrenze)"
                    )
        report_lines.append(
            f"Metodo L: {n_dropped} frame scartati per CRC errato in qcsuper.log, "
            f"{n_rrc} sembrano un record RRC-OTA (0xb0c0) leggibile"
        )
    else:
        report_lines.append("Metodo L saltato: qcsuper.log non indicato o non trovato")

    if args.report:
        with open(args.report, "w") as f:
            f.write("\n".join(report_lines) + "\n")
    else:
        for line in report_lines:
            print(line, file=sys.stderr)

    print(f"warnPosD={warn_pos_d}")
    print(f"warnPosL={warn_pos_l}")
    print(f"warnMDTD={warn_mdt_d}")
    print(f"warnMDTL={warn_mdt_l}")


if __name__ == "__main__":
    main()
