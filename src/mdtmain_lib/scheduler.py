"""Scheduler del test continuo: legge una schedulazione (DSL
START/IN/EVERY/CHECKPOINT, vedi profiles.py) da
main_configs/profile/<nome>.conf ed esegue mdtcap secondo le finestre
attive, gestendo pausa/ripresa, allarmi, invio al server e retention."""
import os
import time
from datetime import datetime, timedelta

from . import (alarmstate, constants, evidence, httpclient, masterlog, mdtmain_config,
               profiles, runner, sound, status, syslog_log, ui)

# Intervallo minimo fra due tentativi di flush_spool() durante le pause
# del test continuo (vedi run_continuous): un valore basso farebbe
# ripetere /CHECK sul server troppo spesso quando c'e' un backlog e il
# server e' irraggiungibile per un periodo lungo.
SPOOL_RETRY_SECONDS = 60


def _default_capture_fn(quiet, should_stop):
    def _capture(args, outdir, max_seconds, header_fn, extra_status_fn, on_tick):
        return runner.run_foreground_with_keypress_stop(
            args, constants.CONTINUOUS_SHM, header_fn=header_fn, extra_status_fn=extra_status_fn,
            max_seconds=max_seconds, outdir=outdir, quiet=quiet,
            should_stop=should_stop, on_tick=on_tick)
    return _capture


def run_continuous(schedule_name, mdtcap_profile_name, contract, host, sim_pin=None,
                    quiet=False, should_stop=None,
                    now_fn=None, capture_fn=None, network_enabled=True, log_fn=None):
    """Ciclo principale, bloccante: torna (stop_reason, ultimo manifest o
    None) quando l'utente preme un tasto (durante una cattura o in pausa)
    per fermare il test continuo (stop_reason "user_keypress" in
    entrambi i casi, cosi' il chiamante puo' mostrare un riepilogo finale
    con lo stesso formato del test locale/USB, vedi _format_result in
    app.py) — oppure quando should_stop() ritorna True (stop_reason
    "signal", usata da --edge-mode per un arresto pulito su SIGTERM, vedi
    edgemode.py). Puo' sollevare profiles.ScheduleSyntaxError se la
    schedulazione non e' valida: il chiamante deve gestirla (msgbox
    interattiva, o syslog_log.error + EXIT_ERROR in --edge-mode/nel
    percorso di collaudo).

    quiet=True (--edge-mode): nessuna schermata dialog (ne' la pausa fra
    una finestra e la successiva, ne' l'upload delle evidenze), sostituita
    da una semplice attesa; ogni evento significativo va comunque su
    syslog (vedi syslog_log.py — no-op finche' non abilitato, quindi
    innocuo per l'uso interattivo normale).

    now_fn/capture_fn/network_enabled/log_fn: SOLO per il collaudo dello
    scheduler (mdtmain --run-local --continuous --mock-time, vedi
    app.run_continuous_headless) — con i default (None/None/True/None)
    il comportamento e' quello di produzione di sempre: now_fn diventa
    datetime.now, capture_fn la vera runner.run_foreground_with_keypress_stop,
    network_enabled resta True, log_fn un no-op. Iniezione esplicita di
    dipendenze (mai una variabile globale mutabile), stesso spirito di
    src/testauth."""
    now_fn = now_fn or datetime.now
    log_fn = log_fn or (lambda msg: None)
    capture_fn = capture_fn or _default_capture_fn(quiet, should_stop)

    schedule_path = os.path.join(constants.CONTINUOUS_SCHEDULE_DIR, schedule_name + ".conf")
    lines = profiles.parse_schedule(schedule_path)  # puo' sollevare ScheduleSyntaxError
    day_state = status.DayState.new(now_fn)
    persistent_dir = evidence.pick_persistent_dir()
    evidence.cleanup_old_evidence(persistent_dir)

    last_manifest = None
    next_spool_attempt = 0.0

    def evaluate_checkpoints():
        """Valuta tutti i comandi CHECKPOINT della schedulazione: chiamata
        sia dal loop esterno sia come on_tick DURANTE una cattura (un
        CHECKPOINT non lancia mai mdtcap, quindi va bene valutarlo con
        la stessa cadenza di poll di tutto il resto, cattura in corso o
        no — necessario perche' un CHECKPOINT annidato dentro una
        finestra IN/EVERY lunga possa davvero scattare)."""
        if not mdtmain_config.get_bool(mdtmain_config.load(), "alarmCheckPoint"):
            return
        now = now_fn().time()
        for idx, line in enumerate(lines):
            if line.kind != "CHECKPOINT" or day_state.checkpoint_fired.get(idx):
                continue
            if not profiles.in_window(line, now):
                continue
            if not alarmstate.is_alarm_pending(now_fn):
                continue
            sound.siren()
            msg = f"mdtmain: ALLARME (checkpoint {line.start}-{line.end})."
            syslog_log.warning(msg)
            log_fn(msg)
            alarmstate.mark_alarm_played(now_fn)
            day_state.checkpoint_fired[idx] = True

    def run_one_capture(line, max_seconds, label):
        nonlocal last_manifest
        outdir = os.path.join(persistent_dir, evidence.timestamp_now())
        args = ["--profile", mdtcap_profile_name, *line.args]
        if sim_pin:
            args += ["--sim-pin", sim_pin]
        mdtmain_config.apply_forced_extended(args)
        mdtmain_config.apply_test_sms(args)
        args.append("--no-beep")
        extra_active = "--extra" in args or "--extended" in args

        msg = f"mdtmain: avvio test continuato ({label})."
        syslog_log.info(msg)
        log_fn(msg)

        stop_reason, manifest = capture_fn(
            args, outdir, max_seconds,
            header_fn=lambda: ui.draw_test_header(has_internet=True),
            extra_status_fn=lambda shm: status.render_dots(
                shm, manifest=None, extra_active=extra_active, day_state=day_state),
            on_tick=evaluate_checkpoints)

        if manifest is not None:
            last_manifest = manifest
            msg = (f"mdtmain: test terminato ({stop_reason}); "
                   f"MDT={manifest.get('hasMDT')} RRC-posizione={manifest.get('hasRRCPos')} "
                   f"controlli extra={manifest.get('extraLevel')}.")
            syslog_log.info(msg)
            log_fn(msg)
        else:
            msg = (f"mdtmain: test terminato senza manifest ({stop_reason}): "
                   "probabile errore/blocco durante la cattura, vedi i log di mdtcap.")
            syslog_log.warning(msg)
            log_fn(msg)

        alarmstate.record_test_result(manifest, now_fn)
        status.update_day_state_from_manifest(day_state, manifest, extra_active)
        _maybe_play_alarm(day_state, now_fn, log_fn)

        if stop_reason not in ("user_keypress", "signal"):
            if network_enabled and manifest is not None:
                package_and_push(manifest, outdir, contract, host, day_state, quiet=quiet)
            evidence.cleanup_old_evidence(persistent_dir)
        return stop_reason

    def idle_wait(next_event_time):
        nonlocal next_spool_attempt
        if should_stop is not None and should_stop():
            return "signal"
        evaluate_checkpoints()
        # Mentre non si sta facendo un test, ne approfitta per smaltire
        # un eventuale backlog di evidenze non ancora inviate — non a
        # ogni giro di questo loop (~POLL_INTERVAL_SECONDS), altrimenti
        # un server irraggiungibile per ore farebbe ripetere /CHECK ogni
        # pochi secondi per niente.
        if network_enabled and time.monotonic() >= next_spool_attempt:
            flush_spool(contract, host, quiet=quiet)
            masterlog.flush_masterlog(host)
            next_spool_attempt = time.monotonic() + SPOOL_RETRY_SECONDS
        if quiet:
            time.sleep(constants.POLL_INTERVAL_SECONDS)
            return None
        if ui.screen_pause_countdown(next_event_time):
            return "user_keypress"
        return None

    # --- START: eseguono in sequenza all'avvio/ripresa di QUESTA
    # esecuzione, nessuna finestra oraria coinvolta (piu' righe START
    # sono ammesse: nessun caso speciale, eseguono tutte in ordine). ---
    for line in lines:
        if line.kind != "START":
            continue
        if should_stop is not None and should_stop():
            return "signal", last_manifest
        stop_reason = run_one_capture(line, max_seconds=None, label="START")
        if stop_reason in ("user_keypress", "signal"):
            return stop_reason, last_manifest

    while True:
        day_state.refresh_day()
        if should_stop is not None and should_stop():
            return "signal", last_manifest
        now_dt = now_fn()
        now = now_dt.time()

        evaluate_checkpoints()

        idx = profiles.active_index(lines, now, kinds=("IN", "EVERY"))
        consumed = day_state.window_consumed_until.get(idx) if idx is not None else None
        pause_until = day_state.every_pause_until.get(idx) if idx is not None else None
        pausing = pause_until is not None and now < pause_until

        if idx is None or (consumed is not None and now < consumed) or pausing:
            next_event = pause_until if pausing else profiles.next_window_start(lines, now, kinds=("IN", "EVERY"))
            stop = idle_wait(next_event)
            if stop:
                return stop, last_manifest
            continue

        line = lines[idx]
        if line.kind == "IN":
            window_end = line.end
        else:  # EVERY
            cycle_end_dt = min(now_dt + timedelta(minutes=line.every_minutes),
                                datetime.combine(now_dt.date(), line.end))
            window_end = cycle_end_dt.time()

        max_seconds = max(0.0, (datetime.combine(now_dt.date(), window_end) - now_dt).total_seconds())
        stop_reason = run_one_capture(line, max_seconds, label=f"{line.kind} fino alle {window_end}")

        if line.kind == "IN":
            day_state.window_consumed_until[idx] = line.end
        else:
            done = day_state.every_cycles_done.get(idx, 0) + 1
            day_state.every_cycles_done[idx] = done
            reached_max = line.max_cycles is not None and done >= line.max_cycles
            if window_end >= line.end or reached_max:
                day_state.window_consumed_until[idx] = line.end
            else:
                day_state.every_pause_until[idx] = (
                    datetime.combine(now_dt.date(), window_end) + timedelta(minutes=line.pause_minutes)
                ).time()

        if stop_reason in ("user_keypress", "signal"):
            return stop_reason, last_manifest


def _maybe_play_alarm(day_state, now_fn, log_fn):
    """Sirena (sound.py — no-op silenzioso fuori dalla modalita'
    --screen): al piu' una volta al giorno, solo nella finestra oraria
    configurata (minAlarmHour/maxAlarmHour) e se gli allarmi non sono
    disattivati (disableAlarm), quando c'e' un flag di evidenza pendente
    (vedi alarmstate.py — condiviso col comando CHECKPOINT dello
    scheduler: qualunque dei due suona per primo consuma il flag per
    l'altro)."""
    if day_state.alarm_played_today:
        return
    config = mdtmain_config.load()
    if mdtmain_config.get_bool(config, "disableAlarm"):
        return
    min_hour = mdtmain_config.get_hour(config, "minAlarmHour")
    max_hour = mdtmain_config.get_hour(config, "maxAlarmHour")
    hour = now_fn().hour
    in_window = (min_hour <= hour <= max_hour) if min_hour <= max_hour \
        else (hour >= min_hour or hour <= max_hour)  # finestra "avvolgente" (es. 22-6)
    if not in_window or not alarmstate.is_alarm_pending(now_fn):
        return
    sound.siren()
    alarmstate.mark_alarm_played(now_fn)
    msg = "mdtmain: ALLARME - rilevata possibile evidenza di tracciamento MDT."
    syslog_log.warning(msg)
    log_fn(msg)
    day_state.alarm_played_today = True


def upload_one(spool_path, contract, host, quiet=False):
    """Invia UN file gia' pronto in log/spool (vedi
    evidence.prepare_for_upload) e, se l'invio riesce, lo rimuove da li'
    (mai altrimenti: resta in attesa di un tentativo successivo). Usata
    sia subito dopo un test (package_and_push sotto) sia per i tentativi
    successivi su un backlog (flush_spool sotto, e
    app.screen_send_spool_manually per l'invio manuale). Ritorna
    (ok, dettaglio_errore_o_None)."""
    dirname = evidence.spool_dirname(spool_path)
    try:
        local_sha = evidence.sha256_file(spool_path)
        if not quiet:
            ui.screen_infobox("Upload delle evidenze...")
        remote_sha = httpclient.push_evidence(host, contract, dirname, spool_path)
        ok = remote_sha == local_sha
        fail_detail = None if ok else "hash locale/remoto non corrispondente"
    except httpclient.ServerError as e:
        ok = False
        fail_detail = str(e)
    if ok:
        evidence.remove_from_spool(spool_path)
        syslog_log.info(f"mdtmain: evidenza inviata al server ({dirname}).")
    else:
        syslog_log.error(f"mdtmain: invio evidenza al server fallito ({dirname}): {fail_detail}.")
    alarmstate.record_evidence_sent(ok, positive=evidence.spool_is_full(spool_path))
    return ok, fail_detail


def package_and_push(manifest, outdir, contract, host, day_state=None, quiet=False):
    """Impacchetta (tar.gz, solo manifest.json se should_keep_full_evidence
    dice di no) e cifra (GPG) l'evidenza di outdir in log/spool (vedi
    evidence.prepare_for_upload), poi tenta SUBITO l'invio (upload_one) —
    se fallisce, il file resta in spool per un tentativo successivo
    (flush_spool sotto, o un invio manuale, vedi
    app.screen_send_spool_manually). day_state, se fornito, viene
    aggiornato per il pallino "Invio dati" del test continuo. Usata anche
    da "Esegui un test inviando i dati" (senza day_state, vedi app.py),
    che si affida al valore di ritorno per segnalare l'esito dell'invio
    all'utente. PRIMA di impacchettare l'evidenza, invoca srv/scanlogs
    (vedi masterlog.py) e ne accumula l'output ndjson in
    log/masterSpool.ndjson/log/master.ndjson, tentando SUBITO l'invio
    (masterlog.flush_masterlog) esattamente come per l'evidenza sopra —
    altrimenti un test singolo (non continuato, quindi senza il ciclo
    idle_wait che riprova periodicamente flush_masterlog) non invierebbe
    mai il masterLog finche' non si apre manualmente "Invia i dati
    manualmente". Un fallimento di scanlogs/flush_masterlog e' solo
    loggato, non blocca mai il tar.gz/l'invio dell'evidenza vera, che
    resta il deliverable critico di questa funzione."""
    try:
        ndjson = masterlog.run_scanlogs(outdir)
    except masterlog.ScanlogsError as e:
        syslog_log.error(f"mdtmain: scanlogs fallito ({e}); proseguo con l'invio evidenza.")
    else:
        masterlog.append_scan_output(ndjson)
        try:
            masterlog.flush_masterlog(host)
        except Exception as e:
            syslog_log.error(f"mdtmain: invio immediato masterLog fallito ({e}); riprovera' piu' tardi.")

    try:
        spool_path = evidence.prepare_for_upload(outdir, manifest)
    except evidence.EvidenceError as e:
        ok = False
        syslog_log.error(f"mdtmain: preparazione evidenza fallita ({e}).")
    else:
        ok, _detail = upload_one(spool_path, contract, host, quiet=quiet)
    if day_state is not None:
        status.record_push_result(day_state, ok=ok)
    return ok


def flush_spool(contract, host, quiet=False, limit=constants.SPOOL_UPLOAD_LIMIT_PER_CYCLE):
    """Da chiamare quando mdtmain NON sta facendo un test (vedi
    run_continuous sopra, durante la pausa fra una finestra e la
    successiva): se ci sono evidenze non ancora inviate in log/spool
    (es. da un invio immediato fallito in package_and_push), prova a
    inviarne fino a "limit" — non tutte in un colpo solo, per non tenere
    occupata a lungo la pausa con un backlog grande — ma solo se il
    server risponde a /CHECK (httpclient.check_server_reachable):
    altrimenti non tenta nessun invio. Si ferma al primo invio fallito
    in questo ciclo (probabile problema piu' ampio, es. server appena
    tornato irraggiungibile a meta'): i file restanti aspetteranno il
    prossimo ciclo. Ritorna il numero di file inviati con successo."""
    pending = evidence.list_spool_files()
    if not pending:
        return 0
    if not quiet:
        ui.screen_infobox("Upload evidenze...")
    try:
        reachable = httpclient.check_server_reachable(host)
    except httpclient.ServerError:
        reachable = False
    if not reachable:
        return 0
    sent = 0
    for spool_path in pending[:limit]:
        ok, _detail = upload_one(spool_path, contract, host, quiet=True)
        if not ok:
            break
        sent += 1
    if sent:
        syslog_log.info(f"mdtmain: {sent} evidenza/e in attesa inviate dallo scheduler.")
    return sent
