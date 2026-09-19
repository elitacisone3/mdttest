"""Configurazione di mdtmain (main_configs/mdtmain.conf, formato
key=value, una chiave per riga — stesso stile di main_configs/server.conf).

Parametri (con i default usati quando il file manca o una chiave e'
assente/non valida):
  disableNet    0/1  Disabilita la sezione impostazioni di rete (salvo
                     con --net-menu, che la mostra comunque).
  minAlarmHour  0-23 Ora di inizio della finestra in cui dare l'allarme.
  maxAlarmHour  0-23 Ora di fine della finestra in cui dare l'allarme.
  disableIMEI   0/1  Disabilita la richiesta di cambio IMEI nel test
                     continuo (anche se un'autorizzazione e' presente).
  disableAlarm  0/1  Disabilita gli allarmi (sirena.wav in --screen).
  autoStart     0/1  Con --auto-start, avvia direttamente il test
                     continuato configurato (testSim non vuoto).
  testPin       str  PIN della SIM del test continuato configurato.
  testSim       str  ICCID della SIM del test continuato configurato.
  mdtcapProfile str  Profilo mdtcap del test continuato configurato
                     (mdt_configs/profile/<nome>.conf).
  schedulerProfile str  Schedulazione del test continuato configurato
                     (main_configs/profile/<nome>.conf). Insieme a
                     testPin/testSim/mdtcapProfile, permette a
                     --edge-mode/--auto-start/"Riprendi test continuo"
                     di avviare il test continuato senza richiedere
                     PIN/profilo/schedulazione (vedi mdtmain --help):
                     salvati da "Imposta test continuato", vanno
                     configurati li' almeno una volta.
  hdmi          0/1  0 = audio su Headphones, 1 = audio su HDMI.
  doGPSFix      0/1  Prima di qualunque test, attende un fix GPS
                     (mdtgps in background, GPS lasciato acceso) cosi'
                     il test parte gia' con un fix "caldo".
  forceExtended 0/1  Forza i controlli extra su mdtcap (aggiunge
                     --extended a ogni test), anche se il profilo/la
                     schedulazione usata non lo prevede gia' da solo.
  testSMS       0/1  Modalita' test SMS: aggiunge --test-sms a ogni
                     invocazione di mdtcap (implica --extended da solo,
                     vedi src/extra_scan:detect_test_sms_trigger e
                     mdtcap --help), usare SOLO per verificare la catena
                     di rilevamento con l'SMS di test, mai in un test
                     reale (default 0).
  alarmCheckPoint 0/1  Abilita la sirena per il comando CHECKPOINT
                     dello scheduler (vedi main_configs/profile/,
                     src/mdtmain_lib/scheduler.py) — se 0, ogni riga
                     CHECKPOINT e' completamente inerte.
  disableSend   0/1  Default 1 (invio disattivato di default): disabilita
                     "Esegui un test inviando i dati"/"Imposta test
                     continuato" (menu principale), le uniche due
                     modalita' che parlano con un server. Impostarlo a 1
                     dalla schermata Impostazioni cancella anche
                     testPin/testSim, cosi' un test continuato gia'
                     configurato non puo' piu' ripartire da solo (vedi
                     app.screen_settings).
  startDisclaim 0/1  Default 0: diventa 1 la prima volta che mdtmain
                     mostra il disclaimer generale all'avvio (vedi
                     app.run_app) - "hai gia' accettato", non si ripete.
  dataDisclaim  0/1  Default 0: diventa 1 la prima volta che si abilita
                     l'invio dati dalla schermata Impostazioni e ne
                     compare il disclaimer dedicato (vedi
                     app.screen_settings) - "hai gia' accettato", non si
                     ripete.
  autoConfig    0/1  Default 0. Se 1, confronta ad ogni avvio l'id
                     hardware del device con quello salvato in
                     mdt_configs/system_id (vedi
                     src/mdtmain_lib/autoconfig.py): se diverso (o il
                     file manca), lo aggiorna e forza disableSend=1,
                     startDisclaim=0, dataDisclaim=0 — pensato per una
                     scheda SD/immagine clonata su un altro device. Se
                     0, mdt_configs/system_id viene svuotato (se non lo
                     e' gia') e la configurazione non viene toccata.
"""
import os

from . import constants

DEFAULTS = {
    "disableNet": "0",
    "minAlarmHour": "10",
    "maxAlarmHour": "23",
    "disableIMEI": "0",
    "disableAlarm": "0",
    "autoStart": "1",
    "testPin": "",
    "testSim": "",
    "mdtcapProfile": "",
    "schedulerProfile": "",
    "hdmi": "1",
    "doGPSFix": "0",
    "forceExtended": "0",
    "testSMS": "0",
    "alarmCheckPoint": "1",
    "disableSend": "1",
    "startDisclaim": "0",
    "dataDisclaim": "0",
    "autoConfig": "0",
}

_BOOL_KEYS = {"disableNet", "disableIMEI", "disableAlarm", "autoStart", "hdmi", "doGPSFix",
              "forceExtended", "testSMS", "alarmCheckPoint",
              "disableSend", "startDisclaim", "dataDisclaim", "autoConfig"}
_HOUR_KEYS = {"minAlarmHour", "maxAlarmHour"}


def _parse_kv(path):
    values = {}
    if not os.path.isfile(path):
        return values
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def load():
    """Ritorna un dict con TUTTE le chiavi di DEFAULTS sempre presenti
    (valore del file se valido, altrimenti il default)."""
    raw = _parse_kv(constants.MDTMAIN_CONF_FILE)
    result = dict(DEFAULTS)
    for key in DEFAULTS:
        if key not in raw:
            continue
        value = raw[key]
        if key in _BOOL_KEYS:
            result[key] = "1" if value == "1" else "0"
        elif key in _HOUR_KEYS:
            try:
                hour = int(value)
            except ValueError:
                continue
            if 0 <= hour <= 23:
                result[key] = str(hour)
        else:
            result[key] = value
    return result


def save(config):
    """Riscrive per intero main_configs/mdtmain.conf (crea la directory
    se serve), nell'ordine di DEFAULTS — solo le chiavi note vengono
    scritte, cosi' il file resta sempre valido anche se 'config' contiene
    altro."""
    os.makedirs(os.path.dirname(constants.MDTMAIN_CONF_FILE), exist_ok=True)
    lines = [
        "# File di configurazione mdtmain (key=value) — generato/aggiornato",
        "# automaticamente da mdtmain (schermata Impostazioni, test continuato).",
        "# Righe vuote o che iniziano con '#' vengono ignorate.",
        "",
    ]
    for key in DEFAULTS:
        lines.append(f"{key}={config.get(key, DEFAULTS[key])}")
    with open(constants.MDTMAIN_CONF_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")


def update(**kwargs):
    """Legge la configurazione attuale, aggiorna una o piu' chiavi (deve
    trattarsi di chiavi note, vedi DEFAULTS) e la riscrive. Ritorna la
    configurazione aggiornata."""
    for key in kwargs:
        if key not in DEFAULTS:
            raise KeyError(f"parametro mdtmain.conf sconosciuto: {key}")
    config = load()
    config.update({k: str(v) for k, v in kwargs.items()})
    save(config)
    return config


def get_bool(config, key):
    return config.get(key, DEFAULTS[key]) == "1"


def get_hour(config, key):
    try:
        return int(config.get(key, DEFAULTS[key]))
    except (TypeError, ValueError):
        return int(DEFAULTS[key])


def apply_forced_extended(args, config=None):
    """Aggiunge "--extended" ad args (in place) se forceExtended=1,
    salvo che non sia gia' presente (es. gia' incluso da un --profile
    mdtcap o da una riga di schedulazione del test continuo). config
    facoltativo, per evitare una load() ripetuta a chi lo ha gia'
    caricato. Ritorna args, per comodita' nelle chiamate."""
    config = config if config is not None else load()
    if get_bool(config, "forceExtended") and "--extended" not in args:
        args.append("--extended")
    return args


def apply_test_sms(args, config=None):
    """Come apply_forced_extended sopra, ma per testSMS=1 -> "--test-sms"
    (mdtcap --test-sms implica gia' da solo --extended, non serve
    aggiungerlo qui separatamente, vedi src/extra_scan
    detect_test_sms_trigger/mdtcap --help)."""
    config = config if config is not None else load()
    if get_bool(config, "testSMS") and "--test-sms" not in args:
        args.append("--test-sms")
    return args
