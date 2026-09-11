#!/usr/bin/env bash
#
# install.sh — verifica e installa le dipendenze di mdtcap
#
# Uso:
#   sudo ./install.sh
#   sudo ./install.sh --configure-system [--diag-port DEV --at-port DEV] [--qcsuper PATH] \
#       [--usb-modem-vid VID --usb-modem-pid PID]
#   sudo ./install.sh --fix-tui
#   sudo ./install.sh --setup-mdtmain
#
# Cosa fa (sempre):
#   - verifica python3, pip3, tshark, qcsuper, dialog/pythondialog
#     (richiesti da mdtmain, l'interfaccia guidata in stile raspi-config),
#     e alcuni comandi di base (udevadm, sha256sum, stty, date, timeout)
#     gia' richiesti da mdtcap, piu' openssl con supporto RIPEMD-160
#     (richiesto da mdtcontract per il contractId, vedi manifest.json in
#     mdtcap);
#   - installa quelli mancanti che si possono installare (python3, pip3,
#     tshark, dialog via apt; qcsuper, pythondialog via pip);
#   - rende eseguibili mdtcap/mdtgps/mdtdiag/mdtimei/mdtcontract/mdtmain e
#     src/decode_mdt_location.py/src/mdt_bitscan.py/src/testauth/
#     src/extra_scan;
#   - stampa un riepilogo finale con quello che resta da fare a mano
#     (es. collegare il modulo USB, verificare il PIN della SIM).
#
# --configure-system: genera/aggiorna mdt_configs/system.conf, il file di
#   configurazione mdtcap con i soli parametri di SISTEMA (porta o
#   --autodetect, --qcsuper) — letto automaticamente da mdtcap ad ogni
#   esecuzione con la precedenza piu' bassa (system.conf < --op <
#   --profile < --config < riga di comando), cosi' non serve ripetere
#   --autodetect/--qcsuper su ogni test. Facoltativo di proposito (non
#   viene mai generato/toccato senza questo flag esplicito): evita che un
#   semplice controllo delle dipendenze sovrascriva una configurazione di
#   sistema gia' regolata a mano. Rigenera il file per intero ad ogni uso
#   (non aggiungere altro li' dentro oltre a porte/autodetect/qcsuper,
#   andrebbe perso al prossimo --configure-system). Tenta anche (best
#   effort, non bloccante) il backup dell'IMEI originale del modulo in
#   mdt_configs/imei, se non esiste gia': serve da riferimento per poter
#   tornare all'IMEI originale dopo un cambio con mdtimei (vedi mdtimei
#   --help), che non ripristina da solo.
#
# --diag-port DEV / --at-port DEV: da passare INSIEME (o nessuno dei due)
#   con --configure-system, per scrivere porte fisse invece di
#   --autodetect (default se nessuno dei due e' specificato). Individuarle
#   prima con "sudo ./mdtcap --list-ports".
#
# --qcsuper PATH: forza il percorso di qcsuper scritto in system.conf,
#   invece di quello rilevato automaticamente da questo script (utile se
#   qcsuper e' uno script .py invece che l'eseguibile installato da pip).
#
# --usb-modem-vid VID / --usb-modem-pid PID: forzano il VID/PID USB (4
#   cifre esadecimali ciascuno, es. "1e0e"/"9000") scritti in system.conf
#   come "--usb-modem-vid"/"--usb-modem-pid", invece di quelli rilevati
#   automaticamente da questo script interrogando via udevadm la prima
#   porta ttyUSB* il cui ID_VENDOR contiene "SimTech" (stesso filtro gia'
#   usato dal backup IMEI piu' sotto). Servono a mdtcap SOLO se lanciato
#   con --usb-modem (facoltativo, vedi mdtcap --help): in quel caso,
#   invece di passare a qcsuper il device path (--diag-port, che con
#   qcsuper --usb-modem fa leggere la porta seriale un BYTE alla volta
#   via pyserial — vedi usb_modem_pyserial.py, read_loop()), mdtcap passa
#   "VID:PID" (formato gia' supportato nativamente da qcsuper --usb-modem,
#   vedi il suo --help), che instrada invece su pyusb/libusb con letture a
#   blocchi (wMaxPacketSize, tipicamente 512 byte) — un percorso diverso
#   nello stesso qcsuper, non qualcosa che questo progetto implementa.
#   VERIFICATO sul campo (due catture LTE reali da ~200s su Vodafone
#   Italia, stesso SIM7600E-H): risultato OPPOSTO all'ipotesi iniziale —
#   --usb-modem non riduce gli avvisi "Wrong CRC" di qcsuper (vedi
#   "Warning diag port" in mdtcap --help), li aumenta (0 in modalita' path
#   contro 962 con --usb-modem), ma cattura anche ~8.5 volte piu' dati
#   grezzi e porta a casa piu' del doppio dei frame LTE-RRC validi (39
#   contro 15): la modalita' path a lettura byte-a-byte sembra perdere
#   molto piu' traffico ancora piu' a monte, in modo silenzioso. ATTENZIONE:
#   durante quel test la macchina risultava in undervoltage permanente
#   (vcgencmd get_throttled), un fattore di confondimento reale — vedi
#   mdtcap --help per i dettagli completi prima di trarre conclusioni.
#   Rilevamento e scrittura in system.conf sono best-effort e non
#   bloccanti come il resto di --configure-system: se non si riesce a
#   determinarli, --usb-modem-vid/--usb-modem-pid restano assenti da
#   system.conf (mdtcap si ferma con un errore chiaro se lanciato con
#   --usb-modem in quel caso, non silenziosamente in modalita' path).
#
# --fix-tui: verifica e corregge (solo se serve, idempotente) le
#   impostazioni di sistema che fanno disegnare correttamente i caratteri
#   grafici (bordi ecc., tipo "┌┬┐╔╦╗█▄▒▀") a TUTTE le TUI ncurses della
#   macchina: dialog/pythondialog (usato da mdtmain, l'interfaccia guidata
#   in stile raspi-config) e pinentry-curses (inserimento passphrase
#   gpg). Senza la variabile d'ambiente NCURSES_NO_UTF8_ACS=1, ncurses
#   prova a disegnare i bordi passando per l'"alternate character set"
#   VT100 invece di scrivere direttamente i byte UTF-8, e se quel
#   passaggio fallisce (capita spesso a seconda di terminale/emulatore/
#   sessione) stampa le lettere ASCII grezze usate internamente da quella
#   mappatura (es. "lqqqqk" invece di "┌────┐"). Verificato sul campo
#   catturando byte per byte l'output di "dialog": senza la variabile ->
#   lettere; con NCURSES_NO_UTF8_ACS=1 -> box-drawing UTF-8 corretto. Non
#   serve invece per whiptail (usato da raspi-config): si appoggia a
#   newt/slang, non a ncurses, e disegna gia' correttamente se il locale
#   e' UTF-8 (verificato anch'esso allo stesso modo) — la variabile non
#   gli fa comunque alcun danno.
#   Impostazioni pure (nessun software toccato), scritte solo se non gia'
#   presenti/corrette:
#     - NCURSES_NO_UTF8_ACS=1 in /etc/environment (letto da PAM per le
#       sessioni SSH/login/su);
#     - lo stesso in /etc/environment.d/99-ncurses-utf8.conf (letto da
#       systemd --user — copre gpg-agent.service, che lancia
#       pinentry-curses);
#     - "Defaults env_keep += NCURSES_NO_UTF8_ACS" in un file dedicato
#       sotto /etc/sudoers.d/ (validato con "visudo -c" PRIMA di
#       installarlo, e l'intero /etc/sudoers viene rivalidato subito
#       dopo — ritirato immediatamente se la validazione fallisce, per
#       non rischiare di rompere sudo): senza questo, "sudo raspi-config"/
#       "sudo ./mdtmain"/ecc. perderebbero comunque la variabile anche
#       partendo da una sessione di login che gia' la eredita
#       correttamente — lo stack PAM di sudo (common-session-
#       noninteractive) non include pam_env, e "env_reset" (attivo in
#       /etc/sudoers) scarta tutto cio' che non e' in env_keep.
#       VERIFICATO sul campo (sessione fresca via "su -l" poi "sudo"):
#       senza questa riga "sudo env" non mostra la variabile, con questa
#       si'. Se visudo non e' installato, questo pezzo viene saltato
#       (segnalato "da sistemare a mano") invece di rischiare di
#       scrivere sudoers senza poterlo validare;
#   e la applica subito (best-effort, non bloccante) alla sessione
#   systemd --user gia' attiva con "systemctl --user set-environment",
#   cosi' non serve nemmeno riavviare gpg-agent perche' la veda. Verifica
#   anche (solo avviso, non lo modifica: troppo invasivo per un flag
#   pensato per la grafica) che il locale sia UTF-8 (LANG/LC_ALL), dato
#   che sia dialog/ncurses sia whiptail/newt ne hanno comunque bisogno a
#   monte. Le sessioni SSH/terminale gia' aperte vanno richiuse e
#   riaperte per ereditare la modifica (un riavvio completo non serve).
#
# --setup-mdtmain: verifica e installa (idempotente, come il resto dello
#   script) quanto serve specificamente per mdtmain in modalita' --screen
#   (schermo/tastiera fisici invece del terminale di lancio, vedi
#   mdtmain --help): "fbi" (immagine di presentazione a schermo intero),
#   "alsa-utils" (comandi "aplay"/"amixer" per i suoni di avviso e per
#   instradare l'audio HDMI/Headphones) via apt se mancanti; verifica
#   inoltre (senza installare, essendo gia' parte dell'immagine di base
#   in uso) che i font console "Uni2-VGA16"/"Uni2-VGA8" richiesti da
#   --screen siano presenti (pacchetto "console-setup"), segnalando "da
#   sistemare a mano" se assenti. Applica anche TUTTO cio' che farebbe
#   --fix-tui (vedi sopra: senza, i pallini/le cornici della TUI
#   comparirebbero come lettere anche in modalita' --screen) — non serve
#   quindi passare entrambi i flag insieme, uno vale per l'altro.

set -uo pipefail
# NB: niente "set -e" qui di proposito. Questo script deve continuare a
# controllare/segnalare TUTTE le dipendenze anche se una singola
# installazione fallisce, per dare un riepilogo completo a fine corsa
# invece di fermarsi al primo problema.

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
MISSING_MANUAL=()   # cose non installabili automaticamente, da segnalare
INSTALLED=()        # cose installate con successo in questa esecuzione
FAILED=()           # tentativi di installazione falliti

say() { echo "[install.sh] $*"; }

usage() {
    # Range dinamico (non piu' un numero di riga fisso, che si era gia'
    # disallineato in passato quando il blocco di commenti in testa e'
    # cresciuto): si ferma da solo prima di "set -uo pipefail", stesso
    # approccio di mdtcap/mdtgps/mdtdiag/mdtimei.
    sed -n '3,/^set -uo pipefail/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
    exit 1
}

# ---- parsing argomenti ------------------------------------------------------

CONFIGURE_SYSTEM=0
FIX_TUI=0
SETUP_MDTMAIN=0
SYS_DIAG_PORT=""
SYS_AT_PORT=""
SYS_QCSUPER=""
SYS_USB_VID=""
SYS_USB_PID=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --configure-system) CONFIGURE_SYSTEM=1; shift ;;
        --fix-tui) FIX_TUI=1; shift ;;
        --setup-mdtmain) SETUP_MDTMAIN=1; shift ;;
        --diag-port) SYS_DIAG_PORT="$2"; shift 2 ;;
        --at-port) SYS_AT_PORT="$2"; shift 2 ;;
        --qcsuper) SYS_QCSUPER="$2"; shift 2 ;;
        --usb-modem-vid) SYS_USB_VID="$2"; shift 2 ;;
        --usb-modem-pid) SYS_USB_PID="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "[install.sh] Argomento sconosciuto: $1" >&2; usage ;;
    esac
done

if [[ ( -n "$SYS_DIAG_PORT" && -z "$SYS_AT_PORT" ) || ( -z "$SYS_DIAG_PORT" && -n "$SYS_AT_PORT" ) ]]; then
    echo "[install.sh] --diag-port e --at-port vanno passati insieme (o nessuno dei due, per --autodetect)." >&2
    exit 1
fi

if [[ ( -n "$SYS_USB_VID" && -z "$SYS_USB_PID" ) || ( -z "$SYS_USB_VID" && -n "$SYS_USB_PID" ) ]]; then
    echo "[install.sh] --usb-modem-vid e --usb-modem-pid vanno passati insieme (o nessuno dei due, per il rilevamento automatico)." >&2
    exit 1
fi
for v in "$SYS_USB_VID" "$SYS_USB_PID"; do
    [[ -z "$v" || "$v" =~ ^[0-9a-fA-F]{4}$ ]] || {
        echo "[install.sh] --usb-modem-vid/--usb-modem-pid vogliono 4 cifre esadecimali ciascuno (es. 1e0e/9000), ricevuto: '$v'." >&2
        exit 1
    }
done

# ---- root -----------------------------------------------------------------

if [[ $EUID -ne 0 ]]; then
    echo "[install.sh] Esegui come root (serve per apt/pip system-wide): sudo ./install.sh" >&2
    exit 1
fi

# ---- apt update una sola volta, solo se serve ------------------------------

APT_UPDATED=0
apt_update_once() {
    if [[ "$APT_UPDATED" -eq 0 ]]; then
        say "Aggiornamento indice pacchetti apt..."
        apt-get update -qq && APT_UPDATED=1
    fi
}

# ---- python3 ----------------------------------------------------------------

if command -v python3 >/dev/null 2>&1; then
    say "python3: OK ($(python3 --version 2>&1))"
else
    say "python3 non trovato, installo..."
    apt_update_once
    if apt-get install -y python3 >/dev/null; then
        INSTALLED+=("python3")
        say "python3 installato."
    else
        FAILED+=("python3")
        say "ATTENZIONE: installazione di python3 fallita."
    fi
fi

# ---- pip3 ---------------------------------------------------------------

if command -v pip3 >/dev/null 2>&1; then
    say "pip3: OK ($(pip3 --version 2>&1 | cut -d' ' -f1-2))"
else
    say "pip3 non trovato, installo..."
    apt_update_once
    if apt-get install -y python3-pip >/dev/null; then
        INSTALLED+=("python3-pip")
        say "pip3 installato."
    else
        FAILED+=("python3-pip")
        say "ATTENZIONE: installazione di pip3 fallita."
    fi
fi

# ---- qcsuper --------------------------------------------------------------
# Richiesto per la cattura Diag/RRC vera e propria (--qcsuper). Si
# installa via pip perche' non e' pacchettizzato per apt.

if command -v qcsuper >/dev/null 2>&1; then
    QCSUPER_VER=$(pip3 show qcsuper 2>/dev/null | sed -n 's/^Version: //p')
    say "qcsuper: OK ($(command -v qcsuper), versione ${QCSUPER_VER:-sconosciuta})"
elif command -v pip3 >/dev/null 2>&1; then
    say "qcsuper non trovato, installo con pip3 (potrebbe richiedere qualche minuto: compila pycrate)..."
    # --break-system-packages: necessario su Debian/Ubuntu recenti (PEP 668,
    # "externally-managed-environment"), qcsuper non e' nei repository apt.
    if pip3 install --upgrade qcsuper --break-system-packages >/dev/null 2>&1; then
        INSTALLED+=("qcsuper")
        say "qcsuper installato: $(command -v qcsuper 2>/dev/null || echo 'vedi PATH, potrebbe servire un nuovo terminale')"
    else
        FAILED+=("qcsuper")
        say "ATTENZIONE: installazione di qcsuper fallita. Riprova a mano con:"
        say "  pip3 install --upgrade qcsuper --break-system-packages"
    fi
else
    MISSING_MANUAL+=("qcsuper (richiede pip3, non disponibile)")
fi

# ---- tshark (opzionale ma consigliato) -------------------------------------
# Senza tshark mdtcap cattura comunque, ma non produce i report MDT/RRC
# derivati (report_mdt_rrc.txt, mdt_location_requests*, --report,
# --parla-chiaro, coordinate decodificate).

if command -v tshark >/dev/null 2>&1; then
    say "tshark: OK ($(tshark --version 2>&1 | grep -m1 '^TShark'))"
else
    say "tshark non trovato (opzionale ma fortemente consigliato: senza, niente report MDT), installo..."
    apt_update_once
    if DEBIAN_FRONTEND=noninteractive apt-get install -y tshark >/dev/null; then
        INSTALLED+=("tshark")
        say "tshark installato."
    else
        FAILED+=("tshark")
        say "ATTENZIONE: installazione di tshark fallita. Riprova a mano con: apt-get install tshark"
    fi
fi

# ---- dialog / pythondialog (richiesti da mdtmain) --------------------------
# "dialog" e' il binario di sistema (dialog(1)) che disegna i menu;
# "pythondialog" e' il pacchetto pip che lo pilota (import Python: "dialog",
# da non confondere con un ipotetico pacchetto pip chiamato semplicemente
# "dialog", che e' un'altra cosa).

if command -v dialog >/dev/null 2>&1; then
    say "dialog: OK ($(dialog --version 2>&1 | head -1))"
else
    say "dialog non trovato, installo..."
    apt_update_once
    if apt-get install -y dialog >/dev/null; then
        INSTALLED+=("dialog")
        say "dialog installato."
    else
        FAILED+=("dialog")
        say "ATTENZIONE: installazione di dialog fallita. Riprova a mano con: apt-get install dialog"
    fi
fi

if python3 -c "import dialog" >/dev/null 2>&1; then
    say "pythondialog: OK"
elif command -v pip3 >/dev/null 2>&1; then
    say "pythondialog non trovato, installo con pip3..."
    if pip3 install pythondialog --break-system-packages >/dev/null 2>&1; then
        INSTALLED+=("pythondialog")
        say "pythondialog installato."
    else
        FAILED+=("pythondialog")
        say "ATTENZIONE: installazione di pythondialog fallita. Riprova a mano con:"
        say "  pip3 install pythondialog --break-system-packages"
    fi
else
    MISSING_MANUAL+=("pythondialog (richiede pip3, non disponibile)")
fi

# ---- comandi di base gia' attesi sul sistema -------------------------------
# Praticamente sempre presenti su una Debian/Raspberry Pi OS di base:
# verifichiamo solo, non li installiamo (rimuovere/reinstallare pacchetti
# di sistema come udev/coreutils non e' compito di questo script).

for cmd in udevadm sha256sum stty date timeout; do
    if command -v "$cmd" >/dev/null 2>&1; then
        say "$cmd: OK"
    else
        MISSING_MANUAL+=("$cmd")
        say "ATTENZIONE: comando '$cmd' non trovato (di norma incluso in udev/coreutils)."
    fi
done

# ---- openssl (richiesto da mdtcontract, per l'hash RIPEMD-160 del
# contractId — vedi mdtcontract --help e il campo "contractId" di
# manifest.json in mdtcap) -----------------------------------------------
# Non basta che "openssl" sia installato: alcune distribuzioni (OpenSSL
# 3.x senza il "legacy provider" abilitato) non registrano l'algoritmo
# RIPEMD-160, che "openssl dgst -rmd160" userebbe silenziosamente
# fallendo solo all'uso vero e proprio — verifichiamo quindi anche che
# funzioni davvero, non solo che il comando esista.
if command -v openssl >/dev/null 2>&1; then
    if printf '' | openssl dgst -rmd160 >/dev/null 2>&1; then
        say "openssl (RIPEMD-160): OK"
    else
        MISSING_MANUAL+=("openssl con supporto RIPEMD-160 (algoritmo non registrato — su OpenSSL 3.x puo' servire abilitare il 'legacy provider')")
        say "ATTENZIONE: openssl e' installato ma 'openssl dgst -rmd160' fallisce: mdtcontract non potra' calcolare il contractId."
    fi
else
    MISSING_MANUAL+=("openssl")
    say "ATTENZIONE: comando 'openssl' non trovato (richiesto da mdtcontract per il contractId)."
fi

# ---- permessi di esecuzione -------------------------------------------------

for script in mdtcap mdtgps mdtdiag mdtimei mdtcontract mdtmain; do
    if [[ -f "$SCRIPT_DIR/$script" ]]; then
        chmod +x "$SCRIPT_DIR/$script" 2>/dev/null && say "$script: eseguibile."
    fi
done
[[ -f "$SCRIPT_DIR/src/decode_mdt_location.py" ]] && \
    chmod +x "$SCRIPT_DIR/src/decode_mdt_location.py" 2>/dev/null && \
    say "src/decode_mdt_location.py: eseguibile."
[[ -f "$SCRIPT_DIR/src/mdt_bitscan.py" ]] && \
    chmod +x "$SCRIPT_DIR/src/mdt_bitscan.py" 2>/dev/null && \
    say "src/mdt_bitscan.py: eseguibile."
[[ -f "$SCRIPT_DIR/src/testauth" ]] && \
    chmod +x "$SCRIPT_DIR/src/testauth" 2>/dev/null && \
    say "src/testauth: eseguibile."
[[ -f "$SCRIPT_DIR/src/extra_scan" ]] && \
    chmod +x "$SCRIPT_DIR/src/extra_scan" 2>/dev/null && \
    say "src/extra_scan: eseguibile."

# ---- --configure-system: genera/aggiorna mdt_configs/system.conf ----------
# Facoltativo (vedi commento in testa al file): non tocca mai
# mdt_configs/system.conf a meno che l'utente non lo chieda esplicitamente.

if [[ "$CONFIGURE_SYSTEM" -eq 1 ]]; then
    SYSTEM_CONF_DIR="$SCRIPT_DIR/mdt_configs"
    SYSTEM_CONF="$SYSTEM_CONF_DIR/system.conf"
    mkdir -p "$SYSTEM_CONF_DIR"

    QCSUPER_PATH="$SYS_QCSUPER"
    if [[ -z "$QCSUPER_PATH" ]]; then
        QCSUPER_PATH=$(command -v qcsuper 2>/dev/null || true)
    fi
    if [[ -z "$QCSUPER_PATH" ]]; then
        say "ATTENZIONE: qcsuper non risulta nel PATH (vedi eventuali errori sopra): scrivo comunque '/usr/local/bin/qcsuper' in system.conf, correggere a mano se necessario."
        QCSUPER_PATH="/usr/local/bin/qcsuper"
    fi

    # ---- VID:PID USB del modulo (per l'opzionale mdtcap --usb-modem) ----
    # Best-effort come il resto di --configure-system: interroga via
    # udevadm (nessun I/O seriale, funziona anche se il modem non risponde
    # su AT) la prima ttyUSB* il cui ID_VENDOR contiene "SimTech" (stesso
    # filtro usato piu' sotto dal backup IMEI) e ne legge
    # ID_VENDOR_ID/ID_MODEL_ID — le 4 cifre esadecimali di VID/PID, le
    # stesse mostrate da "lsusb". Se --usb-modem-vid/--usb-modem-pid sono
    # gia' stati passati espliciti, non tenta il rilevamento.
    # USB_VID/USB_PID sono il valore RISOLTO (esplicito o auto-rilevato,
    # quello scritto davvero nel corpo di system.conf) — tenuto separato
    # da SYS_USB_VID/SYS_USB_PID (che restano non modificati, usati SOLO
    # per capire se erano stati passati espliciti sulla riga di comando)
    # per lo stesso motivo per cui QCSUPER_PATH sopra e' separato da
    # SYS_QCSUPER: la riga "GENERATO da:" qui sotto deve rispecchiare
    # cosa e' stato DAVVERO passato sulla riga di comando, non anche i
    # valori riempiti da un rilevamento automatico.
    USB_VID="$SYS_USB_VID"
    USB_PID="$SYS_USB_PID"
    if [[ -z "$USB_VID" && -z "$USB_PID" ]] && command -v udevadm >/dev/null 2>&1; then
        for p in /dev/ttyUSB* /dev/ttyACM*; do
            [[ -e "$p" ]] || continue
            udevadm info -q property -n "$p" 2>/dev/null | grep -qi '^ID_VENDOR=.*SimTech' || continue
            USB_VID=$(udevadm info -q property -n "$p" 2>/dev/null | sed -n 's/^ID_VENDOR_ID=//p')
            USB_PID=$(udevadm info -q property -n "$p" 2>/dev/null | sed -n 's/^ID_MODEL_ID=//p')
            [[ -n "$USB_VID" && -n "$USB_PID" ]] && break
            USB_VID=""
            USB_PID=""
        done
        if [[ -n "$USB_VID" ]]; then
            say "VID:PID USB rilevato: $USB_VID:$USB_PID (su $p)"
        else
            say "VID:PID USB non rilevato (nessuna porta SimTech trovata ora): --usb-modem-vid/--usb-modem-pid resteranno assenti da system.conf, si puo' rilanciare --configure-system a modem collegato, o passarli a mano."
        fi
    fi

    {
        echo "# File di configurazione mdtcap — SISTEMA (questa macchina/questo collegamento)"
        echo "#"
        echo "# GENERATO da: sudo ./install.sh --configure-system$( [[ -n "$SYS_DIAG_PORT" ]] && printf ' --diag-port %s --at-port %s' "$SYS_DIAG_PORT" "$SYS_AT_PORT" )$( [[ -n "$SYS_QCSUPER" ]] && printf ' --qcsuper %s' "$SYS_QCSUPER" )$( [[ -n "$SYS_USB_VID" ]] && printf ' --usb-modem-vid %s --usb-modem-pid %s' "$SYS_USB_VID" "$SYS_USB_PID" )"
        echo "# il $(date -u +%Y-%m-%dT%H:%M:%SZ). Rigenerato per intero ad ogni uso di"
        echo "# --configure-system: non aggiungere qui altro oltre a"
        echo "# porte/--autodetect/--qcsuper/VID-PID USB (parametri di SISTEMA —"
        echo "# dipendono dalla macchina/dal collegamento hardware, non da operatore o"
        echo "# tipo di test: per quelli vedi mdt_configs/op/*.conf e"
        echo "# mdt_configs/profile/*.conf)."
        echo "#"
        echo "# Caricato automaticamente da mdtcap ad ogni esecuzione (nessuna opzione"
        echo "# da passare), con la precedenza piu' bassa fra i livelli di"
        echo "# configurazione (system.conf < --op < --profile < --config < riga di"
        echo "# comando): valori passati esplicitamente sulla riga di comando vincono"
        echo "# sempre su questo file."
        echo "#"
        echo "# --usb-modem-vid/--usb-modem-pid: usati da mdtcap SOLO se lanciato con"
        echo "# --usb-modem (facoltativo, vedi mdtcap --help) — assenti qui se il"
        echo "# rilevamento non e' riuscito, mdtcap si ferma con un errore chiaro se"
        echo "# --usb-modem viene comunque richiesto in quel caso."
        echo
        if [[ -n "$SYS_DIAG_PORT" ]]; then
            echo "--diag-port $SYS_DIAG_PORT"
            echo "--at-port $SYS_AT_PORT"
        else
            echo "--autodetect"
        fi
        echo "--qcsuper $QCSUPER_PATH"
        if [[ -n "$USB_VID" ]]; then
            echo "--usb-modem-vid $USB_VID"
            echo "--usb-modem-pid $USB_PID"
        fi
    } > "$SYSTEM_CONF"

    say "Configurazione di sistema scritta in $SYSTEM_CONF:"
    if [[ -n "$SYS_DIAG_PORT" ]]; then
        say "  --diag-port $SYS_DIAG_PORT --at-port $SYS_AT_PORT"
    else
        say "  --autodetect"
    fi
    say "  --qcsuper $QCSUPER_PATH"
    if [[ -n "$USB_VID" ]]; then
        say "  --usb-modem-vid $USB_VID --usb-modem-pid $USB_PID (usati solo con mdtcap --usb-modem, facoltativo)"
    else
        say "  (nessun VID:PID USB salvato: mdtcap --usb-modem non sara' utilizzabile finche' non lo si rilancia con il modem collegato, o non si passano --usb-modem-vid/--usb-modem-pid a mano)"
    fi

    if [[ -z "$SYS_DIAG_PORT" && -x "$SCRIPT_DIR/mdtcap" ]]; then
        say "Porte USB attualmente rilevate (informativo, --autodetect le rilevera' di nuovo ad ogni cattura):"
        "$SCRIPT_DIR/mdtcap" --list-ports 2>&1 | sed 's/^/[install.sh]   /'
    fi

    # ---- backup dell'IMEI originale (mdt_configs/imei) ---------------------
    # Best-effort come tutto il resto di questo script: se la porta AT non e'
    # determinabile ora o la lettura fallisce, non blocca l'installazione —
    # mdtcap ritenta comunque da solo ad ogni cattura live (vedi
    # ensure_imei_backup() li'). Mai sovrascritto se il file esiste gia': e'
    # un backup dell'IMEI di fabbrica, non l'ultimo osservato. Serve da
    # riferimento per mdtimei (script separato per cambiare l'IMEI, non
    # ripristina da solo) — vedi mdtimei --help e la guida separata sui
    # rischi legali di quell'operazione.
    IMEI_FILE="$SYSTEM_CONF_DIR/imei"
    if [[ -f "$IMEI_FILE" ]]; then
        say "Backup IMEI: gia' presente in $IMEI_FILE, non toccato."
    elif command -v stty >/dev/null 2>&1; then
        PROBE_AT_PORT="$SYS_AT_PORT"
        if [[ -z "$PROBE_AT_PORT" ]]; then
            for p in /dev/ttyUSB*; do
                [[ -e "$p" ]] || continue
                udevadm info -q property -n "$p" 2>/dev/null | grep -qi '^ID_VENDOR=.*SimTech' || continue
                stty -F "$p" 115200 2>/dev/null || true
                stty -F "$p" raw -echo -echoe -echok time 0 min 0 2>/dev/null || continue
                exec {probe_fd}<>"$p" 2>/dev/null || continue
                printf 'AT\r' >&"$probe_fd" 2>/dev/null
                presp=""
                pstart=$SECONDS
                while IFS= read -r -t 2 -u "$probe_fd" pline 2>/dev/null; do
                    pline="${pline%$'\r'}"
                    [[ -z "$pline" ]] && continue
                    presp+="$pline"$'\n'
                    [[ "$pline" == "OK" || "$pline" == "ERROR" ]] && break
                    (( SECONDS - pstart >= 3 )) && break
                done
                exec {probe_fd}<&-
                if echo "$presp" | grep -q '^OK$'; then
                    PROBE_AT_PORT="$p"
                    break
                fi
            done
        fi
        if [[ -n "$PROBE_AT_PORT" && -e "$PROBE_AT_PORT" ]]; then
            stty -F "$PROBE_AT_PORT" 115200 2>/dev/null || true
            stty -F "$PROBE_AT_PORT" raw -echo -echoe -echok time 0 min 0 2>/dev/null
            exec {imei_fd}<>"$PROBE_AT_PORT" 2>/dev/null
            printf 'AT+CGSN\r' >&"$imei_fd"
            IMEI_VAL=""
            istart=$SECONDS
            while IFS= read -r -t 2 -u "$imei_fd" iline 2>/dev/null; do
                iline="${iline%$'\r'}"
                [[ -z "$iline" ]] && continue
                [[ "$iline" =~ ^[0-9]{14,16}$ ]] && IMEI_VAL="$iline"
                [[ "$iline" == "OK" || "$iline" == "ERROR" ]] && break
                (( SECONDS - istart >= 3 )) && break
            done
            exec {imei_fd}<&-
            if [[ -n "$IMEI_VAL" ]]; then
                echo "$IMEI_VAL" > "$IMEI_FILE"
                say "Backup IMEI: salvato IMEI originale ($IMEI_VAL) in $IMEI_FILE."
            else
                say "ATTENZIONE: backup IMEI non riuscito (nessuna risposta valida da AT+CGSN su $PROBE_AT_PORT)."
            fi
        else
            say "Backup IMEI: nessuna porta AT determinabile ora (con --autodetect verra' salvato automaticamente al primo avvio di mdtcap)."
        fi
    fi
fi

# ---- --setup-mdtmain: dipendenze specifiche di mdtmain --screen -----------
# Vedi la spiegazione di --setup-mdtmain in testa al file.

if [[ "$SETUP_MDTMAIN" -eq 1 ]]; then
    if command -v fbi >/dev/null 2>&1; then
        say "fbi: OK"
    else
        say "fbi non trovato (immagine di presentazione di mdtmain --screen), installo..."
        apt_update_once
        if apt-get install -y fbi >/dev/null; then
            INSTALLED+=("fbi")
            say "fbi installato."
        else
            FAILED+=("fbi")
            say "ATTENZIONE: installazione di fbi fallita. Riprova a mano con: apt-get install fbi"
        fi
    fi

    if command -v aplay >/dev/null 2>&1 && command -v amixer >/dev/null 2>&1; then
        say "alsa-utils (aplay/amixer): OK"
    else
        say "alsa-utils (aplay/amixer, suoni di avviso e instradamento audio di mdtmain --screen) non trovato, installo..."
        apt_update_once
        if apt-get install -y alsa-utils >/dev/null; then
            INSTALLED+=("alsa-utils")
            say "alsa-utils installato."
        else
            FAILED+=("alsa-utils")
            say "ATTENZIONE: installazione di alsa-utils fallita. Riprova a mano con: apt-get install alsa-utils"
        fi
    fi

    # Font console "Uni2-VGA16"/"Uni2-VGA8" (pacchetto "console-setup"):
    # solo verifica, non installazione — gia' parte dell'immagine di base
    # normalmente in uso (Raspberry Pi OS), installarla da zero solo per
    # questo sarebbe sproporzionato; segnaliamo "da sistemare a mano" se
    # per qualche motivo mancano davvero.
    if [[ -f /usr/share/consolefonts/Uni2-VGA16.psf.gz && -f /usr/share/consolefonts/Uni2-VGA8.psf.gz ]]; then
        say "font console Uni2-VGA16/Uni2-VGA8 (mdtmain --screen): OK"
    else
        MISSING_MANUAL+=("font console Uni2-VGA16/Uni2-VGA8 (pacchetto 'console-setup', vedi apt-get install console-setup)")
        say "ATTENZIONE: font console Uni2-VGA16/Uni2-VGA8 non trovati in /usr/share/consolefonts/ (mdtmain --screen non potra' correggere pallini/cornici mostrati come lettere)."
    fi
fi

# ---- --fix-tui: sistema le TUI ncurses (dialog, pinentry-curses, ecc.) -----
# Vedi la spiegazione di --fix-tui in testa al file. Idempotente: non
# duplica/riscrive nulla se gia' presente e corretto. Applicato anche da
# --setup-mdtmain (senza, i pallini/le cornici della TUI comparirebbero
# come lettere anche in modalita' --screen — vedi spiegazione in testa
# al file).

if [[ "$FIX_TUI" -eq 1 || "$SETUP_MDTMAIN" -eq 1 ]]; then
    TUI_CHANGED=0

    # Locale: solo verifica/avviso, non lo tocchiamo qui (cambiare la
    # localizzazione della macchina e' fuori dallo scopo di un flag
    # pensato per la grafica ncurses) — vedi "sudo dpkg-reconfigure
    # locales" o raspi-config per quello.
    case "${LANG:-}${LC_ALL:-}" in
        *[Uu][Tt][Ff]-8*|*[Uu][Tt][Ff]8*)
            say "--fix-tui: locale OK (LANG=${LANG:-}, LC_ALL=${LC_ALL:-})."
            ;;
        *)
            MISSING_MANUAL+=("locale UTF-8 (LANG/LC_ALL attuali: '${LANG:-}'/'${LC_ALL:-}', ne serve uno con '.UTF-8', es. it_IT.UTF-8)")
            say "ATTENZIONE: locale non UTF-8 (LANG=${LANG:-}, LC_ALL=${LC_ALL:-}): dialog/whiptail disegneranno comunque male anche con NCURSES_NO_UTF8_ACS=1. Vedi 'sudo dpkg-reconfigure locales' o raspi-config."
            ;;
    esac

    # /etc/environment: letto da PAM per le sessioni SSH/login/su/sudo
    # (copre anche raspi-config lanciato con sudo).
    ENV_FILE="/etc/environment"
    [[ -f "$ENV_FILE" ]] || : > "$ENV_FILE"
    if grep -qxF "NCURSES_NO_UTF8_ACS=1" "$ENV_FILE" 2>/dev/null; then
        say "--fix-tui: $ENV_FILE gia' corretto (NCURSES_NO_UTF8_ACS=1)."
    else
        if grep -q '^NCURSES_NO_UTF8_ACS=' "$ENV_FILE" 2>/dev/null; then
            sed -i 's/^NCURSES_NO_UTF8_ACS=.*/NCURSES_NO_UTF8_ACS=1/' "$ENV_FILE"
        else
            echo "NCURSES_NO_UTF8_ACS=1" >> "$ENV_FILE"
        fi
        TUI_CHANGED=1
        say "--fix-tui: aggiunta NCURSES_NO_UTF8_ACS=1 a $ENV_FILE."
    fi

    # /etc/environment.d/: letto da systemd --user, copre
    # gpg-agent.service (che lancia pinentry-curses) anche se non e'
    # (ancora) partito in questa sessione di login.
    ENV_D_FILE="/etc/environment.d/99-ncurses-utf8.conf"
    if [[ -f "$ENV_D_FILE" ]] && grep -qxF "NCURSES_NO_UTF8_ACS=1" "$ENV_D_FILE" 2>/dev/null; then
        say "--fix-tui: $ENV_D_FILE gia' corretto."
    else
        mkdir -p /etc/environment.d
        echo "NCURSES_NO_UTF8_ACS=1" > "$ENV_D_FILE"
        TUI_CHANGED=1
        say "--fix-tui: scritto $ENV_D_FILE."
    fi

    # Applica subito (best-effort, non bloccante: es. non disponibile in
    # container/chroot senza systemd --user attivo) alla sessione
    # systemd --user gia' in esecuzione, cosi' non serve nemmeno
    # riavviare gpg-agent perche' veda la nuova variabile.
    if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
        if systemctl --user set-environment NCURSES_NO_UTF8_ACS=1 2>/dev/null; then
            say "--fix-tui: NCURSES_NO_UTF8_ACS=1 applicata anche alla sessione systemd --user attiva (gpg-agent la vedra' al prossimo avvio, senza bisogno di riavviarlo)."
        else
            say "--fix-tui: non sono riuscito ad applicare la variabile alla sessione systemd --user attiva (non bloccante: verra' comunque letta al prossimo login)."
        fi
    fi

    # sudo NON eredita /etc/environment: lo stack PAM di sudo
    # (common-session-noninteractive) non include pam_env, e "env_reset"
    # (attivo in /etc/sudoers) scarta comunque la variabile a meno che
    # non sia in env_keep — quindi anche da una sessione di login fresca
    # (che la vede correttamente, via pam_env di sshd/login/su), "sudo
    # raspi-config"/"sudo ./mdtmain"/ecc. la perderebbero comunque senza
    # questo. VERIFICATO sul campo (sessione fresca via "su -l" + sudo):
    # senza questo blocco "sudo env" non la mostra, con questo si'.
    SUDOERS_D="/etc/sudoers.d/020_ncurses-utf8"
    if grep -rqE 'env_keep.*NCURSES_NO_UTF8_ACS' /etc/sudoers /etc/sudoers.d/ 2>/dev/null; then
        say "--fix-tui: sudo eredita gia' NCURSES_NO_UTF8_ACS (env_keep)."
    elif ! command -v visudo >/dev/null 2>&1; then
        MISSING_MANUAL+=("env_keep NCURSES_NO_UTF8_ACS in sudoers (visudo non trovato, non tocco /etc/sudoers.d/ senza poterlo validare)")
        say "ATTENZIONE: visudo non trovato, non aggiungo l'env_keep sudoers per NCURSES_NO_UTF8_ACS (rischio di rompere sudo senza potervi validare la modifica)."
    else
        TMP_SUDOERS=$(mktemp)
        echo 'Defaults env_keep += "NCURSES_NO_UTF8_ACS"' > "$TMP_SUDOERS"
        if visudo -c -f "$TMP_SUDOERS" >/dev/null 2>&1; then
            install -m 0440 "$TMP_SUDOERS" "$SUDOERS_D"
            if visudo -c >/dev/null 2>&1; then
                TUI_CHANGED=1
                say "--fix-tui: aggiunto $SUDOERS_D (sudo ora eredita NCURSES_NO_UTF8_ACS dalla sessione di login)."
            else
                # Non dovrebbe succedere (il file da solo era valido), ma
                # se la validazione GLOBALE fallisce lo ritiriamo subito:
                # meglio senza il fix TUI sotto sudo che con sudo rotto.
                rm -f "$SUDOERS_D"
                FAILED+=("env_keep NCURSES_NO_UTF8_ACS in sudoers (validazione globale fallita dopo l'installazione, ritirato)")
                say "ATTENZIONE: $SUDOERS_D rimosso subito, la validazione di /etc/sudoers nel suo insieme e' fallita dopo averlo aggiunto."
            fi
        else
            FAILED+=("env_keep NCURSES_NO_UTF8_ACS in sudoers (visudo -c ha rifiutato il file, non installato)")
            say "ATTENZIONE: visudo ha rifiutato la riga env_keep per NCURSES_NO_UTF8_ACS, non installata."
        fi
        rm -f "$TMP_SUDOERS"
    fi

    if [[ "$TUI_CHANGED" -eq 1 ]]; then
        INSTALLED+=("impostazioni TUI ncurses (NCURSES_NO_UTF8_ACS=1 in /etc/environment, /etc/environment.d/ e env_keep sudoers)")
        say "--fix-tui: fatto. Richiudi e riapri le sessioni SSH/terminale gia' aperte per ereditare la modifica (un riavvio completo non serve)."
    else
        say "--fix-tui: nessuna modifica necessaria, era gia' tutto corretto."
    fi
fi

# ---- riepilogo --------------------------------------------------------------

echo
say "=== Riepilogo ==="
if [[ ${#INSTALLED[@]} -gt 0 ]]; then
    say "Installati in questa esecuzione: ${INSTALLED[*]}"
fi
if [[ ${#FAILED[@]} -gt 0 ]]; then
    say "ATTENZIONE — installazione fallita per: ${FAILED[*]} (vedi i messaggi sopra)"
fi
if [[ ${#MISSING_MANUAL[@]} -gt 0 ]]; then
    say "Da sistemare a mano: ${MISSING_MANUAL[*]}"
fi

say "Cose che questo script NON verifica (dipendono dall'hardware/uso, non dal software):"
say "  - modulo USB (es. SIM7600E-H) collegato e riconosciuto: sudo ./mdtcap --list-ports"
say "  - PIN della SIM (--sim-pin), APN dell'operatore (--apn): vedi README.md"

if [[ "$CONFIGURE_SYSTEM" -eq 0 && ! -f "$SCRIPT_DIR/mdt_configs/system.conf" ]]; then
    say "Nota: mdt_configs/system.conf non esiste ancora (porte/--autodetect/--qcsuper"
    say "vanno quindi passati a mano ad ogni cattura). Per generarlo: sudo ./install.sh --configure-system"
fi

if [[ ${#FAILED[@]} -eq 0 && ${#MISSING_MANUAL[@]} -eq 0 ]]; then
    say "Tutto pronto. Prossimo passo: sudo ./mdtcap --list-ports (o --autodetect)."
    exit 0
else
    say "Installazione completata con avvisi, vedi sopra."
    exit 1
fi
