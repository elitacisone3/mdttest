"""Avvio di mdtcap in primo piano con poll non bloccante della tastiera
('premi un tasto per fermare il test' -> crea mdtStop in --shm) insieme a
limiti di tempo/dimensione opzionali (test locale) e una scadenza rigida
(fine finestra oraria, test continuo). Disegna esso stesso lo schermo
(header + contenuto), perche' con --tui + --shm mdtcap non stampa piu'
nulla dopo l'elenco iniziale delle azioni."""
import json
import os
import select
import subprocess
import sys
import time

from . import constants

CLEAR_SCREEN = "\x1b[2J\x1b[H"

SHM_FIELDS = [
    "lte", "gps", "mdt", "mdtPos", "rrc", "rrcPos", "contract", "path", "ok",
    "diagWarn", "warnPosD", "warnPosL", "warnMDTD", "warnMDTL", "extraLevel",
    "extra_SMSSTK_L", "extra_SMSSTK_N", "extra_NASId_L", "extra_NASId_N",
    "extra_RRCCiph_L", "extra_RRCCiph_N", "extra_cellSys_L", "extra_cellSys_N",
    "extra_GPSLoc_L", "extra_GPSLoc_N", "extra_WCDMA3G_L", "extra_WCDMA3G_N",
]


def prepare_shm_dir(shm_dir):
    os.makedirs(shm_dir, exist_ok=True)
    stop_file = os.path.join(shm_dir, "mdtStop")
    if os.path.exists(stop_file):
        os.remove(stop_file)


def signal_stop(shm_dir):
    open(os.path.join(shm_dir, "mdtStop"), "w").close()


def read_shm(shm_dir):
    """Dict {campo: stringa} per i soli file presenti (mdtcap non ha
    ancora finalizzato quelli mancanti)."""
    out = {}
    for field in SHM_FIELDS:
        path = os.path.join(shm_dir, field)
        try:
            with open(path, "r") as f:
                out[field] = f.read()
        except OSError:
            continue
    return out


def read_manifest(outdir):
    path = os.path.join(outdir, "manifest.json")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def dir_size_bytes(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def start_mdtcap(args, shm_dir, outdir=None, log_path=None, inherit_stdout=False, tui=True):
    """inherit_stdout=True lascia stdout/stderr di mdtcap ereditati da
    questo processo (nessuna redirezione): serve a mostrare dal vivo
    l'elenco --tui di mdtcap stesso (vedi run_foreground_with_keypress_stop,
    passthrough_tui), che con --shm smette di stampare solo DOPO l'elenco
    (fine cattura), non l'elenco stesso.
    tui=False non passa affatto "--tui"/"--no-banner": mdtcap stampa il
    proprio log normale, scorrevole e per intero (banner incluso), senza
    nessuna riscrittura/pulizia schermo — usato dalla modalita' di debug
    "mdtmain --run-local" per vedere ESATTAMENTE l'output di mdtcap,
    utile per isolare un problema all'avvio dal wrapper --tui/dialog di
    mdtmain (vedi run_local_test_headless in app.py)."""
    full_args = [constants.MDTCAP]
    if tui:
        full_args += ["--tui", "--no-banner"]
    full_args += ["--shm", shm_dir]
    if outdir:
        # "--outdir-base """ dopo "--outdir": annulla esplicitamente un
        # eventuale --outdir-base ereditato da system.conf/--op
        # (autorilevato via MCC-MNC)/--profile/--config, che altrimenti
        # farebbe fallire mdtcap subito ("Non usare --outdir insieme a
        # --outdir-base", mutuamente esclusivi anche se arrivano da
        # livelli diversi) proprio quando serve forzare un percorso
        # preciso (tmpfs per il test locale, mountpoint USB, cartella di
        # evidenza del test continuo). Ultimo ad essere valutato (la
        # riga di comando vince sempre, vedi il commento sull'ordine di
        # precedenza in mdtcap), quindi vince comunque anche se un
        # --op/--profile/--config successivo negli "args" del chiamante
        # tentasse di reimpostare --outdir-base.
        full_args += ["--outdir", outdir, "--outdir-base", ""]
    full_args += args
    if inherit_stdout:
        stdout_target = None
        stderr_target = None
    else:
        stdout_target = open(log_path, "wb") if log_path else subprocess.DEVNULL
        stderr_target = subprocess.STDOUT if log_path else subprocess.DEVNULL
    return subprocess.Popen(full_args, stdin=subprocess.DEVNULL, stdout=stdout_target,
                             stderr=stderr_target)


class _RawKeyPoll:
    """Mette stdin in modalita' cbreak (se e' una tty) cosi' una singola
    pressione di tasto e' rilevabile con select() senza bloccare e senza
    richiedere INVIO. No-op silenzioso se stdin non e' un terminale reale."""

    def __init__(self):
        self._is_tty = sys.stdin.isatty()
        self._old_settings = None

    def __enter__(self):
        if self._is_tty:
            import termios
            import tty
            self._old_settings = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, *exc):
        if self._is_tty and self._old_settings is not None:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_settings)

    def key_pressed(self, timeout):
        if not self._is_tty:
            time.sleep(timeout)
            return False
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if ready:
            try:
                os.read(sys.stdin.fileno(), 1)
            except OSError:
                pass
            return True
        return False


def run_foreground_with_keypress_stop(args, shm_dir, header_fn, extra_status_fn=None,
                                       max_seconds=None,
                                       max_bytes=None, outdir=None, log_path=None,
                                       passthrough_tui=False, mdtcap_tui=True,
                                       quiet=False, should_stop=None, on_tick=None):
    """Avvia mdtcap ed esegue il loop di visualizzazione/poll. Ritorna
    (stop_reason, manifest_dict_or_None) — stop_reason in
    "user_keypress" | "signal" | "limit_reached" | "finished".

    passthrough_tui=True (test locale/USB): mdtcap disegna da solo, dal
    vivo, il proprio elenco --tui (righe di stato colorate) direttamente
    sul terminale — questo loop si limita a stampare UNA volta l'header
    (riga 1: "MDTCap {versione}"/ip o "NO INTERNET"; riga 2: vuota) prima
    di avviarlo, poi solo a fare polling di tastiera/limiti senza pero'
    scrivere piu' nulla a schermo (competerebbe con i redraw ANSI di
    mdtcap). Incompatibile con extra_status_fn (ignorato se presente),
    usato invece dal test continuo, che tiene l'output di mdtcap su file
    di log e disegna i propri 4 pallini di stato.

    mdtcap_tui=False (solo con passthrough_tui=True): non passa "--tui" a
    mdtcap, che stampa quindi il proprio log normale/scorrevole (vedi
    start_mdtcap) invece dell'elenco a righe fisse — modalita' di debug
    (mdtmain --run-local).

    quiet=True (--edge-mode, vedi app.run_edge_mode): non scrive NULLA a
    schermo in questo loop (nessun terminale garantito) — il poll di
    tastiera/limiti prosegue invariato, semplicemente senza ridisegnare
    header/stato a ogni giro.

    should_stop, se passata, e' richiamata a ogni giro (in aggiunta al
    poll di tastiera): se ritorna True la prima volta, chiede a mdtcap di
    fermarsi esattamente come un tasto premuto (stop_reason "signal"
    invece di "user_keypress") — usata da --edge-mode per un arresto
    pulito su SIGTERM (vedi edgemode.py), che aspetta comunque la
    normale fine di mdtcap (stesso ciclo "signal_stop poi attendi
    proc.poll()" gia' usato per max_seconds/max_bytes sotto), non un
    kill immediato.

    on_tick, se passata, e' richiamata una volta per giro (stessa
    cadenza di poll di tutto il resto, ~POLL_INTERVAL_SECONDS), cattura
    in corso o no: usata da scheduler.run_continuous per valutare i
    comandi CHECKPOINT della DSL anche DURANTE una cattura lunga (un
    CHECKPOINT non lancia mai mdtcap, ma senza questo aggancio uno
    annidato dentro una finestra IN/EVERY lunga non scatterebbe mai,
    dato che altrimenti verrebbe valutato solo fra una cattura e la
    successiva)."""
    prepare_shm_dir(shm_dir)

    # L'header (riga 1/2) va scritto e SVUOTATO (flush) PRIMA di avviare
    # il sottoprocesso, non dopo: con inherit_stdout=True (passthrough_tui)
    # mdtcap eredita lo stesso terminale e comincia subito a scriverci
    # (echo "Operatore auto-rilevato...", poi il proprio --tui) — se
    # l'ordine fosse invertito, i due processi scriverebbero in
    # concorrenza sullo stesso terminale (race condition reale, non solo
    # teorica: osservata nella pratica), con effetti come testo che
    # compare/scompare o l'intestazione "Stato:" duplicata, a seconda di
    # chi arriva prima.
    if passthrough_tui:
        sys.stdout.write(CLEAR_SCREEN)
        sys.stdout.write(header_fn() + "\n\n")
        sys.stdout.flush()

    proc = start_mdtcap(args, shm_dir, outdir=outdir, log_path=log_path,
                         inherit_stdout=passthrough_tui, tui=mdtcap_tui)
    start_time = time.monotonic()
    stop_reason = None

    with _RawKeyPoll() as keys:
        while True:
            if not quiet and not passthrough_tui:
                sys.stdout.write(CLEAR_SCREEN)
                sys.stdout.write(header_fn() + "\n\n")
                if extra_status_fn is not None:
                    sys.stdout.write(extra_status_fn(read_shm(shm_dir)) + "\n")
                else:
                    sys.stdout.write("Test in corso... premere un tasto per interrompere.\n")
                sys.stdout.flush()

            if on_tick is not None:
                on_tick()

            if keys.key_pressed(constants.POLL_INTERVAL_SECONDS):
                if stop_reason is None:
                    stop_reason = "user_keypress"
                    signal_stop(shm_dir)
            elif should_stop is not None and stop_reason is None and should_stop():
                stop_reason = "signal"
                signal_stop(shm_dir)
            elif max_seconds is not None and stop_reason is None and (time.monotonic() - start_time) > max_seconds:
                stop_reason = "limit_reached"
                signal_stop(shm_dir)
            elif (max_bytes is not None and outdir is not None and stop_reason is None
                  and os.path.isdir(outdir) and dir_size_bytes(outdir) > max_bytes):
                stop_reason = "limit_reached"
                signal_stop(shm_dir)

            if proc.poll() is not None:
                break

    manifest = read_manifest(outdir) if outdir else None
    return stop_reason or "finished", manifest
