"""Macchina a stati principale di mdtmain: verifica/configurazione di
rete, poi le 4 modalita' di test, sempre con ritorno al menu principale
(successo o errore gestito)."""
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import termios
import time
import tty
from datetime import datetime

from . import (constants, contract, edgemode, evidence, httpclient, masterlog, mdtmain_config,
               netconfig, netinfo, profiles, runner, screenmode, scheduler, sound, syslog_log,
               ui, usbmount)


_STARTUP_DISCLAIM_TEXT = """Attenzione:

Questo programma è in versione beta. Non è un tool di sicurezza né un
tool di offesa.
Si utilizza per vedere se l'operatore telefonico traccia gli spostamenti
con MDT o altre tecniche.
Le configurazioni extra sono sperimentali. I dati vanno visionati da
personale esperto.
Si declina ogni responsabilità per un uso scorretto."""


def run_app(skip_network_setup=False, force_network_setup=False, auto_start=False):
    """skip_network_setup (--main): salta la schermata di rete anche
    senza Internet. force_network_setup (--net-menu): la mostra sempre,
    anche con Internet gia' presente e anche se disableNet=1 (unico modo
    per raggiungerla quando disableNet e' attivo). auto_start
    (--auto-start): se autoStart=1 e un test continuato e' completamente
    configurato (testSim/mdtcapProfile/schedulerProfile non vuoti),
    riprende il test continuato SENZA richiedere PIN/conferma/
    riselezione profilo (vedi _resume_continuous_test) — se l'ICCID
    della SIM inserita non corrisponde, mostra un errore e prosegue con
    il flusso normale (autoStart NON viene disattivato: e' una modalita'
    persistente, si disattiva solo dalla schermata Impostazioni).

    Non chiamata da run_edge_mode() (--edge-mode e' un percorso separato,
    pensato per girare senza terminale/interazione): il disclaimer di
    avvio sotto e' quindi mostrato solo nei percorsi interattivi
    (lancio normale, --auto-start), mai in un deployment headless."""
    config = mdtmain_config.load()
    if not mdtmain_config.get_bool(config, "startDisclaim"):
        mdtmain_config.update(startDisclaim="1")
        ui.screen_msgbox(_STARTUP_DISCLAIM_TEXT)
    disable_net = mdtmain_config.get_bool(config, "disableNet")
    has_internet = netinfo.has_internet()

    resumed = (auto_start and mdtmain_config.get_bool(config, "autoStart")
               and config["testSim"] and config["mdtcapProfile"] and config["schedulerProfile"])
    if resumed:
        _resume_continuous_test(config)  # gestisce da sola il caso ICCID non corrispondente
    elif force_network_setup:
        has_internet = screen_network_setup()
    elif not disable_net and not has_internet and not skip_network_setup:
        has_internet = screen_network_setup()

    while True:
        if not screen_main_menu(has_internet):
            return
        has_internet = netinfo.has_internet()


# ---- rete -------------------------------------------------------------

def screen_network_setup():
    """Ritorna True se, all'uscita da questo loop, c'e' connessione a
    Internet (rete configurata con successo o gia' presente); False se
    l'utente ha scelto esplicitamente di continuare offline (scelta solo
    logica, non tocca la configurazione di rete del sistema)."""
    while True:
        ui.refresh_background_title(has_internet=False)
        choice = ui.screen_menu(
            "Configurazione rete",
            "Nessuna connessione a Internet rilevata.",
            [("1", "Configura Ethernet"),
             ("2", "Configura WiFi"),
             ("3", "Salta (vai al menu principale)"),
             ("4", "Ricontrolla connessione")],
        )
        if choice is None or choice == "3":
            return False
        if choice == "1":
            _screen_ethernet_config()
        elif choice == "2":
            _screen_wifi_config()
        elif choice == "4":
            pass
        if netinfo.has_internet():
            return True


def _ask_static_ip():
    ip = ui.screen_inputbox("Indirizzo IP:")
    if not ip:
        return None
    prefix = ui.screen_inputbox("Prefisso di rete (es. 24 per 255.255.255.0):", init="24")
    gw = ui.screen_inputbox("Gateway:")
    dns = ui.screen_inputbox("DNS (opzionale):")
    return ip, prefix, gw, dns


def _screen_ethernet_config():
    ifaces = netinfo.list_ethernet_interfaces()
    if not ifaces:
        ui.screen_msgbox("Nessuna interfaccia Ethernet trovata.")
        return
    iface = ifaces[0] if len(ifaces) == 1 else ui.screen_menu(
        "Interfaccia Ethernet", "Selezionare l'interfaccia:", [(i, "") for i in ifaces])
    if not iface:
        return
    mode = ui.screen_menu("Ethernet", "Modalita' indirizzo IP:",
                           [("dhcp", "DHCP (automatico)"), ("static", "Statica")])
    if not mode:
        return
    ip = prefix = gw = dns = None
    if mode == "static":
        vals = _ask_static_ip()
        if vals is None:
            return
        ip, prefix, gw, dns = vals
    stack = netinfo.detect_network_stack()
    if stack == "networkmanager":
        _, msg = netconfig.configure_ethernet_nm(iface, mode, ip, prefix, gw, dns)
    elif stack == "dhcpcd":
        _, msg = netconfig.configure_ethernet_dhcpcd(iface, mode, ip, prefix, gw, dns)
    else:
        msg = "Nessuno stack di rete supportato rilevato (ne' NetworkManager, ne' dhcpcd)."
    ui.screen_msgbox(msg)


def _screen_wifi_config():
    ifaces = netinfo.list_wifi_interfaces()
    if not ifaces:
        ui.screen_msgbox("Nessuna interfaccia WiFi trovata.")
        return
    iface = ifaces[0] if len(ifaces) == 1 else ui.screen_menu(
        "Interfaccia WiFi", "Selezionare l'interfaccia:", [(i, "") for i in ifaces])
    if not iface:
        return
    stack = netinfo.detect_network_stack()
    ssids = netinfo.scan_wifi_ssids(iface, stack)
    choices = [(s, "") for s in ssids] + [("__manual__", "Altro (inserisci manualmente)")]
    ssid = ui.screen_menu("Reti WiFi", "Selezionare una rete:", choices)
    if not ssid:
        return
    if ssid == "__manual__":
        ssid = ui.screen_inputbox("Nome rete (SSID):")
        if not ssid:
            return
    password = ui.screen_passwordbox(f"Password per '{ssid}' (vuota se rete aperta):")
    if password is None:
        return
    mode = ui.screen_menu("WiFi", "Modalita' indirizzo IP:",
                           [("dhcp", "DHCP (automatico)"), ("static", "Statica")])
    if not mode:
        return
    ip = prefix = gw = dns = None
    if mode == "static":
        vals = _ask_static_ip()
        if vals is None:
            return
        ip, prefix, gw, dns = vals
    if stack == "networkmanager":
        _, msg = netconfig.configure_wifi_nm(iface, ssid, password, mode, ip, prefix, gw, dns)
    elif stack == "dhcpcd":
        _, msg = netconfig.configure_wifi_wpa_supplicant(iface, ssid, password, mode, ip, prefix, gw, dns)
    else:
        msg = "Nessuno stack di rete supportato rilevato (ne' NetworkManager, ne' dhcpcd)."
    ui.screen_msgbox(msg)


# ---- menu principale ----------------------------------------------------

def screen_main_menu(has_internet):
    ui.refresh_background_title(has_internet)
    config = mdtmain_config.load()
    choices = [("1", "Esegui un test in locale (senza salvare)"),
               ("2", "Esegui un test salvando le evidenze su chiavetta USB")]
    # "3"/"4" sono le uniche due modalita' che inviano dati a un server:
    # nascoste (non solo bloccate a schermata scelta) se disableSend=1
    # (default), stesso schema gia' usato sotto per "10"-"13" (numeri
    # riservati/stabili, aggiunti solo se applicabile - la dispatch piu'
    # sotto non cambia).
    if not mdtmain_config.get_bool(config, "disableSend"):
        choices.append(("3", "Esegui un test inviando i dati"))
        choices.append(("4", "Imposta test continuato (condividendo le evidenze)"))
    choices += [("5", "Test baseband"),
                ("6", "Test GPS"),
                ("7", "Download certificato identità di rete"),
                ("8", "Identità sistema"),
                ("9", "Impostazioni")]
    # Mostrata solo se c'e' davvero qualcosa da inviare (evidenza rimasta
    # in log/spool da un invio immediato fallito, vedi
    # scheduler.package_and_push/flush_spool): non ha senso proporla
    # altrimenti.
    if evidence.list_spool_files():
        choices.append(("10", "Invia i dati manualmente"))
    # Mostrate solo se un test continuato e' completamente configurato
    # (stessa condizione di --auto-start/--edge-mode: testSim non basta
    # da solo, serve anche mdtcapProfile/schedulerProfile).
    if config["testSim"] and config["mdtcapProfile"] and config["schedulerProfile"]:
        choices.append(("11", "Visualizza impostazioni test continuo"))
        choices.append(("12", "Riprendi test continuo"))
        choices.append(("13", "Rimuovi test continuo"))
    choice = ui.screen_menu("MDTCap", "Selezionare un'operazione:", choices)
    if choice is None:
        return not ui.screen_yesno("Uscire da MDTCap?")
    try:
        if choice == "1":
            screen_local_test()
        elif choice == "2":
            screen_usb_test()
        elif choice == "3":
            screen_send_data_test()
        elif choice == "4":
            screen_continuous_test()
        elif choice == "5":
            screen_baseband_test()
        elif choice == "6":
            screen_gps_test()
        elif choice == "7":
            screen_download_config()
        elif choice == "8":
            screen_system_identity()
        elif choice == "9":
            screen_settings()
        elif choice == "10":
            screen_send_spool_manually()
        elif choice == "11":
            screen_view_continuous_config()
        elif choice == "12":
            screen_resume_continuous_test()
        elif choice == "13":
            screen_remove_continuous_test()
    except Exception as e:  # qualunque errore riporta sempre al menu principale
        ui.screen_msgbox(f"Errore: {e}")
    return True


# ---- impostazioni ---------------------------------------------------------

def _ask_hour(label, current):
    """Numero intero 0-23, pre-riempito con il valore attuale. Ritorna
    l'intero, o None se l'utente ha annullato."""
    while True:
        raw = ui.screen_inputbox(f"{label} (0-23):", init=str(current))
        if raw is None:
            return None
        raw = raw.strip()
        if not raw.isdigit() or not (0 <= int(raw) <= 23):
            ui.screen_msgbox("Valore non valido: inserire un numero intero da 0 a 23.")
            continue
        return int(raw)


_DATA_DISCLAIM_TEXT = """Attenzione:

L'utilizzo di questa parte del programma è riservato al progetto di
monitoraggio.
Non vanno usate le SIM personali.
Occorrono dei token di accesso per abilitare l'invio dei dati."""


def screen_settings():
    config = mdtmain_config.load()
    items = [
        ("autostart", "Avvio automatico", mdtmain_config.get_bool(config, "autoStart")),
        ("alarms", "Attiva allarmi", not mdtmain_config.get_bool(config, "disableAlarm")),
        ("hdmi", "Allarmi su HDMI", mdtmain_config.get_bool(config, "hdmi")),
        ("gpsfix", "Forza il fix GPS prima dei test", mdtmain_config.get_bool(config, "doGPSFix")),
        ("extended", "Imposta i test approfonditi", mdtmain_config.get_bool(config, "forceExtended")),
        ("testsms", "Modalità test SMS", mdtmain_config.get_bool(config, "testSMS")),
        ("checkpoint", "Abilita la sirena nei checkpoint", mdtmain_config.get_bool(config, "alarmCheckPoint")),
        ("disablesend", "Disabilita l'invio delle evidenze", mdtmain_config.get_bool(config, "disableSend")),
    ]
    selected = ui.screen_checklist("Impostazioni", "Selezionare le opzioni attive:", items)
    if selected is None:
        return
    # Salvate SUBITO, prima di chiedere le ore allarme sotto: due passi
    # logicamente separati (checklist / fascia oraria), che non devono
    # condividere un solo "annulla": altrimenti un Cancel sulla sola
    # fascia oraria (schermata successiva, scollegata dalla checklist)
    # scartava in silenzio anche le scelte appena fatte qui sopra
    # (es. disableSend), lasciando tutto come prima senza alcun avviso.
    disable_send = "1" if "disablesend" in selected else "0"
    updates = dict(
        autoStart="1" if "autostart" in selected else "0",
        disableAlarm="0" if "alarms" in selected else "1",
        hdmi="1" if "hdmi" in selected else "0",
        doGPSFix="1" if "gpsfix" in selected else "0",
        forceExtended="1" if "extended" in selected else "0",
        testSMS="1" if "testsms" in selected else "0",
        alarmCheckPoint="1" if "checkpoint" in selected else "0",
        disableSend=disable_send,
    )
    if disable_send == "1":
        # Cosi' un test continuato gia' configurato non puo' piu' ripartire
        # da solo (--auto-start/"Riprendi test continuo" richiedono
        # testSim non vuoto, vedi run_app/screen_main_menu).
        updates["testPin"] = ""
        updates["testSim"] = ""
    mdtmain_config.update(**updates)
    if disable_send == "0" and not mdtmain_config.get_bool(config, "dataDisclaim"):
        mdtmain_config.update(dataDisclaim="1")
        ui.screen_msgbox(_DATA_DISCLAIM_TEXT)

    min_hour = _ask_hour("Allarmi dalle ore", mdtmain_config.get_hour(config, "minAlarmHour"))
    if min_hour is None:
        return
    max_hour = _ask_hour("Allarmi fino alle ore", mdtmain_config.get_hour(config, "maxAlarmHour"))
    if max_hour is None:
        return
    mdtmain_config.update(minAlarmHour=str(min_hour), maxAlarmHour=str(max_hour))
    ui.screen_msgbox("Impostazioni salvate.")


# ---- passaggi comuni a tutti i test -------------------------------------

def _confirm_sim_inserted():
    return ui.screen_yesno("Inserire la SIM nel dispositivo, poi confermare.")


def _ensure_gps_fix_if_needed(quiet=False):
    """Se doGPSFix=1 in mdtmain.conf, attende un fix GPS (mdtgps in
    background, GPS lasciato acceso) PRIMA di avviare il test vero e
    proprio, cosi' parte gia' con un fix "caldo" invece di doverlo
    aspettare durante l'eventuale --gps-wait del profilo. Best-effort e
    non bloccante: un fix mancato avvisa ma non impedisce comunque il
    test (mdtcap resta il gate vero e proprio se il profilo lo
    richiede). No-op se doGPSFix=0 (default).

    quiet=True (--edge-mode): nessuna schermata (nessun terminale
    garantito), gli stessi avvisi vanno solo su syslog (vedi
    syslog_log.py)."""
    if not mdtmain_config.get_bool(mdtmain_config.load(), "doGPSFix"):
        return
    if not quiet:
        ui.screen_infobox("Attesa fix GPS...")
    try:
        proc = subprocess.run(
            [constants.MDTGPS, "--autodetect", "--no-banner"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        if quiet:
            syslog_log.error(f"mdtmain: impossibile eseguire mdtgps: {e}")
        else:
            ui.screen_msgbox(f"Impossibile eseguire mdtgps: {e}")
        return
    if proc.returncode == 2:
        if quiet:
            syslog_log.warning("mdtmain: nessun fix GPS ottenuto entro il timeout, il test prosegue comunque.")
        else:
            ui.screen_msgbox("Nessun fix GPS ottenuto entro il timeout: il test prosegue comunque.")


def _ask_sim_pin(init=""):
    """PIN della SIM da passare a mdtcap (--sim-pin). Campo facoltativo
    (si puo' confermare vuoto con "Ok" se la SIM non ha il PIN attivo:
    in quel caso "--sim-pin" non viene proprio aggiunto alla riga di
    comando, vedi i chiamanti); se inserito, deve essere esattamente 4
    cifre numeriche, altrimenti richiede di nuovo. init: valore
    pre-riempito (usato da --auto-start col PIN gia' salvato in
    mdtmain.conf, comunque modificabile/confermabile). Ritorna la
    stringa PIN, "" se lasciata vuota, o None se l'utente ha scelto
    "Annulla"/ESC. Mascherato come la password WiFi (screen_passwordbox),
    trattandosi comunque di un codice sensibile."""
    while True:
        pin = ui.screen_passwordbox("PIN della SIM (lasciare vuoto se non richiesto):", init=init)
        if pin is None:
            return None
        if not pin:
            return ""
        if not (pin.isdigit() and len(pin) == 4):
            ui.screen_msgbox("PIN non valido: deve essere numerico di 4 cifre, oppure lasciato vuoto.")
            init = ""
            continue
        return pin


def _ask_test_duration_minutes():
    """Durata del test in minuti, da convertire in secondi per
    "--duration" di mdtcap. Facoltativa: se lasciata vuota, "--duration"
    non viene passato affatto (la durata dipendera' da quella del
    profilo scelto). Ritorna i SECONDI ("--duration N") come stringa se
    l'utente ha inserito un numero di minuti valido, "" se lasciata
    vuota (nessun --duration), o None se ha scelto "Annulla"/ESC."""
    while True:
        raw = ui.screen_inputbox(
            "Durata del test in minuti (lasciare vuoto per usare quella del profilo):")
        if raw is None:
            return None
        raw = raw.strip()
        if not raw:
            return ""
        if not raw.isdigit() or int(raw) <= 0:
            ui.screen_msgbox(
                "Valore non valido: inserire un numero di minuti maggiore di zero, "
                "oppure lasciare vuoto per usare quella del profilo.")
            continue
        return str(int(raw) * 60)


def _select_mdtcap_profile():
    names = profiles.list_mdtcap_profiles()
    if not names:
        ui.screen_msgbox("Nessun profilo trovato in mdt_configs/profile/.")
        return None
    return ui.screen_menu("Profilo di test", "Selezionare un profilo:", [(n, "") for n in names])


# ---- test in locale (no-save) -------------------------------------------

def _read_report_finale(outdir):
    """Contenuto di report_finale.txt (scritto da mdtcap solo se
    --report e/o --parla-chiaro sono stati richiesti dal profilo — vedi
    manifest["extended"]/i profili in mdt_configs/profile/), o None se
    assente/vuoto. Va sempre letto PRIMA di un eventuale
    evidence.wipe_tmpfs(outdir), che lo cancellerebbe."""
    try:
        with open(os.path.join(outdir, "report_finale.txt"), "r") as f:
            content = f.read().strip()
    except OSError:
        return None
    return content or None


def _run_local_test_core(args, mdtcap_tui=True):
    """Nucleo condiviso fra screen_local_test (dialog) e
    run_local_test_headless (mdtmain --run-local, debug): avvia mdtcap e
    ripulisce sempre lo --shm/outdir temporanei, con o senza il suo
    --tui (vedi mdtcap_tui in runner.run_foreground_with_keypress_stop).
    Ritorna (stop_reason, manifest_dict_or_None, report_text_o_None)."""
    outdir = "/dev/shm/mdtcap_local_data"
    _ensure_gps_fix_if_needed()
    try:
        stop_reason, manifest = runner.run_foreground_with_keypress_stop(
            args, constants.LOCAL_TEST_SHM,
            header_fn=lambda: ui.draw_test_header(has_internet=False),
            max_seconds=constants.LOCAL_TEST_MAX_SECONDS,
            max_bytes=constants.LOCAL_TEST_MAX_BYTES,
            outdir=outdir,
            passthrough_tui=True,
            mdtcap_tui=mdtcap_tui,
        )
        _play_end_of_test_sounds(manifest)
        return stop_reason, manifest, _read_report_finale(outdir)
    finally:
        evidence.wipe_tmpfs(outdir)
        evidence.wipe_tmpfs(constants.LOCAL_TEST_SHM)


def _play_end_of_test_sounds(manifest):
    """Modalita' --screen (sound.py e' un no-op silenzioso altrimenti):
    beep di fine test (sostituisce il carattere BEL di mdtcap --beep,
    che potrebbe non produrre alcun suono udibile su un framebuffer) e,
    se il manifest mostra evidenza (MDT o RRC con posizione), anche
    MDT.wav — solo per test locale/USB, MAI per il test continuato (ha
    la propria logica "sirena", vedi scheduler.py)."""
    sound.beep()
    if manifest and (manifest.get("hasMDT") or manifest.get("hasRRCPos")):
        sound.mdt_found()


def screen_local_test():
    if not _confirm_sim_inserted():
        return
    sim_pin = _ask_sim_pin()
    if sim_pin is None:
        return
    duration_seconds = _ask_test_duration_minutes()
    if duration_seconds is None:
        return
    profile = _select_mdtcap_profile()
    if not profile:
        return
    args = ["--profile", profile]
    if sim_pin:
        args += ["--sim-pin", sim_pin]
    if duration_seconds:
        args += ["--duration", duration_seconds]
    mdtmain_config.apply_forced_extended(args)
    mdtmain_config.apply_test_sms(args)
    args.append("--no-beep")
    stop_reason, manifest, report_text = _run_local_test_core(args)
    ui.screen_msgbox(_format_result(manifest, stop_reason, report_text))


def _format_result(manifest, stop_reason, report_text=None):
    """report_text (report_finale.txt, --report/--parla-chiaro): quando
    presente e' il messaggio principale, gia' pensato per un pubblico non
    tecnico (--parla-chiaro conclude sempre con una frase in linguaggio
    semplice). Senza --report/--parla-chiaro nel profilo, si ripiega sul
    riepilogo sintetico del manifest, con Si'/No al posto dei booleani
    grezzi (non tutti gli utenti li leggono a colpo d'occhio)."""
    if report_text:
        return f"Test terminato ({stop_reason}).\n\n{report_text}"
    if manifest is None:
        return f"Test terminato ({stop_reason}). Nessun manifest.json trovato (errore durante la cattura)."
    si_no = lambda v: "Si'" if v else "No"
    lines = [f"Test terminato ({stop_reason})."]
    lines.append(f"Esito: {si_no(manifest.get('OK'))}")
    lines.append(f"Tracce MDT rilevate: {si_no(manifest.get('hasMDT'))}  "
                 f"Tracce RRC rilevate: {si_no(manifest.get('hasRRC'))}")
    if manifest.get("extended"):
        lines.append(f"Livello controlli extra: {manifest.get('extraLevel')}")
    return "\n".join(lines)


def run_local_test_headless(profile=None, sim_pin=None, duration_minutes=None):
    """mdtmain --run-local: bypassa TUTTE le schermate dialog e lancia il
    test in locale direttamente da riga di comando, con mdtcap SENZA
    --tui (log normale, scorrevole, interamente visibile, banner
    incluso) — pensato per il debug, per isolare se un problema
    all'avvio (es. testo che compare/scompare troppo in fretta sotto la
    TUI) e' in mdtcap stesso o nel wrapper --tui/dialog di mdtmain.
    Stampa il risultato in chiaro su stdout invece che in una msgbox.
    Ritorna il codice di uscita (constants.EXIT_OK/EXIT_ERROR)."""
    if sim_pin and not (sim_pin.isdigit() and len(sim_pin) == 4):
        print("mdtmain --run-local: --sim-pin deve essere numerico di 4 cifre (o omesso).",
              file=sys.stderr)
        return constants.EXIT_ERROR

    duration_seconds = None
    if duration_minutes:
        if not (duration_minutes.isdigit() and int(duration_minutes) > 0):
            print("mdtmain --run-local: --duration deve essere un numero di minuti maggiore di zero.",
                  file=sys.stderr)
            return constants.EXIT_ERROR
        duration_seconds = str(int(duration_minutes) * 60)

    if not profile:
        print("mdtmain --run-local: --profile e' obbligatorio. Profili disponibili "
              "in mdt_configs/profile/:", file=sys.stderr)
        for n in profiles.list_mdtcap_profiles():
            print(f"  {n}", file=sys.stderr)
        return constants.EXIT_ERROR

    args = ["--profile", profile]
    if sim_pin:
        args += ["--sim-pin", sim_pin]
    if duration_seconds:
        args += ["--duration", duration_seconds]
    mdtmain_config.apply_forced_extended(args)
    mdtmain_config.apply_test_sms(args)

    stop_reason, manifest, report_text = _run_local_test_core(args, mdtcap_tui=False)
    print()
    print(_format_result(manifest, stop_reason, report_text))
    return constants.EXIT_OK if manifest is not None else constants.EXIT_ERROR


def run_continuous_headless(schedule=None, profile=None, sim_pin=None,
                             mock_time=None, mock_until=None, dry_run=False):
    """mdtmain --run-local --continuous: collauda lo SCHEDULER (non un
    singolo mdtcap) senza schermate dialog, senza aspettare le vere ore
    del giorno (--mock-time) e, con --dry-run, senza bisogno di un
    modem/una SIM reali. Ogni decisione (avvio/fine finestra, pausa,
    allarme, invio) e' stampata in chiaro su stdout. Ritorna il codice
    di uscita (constants.EXIT_OK/EXIT_ERROR)."""
    if not schedule:
        print("mdtmain --run-local --continuous: --schedule e' obbligatorio. Schedulazioni "
              "disponibili in main_configs/profile/:", file=sys.stderr)
        for n in profiles.list_continuous_schedules():
            print(f"  {n}", file=sys.stderr)
        return constants.EXIT_ERROR
    if not profile:
        print("mdtmain --run-local --continuous: --profile e' obbligatorio. Profili disponibili "
              "in mdt_configs/profile/:", file=sys.stderr)
        for n in profiles.list_mdtcap_profiles():
            print(f"  {n}", file=sys.stderr)
        return constants.EXIT_ERROR
    if sim_pin and not (sim_pin.isdigit() and len(sim_pin) == 4):
        print("mdtmain --run-local --continuous: --sim-pin deve essere numerico di 4 cifre "
              "(o omesso).", file=sys.stderr)
        return constants.EXIT_ERROR

    now_fn = datetime.now
    if mock_time:
        try:
            mock_start = datetime.combine(datetime.now().date(), profiles.parse_hhmm(mock_time))
        except ValueError:
            print(f"mdtmain --run-local --continuous: --mock-time non valido: {mock_time!r} "
                  "(atteso HH:MM).", file=sys.stderr)
            return constants.EXIT_ERROR
        real_at_set = datetime.now()
        now_fn = lambda: mock_start + (datetime.now() - real_at_set)
        print(f"Orologio simulato: parte da {mock_time}, avanza in tempo reale da qui.")

    should_stop = None
    if mock_until:
        try:
            until_t = profiles.parse_hhmm(mock_until)
        except ValueError:
            print(f"mdtmain --run-local --continuous: --mock-until non valido: {mock_until!r} "
                  "(atteso HH:MM).", file=sys.stderr)
            return constants.EXIT_ERROR
        should_stop = lambda: now_fn().time() >= until_t

    def log_fn(msg):
        print(f"[{now_fn():%H:%M:%S}] {msg}")

    def capture_fn(args, outdir, max_seconds, header_fn, extra_status_fn, on_tick):
        log_fn("avvio mdtcap: " + " ".join(args) +
               (f" (max {max_seconds:.0f}s)" if max_seconds is not None else " (nessun tetto)"))
        if dry_run:
            return _dry_run_wait(max_seconds, on_tick, should_stop)
        return runner.run_foreground_with_keypress_stop(
            args, constants.CONTINUOUS_SHM, header_fn=header_fn, extra_status_fn=None,
            max_seconds=max_seconds, outdir=outdir, quiet=True,
            should_stop=should_stop, on_tick=on_tick)

    if not dry_run:
        try:
            _iccid, contract_id = contract.get_sim_user()
        except contract.ContractError as e:
            print(f"mdtmain --run-local --continuous: impossibile leggere la SIM: {e}",
                  file=sys.stderr)
            return constants.EXIT_ERROR
    else:
        contract_id = "DRYRUN"

    print("Premere Ctrl+C per fermare (o attendere --mock-until, se passato).")
    try:
        stop_reason, _manifest = scheduler.run_continuous(
            schedule, profile, contract_id, host=None, sim_pin=sim_pin,
            quiet=True, should_stop=should_stop, now_fn=now_fn, capture_fn=capture_fn,
            network_enabled=False, log_fn=log_fn)
    except profiles.ScheduleSyntaxError as e:
        print(f"mdtmain --run-local --continuous: {e}", file=sys.stderr)
        return constants.EXIT_ERROR
    print(f"\nTerminato: {stop_reason}")
    return constants.EXIT_OK


def _dry_run_wait(max_seconds, on_tick, should_stop):
    """--dry-run: non avvia mdtcap, attende in incrementi di
    POLL_INTERVAL_SECONDS (stessa cadenza del poll reale) cosi'
    on_tick (CHECKPOINT) resta esercitabile anche senza hardware."""
    start = time.monotonic()
    while True:
        if on_tick is not None:
            on_tick()
        if should_stop is not None and should_stop():
            return "signal", None
        elapsed = time.monotonic() - start
        if max_seconds is not None and elapsed >= max_seconds:
            return "finished", None
        remaining = (max_seconds - elapsed) if max_seconds is not None else constants.POLL_INTERVAL_SECONDS
        time.sleep(min(constants.POLL_INTERVAL_SECONDS, max(0.0, remaining)))


def _format_continuous_result(manifest, stop_reason):
    """Come _format_result, ma per il test continuo "nessun manifest"
    non e' per forza un errore (l'utente puo' aver interrotto durante
    una pausa, senza che sia mai partita una finestra di cattura)."""
    if manifest is None:
        return f"Test continuo interrotto ({stop_reason}). Nessuna finestra di cattura completata."
    return _format_result(manifest, stop_reason)


# ---- test su chiavetta USB ------------------------------------------------

def _wait_for_usb_insert():
    """Attesa chiavetta USB con poll periodico: un infobox dialog (si
    disegna e ritorna subito, senza attendere input, vedi ui.screen_infobox)
    invece di testo ANSI grezzo, cosi' resta coerente con il resto della
    grafica dialog. Non si puo' usare un widget dialog "vero" (es.
    inputbox/msgbox) perche' quelli bloccano in attesa di OK/Annulla e non
    si prestano al poll misto tastiera/timer di questo ciclo (stessa
    ragione per cui screen_pause_countdown in ui.py usa anch'esso un
    infobox, non un widget bloccante)."""
    while True:
        candidates = usbmount.list_removable_unmounted()
        if candidates:
            return candidates[0]
        ui.screen_infobox("Inserire una chiavetta USB, oppure premere un tasto per annullare.")
        if not sys.stdin.isatty():
            time.sleep(constants.POLL_INTERVAL_SECONDS)
            continue
        ready, _, _ = select.select([sys.stdin], [], [], constants.POLL_INTERVAL_SECONDS)
        if ready:
            os.read(sys.stdin.fileno(), 1)
            return None


def screen_usb_test():
    if not _confirm_sim_inserted():
        return
    sim_pin = _ask_sim_pin()
    if sim_pin is None:
        return
    duration_seconds = _ask_test_duration_minutes()
    if duration_seconds is None:
        return
    profile = _select_mdtcap_profile()
    if not profile:
        return
    dev = _wait_for_usb_insert()
    if dev is None:
        return
    ok, msg = usbmount.mount_usb(dev["path"])
    if not ok:
        ui.screen_msgbox(f"Impossibile montare la chiavetta: {msg}")
        return
    args = ["--profile", profile]
    if sim_pin:
        args += ["--sim-pin", sim_pin]
    if duration_seconds:
        args += ["--duration", duration_seconds]
    mdtmain_config.apply_forced_extended(args)
    mdtmain_config.apply_test_sms(args)
    args.append("--no-beep")
    outdir = os.path.join(constants.USB_MOUNTPOINT, constants.USB_EVIDENCE_SUBDIR, evidence.timestamp_now())
    _ensure_gps_fix_if_needed()
    try:
        stop_reason, manifest = runner.run_foreground_with_keypress_stop(
            args, constants.USB_TEST_SHM,
            header_fn=lambda: ui.draw_test_header(has_internet=False),
            outdir=outdir,
            passthrough_tui=True,
        )
        _play_end_of_test_sounds(manifest)
        ui.screen_msgbox(_format_result(manifest, stop_reason, _read_report_finale(outdir)))
    finally:
        evidence.wipe_tmpfs(constants.USB_TEST_SHM)
        usbmount.umount_usb()
        ui.screen_msgbox("Rimuovere la chiavetta USB.")


# ---- passi comuni ai test che inviano dati al server (continuo / invio) ----

def _prepare_server_test(confirm_text, prefill_pin=None):
    """Conferma SIM, PIN, conferma esplicita dell'invio cifrato al
    server, lettura ICCID/contractId, configurazione server, verifica
    (ed eventuale registrazione) del contratto — passi comuni a "Imposta
    test continuato" e "Esegui un test inviando i dati". Ritorna
    (sim_pin, iccid, contract_id, host), o None se l'utente ha annullato
    o un passo e' fallito (errore gia' mostrato al chiamante)."""
    if not _confirm_sim_inserted():
        return None
    sim_pin = _ask_sim_pin(init=prefill_pin or "")
    if sim_pin is None:
        return None
    if not ui.screen_yesno(confirm_text):
        return None
    # Da qui in poi solo I/O bloccante (lettura SIM, chiamate al server):
    # senza un indicatore la UI resta ferma sull'ultima schermata per
    # qualche secondo, sembrando bloccata/in crash. "Caricamento..." resta
    # visibile finche' non appare la prossima schermata/msgbox (screen_infobox
    # non richiede una chiusura esplicita, vedi ui.screen_infobox).
    ui.screen_infobox("Caricamento...")
    try:
        iccid, contract_id = contract.get_sim_user()
    except contract.ContractError as e:
        ui.screen_msgbox(f"Impossibile leggere la SIM: {e}")
        return None

    try:
        server = httpclient.load_server_conf()
        host = server["host"]
    except httpclient.ServerError as e:
        ui.screen_msgbox(f"Configurazione server non valida: {e}")
        return None

    registered, reachable = httpclient.verify_contract_with_cache(host, contract_id)
    if not reachable and not registered:
        ui.screen_msgbox("Server non raggiungibile (nessuna verifica precedente in cache).")
        return None
    if not reachable:
        syslog_log.warning(
            f"mdtmain: server non raggiungibile, uso la verifica del contratto in cache ({contract_id}).")

    if not registered:
        token = ui.screen_inputbox("Contratto non registrato. Inserire il token di autorizzazione:")
        if not token:
            return None
        try:
            ok = httpclient.register_token(host, token, contract_id)
        except httpclient.ServerError as e:
            ui.screen_msgbox(f"Registrazione fallita: {e}")
            return None
        if not ok:
            ui.screen_msgbox("Registrazione rifiutata dal server.")
            return None

    return sim_pin, iccid, contract_id, host


_SEND_DATA_WARNING = "Questo test invierà i dati di evidenza al server centrale in modo cifrato."


# ---- test continuo ---------------------------------------------------------

def screen_continuous_test(prefill_pin=None):
    prep = _prepare_server_test(
        f"Confermare l'avvio del test continuo?\n{_SEND_DATA_WARNING}", prefill_pin=prefill_pin)
    if prep is None:
        return
    sim_pin, iccid, contract_id, host = prep

    mdtcap_profile = _select_mdtcap_profile()
    if not mdtcap_profile:
        return

    schedule_names = profiles.list_continuous_schedules()
    if not schedule_names:
        ui.screen_msgbox("Nessuna schedulazione trovata in main_configs/profile/.")
        return
    schedule_name = ui.screen_menu("Schedulazione", "Selezionare una schedulazione:",
                                    [(n, "") for n in schedule_names])
    if not schedule_name:
        return

    # Salvati insieme (non solo PIN/ICCID come prima di --edge-mode):
    # profilo e schedulazione sono scelti qui interattivamente ogni
    # volta, ma --edge-mode/--auto-start/"Riprendi test continuo"
    # (nessuna schermata di selezione) devono poterli ritrovare da soli
    # — vedi mdtmain --help/app.run_edge_mode()/_resume_continuous_test.
    mdtmain_config.update(testPin=sim_pin, testSim=iccid,
                           mdtcapProfile=mdtcap_profile, schedulerProfile=schedule_name)

    _screen_imei_step()
    _ensure_gps_fix_if_needed()

    ui.screen_infobox("Avvio del modulo in corso, attendere...")
    try:
        stop_reason, manifest = scheduler.run_continuous(
            schedule_name, mdtcap_profile, contract_id, host, sim_pin=sim_pin)
    except profiles.ScheduleSyntaxError as e:
        ui.screen_msgbox(f"Schedulazione non valida: {e}")
        return
    ui.screen_msgbox(_format_continuous_result(manifest, stop_reason))


def screen_view_continuous_config():
    """"Visualizza impostazioni test continuo" (menu principale, mostrata
    solo se un test continuato e' completamente configurato, vedi
    screen_main_menu)."""
    config = mdtmain_config.load()
    ui.screen_msgbox(f"Profilo: {config['mdtcapProfile']}")


def _resume_continuous_test(config):
    """Riprende il test continuato gia' configurato (config deve avere
    testSim/mdtcapProfile/schedulerProfile non vuoti, verificato dal
    chiamante) SENZA richiedere PIN/conferma/riselezione profilo: usa
    direttamente i valori salvati. Ferma tutto con una msgbox se l'ICCID
    della SIM inserita non corrisponde a quello configurato. Usata sia
    da "Riprendi test continuo" (menu) sia da --auto-start (run_app)."""
    try:
        iccid, contract_id = contract.get_sim_user()
    except contract.ContractError as e:
        ui.screen_msgbox(f"Impossibile leggere la SIM: {e}")
        return
    if iccid != config["testSim"]:
        ui.screen_msgbox("Errore sim non corrispondente")
        return

    try:
        server = httpclient.load_server_conf()
        host = server["host"]
    except httpclient.ServerError as e:
        ui.screen_msgbox(f"Configurazione server non valida: {e}")
        return
    registered, reachable = httpclient.verify_contract_with_cache(host, contract_id)
    if not reachable and not registered:
        ui.screen_msgbox("Server non raggiungibile (nessuna verifica precedente in cache).")
        return
    if not reachable:
        syslog_log.warning(
            f"mdtmain: server non raggiungibile, riprendo il test continuato usando la "
            f"verifica del contratto in cache ({contract_id}).")
    if not registered:
        ui.screen_msgbox("Contratto non registrato sul server: usare 'Imposta test "
                          "continuato' per registrarlo con un token.")
        return

    _screen_imei_step()
    _ensure_gps_fix_if_needed()
    ui.screen_infobox("Avvio del modulo in corso, attendere...")
    try:
        stop_reason, manifest = scheduler.run_continuous(
            config["schedulerProfile"], config["mdtcapProfile"], contract_id, host,
            sim_pin=config["testPin"])
    except profiles.ScheduleSyntaxError as e:
        ui.screen_msgbox(f"Schedulazione non valida: {e}")
        return
    ui.screen_msgbox(_format_continuous_result(manifest, stop_reason))


def screen_resume_continuous_test():
    """"Riprendi test continuo" (menu principale)."""
    config = mdtmain_config.load()
    _resume_continuous_test(config)


def screen_remove_continuous_test():
    """"Rimuovi test continuo" (menu principale): azzera ICCID/PIN/
    profilo mdtcap/schedulazione salvati (autoStart non viene toccato:
    diventa innocuo da solo, dato che il gate su testSim fallisce)."""
    if not ui.screen_yesno("Confermare la rimozione del test continuato configurato?"):
        return
    mdtmain_config.update(testSim="", testPin="", mdtcapProfile="", schedulerProfile="")
    ui.screen_msgbox("Test continuato rimosso.")


# ---- modalita' --edge-mode (servizio non presidiato) -----------------------

def run_edge_mode():
    """mdtmain --edge-mode: stesso test continuato di "Imposta test
    continuato" sopra, ma pensato per girare come servizio systemd (non
    ancora installato, vedi mdtmain --help) SENZA nessuna schermata (non
    c'e' nessun terminale/nessuna persona che possa rispondere a un
    dialog) — richiede quindi che testSim/mdtcapProfile/schedulerProfile
    siano gia' stati salvati da un uso interattivo precedente di "Imposta test
    continuato" (autoStart=1, il default). A differenza di quella
    schermata: nessuna conferma esplicita di invio dati (implicita nella
    sola esistenza di una configurazione salvata), e nessuna richiesta di
    token se il contratto non risulta registrato (nessuno schermo per
    chiederlo: fallisce con un errore su syslog, da registrare a mano
    prima di riprovare). Ogni evento significativo (avvio/fine
    finestra, allarme, evidenza inviata, errore/blocco) va su syslog
    (vedi syslog_log.py), MAI su schermo. Ritorna
    constants.EXIT_OK/EXIT_ERROR.

    Eccezione: se il test continuato NON e' configurato ma uno schermo
    HDMI risulta collegato e attivo (screenmode.hdmi_display_active()),
    non ci si ferma con un errore — si assume che qualcuno l'abbia
    appena collegato per configurare/usare il device a mano, e si
    propone il menu principale come in un avvio interattivo normale
    (saltando solo la configurazione di rete: --edge-mode non e' pensato
    per quello)."""
    config = mdtmain_config.load()
    if not (mdtmain_config.get_bool(config, "autoStart") and config["testSim"]
            and config["mdtcapProfile"] and config["schedulerProfile"]):
        if screenmode.hdmi_display_active():
            syslog_log.warning(
                "mdtmain: --edge-mode senza test continuato configurato, ma uno schermo HDMI "
                "risulta collegato e attivo: mostro il menu principale invece di fermarmi.")
            try:
                run_app(skip_network_setup=True, force_network_setup=False, auto_start=False)
            except KeyboardInterrupt:
                pass
            finally:
                ui.clear_screen()
            return constants.EXIT_OK
        syslog_log.error(
            "mdtmain: --edge-mode richiede un test continuato gia' configurato "
            "(autoStart/testSim/mdtcapProfile/schedulerProfile): usare prima 'Imposta test "
            "continuato' in modo interattivo, oppure collegare uno schermo HDMI attivo. Arresto.")
        return constants.EXIT_ERROR

    try:
        iccid, contract_id = contract.get_sim_user()
    except contract.ContractError as e:
        syslog_log.error(f"mdtmain: --edge-mode impossibile leggere la SIM ({e}). Arresto.")
        return constants.EXIT_ERROR
    if iccid != config["testSim"]:
        syslog_log.error(
            "mdtmain: --edge-mode l'ICCID della SIM inserita non corrisponde a quello "
            "configurato per il test continuato. Arresto.")
        return constants.EXIT_ERROR

    try:
        server = httpclient.load_server_conf()
        host = server["host"]
    except httpclient.ServerError as e:
        syslog_log.error(f"mdtmain: --edge-mode configurazione server non valida ({e}). Arresto.")
        return constants.EXIT_ERROR

    registered, reachable = httpclient.verify_contract_with_cache(host, contract_id)
    if not reachable and not registered:
        syslog_log.error(
            "mdtmain: --edge-mode server non raggiungibile e nessuna verifica precedente "
            "in cache. Arresto.")
        return constants.EXIT_ERROR
    if not reachable:
        syslog_log.warning(
            f"mdtmain: --edge-mode server non raggiungibile, riprendo usando la verifica "
            f"del contratto in cache ({contract_id}).")
    if not registered:
        syslog_log.error(
            "mdtmain: --edge-mode contratto non registrato sul server (serve un token, "
            "non richiedibile senza schermo: registrarlo con un uso interattivo). Arresto.")
        return constants.EXIT_ERROR

    _ensure_gps_fix_if_needed(quiet=True)

    syslog_log.info(
        f"mdtmain: --edge-mode avvio test continuato (profilo {config['mdtcapProfile']!r}, "
        f"schedulazione {config['schedulerProfile']!r}).")
    try:
        stop_reason, manifest = scheduler.run_continuous(
            config["schedulerProfile"], config["mdtcapProfile"], contract_id, host,
            sim_pin=config["testPin"], quiet=True, should_stop=edgemode.should_stop)
    except Exception as e:  # non deve mai morire in silenzio sotto systemd
        syslog_log.error(f"mdtmain: --edge-mode interrotto da un errore imprevisto: {e}")
        return constants.EXIT_ERROR

    syslog_log.info(f"mdtmain: --edge-mode test continuato terminato ({stop_reason}).")
    return constants.EXIT_OK


# ---- test che invia i dati (come il continuo, ma una tantum) --------------

def screen_send_data_test():
    """Stessa verifica/registrazione contratto e stesso avviso di invio
    cifrato di "Imposta test continuato", ma senza schedulazione: un
    solo mdtcap subito, con durata chiesta esplicitamente invece di una
    finestra oraria. A differenza del test continuato non salva
    PIN/ICCID in mdtmain.conf (nessun test continuato viene configurato
    qui) — unica altra differenza, insieme all'assenza della
    schedulazione."""
    prep = _prepare_server_test(f"Confermare l'avvio del test?\n{_SEND_DATA_WARNING}")
    if prep is None:
        return
    sim_pin, _iccid, contract_id, host = prep

    profile = _select_mdtcap_profile()
    if not profile:
        return
    duration_seconds = _ask_test_duration_minutes()
    if duration_seconds is None:
        return

    _screen_imei_step()

    args = ["--profile", profile]
    if sim_pin:
        args += ["--sim-pin", sim_pin]
    if duration_seconds:
        args += ["--duration", duration_seconds]
    mdtmain_config.apply_forced_extended(args)
    mdtmain_config.apply_test_sms(args)
    args.append("--no-beep")

    persistent_dir = evidence.pick_persistent_dir()
    evidence.cleanup_old_evidence(persistent_dir)
    outdir = os.path.join(persistent_dir, evidence.timestamp_now())
    _ensure_gps_fix_if_needed()
    try:
        stop_reason, manifest = runner.run_foreground_with_keypress_stop(
            args, constants.SEND_TEST_SHM,
            header_fn=lambda: ui.draw_test_header(has_internet=True),
            outdir=outdir,
            passthrough_tui=True,
        )
        _play_end_of_test_sounds(manifest)

        push_ok = None
        if manifest is not None:
            push_ok = scheduler.package_and_push(manifest, outdir, contract_id, host)

        message = _format_result(manifest, stop_reason, _read_report_finale(outdir))
        if push_ok is not None:
            message += f"\n\nInvio al server: {'riuscito' if push_ok else 'fallito'}."
        ui.screen_msgbox(message)
    finally:
        evidence.wipe_tmpfs(constants.SEND_TEST_SHM)
        evidence.cleanup_old_evidence(persistent_dir)


# ---- invio manuale del backlog (log/spool) ---------------------------------

def screen_send_spool_manually():
    """"Invia i dati manualmente" (menu principale, mostrata solo se
    log/spool contiene gia' delle evidenze in attesa — vedi
    screen_main_menu): invia i file rimasti da un invio immediato fallito
    (package_and_push, subito dopo un test) o non ancora tentato dallo
    scheduler (flush_spool, durante una pausa del test continuato), uno
    alla volta, con una msgbox di avanzamento ridisegnata a ogni giro
    (stessa tecnica non bloccante di ui.screen_pause_countdown: si esce
    temporaneamente dal "modo dialog" solo per il poll di tastiera, MAI
    un widget bloccante). "Premere un tasto per fermare" diventa
    "Completo l'ultimo upload..." al primo tasto premuto — l'invio in
    corso finisce comunque (mai interrotto a meta'), solo DOPO
    l'operazione si ferma."""
    if not _confirm_sim_inserted():
        return
    try:
        _iccid, contract_id = contract.get_sim_user()
    except contract.ContractError as e:
        ui.screen_msgbox(f"Impossibile leggere la SIM: {e}")
        return
    try:
        server = httpclient.load_server_conf()
        host = server["host"]
    except httpclient.ServerError as e:
        ui.screen_msgbox(f"Configurazione server non valida: {e}")
        return

    pending = evidence.list_spool_files()
    total = len(pending)
    if total == 0:
        ui.screen_msgbox("Nessuna evidenza in attesa di invio.")
        return

    sent = 0
    stopping = False
    error_detail = None
    is_tty = sys.stdin.isatty()
    old_settings = None
    try:
        if is_tty:
            old_settings = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        for spool_path in pending:
            label = "Completo l'ultimo upload..." if stopping else "Premere un tasto per fermare."
            ui.screen_infobox(f"Invio evidenze in corso: {sent}/{total}.\n{label}")
            ok, detail = scheduler.upload_one(spool_path, contract_id, host, quiet=True)
            if not ok:
                error_detail = detail
                break
            sent += 1
            if stopping:
                break
            if is_tty:
                ready, _, _ = select.select([sys.stdin], [], [], 0)
                if ready:
                    try:
                        os.read(sys.stdin.fileno(), 1)
                    except OSError:
                        pass
                    stopping = True
    finally:
        if is_tty and old_settings is not None:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)

    # Stesso comportamento di retry di scheduler.idle_wait(), ma
    # best-effort e silenzioso: non deve alterare il riepilogo
    # dell'invio manuale sopra (sent/total/error_detail riguardano solo
    # le evidenze, masterSpool.ndjson e' un canale separato).
    try:
        masterlog.flush_masterlog(host)
    except Exception:
        pass

    if error_detail is not None:
        ui.screen_msgbox("Errore upload")
    else:
        ui.screen_msgbox(f"Invio completato ({sent}/{total}).")


def _screen_imei_step():
    """Se e' presente un file per il cambio IMEI (facoltativo,
    funzionalita' sperimentale), lo richiede; se lasciato vuoto,
    l'IMEI di default/fabbrica viene ripristinato. Salta del tutto la
    richiesta (senza nemmeno mostrarla) se disableIMEI=1 in
    mdtmain.conf."""
    if mdtmain_config.get_bool(mdtmain_config.load(), "disableIMEI"):
        return
    if not os.path.isfile(constants.IMEI_AUTH_FILE):
        return
    if not ui.screen_yesno("E' presente un'autorizzazione al cambio IMEI. Applicarla ora?"):
        return
    ui.screen_msgbox("Gestione IMEI: usare mdtimei direttamente per applicare/ripristinare l'IMEI "
                      "(mdtmain non lo automatizza in questa versione).")


# ---- test baseband (mdtdiag) ------------------------------------------------

_PAREN_RE = re.compile(r"\s*\([^)]*\)")
_BASEBAND_FIELDS = ["Modulo", "IMEI", "ICCID", "IMSI"]


def _strip_parens(text):
    """Rimuove eventuali parentesi tonde e il loro contenuto (es. "(fw
    X)", "(SIM bloccata o non inserita)"), per un valore piu' sintetico
    nella msgbox."""
    return _PAREN_RE.sub("", text).strip()


def _parse_labeled_block(text):
    """Righe "Label   : valore" in un dict {label.strip(): valore.strip()}
    (ultima vince se un'etichetta compare piu' volte). Righe senza ":" o
    vuote vengono ignorate — cosi' i messaggi di log (su stderr, mai
    catturati qui) e le intestazioni "=== ... ===" non finiscono nel
    risultato."""
    fields = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        fields[label.strip()] = value.strip()
    return fields


def screen_baseband_test():
    ui.screen_infobox("Attendere...")
    try:
        proc = subprocess.run(
            [constants.MDTDIAG, "--autodetect", "--no-banner"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        ui.screen_msgbox(f"Impossibile eseguire mdtdiag: {e}", title="Test baseband")
        return
    fields = _parse_labeled_block(proc.stdout.decode(errors="replace"))
    lines = [f"{label}: {_strip_parens(fields[label])}"
             for label in _BASEBAND_FIELDS if label in fields]
    if not lines:
        ui.screen_msgbox("Impossibile leggere l'identita' del modulo/SIM "
                          "(modem non rilevato o nessuna risposta).", title="Test baseband")
        return
    ui.screen_msgbox("Identita' modulo/SIM:\n" + "\n".join(lines), title="Test baseband")


# ---- test GPS (mdtgps) --------------------------------------------------

_GPS_FIELDS = ["Latitudine", "Longitudine", "Altitudine (MSL)", "Velocita' sul terreno"]


def screen_gps_test():
    ui.screen_infobox("Attendere...")
    try:
        proc = subprocess.run(
            [constants.MDTGPS, "--autodetect", "--no-banner"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        ui.screen_msgbox(f"Impossibile eseguire mdtgps: {e}", title="Test GPS")
        return
    if proc.returncode == 2:
        ui.screen_msgbox("Nessun fix GPS ottenuto entro il timeout.", title="Test GPS")
        return
    fields = _parse_labeled_block(proc.stdout.decode(errors="replace"))
    lines = [f"{label}: {fields[label]}" for label in _GPS_FIELDS if label in fields]
    if not lines:
        ui.screen_msgbox("Impossibile leggere la posizione GPS (modem non rilevato o nessuna risposta).",
                          title="Test GPS")
        return
    ui.screen_msgbox("\n".join(lines), title="Test GPS")


# ---- identita' sistema (mdtcontract --get-keys) -----------------------------

def screen_system_identity():
    try:
        keys = contract.get_keys()
    except contract.ContractError as e:
        ui.screen_msgbox(f"Impossibile leggere l'identita' di sistema: {e}", title="Identita' sistema")
        return
    missing = "(assente)"
    lines = [
        f"DVID: {keys.get('DVID', '')}",
        f"CODE: {keys.get('CODE', '')}",
        "",
        f"AUTH: {keys.get('AUTH') or missing}",
        f"IMEI: {keys.get('IMEI') or missing}",
        f"DATA: {keys.get('DATA') or missing}",
    ]
    ui.screen_msgbox("\n".join(lines), title="Identita' sistema")


# ---- download configurazione ------------------------------------------------

def screen_download_config():
    try:
        token = contract.get_imei_token()
        devid = contract.get_devid()
    except contract.ContractError as e:
        ui.screen_msgbox(f"Impossibile calcolare token/devId: {e}")
        return

    try:
        server = httpclient.load_server_conf()
        host = server["host"]
    except httpclient.ServerError as e:
        ui.screen_msgbox(f"Configurazione server non valida: {e}")
        return

    try:
        data = httpclient.download_imei_auth(host, token)
    except httpclient.ServerError as e:
        ui.screen_msgbox(f"Download fallito: {e}")
        return
    if data is None:
        ui.screen_msgbox("Nessuna configurazione disponibile per questo device (404).")
        return

    fd, tmp_path = tempfile.mkstemp(prefix="mdtmain-imei-auth-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        proc = subprocess.run(
            [constants.TESTAUTH, "--auth-file", tmp_path, "--DEVID", devid],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            ui.screen_msgbox("Verifica della firma fallita: " +
                              proc.stderr.decode(errors="replace").strip())
        else:
            os.makedirs(os.path.dirname(constants.IMEI_AUTH_FILE), exist_ok=True)
            shutil.copy2(tmp_path, constants.IMEI_AUTH_FILE)
            ui.screen_msgbox("Configurazione scaricata e verificata con successo.")
    finally:
        os.remove(tmp_path)

    reason = ui.screen_inputbox("Motivazione (max 512 caratteri):", width=76)
    if reason:
        try:
            httpclient.submit_imei_request(host, token, devid, reason)
        except httpclient.ServerError as e:
            ui.screen_msgbox(f"Invio motivazione fallito: {e}")
