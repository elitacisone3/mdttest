#!/usr/bin/env python3
"""
Estrae e decodifica le coordinate GPS trasmesse via MDT (LTE-RRC LocationInfo)
da un file pcap prodotto da qcsuper.

Il dissector lte-rrc di Wireshark espone il campo "Ellipsoid Point" come
OCTET STRING grezzo (non decodificato in gradi): questo script lo interpreta
secondo la codifica UPER nativa "Ellipsoid-Point" / "EllipsoidPointWithAltitude"
di 3GPP TS 36.355 (LPP) — verificato contro il codice sorgente del dissector
Wireshark (epan/dissectors/asn1/lte-rrc/lte-rrc.cnf, che per questi campi
chiama dissect_lpp_Ellipsoid_Point_PDU/EllipsoidPointWithAltitude_PDU
direttamente sul contenuto grezzo dell'OCTET STRING) e contro la grammatica
ASN.1 in epan/dissectors/asn1/lpp/LPP-PDU-Definitions.asn.

Include anche coarseLocationInfo-r17 (Release 17, aggiunto come IE fratello
di logMeasReport-r10 in UEInformationResponse-v1710-IEs, non annidato al suo
interno): stessa codifica Ellipsoid-Point a 6 ottetti (lte-rrc.cnf chiama lo
stesso dissect_lpp_Ellipsoid_Point_PDU), quindi decodificabile con la stessa
decode_ellipsoid_point(). Omesso in una versione precedente di questo script,
causava un falso negativo: una risposta UE con solo coarseLocationInfo-r17
(senza logMeasReport-r10/locationInfo-r10/r11/r16) non produceva alcuna riga
in coordinate_estratte.csv.

Uso:
    decode_mdt_location.py capture.pcap -o coordinate_estratte.csv
"""
import sys
import csv
import subprocess
import argparse

LOCATION_ELEMENT_FILTER = (
    "lte-rrc.locationInfo_r10_element or "
    "lte-rrc.locationInfo_r11_element or "
    "lte-rrc.locationInfo_r16_element or "
    "lte-rrc.coarseLocationInfo_r17"
)

FIELDS = [
    "frame.number",
    "frame.time",
    "lte-rrc.ellipsoid_Point_r10",
    "lte-rrc.ellipsoidPointWithAltitude_r10",
    "lte-rrc.coarseLocationInfo_r17",
]


def decode_ellipsoid_point(b: bytes):
    """
    Decodifica 6 (Ellipsoid-Point) o 8 byte (EllipsoidPointWithAltitude)
    secondo la codifica UPER nativa 3GPP TS 36.355 (LPP), riusata
    direttamente (nessun ottetto "tipo di shape" TS 23.032 davanti: lo
    conferma il codice sorgente del dissector Wireshark, che chiama
    dissect_lpp_Ellipsoid_Point_PDU/EllipsoidPointWithAltitude_PDU sul
    contenuto grezzo dell'OCTET STRING, vedi epan/dissectors/asn1/lte-rrc/
    lte-rrc.cnf — ellipsoid-Point-r10/ellipsoidPointWithAltitude-r10):
      ottetti 0-2     : segno (bit alto) + gradi di latitudine, INTEGER
                        PER-vincolato (0..8388607), 23 bit, valore diretto
      ottetti 3-5     : gradi di longitudine, INTEGER PER-vincolato
                        (-8388608..8388607), 24 bit codificati come offset
                        dal minimo (valore_wire = longitudine + 8388608,
                        binario NON in complemento a 2: e' cosi' che UPER
                        codifica un INTEGER con range con segno)
      ottetti 6-7 (op): direzione (bit alto) + altitudine in metri (15 bit)
    """
    if len(b) < 6:
        return None

    lat_sign = (b[0] >> 7) & 0x1
    lat_val = ((b[0] & 0x7F) << 16) | (b[1] << 8) | b[2]
    latitude = lat_val * 90.0 / (1 << 23)
    if lat_sign:
        latitude = -latitude

    lon_raw = (b[3] << 16) | (b[4] << 8) | b[5]
    lon_raw -= 1 << 23  # offset dal minimo del range PER (-8388608), non complemento a 2
    longitude = lon_raw * 360.0 / (1 << 24)

    altitude = None
    if len(b) >= 8:
        alt_dir = (b[6] >> 7) & 0x1
        alt_val = ((b[6] & 0x7F) << 8) | b[7]
        altitude = -alt_val if alt_dir else alt_val

    return latitude, longitude, altitude


def run_tshark(pcap_path: str):
    cmd = ["tshark", "-r", pcap_path, "-Y", LOCATION_ELEMENT_FILTER, "-T", "fields"]
    for f in FIELDS:
        cmd += ["-e", f]
    cmd += ["-E", "header=n", "-E", "separator=\t", "-E", "occurrence=f"]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        print("ERRORE: tshark non trovato nel PATH", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"ERRORE: tshark ha fallito: {e.stderr}", file=sys.stderr)
        sys.exit(1)

    return proc.stdout.splitlines()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pcap", help="file pcap generato da qcsuper (--pcap-dump)")
    ap.add_argument("-o", "--out", default="coordinate_estratte.csv", help="file CSV di output")
    args = ap.parse_args()

    rows = []
    for line in run_tshark(args.pcap):
        if not line.strip():
            continue
        parts = line.split("\t")
        while len(parts) < len(FIELDS):
            parts.append("")
        frame_no, frame_time, ep_hex, epa_hex, coarse_hex = parts[:5]

        raw_hex = epa_hex or ep_hex or coarse_hex
        if epa_hex:
            source_field = "ellipsoidPointWithAltitude_r10"
        elif ep_hex:
            source_field = "ellipsoid_Point_r10"
        else:
            source_field = "coarseLocationInfo_r17"
        if not raw_hex:
            continue

        try:
            raw_bytes = bytes.fromhex(raw_hex.replace(":", ""))
        except ValueError:
            continue

        decoded = decode_ellipsoid_point(raw_bytes)
        if not decoded:
            continue

        lat, lon, alt = decoded
        rows.append({
            "frame_number": frame_no,
            "frame_time": frame_time,
            "latitude_deg": f"{lat:.6f}",
            "longitude_deg": f"{lon:.6f}",
            "altitude_m": alt if alt is not None else "",
            "source_field": source_field,
            "raw_hex": raw_hex,
        })

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "frame_number", "frame_time", "latitude_deg", "longitude_deg",
            "altitude_m", "source_field", "raw_hex",
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} coordinate estratte e decodificate -> {args.out}")


if __name__ == "__main__":
    main()
