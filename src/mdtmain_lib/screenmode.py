"""Modalita' --screen: usa lo schermo HDMI collegato (la console fisica
del dispositivo, di norma /dev/tty1) per l'output e la tastiera collegata
per l'input, invece del terminale (SSH/seriale) da cui mdtmain e' stato
lanciato — pensato per un uso "da postazione fissa" senza terminale
remoto.

Per la durata di mdtmain sopprime temporaneamente:
  - i messaggi del kernel sulla console (altrimenti si sovrapporrebbero
    alla TUI dialog/mdtcap), abbassando il livello di log della console
    (equivalente a "dmesg -n 1");
  - il login (getty) su quella console (altrimenti competerebbe con
    mdtmain per lo stesso terminale), fermando temporaneamente
    getty@<console>.service.
Entrambi vengono ripristinati da deactivate(), registrata anche con
atexit cosi' da scattare anche su uscita normale/eccezione non gestita
(non su SIGKILL, che nessun processo puo' intercettare).

Instrada anche l'audio (usato da sound.py) su HDMI o Headphones secondo
il parametro "hdmi" di mdtmain.conf, tramite il controllo ALSA standard
del Raspberry Pi (bcm2835): best-effort, se la scheda audio e' diversa e
non lo espone questo passo fallisce in silenzio, i suoni restano provati
comunque sull'uscita di default della scheda.

Carica anche un font console con una unicode map piu' ampia ("Uni2-VGA16",
cella 8x16, o "Uni2-VGA8", cella 8x8, se lo schermo risulta piccolo — vedi
_pick_console_font()): senza, il pallino ● (usato dalla TUI di mdtcap) e i
caratteri di disegno delle cornici (usati da dialog) non sono nella
unicode map del font di default (verificato via l'ioctl GIO_UNIMAP: solo
~65 voci, niente oltre l'ASCII di base) e il kernel li sostituisce con un
carattere segnaposto (compare come asterisco) — entrambi i font "Uni2-*"
li includono. Ripristinato da deactivate() con "setupcon", che riapplica
il font/keymap configurati di sistema.

Mostra anche, prima di prendere il controllo, l'immagine di presentazione
src/res/mdtcap.png a schermo intero con "fbi" per qualche secondo (salvo
--no-banner)."""
import atexit
import fcntl
import glob
import os
import struct
import subprocess
import termios
import time

from . import constants

_state = {"active": False, "needs_cleanup": False}

_CONSOLE_FONT = "Uni2-VGA16"
_CONSOLE_FONT_SMALL = "Uni2-VGA8"
_SMALL_SCREEN_COLS = 120
_SMALL_SCREEN_ROWS = 44


def show_splash(seconds=2):
    """Immagine di presentazione (src/res/mdtcap.png) a schermo intero
    con "fbi" per "seconds" secondi, poi la chiude — best-effort: se fbi
    non e' installato o l'immagine manca, no-op silenzioso (non deve mai
    bloccare l'avvio). Disegna direttamente sul framebuffer: non serve
    gia' possedere una console come terminale di controllo."""
    image = constants.MDTCAP_SPLASH_PNG
    if not os.path.isfile(image):
        return
    fb = "/dev/fb0"  # unico framebuffer tipico su Raspberry Pi
    try:
        proc = subprocess.Popen(
            ["fbi", "--noautoup", "--noverbose", "--noedit", "--blend", "1",
             "--nointeractive", "-d", fb, image],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        return
    time.sleep(seconds)
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _console_size(console):
    """(righe, colonne) attuali della console (col font gia' in uso in
    quel momento — va quindi interrogato PRIMA di cambiare font, per
    decidere se lo schermo fisico e' "piccolo"), o None se non
    determinabile."""
    try:
        fd = os.open(console, os.O_RDWR)
        try:
            packed = fcntl.ioctl(fd, termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
            rows, cols, _xpixel, _ypixel = struct.unpack("HHHH", packed)
            if rows and cols:
                return rows, cols
            return None
        finally:
            os.close(fd)
    except OSError:
        return None


def _pick_console_font(console):
    """"Uni2-VGA8" (cella 8x8, quindi piu' righe/colonne a parita' di
    risoluzione fisica) se lo schermo risulta piu' piccolo di
    120x44 col font di default attuale, altrimenti "Uni2-VGA16" (cella
    8x16, il default). Entrambi hanno la stessa unicode map (vedi sopra
    nel docstring del modulo)."""
    size = _console_size(console)
    if size is not None:
        rows, cols = size
        if cols < _SMALL_SCREEN_COLS or rows < _SMALL_SCREEN_ROWS:
            return _CONSOLE_FONT_SMALL
    return _CONSOLE_FONT


def _set_console_font(console, font):
    try:
        subprocess.run(["setfont", font, "-C", console], check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def set_audio_output(hdmi):
    """Instrada l'audio su HDMI (hdmi=True) o Headphones (hdmi=False).
    Best-effort (ALSA, controllo "PCM Playback Route" del Raspberry Pi:
    0=auto, 1=Headphones, 2=HDMI) — silenzioso se la scheda non lo
    espone (hardware diverso da un Raspberry Pi/bcm2835)."""
    value = "2" if hdmi else "1"
    try:
        subprocess.run(["amixer", "cset", "numid=3", value],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except OSError:
        pass


def hdmi_display_active():
    """True se ALMENO un connettore HDMI del sistema risulta "connected"
    (schermo fisicamente collegato E rilevato, vedi /sys/class/drm/
    *-HDMI-*/status — il driver KMS "vc4-kms-v3d", di default su
    Raspberry Pi OS da Bullseye in poi, espone cosi' lo stato hotplug per
    ciascun connettore). Best-effort: ritorna False se non determinabile
    (nessun /sys/class/drm, hardware/driver diverso, permessi, ...).
    Usata SOLO da --edge-mode (vedi app.run_edge_mode()) per decidere se
    proporre comunque il menu principale quando il test continuato non
    e' configurato — non usata da --screen "normale", che non richiede
    (e non verifica) un monitor davvero acceso."""
    for status_path in glob.glob("/sys/class/drm/card*-HDMI-*/status"):
        try:
            with open(status_path, "r") as f:
                if f.read().strip() == "connected":
                    return True
        except OSError:
            continue
    return False


def activate(hdmi=True, console="/dev/tty1", show_banner=True):
    """No-op se gia' attiva. Da chiamare una volta sola, il prima
    possibile (prima di qualunque output dialog/mdtcap)."""
    if _state["active"]:
        return
    _state["console"] = console

    if show_banner:
        show_splash()

    set_audio_output(hdmi)
    # Dimensione dello schermo misurata PRIMA di cambiare font (dipende
    # dal font ancora in uso in quel momento): decide se serve il font
    # piccolo per avere piu' righe/colonne a parita' di risoluzione fisica.
    _set_console_font(console, _pick_console_font(console))

    # Log del kernel sulla console: abbassato al minimo (solo messaggi
    # di emergenza), ripristinato da deactivate(). "dmesg -n" agisce sul
    # console_loglevel del kernel per TUTTE le console, non solo questa —
    # e' l'unico meccanismo standard disponibile (non esiste un
    # equivalente per-tty).
    try:
        with open("/proc/sys/kernel/printk", "r") as f:
            _state["prior_printk"] = f.read().split()[0]
        subprocess.run(["dmesg", "-n", "1"], check=False)
    except OSError:
        _state["prior_printk"] = None

    # getty sulla console scelta: fermato per la durata di mdtmain
    # (altrimenti competerebbe per lo stesso terminale/la stessa
    # tastiera), ripristinato da deactivate() solo se era davvero attivo.
    unit = f"getty@{os.path.basename(console)}.service"
    _state["getty_unit"] = unit
    try:
        was_active = subprocess.run(
            ["systemctl", "is-active", "--quiet", unit]).returncode == 0
        _state["getty_was_active"] = was_active
        if was_active:
            subprocess.run(["systemctl", "stop", unit], check=False)
    except OSError:
        _state["getty_was_active"] = False

    # Da qui in poi il sistema e' gia' stato modificato (printk/getty):
    # registriamo SUBITO il ripristino, PRIMA dei passi rischiosi che
    # seguono (fork/setsid/apertura della console) — non alla fine della
    # funzione. Capitato per davvero: un'eccezione nei passi sotto,
    # prima che un "atexit.register" a fondo funzione fosse mai
    # raggiunto, aveva lasciato getty@tty1 fermo e il log del kernel
    # abbassato per sempre (nessuna pulizia mai registrata). deactivate()
    # usa needs_cleanup (non "active", vero solo a presa di controllo
    # completata) per sapere se c'e' qualcosa da ripristinare.
    _state["needs_cleanup"] = True
    atexit.register(deactivate)

    # os.setsid() fallisce con "Operation not permitted" se il processo
    # e' gia' leader del proprio gruppo di processi — il caso normale
    # quando lanciato come comando in primo piano da una shell
    # interattiva (es. "sudo ./mdtmain --screen"). Un fork preliminare lo
    # evita sempre: il figlio ottiene un PID nuovo, mai leader di alcun
    # gruppo esistente, quindi setsid() nel figlio riesce sempre. Il
    # processo originale (quello lanciato dalla shell/sessione SSH) esce
    # subito dopo: da questo momento mdtmain continua a vivere SOLO come
    # processo figlio (root, gia' elevato da sudo prima del fork),
    # staccato dal terminale di lancio, sulla console HDMI scelta.
    pid = os.fork()
    if pid > 0:
        os._exit(0)

    # Nuova sessione (si stacca dall'eventuale terminale di controllo
    # ereditato), poi apre la console SENZA O_NOCTTY — su Linux un
    # leader di sessione senza gia' una tty di controllo che ne apre una
    # ne diventa automaticamente il controllore; TIOCSCTTY lo forza
    # esplicitamente anche se cosi' non fosse. Necessario perche' la
    # tastiera collegata a quella console arrivi davvero su stdin
    # (altrimenti dialog/mdtcap continuerebbero a leggere dal vecchio
    # terminale).
    os.setsid()
    fd = os.open(console, os.O_RDWR)
    try:
        fcntl.ioctl(fd, termios.TIOCSCTTY, 0)
    except OSError:
        pass
    os.dup2(fd, 0)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    if fd > 2:
        os.close(fd)

    _state["active"] = True


def deactivate():
    """Ripristina getty, livello di log della console e font. Sicura da
    chiamare piu' volte, ed efficace anche se activate() non e' arrivata
    in fondo (vedi needs_cleanup, impostato subito dopo aver toccato
    printk/getty, non a presa di controllo completata)."""
    if not _state.get("needs_cleanup"):
        return
    _state["needs_cleanup"] = False
    _state["active"] = False
    if _state.get("prior_printk"):
        try:
            subprocess.run(["dmesg", "-n", _state["prior_printk"]], check=False)
        except OSError:
            pass
    if _state.get("getty_was_active"):
        try:
            subprocess.run(["systemctl", "start", _state["getty_unit"]], check=False)
        except OSError:
            pass
    # Font: "setupcon" riapplica font/keymap configurati di sistema per
    # quella console (stesso comando usato da raspi-config dopo un
    # cambio tastiera/locale) — "--force" e' solo "non verificare che
    # siamo su una console vera" (serve perche' qui stdin/stdout NON sono
    # piu' quelli originali di mdtmain), NON accetta il device come
    # argomento posizionale: va invece rediretto sulla console scelta
    # (equivalente a "setupcon --force <> /dev/ttyN >&0 2>&1" in shell),
    # altrimenti agirebbe sul terminale sbagliato (o su nessuno).
    # setfont -R (reset ai default di avvio) e' stato provato prima ma
    # fallisce su questo sistema (ioctl KD_FONT_OP_SET_DEFAULT assente).
    try:
        fd = os.open(_state["console"], os.O_RDWR)
        try:
            subprocess.run(["setupcon", "--force"], stdin=fd, stdout=fd, stderr=fd, check=False)
        finally:
            os.close(fd)
    except OSError:
        pass
