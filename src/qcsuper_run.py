#!/usr/bin/env python3
"""Lanciatore di qcsuper per la cattura live di mdtcap (vedi mdtcap
--full-diag-log e start_qcsuper_capture()).

qcsuper --dlf-dump registra il modulo DlfDumper DOPO PcapDumper e, a
differenza di quest'ultimo, non imposta "limit_registered_logs": abilita
quindi sul modem TUTTI i log code di tutti i sottosistemi. La maschera del
modem e' unica, per cui vince l'ultima inviata. Su un SIM7600 il risultato
misurato e' di ~250 record/s, solo lo 0,03% LTE-RRC, con qcsuper al 95-100%
di CPU: proprio le raffiche di un attach vengono perse a monte, senza
traccia nei log. Questo lanciatore limita DlfDumper alla stessa lista di
log di protocollo di PcapDumper (RRC 2G/3G/4G/5G, NAS 3G/4G), poi esegue il
normale main() di qcsuper con gli stessi argomenti: il .dlf resta un dump
qcsuper/QXDM valido, solo senza i log fisici/di sistema che nessuna analisi
di mdtcap usa.

Ripristina anche la gestione di SIGINT. mdtcap avvia qcsuper in
background ("&") da uno script bash non interattivo: in quel caso bash
lo fa partire con SIGINT IGNORATO, e Python non installa il proprio
gestore (KeyboardInterrupt). Il "kill -INT" con cui mdtcap chiede a
qcsuper di chiudersi (finalize) non aveva quindi mai effetto: dopo 15s
qcsuper veniva sempre terminato con SIGKILL, senza scrivere gli ultimi
dati e senza disattivare la maschera di log sul modem.

Uso: qcsuper_run.py [--full-mask] QCSUPER_BIN [argomenti di qcsuper...]
--full-mask non limita la maschera (mdtcap --full-diag-log), ma
ripristina comunque SIGINT. QCSUPER_BIN e' l'eseguibile/script di qcsuper
configurato in mdtcap (--qcsuper): se e' un sorgente non installato come
pacchetto, la sua cartella viene aggiunta a sys.path prima dell'import."""
import os
import signal
import sys
import time

# Il .dlf viene letto mentre qcsuper lo scrive (mdtcap --self-test,
# --mdt-led): DlfDumper non svuota mai il buffer del file e, con la
# maschera ridotta, pochi record possono restare in memoria per minuti.
# Lo svuotiamo al massimo una volta ogni FLUSH_INTERVAL_S.
FLUSH_INTERVAL_S = 1.0


def _patch_periodic_flush(dlf_dumper_cls):
    original_on_log = dlf_dumper_cls.on_log

    def on_log(self, *args, **kwargs):
        result = original_on_log(self, *args, **kwargs)
        now = time.monotonic()
        if now - getattr(self, "_mdtcap_last_flush", 0.0) >= FLUSH_INTERVAL_S:
            self.dlf_file.flush()
            self._mdtcap_last_flush = now
        return result

    dlf_dumper_cls.on_log = on_log


def main():
    args = sys.argv[1:]
    full_mask = bool(args) and args[0] == "--full-mask"
    if full_mask:
        args = args[1:]
    if not args:
        print("uso: qcsuper_run.py [--full-mask] QCSUPER_BIN [argomenti qcsuper...]", file=sys.stderr)
        return 2
    signal.signal(signal.SIGINT, signal.default_int_handler)
    qcsuper_bin = os.path.realpath(args[0])
    # Un checkout sorgente di qcsuper (es. .../QCSuper/qcsuper.py) contiene
    # il pacchetto "qcsuper" accanto allo script: va reso importabile.
    sys.path.insert(0, os.path.dirname(qcsuper_bin))

    from qcsuper.modules import dlf_dump
    from qcsuper.modules._enable_log_mixin import TYPES_FOR_RAW_PACKET_LOGGING
    from qcsuper.main import main as qcsuper_main

    if not full_mask:
        # Attributo di classe: _fill_log_mask() lo cerca con hasattr(self, ...)
        dlf_dump.DlfDumper.limit_registered_logs = list(TYPES_FOR_RAW_PACKET_LOGGING)
    _patch_periodic_flush(dlf_dump.DlfDumper)

    sys.argv = [qcsuper_bin] + args[1:]
    return qcsuper_main()


if __name__ == "__main__":
    sys.exit(main())
