"""Wrapper sopra python3-dialog (pacchetto pip 'pythondialog', import
'dialog') per un'interfaccia in stile raspi-config, piu' le schermate ad
alta frequenza di refresh (test in corso, pausa) disegnate direttamente
in ANSI raw, dove 'dialog' stesso non si presta a un poll misto
tastiera/timer/processo esterno (vedi runner.py)."""
import os
import select
import shutil
import sys
import termios
import time
import tty

import dialog

from . import alarmstate, constants, netinfo

# ESCDELAY basso (alcune distro lo riducono per un ESC piu' reattivo in
# editor come vim) fa scambiare a ncurses una sequenza freccia/funzione
# (ESC seguito da altri byte) per un ESC "solitario" se quei byte non
# arrivano abbastanza vicini nel tempo - facile su una sessione SSH con
# anche solo un po' di jitter: un tasto freccia premuto normalmente puo'
# essere interpretato come "Annulla" (ESC chiude qualunque dialog), con
# l'effetto di un checkbox/menu che sembra "non rispondere" pur avendo
# ricevuto davvero la pressione del tasto. 100ms e' il valore raccomandato
# da ncurses stesso per questo problema; setdefault non sovrascrive un
# valore che l'utente avesse gia' impostato nel proprio ambiente.
os.environ.setdefault("ESCDELAY", "100")

_d = dialog.Dialog(dialog="dialog")
_d.set_background_title(f"MDTCap {constants.VERSION}")

CLEAR_SCREEN = "\x1b[2J\x1b[H"


def clear_screen():
    """'dialog' disegna sullo schermo normale (nessun alternate screen
    buffer): senza questo, l'ultima schermata mostrata (es. il menu
    principale o "Uscire da MDTCap?") resta visibile come residuo dopo
    che mdtmain e' gia' terminato. Da chiamare una volta sola all'uscita
    dal ciclo interattivo (vedi mdtmain), MAI nella modalita' di debug
    "--run-local" (cancellerebbe l'output che quella modalita' serve a
    mostrare)."""
    sys.stdout.write(CLEAR_SCREEN)
    sys.stdout.flush()


# ---- finestra del terminale (solo sessioni SSH/terminale, MAI --screen) ----
# La console fisica (--screen) non ha un "titolo di finestra": queste
# funzioni vanno usate solo quando mdtmain gira in un vero emulatore di
# terminale (xterm e compatibili — la maggioranza dei cilent SSH),
# best-effort (un emulatore che non le supporta le ignora silenziosamente,
# nessun danno).

def request_larger_window(rows=44, cols=132):
    """Chiede all'emulatore di terminale di ridimensionare la propria
    finestra (sequenza xterm "resize window", CSI 8 ; righe ; colonne t)
    SOLO se quella attuale e' piu' piccola di "cols"x"rows" (larghezza <
    132 colonne o altezza < 44 righe, di default): una finestra piccola
    (es. 80x24) troncava report lunghi dietro l'indicatore di
    scorrimento di dialog (vedi screen_msgbox) — su una gia' abbastanza
    grande non tocca nulla."""
    size = shutil.get_terminal_size(fallback=(cols, rows))
    if size.columns >= cols and size.lines >= rows:
        return
    sys.stdout.write(f"\x1b[8;{rows};{cols}t")
    sys.stdout.flush()


def set_window_title(title):
    """Imposta il titolo della finestra (OSC 0), impilando prima quello
    attuale (CSI 22;0 t) cosi' restore_window_title() puo' ripristinarlo
    senza doverlo prima leggere (non affidabile su molti terminali)."""
    sys.stdout.write("\x1b[22;0t")
    sys.stdout.write(f"\x1b]0;{title}\x07")
    sys.stdout.flush()


def restore_window_title():
    """Ripristina il titolo impilato da set_window_title() (CSI 23;0 t)."""
    sys.stdout.write("\x1b[23;0t")
    sys.stdout.flush()


def header_text(net_status_text=None, show_alarm=True):
    """'MDTCap {VERSION}' a sinistra, hostname/IP (o 'NO INTERNET', ed
    eventualmente log/lastAlarm davanti a tutto: vedi
    current_net_status_text) a destra, con padding calcolato sulla
    larghezza attuale del terminale."""
    left = f"MDTCap {constants.VERSION}"
    right = net_status_text if net_status_text is not None else current_net_status_text(show_alarm=show_alarm)
    cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    pad = max(1, cols - len(left) - len(right))
    return left + (" " * pad) + right


def current_net_status_text(has_internet=None, show_alarm=True):
    """hostname / (indirizzo ip, oppure "NO INTERNET" al posto
    dell'ip) — preceduto dal contenuto di log/lastAlarm (vedi
    alarmstate.read_last_alarm_text) quando show_alarm e' vero e c'e'
    davvero qualcosa da mostrare: MAI durante un test in corso (vedi
    draw_test_header sotto, show_alarm=False li') — mostrare l'ultimo
    allarme mentre un test nuovo e' gia' iniziato sarebbe fuorviante."""
    host = netinfo.get_hostname()
    ip_or_no_internet = "NO INTERNET" if has_internet is False else (netinfo.get_primary_ip() or "?")
    right = f"{host} / {ip_or_no_internet}"
    if show_alarm:
        alarm = alarmstate.read_last_alarm_text()
        if alarm:
            right = f"{alarm} / {right}"
    return right


def refresh_background_title(has_internet=None):
    _d.set_background_title(header_text(current_net_status_text(has_internet)))


def _title_kwargs(title):
    # pythondialog passa 'title' a "--title" senza controllare che non sia
    # None: se il chiamante non ne passa uno, la chiave va omessa del
    # tutto (mai title=None), altrimenti pythondialog solleva
    # AttributeError internamente (str.startswith su None).
    return {"title": title} if title else {}


def screen_menu(title, text, choices, height=0, width=0, menu_height=0):
    """choices: lista di (tag, descrizione). Ritorna il tag scelto, o
    None se l'utente ha annullato/premuto ESC. Il riquadro resta
    centrato sullo schermo (comportamento nativo di dialog(1) con
    height/width/menu_height a 0): log/lastAlarm non vive piu' qui (era
    un riquadro --infobox separato in basso a sinistra, rimosso — vedi
    current_net_status_text/header_text, ora e' nella scritta in alto a
    destra insieme a hostname/IP)."""
    code, tag = _d.menu(text, choices=choices, height=height, width=width,
                         menu_height=menu_height, **_title_kwargs(title))
    return tag if code == _d.OK else None


def screen_yesno(text, title=None):
    code = _d.yesno(text, **_title_kwargs(title))
    return code == _d.OK


def screen_inputbox(text, init="", title=None, width=70):
    code, value = _d.inputbox(text, init=init, width=width, **_title_kwargs(title))
    return value if code == _d.OK else None


def screen_passwordbox(text, init="", title=None, width=70):
    code, value = _d.passwordbox(text, init=init, width=width, insecure=True, **_title_kwargs(title))
    return value if code == _d.OK else None


def screen_msgbox(text, title=None):
    """Dimensiona il box sul CONTENUTO reale (altezza = numero di righe,
    larghezza = riga piu' lunga), entrambe con un margine fisso e capate
    alle dimensioni del terminale reale, invece di height/width fissi.
    L'altezza gia' andava cosi': con un report lungo (--report/
    --parla-chiaro), "height=0" lasciava scegliere a dialog un'altezza
    inferiore a quella davvero disponibile, troncando il contenuto dietro
    un indicatore di scorrimento ("35%" ecc.) molto prima del necessario.
    La larghezza pero' usava SEMPRE la larghezza intera del terminale,
    anche per un testo di una riga ("Impostazioni salvate."): un riquadro
    enorme per un messaggio breve. Ora la larghezza segue il contenuto
    (con un minimo per restare un riquadro riconoscibile, non una
    fessura), lo stesso identico contenuto lungo continua comunque a
    ricevere tutta la larghezza disponibile quando gli serve davvero
    (nessuna riga del testo puo' essere piu' larga del terminale stesso,
    quindi min()/max() qui sotto arrivano comunque al caso precedente)."""
    term_size = shutil.get_terminal_size(fallback=(80, 24))
    lines = text.split("\n")
    content_lines = len(lines)
    content_width = max((len(line) for line in lines), default=0)
    height = min(content_lines + 4, max(1, term_size.lines - 2))
    width = min(max(content_width + 4, 30), max(1, term_size.columns - 4))
    _d.msgbox(text, height=height, width=width, **_title_kwargs(title))


def screen_infobox(text, title=None):
    _d.infobox(text, width=70, **_title_kwargs(title))


def screen_checklist(title, text, items, height=0, width=0, list_height=0):
    """items: lista di (tag, descrizione, selezionato_bool). Ritorna
    l'insieme dei tag lasciati selezionati, o None se l'utente ha
    annullato/premuto ESC."""
    choices = [(tag, desc, bool(checked)) for tag, desc, checked in items]
    code, tags = _d.checklist(text, choices=choices, height=height, width=width,
                               list_height=list_height, **_title_kwargs(title))
    return set(tags) if code == _d.OK else None


# ---- schermate ANSI raw (test in corso, pausa) -----------------------------
# 'dialog' rilancia il binario dialog(1) ad ogni chiamata e non si presta a
# un refresh periodico misto a poll di tastiera/timer: qui si esce
# temporaneamente dal 'modo dialog' e si scrive direttamente sul terminale,
# come gia' fa mdtcap --tui.

def draw_test_header(has_internet=None):
    return header_text(current_net_status_text(has_internet, show_alarm=False))


def screen_pause_countdown(until_time):
    """Schermata di pausa fra una finestra e la successiva del test
    continuo. Ritorna True se l'utente ha premuto un tasto (ferma il
    test continuo e torna al menu), False se e' il momento di
    ricontrollare se una finestra e' diventata attiva."""
    until_str = until_time.strftime("%H:%M") if until_time else "?"
    is_tty = sys.stdin.isatty()
    old_settings = None
    try:
        if is_tty:
            old_settings = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        # infobox al posto del testo ANSI grezzo di prima: si disegna e
        # ritorna subito (non attende input, vedi screen_infobox), quindi
        # il poll tastiera sotto — che decide davvero se fermarsi — resta
        # invariato e a carico nostro, non del widget.
        screen_infobox(
            f"In pausa fino alle {until_str}.\n"
            "Premere un tasto per interrompere e tornare al menu principale.")
        if not is_tty:
            time.sleep(constants.POLL_INTERVAL_SECONDS)
            return False
        ready, _, _ = select.select([sys.stdin], [], [], constants.POLL_INTERVAL_SECONDS)
        if ready:
            try:
                os.read(sys.stdin.fileno(), 1)
            except OSError:
                pass
            return True
        return False
    finally:
        if is_tty and old_settings is not None:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)
