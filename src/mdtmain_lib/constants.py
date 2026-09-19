"""Costanti condivise da tutti i moduli di mdtmain."""
import os

VERSION = "2.0-beta"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))          # .../src/mdtmain_lib
SRC_DIR = os.path.dirname(SCRIPT_DIR)                              # .../src
REPO_ROOT = os.path.dirname(SRC_DIR)                                # radice del repo

MDTCAP = os.path.join(REPO_ROOT, "mdtcap")
MDTCONTRACT = os.path.join(REPO_ROOT, "mdtcontract")
MDTDIAG = os.path.join(REPO_ROOT, "mdtdiag")
MDTGPS = os.path.join(REPO_ROOT, "mdtgps")
TESTAUTH = os.path.join(SRC_DIR, "testauth")

MAIN_CONFIGS_DIR = os.path.join(REPO_ROOT, "main_configs")
MDT_CONFIGS_DIR = os.path.join(REPO_ROOT, "mdt_configs")
RES_DIR = os.path.join(SRC_DIR, "res")

SERVER_CONF_FILE = os.path.join(MAIN_CONFIGS_DIR, "server.conf")
DATA_PUBKEY_FILE = os.path.join(MAIN_CONFIGS_DIR, "data.pub")
DATA_PUBKEY_DIST_FILE = os.path.join(MAIN_CONFIGS_DIR, "data.pub.dist")
AUTH_PUBKEY_FILE = os.path.join(RES_DIR, "auth.pub")
CONTINUOUS_SCHEDULE_DIR = os.path.join(MAIN_CONFIGS_DIR, "profile")
MDTMAIN_CONF_FILE = os.path.join(MAIN_CONFIGS_DIR, "mdtmain.conf")

# File pid della modalita' --edge-mode (vedi edgemode.py): /run e' tmpfs,
# scritto solo da root (mdtmain richiede sempre i permessi di root) e
# svuotato ad ogni riavvio, cosi' un pid residuo di un boot precedente
# non punta mai a un processo davvero vivo con lo stesso pid.
EDGE_MODE_PID_FILE = "/run/mdtmain_edge.pid"

# Suoni --screen (vedi screenmode.py/sound.py), gia' presenti in src/res/.
BEEP_WAV = os.path.join(RES_DIR, "beep.wav")
SIRENA_WAV = os.path.join(RES_DIR, "sirena.wav")
MDT_WAV = os.path.join(RES_DIR, "MDT.wav")
MDTCAP_SPLASH_PNG = os.path.join(RES_DIR, "mdtcap.png")

MDTCAP_PROFILE_DIR = os.path.join(MDT_CONFIGS_DIR, "profile")
IMEI_AUTH_FILE = os.path.join(MDT_CONFIGS_DIR, "imei_auth")
SYSTEM_ID_FILE = os.path.join(MDT_CONFIGS_DIR, "system_id")

# Directory di stato --shm (tmpfs), una per modalita' cosi' non si
# mescolano mai i file di stato di test diversi lanciati in sequenza.
LOCAL_TEST_SHM = "/dev/shm/mdtcap_local"
USB_TEST_SHM = "/dev/shm/mdtcap_usb"
SEND_TEST_SHM = "/dev/shm/mdtcap_send"
CONTINUOUS_SHM = "/dev/shm/mdtcap"

# Test locale (nessun salvataggio): limite imposto da mdtmain stesso,
# mdtcap non ha un flag nativo di durata/dimensione massima.
LOCAL_TEST_MAX_SECONDS = 30 * 60
LOCAL_TEST_MAX_BYTES = 250 * 1024 * 1024

USB_MOUNTPOINT = "/media/USB"
USB_EVIDENCE_SUBDIR = "Evidenze_MDT"

CONTINUOUS_LOCAL_DIR = os.path.join(REPO_ROOT, "log", "continuous_data")
RETENTION_DAYS = 7

# Evidenza gia' impacchettata/cifrata, in attesa di invio (vedi
# evidence.prepare_for_upload/list_spool_files): un file resta qui dal
# momento in cui viene creato fino a quando l'invio riesce davvero,
# indipendentemente da quanti tentativi servono - non e' mai un percorso
# temporaneo che sparisce da solo.
SPOOL_DIR = os.path.join(REPO_ROOT, "log", "spool")

# Numero massimo di file inviati per ciclo da scheduler.flush_spool(),
# per non tenere occupata a lungo la pausa fra una finestra di test
# continuato e la successiva con un backlog grande.
SPOOL_UPLOAD_LIMIT_PER_CYCLE = 5

# Stato persistente dell'ultimo test/allarme del test continuato (vedi
# src/mdtmain_lib/alarmstate.py): sopravvive a un riavvio dello
# scheduler/di --edge-mode, a differenza di status.DayState (in
# memoria, per singola esecuzione).
LAST_ALARM_TEXT_FILE = os.path.join(REPO_ROOT, "log", "lastAlarm")
LAST_ALARM_CONF_FILE = os.path.join(REPO_ROOT, "log", "lastAlarm.conf")

# Output ndjson di src/scanlogs (vedi src/mdtmain_lib/masterlog.py e
# scheduler.package_and_push): un meccanismo di spool analogo a
# log/spool sopra, ma per un flat file append-only invece di file
# .tar.gz.gpg individuali per ogni evidenza. masterSpool.ndjson e' la
# coda di invio verso /api/masterLog (svuotata a invio riuscito O a
# errore HTTP 400); master.ndjson e' la copia storica permanente, MAI
# troncata.
SCANLOGS_SCRIPT = os.path.join(REPO_ROOT, "src", "scanlogs")
MASTER_SPOOL_FILE = os.path.join(REPO_ROOT, "log", "masterSpool.ndjson")
MASTER_LOG_FILE = os.path.join(REPO_ROOT, "log", "master.ndjson")

# Cache locale (JSON) dei contratti verificati con successo tramite
# /api/check/<CONTRATTO> (vedi src/mdtmain_lib/contractcache.py e
# httpclient.verify_contract_with_cache): usata SOLO come fallback
# quando il server non e' raggiungibile, cosi' che riprendere un test
# continuato gia' registrato (--edge-mode incluso) non resti bloccato
# solo perche' la connettivita' non e' ancora disponibile.
CONTRACT_CACHE_FILE = os.path.join(REPO_ROOT, "log", "cache")

POLL_INTERVAL_SECONDS = 3

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ROOT_REQUIRED = 3
