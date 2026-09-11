#!/usr/bin/env python3
"""
Genera un file .dlf sintetico (formato letto da qcsuper --dlf-read, lo
stesso usato da mdtcap --analyze-dlf) contenente traffico LTE-RRC MDT, senza
bisogno di modem/SIM/rete reali. Utile per testare mdtcap end-to-end (vedi
la guida in synthetic_test/README.md).

Le PDU RRC sono codificate in UPER con pycrate (modulo ASN.1
EUTRA-RRC-Definitions), poi incapsulate come frame diag
LOG_LTE_RRC_OTA_MSG_LOG_C (0xb0c0, extended header version 0) dentro
record DLF (12 byte di header: log_length u16, log_type u16, log_time u64),
lo stesso formato scritto da qcsuper (vedi qcsuper/inputs/dlf_read.py e
qcsuper/modules/pcap_dump.py).

Scenari disponibili (--scenario):
  full              (default) sequenza completa: loggedMeasurementConfiguration
                    (DL) -> ueInformationRequest+logMeasReportReq (DL) ->
                    ueInformationResponse+logMeasReport+locationInfo GPS (UL).
                    Atteso in mdtcap: Operatore=MDT,GPS,Attiva UE=GPS RRC=1(1 GPS) MDT=2
  config-only       solo loggedMeasurementConfiguration (DL): la rete configura
                    il logging ma non chiede ancora l'invio delle misure.
                    Atteso: Operatore=MDT UE=OK RRC=0 MDT=1
  request-only      loggedMeasurementConfiguration + ueInformationRequest con
                    logMeasReportReq (entrambi DL), nessuna risposta UE.
                    Atteso: Operatore=MDT,Attiva UE=OK RRC=0 MDT=2
  response-no-gps   ueInformationRequest (DL) + ueInformationResponse con
                    logMeasReport MA SENZA locationInfo (UL): l'UE risponde
                    alle misure ma senza posizione (locationInfo-r10 e'
                    OPTIONAL in LogMeasInfo-r10, vedi EUTRA-RRC-Definitions.asn).
                    Atteso: Operatore=MDT,Attiva UE=OK RRC=1(0 GPS,1 senza) MDT=1
  r17-only          ueInformationResponse con SOLO coarseLocationInfo-r17
                    (Release 17, aggiunto come IE fratello di logMeasReport-r10
                    in UEInformationResponse-v1710-IEs, non annidato al suo
                    interno), nessun'altra PDU. E' il caso di regressione che
                    ha rivelato un falso negativo in una versione precedente
                    di mdtcap (nessuno dei filtri intercettava questo IE):
                    rieseguire questo scenario dopo ogni modifica ai filtri
                    MDT_*_FILTER in mdtcap per verificare che resti rilevato.
                    Atteso: Operatore=OK UE=GPS RRC=1(1 GPS) MDT=0

  Scenari per mdtcap --extended (src/extra_scan), traffico DIVERSO da MDT:
  rrcciph-eea0            SecurityModeCommand con cifratura/integrita' nulla
                          (EEA0/EIA0). Atteso: RRCCiph=A.
  cellsys-2g-downgrade    RRCConnectionRelease con redirectedCarrierInfo=geran.
                          Atteso: cellSys=C (1 evento, sotto cum_threshold=2).
  wcdma3g-3g-downgrade    RRCConnectionRelease con redirectedCarrierInfo=utra-FDD.
                          Atteso: WCDMA3G=W (1 evento, sotto cum_threshold=3).
  nasid-identity-imsi     NAS EMM Identity Request (tipo 85, IMSI).
                          Atteso: NASId=C (1 evento, sotto cum_threshold=3).
  nasid-guti-realloc-frequent  due GUTI Reallocation Command (tipo 80) a <60s.
                          Atteso: NASId=W.
  smsstk-silent-sms       SMS-DELIVER con TP-DCS class 0 (0xF0), dentro NAS
                          Downlink Transport. Atteso: SMSSTK=W (sotto cum_threshold=5).

  Scenari per mdtcap --test-sms (SMS "magica" di test, vedi
  src/extra_scan:detect_test_sms_trigger e mdtcap --test-sms):
  testsms-rrcciph / testsms-cellsys / testsms-wcdma3g / testsms-nasid /
  testsms-smsstk   SMS-DELIVER visibile (TP-DCS 0x00) col testo magico e
                   un token di categoria. Atteso: SOLO quella categoria=A,
                   e SOLO se mdtcap e' lanciato con --test-sms (altrimenti
                   nessun effetto).
  testsms-all      Come sopra, token ALL____: tutte e 5 le categorie=A.

Uso:
    python3 gen_mdt_dlf.py [opzioni]
    python3 gen_mdt_dlf.py --scenario r17-only -o r17_only.dlf
    python3 gen_mdt_dlf.py --lat 45.4642 --lon 9.1900 --mcc 222 --mnc 10 -o milano.dlf

Vedi synthetic_test/README.md per la guida completa (come rigenerare il
pcap, come lanciare mdtcap --analyze-dlf, tabella scenario -> verdetto atteso).
"""
import argparse
import time
from datetime import datetime, timedelta, timezone
from struct import pack

from pycrate_asn1dir.RRCLTE import EUTRA_RRC_Definitions as D
from pycrate_mobile import TS24301_EMM as EMM
from pycrate_mobile import TS23040_SMS as SMS

LOG_LTE_RRC_OTA_MSG_LOG_C = 0xB0C0
# Stessi log type di src/extra_scan (LOG_LTE_NAS_EMM_OTA_IN/OUT_MSG_LOG_C):
# frame diag per messaggi NAS EMM (Identity Request/GUTI realloc/SMS via NAS
# transport), header <BBBB> invece dell'header RRC con freq/sfn/channel_type
# - vedi diag_nas_frame() sotto. IN = downlink (rete->UE), OUT = uplink.
LOG_LTE_NAS_EMM_OTA_IN_MSG_LOG_C = 0xB0EC
LOG_LTE_NAS_EMM_OTA_OUT_MSG_LOG_C = 0xB0ED

LTE_DL_CCCH_v0 = 5
LTE_DL_DCCH_v0 = 6
LTE_UL_CCCH_v0 = 7
LTE_UL_DCCH_v0 = 8

SCENARIOS = (
    "full", "config-only", "request-only", "response-no-gps", "r17-only",
    "rrcciph-eea0", "cellsys-2g-downgrade", "wcdma3g-3g-downgrade",
    "nasid-identity-imsi", "nasid-guti-realloc-frequent", "smsstk-silent-sms",
    "testsms-rrcciph", "testsms-cellsys", "testsms-wcdma3g", "testsms-nasid",
    "testsms-smsstk", "testsms-all",
)

# Token esatti a 7 caratteri attesi da src/extra_scan:TEST_SMS_CATEGORY_TOKENS/
# TEST_SMS_ALL_TOKEN - duplicati qui (non importiamo extra_scan: e' un
# eseguibile senza estensione .py, non un modulo, e i due file restano
# volutamente indipendenti) per gli scenari testsms-*.
TEST_SMS_TOKENS = {
    "testsms-rrcciph": "RRCCiph",
    "testsms-cellsys": "cellSys",
    "testsms-wcdma3g": "WCDMA3G",
    "testsms-nasid": "NASId__",
    "testsms-smsstk": "SMSSTK_",
    "testsms-all": "ALL____",
}


def mcc_mnc(mcc_digits, mnc_digits):
    return {'mcc': [int(c) for c in mcc_digits], 'mnc': [int(c) for c in mnc_digits]}


def encode_ellipsoid_point(lat, lon):
    """
    Ellipsoid-Point (3GPP TS 36.355/LPP, SEQUENCE{latitudeSign ENUM,
    degreesLatitude INTEGER(0..8388607), degreesLongitude INTEGER
    (-8388608..8388607)}) codificata UPER: 6 ottetti, NESSUN ottetto "tipo
    di shape" davanti (a differenza del formato TS 23.032 usato altrove).
    Verificato contro il codice sorgente del dissector Wireshark
    (epan/dissectors/asn1/lte-rrc/lte-rrc.cnf: il campo ellipsoid-Point-r10
    passa l'intero contenuto dell'OCTET STRING a
    dissect_lpp_Ellipsoid_Point_PDU) e contro la grammatica ASN.1 in
    epan/dissectors/asn1/lpp/LPP-PDU-Definitions.asn. La longitudine e'
    un INTEGER PER-vincolato con range negativo: UPER la codifica come
    offset dal minimo del range (valore + 8388608), NON in complemento a 2.
    """
    lat_sign = 1 if lat < 0 else 0
    lat_val = round(abs(lat) / 90.0 * (1 << 23))
    lon_val = round(lon / 360.0 * (1 << 24)) + (1 << 23)
    return bytes([
        (lat_sign << 7) | ((lat_val >> 16) & 0x7F),
        (lat_val >> 8) & 0xFF,
        lat_val & 0xFF,
        (lon_val >> 16) & 0xFF,
        (lon_val >> 8) & 0xFF,
        lon_val & 0xFF,
    ])


def trace_reference(mcc, mnc, trace_id, session_ref, tce_id):
    return {
        'traceReference-r10': {
            'plmn-Identity-r10': mcc_mnc(mcc, mnc),
            'traceId-r10': trace_id,
        },
        'traceRecordingSessionRef-r10': session_ref,
        'tce-Id-r10': tce_id,
    }


def build_logged_measurement_configuration(args):
    """
    absoluteTimeInfo-r10 e' un BIT STRING(48) con la codifica BCD compressa
    di TS 36.331 (non e' interpretato da mdtcap, solo decorativo): valore
    fisso di esempio, indipendente da --base-time.
    """
    msg = D.DL_DCCH_Message
    msg.set_val({
        'message': ('c1', ('loggedMeasurementConfiguration-r10', {
            'criticalExtensions': ('c1', ('loggedMeasurementConfiguration-r10', {
                **trace_reference(args.mcc, args.mnc, args.trace_id, args.session_ref, args.tce_id),
                'absoluteTimeInfo-r10': (
                    int.from_bytes(b'\x18\x09\x05\x12\x00\x00', 'big'), 48
                ),
                'loggingDuration-r10': 'min60',
                'loggingInterval-r10': 'ms5120',
            }))
        }))
    })
    buf = msg.to_uper()
    msg.reset_val()
    return buf


def build_ue_information_request():
    msg = D.DL_DCCH_Message
    msg.set_val({
        'message': ('c1', ('ueInformationRequest-r9', {
            'rrc-TransactionIdentifier': 1,
            'criticalExtensions': ('c1', ('ueInformationRequest-r9', {
                'rach-ReportReq-r9': False,
                'rlf-ReportReq-r9': False,
                'nonCriticalExtension': {
                    'nonCriticalExtension': {
                        'logMeasReportReq-r10': 'true',
                    }
                }
            }))
        }))
    })
    buf = msg.to_uper()
    msg.reset_val()
    return buf


def build_ue_information_response(args, with_location):
    """
    ueInformationResponse-r9 con logMeasReport-r10. locationInfo-r10 e'
    OPTIONAL dentro LogMeasInfo-r10 (EUTRA-RRC-Definitions.asn): con
    with_location=False lo si omette per simulare una risposta MDT senza
    posizione (scenario response-no-gps). absoluteTimeStamp-r10 e' un BIT
    STRING(48) BCD (TS 36.331, non interpretato da mdtcap): valore fisso di
    esempio, indipendente da --base-time.
    """
    log_meas_info = {
        'relativeTimeStamp-r10': 5,
        'servCellIdentity-r10': {
            'plmn-Identity': mcc_mnc(args.mcc, args.mnc),
            'cellIdentity': (0x1A2B3C4, 28),
        },
        'measResultServCell-r10': {
            'rsrpResult-r10': args.rsrp,
            'rsrqResult-r10': args.rsrq,
        },
    }
    if with_location:
        ep = encode_ellipsoid_point(args.lat, args.lon)
        log_meas_info['locationInfo-r10'] = {
            'locationCoordinates-r10': ('ellipsoid-Point-r10', ep),
        }

    msg = D.UL_DCCH_Message
    msg.set_val({
        'message': ('c1', ('ueInformationResponse-r9', {
            'rrc-TransactionIdentifier': 1,
            'criticalExtensions': ('c1', ('ueInformationResponse-r9', {
                'nonCriticalExtension': {
                    'nonCriticalExtension': {
                        'logMeasReport-r10': {
                            'absoluteTimeStamp-r10': (
                                int.from_bytes(b'\x18\x09\x05\x12\x00\x05', 'big'), 48
                            ),
                            **trace_reference(args.mcc, args.mnc, args.trace_id, args.session_ref, args.tce_id),
                            'logMeasInfoList-r10': [log_meas_info],
                        }
                    }
                }
            }))
        }))
    })
    buf = msg.to_uper()
    msg.reset_val()
    return buf


def build_ue_information_response_r17_only(args):
    """
    ueInformationResponse-r9 con SOLO coarseLocationInfo-r17 (Release 17),
    incapsulato nella catena reale di nonCriticalExtension prevista dalla
    grammatica ASN.1 (v930 -> v1020 [assente] -> v1130 -> v1250 -> v1530 ->
    v1610 -> v1710), SENZA logMeasReport-r10: e' l'IE fratello, non annidato,
    che nessuno dei filtri di mdtcap intercettava prima della fix (vedi
    docstring dello scenario in testa a questo file).
    """
    ep = encode_ellipsoid_point(args.lat, args.lon)
    msg = D.UL_DCCH_Message
    msg.set_val({
        'message': ('c1', ('ueInformationResponse-r9', {
            'rrc-TransactionIdentifier': 1,
            'criticalExtensions': ('c1', ('ueInformationResponse-r9', {
                'nonCriticalExtension': {                      # v930
                    'nonCriticalExtension': {                  # v1020 -- niente logMeasReport-r10
                        'nonCriticalExtension': {              # v1130
                            'nonCriticalExtension': {          # v1250
                                'nonCriticalExtension': {      # v1530
                                    'nonCriticalExtension': {  # v1610
                                        'nonCriticalExtension': {  # v1710
                                            'coarseLocationInfo-r17': ep,
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }))
        }))
    })
    buf = msg.to_uper()
    msg.reset_val()
    return buf


def build_security_mode_command_eea0():
    """
    SecurityModeCommand (DL-DCCH) con cifratura e integrita' NULL
    (EEA0/EIA0) in SecurityAlgorithmConfig - RRCCiph.eea0_eia0 in
    extra_configs/main.conf, filtro tshark
    "lte-rrc.cipheringAlgorithm==0 or lte-rrc.integrityProtAlgorithm==0".
    Struttura verificata con pycrate (set_val + to_uper riusciti al primo
    tentativo, nessun IE opzionale necessario oltre securityConfigSMC).
    """
    msg = D.DL_DCCH_Message
    msg.set_val({
        'message': ('c1', ('securityModeCommand', {
            'rrc-TransactionIdentifier': 1,
            'criticalExtensions': ('c1', ('securityModeCommand-r8', {
                'securityConfigSMC': {
                    'securityAlgorithmConfig': {
                        'cipheringAlgorithm': 'eea0',
                        'integrityProtAlgorithm': 'eia0-v920',
                    }
                }
            }))
        }))
    })
    buf = msg.to_uper()
    msg.reset_val()
    return buf


def build_rrc_connection_release_redirect(target):
    """
    RRCConnectionRelease (DL-DCCH) con redirectedCarrierInfo verso 'target'
    ("geran"/"utra-FDD"/"utra-TDD") - cellSys.forced_2g_downgrade
    (target="geran", filtro "lte-rrc.redirectedCarrierInfo==1") o
    WCDMA3G.forced_3g_downgrade (target="utra-FDD"/"utra-TDD", filtro
    "lte-rrc.redirectedCarrierInfo==2 or ...==3 or ...==6") in
    extra_configs/main.conf. "geran" richiede una CarrierFreqsGERAN
    (SEQUENCE) invece di un semplice ARFCN intero come utra-FDD/utra-TDD -
    valori minimi verificati validi con pycrate (to_uper riuscito).
    """
    if target == "geran":
        redirected = ('geran', {
            'startingARFCN': 1,
            'bandIndicator': 'dcs1800',
            'followingARFCNs': ('explicitListOfARFCNs', []),
        })
    else:
        redirected = (target, 1)  # utra-FDD/utra-TDD: ARFCN-ValueUTRA, intero semplice

    msg = D.DL_DCCH_Message
    msg.set_val({
        'message': ('c1', ('rrcConnectionRelease', {
            'rrc-TransactionIdentifier': 1,
            'criticalExtensions': ('c1', ('rrcConnectionRelease-r8', {
                'releaseCause': 'other',
                'redirectedCarrierInfo': redirected,
            }))
        }))
    })
    buf = msg.to_uper()
    msg.reset_val()
    return buf


def build_nas_identity_request_bytes():
    """
    NAS EMM Identity Request, tipo IMSI - NASId.unsolicited_identity_imsi,
    filtro tshark "nas-eps.nas_msg_emm_type==85 and nas-eps.emm.id_type2==1".
    I valori di default della classe pycrate sono gia' esattamente questo
    (Type=85, IDType.V=1/IMSI): nessuna personalizzazione necessaria,
    verificato col byte-dump (07 55 01).
    """
    return EMM.EMMIdentityRequest().to_bytes()


def build_nas_guti_realloc_bytes():
    """
    NAS EMM GUTI Reallocation Command - NASId.guti_realloc_anomaly, filtro
    tshark "nas-eps.nas_msg_emm_type==80". Valori di default della classe
    pycrate (GUTI placeholder, nessuna TAIList/DCNID/UERadioCapID opzionale
    emessa) gia' sufficienti, verificato col byte-dump.
    """
    return EMM.EMMGUTIReallocCommand().to_bytes()


def build_sms_deliver_tpdu(text, dcs):
    """
    SMS-DELIVER TPDU (TS 23.040 9.2.2.1) con TP-UD=text, TP-DCS=dcs (dict
    Group/Charset/Class, vedi pycrate_mobile.TS23038.SMS_DCS) - usata sia
    per lo scenario SMSSTK.silent_sms (dcs classe 0/2, TP-DCS 0xF0/0xF2)
    sia per gli scenari testsms-* (dcs "generale" senza classe, TP-DCS
    0x00, SMS visibile normale). encode_7b/GSM 7-bit e' gestito
    automaticamente da pycrate (TP_UD.UD accetta una str Python).
    """
    sms = SMS.SMS_DELIVER()
    sms.set_val({
        'TP_MMS': 0,
        'TP_OA': {'Ext': 1, 'Type': 1, 'NumberingPlan': 1, 'Num': '391234567'},
        'TP_PID': {'Format': 0, 'Telematic': {'Telematic': 0, 'Protocol': 0}},
        'TP_DCS': dcs,
        'TP_SCTS': (time.gmtime(), 0.0),
        'TP_UD': {'UD': text},
    })
    return sms.to_bytes()


def build_nas_dl_transport_with_sms(tpdu_bytes):
    """
    NAS EMM 'Downlink NAS Transport' (tipo 98) con l'SMS-DELIVER TPDU come
    NASContainer - lo stesso contenitore che src/extra_scan cerca (byte di
    tipo messaggio 98/99 nei primi 8 byte, poi scansione byte-a-byte del
    resto alla ricerca di un TPDU plausibile, vedi detect_silent_sms/
    detect_test_sms_trigger). Uso pycrate anche qui (non solo un LV a
    mano) per un frame NAS realistico end-to-end.
    """
    d = EMM.EMMDLNASTransport()
    d.set_val({'NASContainer': {'V': tpdu_bytes}})
    return d.to_bytes()


def diag_nas_frame(nas_bytes, rrc_rel=9, rrc_ver_minor=0, rrc_ver_major=0):
    """
    Payload del frame diag LOG_LTE_NAS_EMM_OTA_IN/OUT_MSG_LOG_C (0xb0ec/
    0xb0ed): header a 4 byte '<BBBB>' (ext_header_ver, rrc_rel,
    rrc_ver_minor, rrc_ver_major) + messaggio NAS grezzo - fonte:
    qcsuper/modules/pcap_dump.py (unpack('<BBBB', log_payload[:4])),
    STESSO formato gia' assunto da src/extra_scan:detect_silent_sms
    (payload[4:] per saltare l'header). A differenza del frame RRC
    (diag_log_frame sopra) non c'e' alcun campo freq/sfn/channel_type/
    length: il messaggio NAS segue direttamente l'header.
    """
    return pack('<BBBB', 0, rrc_rel, rrc_ver_minor, rrc_ver_major) + nas_bytes


def diag_log_frame(rrc_bytes, channel_type, freq=1300, sfn=100,
                    bearer_id=1, phy_cellid=100, rrc_rel=9, rrc_ver=0):
    """
    Costruisce il payload del LOG_LTE_RRC_OTA_MSG_LOG_C (0xb0c0), extended
    header version 0, come atteso da qcsuper/modules/pcap_dump.py:
      base header (6B): ext_header_ver(B) rrc_rel(B) rrc_ver(B) bearer_id(B) phy_cellid(H)
      ext header  (7B): freq(H) sfn(H) channel_type(B) length(H)
      payload: rrc_bytes (RRC PDU UPER-encoded, esatto in TS 36.331)
    """
    ext_header_ver = 0
    base = pack('<BBBBH', ext_header_ver, rrc_rel, rrc_ver, bearer_id, phy_cellid)
    ext = pack('<HHBH', freq, sfn, channel_type, len(rrc_bytes))
    return base + ext + rrc_bytes


def dlf_timestamp(dt):
    """
    Timestamp diag LOG standard: bit alti = unita' da 20ms dal 1980-01-06,
    20 bit bassi = mantissa (vedi qcsuper/inputs/dlf_read.py).
    """
    TIMESTAMP_OFFSET = datetime(1980, 1, 6, tzinfo=timezone.utc).timestamp()
    delta = dt.timestamp() - TIMESTAMP_OFFSET
    units_20ms = int(delta * 50)
    return (units_20ms << 20)


def dlf_record(log_type, payload, dt):
    log_length = 12 + len(payload)
    header = pack('<HHQ', log_length, log_type, dlf_timestamp(dt))
    return header + payload


def hexbytes(s):
    try:
        b = bytes.fromhex(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"valore esadecimale non valido: {s!r}")
    if not b:
        raise argparse.ArgumentTypeError("il valore esadecimale non puo' essere vuoto")
    return b


def mcc_digits(s):
    if not (len(s) == 3 and s.isdigit()):
        raise argparse.ArgumentTypeError(f"MCC deve essere di 3 cifre, ricevuto: {s!r}")
    return s


def mnc_digits(s):
    if not (len(s) in (2, 3) and s.isdigit()):
        raise argparse.ArgumentTypeError(f"MNC deve essere di 2 o 3 cifre, ricevuto: {s!r}")
    return s


def iso_time(s):
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        raise argparse.ArgumentTypeError(f"data/ora non valida (attesa ISO 8601, es. 2026-09-05T12:00:00Z): {s!r}")


def parse_args():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("-o", "--out", default="synthetic_mdt_capture.dlf",
                     help="file .dlf di output (default: %(default)s)")
    ap.add_argument("--scenario", choices=SCENARIOS, default="full",
                     help="sequenza di messaggi RRC da generare (default: %(default)s); vedi elenco in testa a questo file")
    ap.add_argument("--lat", type=float, default=41.902782,
                     help="latitudine da codificare in Ellipsoid-Point, gradi decimali (default: %(default)s, Roma)")
    ap.add_argument("--lon", type=float, default=12.496366,
                     help="longitudine da codificare in Ellipsoid-Point, gradi decimali (default: %(default)s, Roma)")
    ap.add_argument("--mcc", type=mcc_digits, default="222",
                     help="MCC del PLMN di trace (default: %(default)s, Italia)")
    ap.add_argument("--mnc", type=mnc_digits, default="01",
                     help="MNC del PLMN di trace (default: %(default)s, TIM)")
    ap.add_argument("--trace-id", type=hexbytes, default=bytes.fromhex("010203"),
                     help="traceId-r10, esadecimale (default: 010203)")
    ap.add_argument("--session-ref", type=hexbytes, default=bytes.fromhex("0001"),
                     help="traceRecordingSessionRef-r10, esadecimale (default: 0001)")
    ap.add_argument("--tce-id", type=hexbytes, default=bytes.fromhex("10"),
                     help="tce-Id-r10, esadecimale (default: 10)")
    ap.add_argument("--rsrp", type=int, default=60, metavar="0-97",
                     help="rsrpResult-r10, RSRP-Range 3GPP TS 36.331 (default: %(default)s ~= -81dBm)")
    ap.add_argument("--rsrq", type=int, default=20, metavar="0-34",
                     help="rsrqResult-r10, RSRQ-Range 3GPP TS 36.331 (default: %(default)s ~= -10dB)")
    ap.add_argument("--base-time", type=iso_time, default=datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc),
                     help="timestamp UTC del primo record, ISO 8601 (default: %(default)s)")
    args = ap.parse_args()

    if not (0 <= args.rsrp <= 97):
        ap.error("--rsrp deve essere tra 0 e 97 (RSRP-Range, TS 36.331)")
    if not (0 <= args.rsrq <= 34):
        ap.error("--rsrq deve essere tra 0 e 34 (RSRQ-Range, TS 36.331)")
    if args.base_time.tzinfo is None:
        args.base_time = args.base_time.replace(tzinfo=timezone.utc)

    return args


def build_records(args):
    """Ritorna la lista di (log_type, payload_diag, timestamp) per lo
    scenario scelto - log_type e' LOG_LTE_RRC_OTA_MSG_LOG_C per i frame RRC
    (come prima) o LOG_LTE_NAS_EMM_OTA_IN_MSG_LOG_C per i nuovi frame NAS
    (Identity Request/GUTI realloc/SMS via NAS transport, tutti downlink in
    questi scenari sintetici)."""
    t = args.base_time
    records = []
    RRC = LOG_LTE_RRC_OTA_MSG_LOG_C
    NAS_IN = LOG_LTE_NAS_EMM_OTA_IN_MSG_LOG_C

    if args.scenario == "full":
        records.append((RRC, diag_log_frame(build_logged_measurement_configuration(args), LTE_DL_DCCH_v0), t))
        records.append((RRC, diag_log_frame(build_ue_information_request(), LTE_DL_DCCH_v0), t + timedelta(seconds=5)))
        records.append((RRC, diag_log_frame(build_ue_information_response(args, with_location=True), LTE_UL_DCCH_v0), t + timedelta(seconds=7)))

    elif args.scenario == "config-only":
        records.append((RRC, diag_log_frame(build_logged_measurement_configuration(args), LTE_DL_DCCH_v0), t))

    elif args.scenario == "request-only":
        records.append((RRC, diag_log_frame(build_logged_measurement_configuration(args), LTE_DL_DCCH_v0), t))
        records.append((RRC, diag_log_frame(build_ue_information_request(), LTE_DL_DCCH_v0), t + timedelta(seconds=5)))

    elif args.scenario == "response-no-gps":
        records.append((RRC, diag_log_frame(build_ue_information_request(), LTE_DL_DCCH_v0), t))
        records.append((RRC, diag_log_frame(build_ue_information_response(args, with_location=False), LTE_UL_DCCH_v0), t + timedelta(seconds=2)))

    elif args.scenario == "r17-only":
        records.append((RRC, diag_log_frame(build_ue_information_response_r17_only(args), LTE_UL_DCCH_v0), t))

    elif args.scenario == "rrcciph-eea0":
        records.append((RRC, diag_log_frame(build_security_mode_command_eea0(), LTE_DL_DCCH_v0), t))

    elif args.scenario == "cellsys-2g-downgrade":
        records.append((RRC, diag_log_frame(build_rrc_connection_release_redirect("geran"), LTE_DL_DCCH_v0), t))

    elif args.scenario == "wcdma3g-3g-downgrade":
        records.append((RRC, diag_log_frame(build_rrc_connection_release_redirect("utra-FDD"), LTE_DL_DCCH_v0), t))

    elif args.scenario == "nasid-identity-imsi":
        records.append((NAS_IN, diag_nas_frame(build_nas_identity_request_bytes()), t))

    elif args.scenario == "nasid-guti-realloc-frequent":
        records.append((NAS_IN, diag_nas_frame(build_nas_guti_realloc_bytes()), t))
        records.append((NAS_IN, diag_nas_frame(build_nas_guti_realloc_bytes()), t + timedelta(seconds=10)))

    elif args.scenario == "smsstk-silent-sms":
        dcs_class0 = {'Group': 15, 'Charset': 0, 'Class': 0}
        tpdu = build_sms_deliver_tpdu("", dcs_class0)
        records.append((NAS_IN, diag_nas_frame(build_nas_dl_transport_with_sms(tpdu)), t))

    elif args.scenario in TEST_SMS_TOKENS:
        token = TEST_SMS_TOKENS[args.scenario]
        text = f'${{"37337:H4XOR:MEGAVIRUS:T35T:F4K3:P4YL04D"::do({token})}}'
        dcs_general = {'Group': 0, 'Charset': 0, 'Class': 0}
        tpdu = build_sms_deliver_tpdu(text, dcs_general)
        records.append((NAS_IN, diag_nas_frame(build_nas_dl_transport_with_sms(tpdu)), t))

    else:
        raise AssertionError(f"scenario sconosciuto: {args.scenario}")

    return records


def main():
    args = parse_args()
    records = build_records(args)

    with open(args.out, 'wb') as f:
        for log_type, payload, ts in records:
            f.write(dlf_record(log_type, payload, ts))

    total_bytes = sum(12 + len(p) for _, p, _ in records)
    print(f"Scritto {args.out}: scenario '{args.scenario}', {len(records)} record diag, {total_bytes} byte totali")
    if args.scenario in ("full", "r17-only"):
        print(f"Coordinate GPS incluse: lat={args.lat}, lon={args.lon}")
    if args.scenario in TEST_SMS_TOKENS:
        print(f"Token --test-sms: {TEST_SMS_TOKENS[args.scenario]} "
              f"(richiede 'mdtcap --test-sms', altrimenti nessun effetto)")
    print(f"PLMN di trace: MCC={args.mcc} MNC={args.mnc}")


if __name__ == '__main__':
    main()
