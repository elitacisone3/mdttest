#!/usr/bin/env python3
"""Azzera la maschera di log DIAG del modem dopo una chiusura forzata di
qcsuper (vedi mdtcap: finalize() e il marcatore DIAG_DIRTY_MARKER).

Perche': se qcsuper viene terminato con SIGKILL non esegue la propria
pulizia (on_deinit), e la maschera di log che aveva impostato resta attiva
sul modem, che continua a inviare log sulla porta DIAG anche a cattura
finita. Con la maschera "tutti i log" (qcsuper --dlf-dump senza
limitazioni, vedi src/qcsuper_run.py) il flusso e' tale che, alla cattura
successiva, la richiesta con cui qcsuper disattiva/configura i log
(DIAG_LOG_CONFIG_F) va in timeout: la risposta si perde nel flusso e i log
non vengono abilitati.

Per questo il reset NON usa il meccanismo richiesta/risposta di qcsuper:
invia piu' volte (incapsulati HDLC, con lo stesso codice di qcsuper) gli
stessi due comandi che qcsuper manda all'avvio:
  - DIAG_LOG_CONFIG_F con LOG_CONFIG_DISABLE_OP (disattiva tutti i log)
  - DIAG_EXT_MSG_CONFIG_F, SET_ALL_RT_MASKS a MSG_LVL_NONE (messaggi debug)
svuotando nel frattempo l'ingresso a blocchi grandi, poi verifica l'effetto
misurando il flusso in ingresso (byte/s) prima e dopo.

Uso: diag_mask_reset.py QCSUPER_BIN DIAG_ARG
DIAG_ARG e' lo stesso valore passato a "qcsuper --usb-modem": un device
(/dev/ttyUSB0), "VID:PID" o "auto". Per VID:PID/auto il device viene
risolto con il codice di qcsuper; se il modem non espone un tty si usa
direttamente l'endpoint USB.

Stampa una riga "reset pre=<B/s> post=<B/s> ok=<0|1> via=<tty|usb>".
Exit: 0 reset verificato, 1 flusso ancora presente, 2 errore (porta non
apribile/non trovata)."""
import os
import sys
import time
from struct import pack

# Opcode/costanti come in qcsuper (protocol/messages.py, inputs/_base_input.py)
DIAG_LOG_CONFIG_F = 115
DIAG_EXT_MSG_CONFIG_F = 125
LOG_CONFIG_DISABLE_OP = 0
MSG_EXT_SUBCMD_SET_ALL_RT_MASKS = 5
MSG_LVL_NONE = 0

# Sotto questo flusso residuo (byte/s) la maschera e' considerata azzerata:
# un modem senza log attivi non invia praticamente nulla sulla porta DIAG.
OK_THRESHOLD_BPS = 512
MEASURE_SECONDS = 2.0
ATTEMPTS = 3


def build_frames(hdlc):
    trailer = hdlc.TRAILER_CHAR
    frames = []
    for opcode, payload in ((DIAG_LOG_CONFIG_F, pack("<3xI", LOG_CONFIG_DISABLE_OP)),
                            (DIAG_EXT_MSG_CONFIG_F,
                             pack("<BxxI", MSG_EXT_SUBCMD_SET_ALL_RT_MASKS, MSG_LVL_NONE))):
        # Il trailer iniziale chiude un eventuale frame parziale ancora nel
        # buffer del modem, cosi' il comando viene riconosciuto da solo.
        frames.append(trailer + hdlc.hdlc_encapsulate(bytes([opcode]) + payload))
    return frames


class TtyPort:
    via = "tty"

    def __init__(self, path):
        import termios
        import tty
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            tty.setraw(self.fd)
        except termios.error:
            pass

    def write(self, data):
        os.write(self.fd, data)

    def drain(self, seconds):
        import select
        total = 0
        end = time.monotonic() + seconds
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return total
            ready, _, _ = select.select([self.fd], [], [], min(left, 0.2))
            if ready:
                try:
                    total += len(os.read(self.fd, 65536))
                except BlockingIOError:
                    pass

    def close(self):
        os.close(self.fd)


class UsbPort:
    via = "usb"

    def __init__(self, dev_intf):
        self.dev = dev_intf

    def write(self, data):
        self.dev.write_endpoint.write(data)

    def drain(self, seconds):
        from usb.core import USBError
        total = 0
        end = time.monotonic() + seconds
        size = getattr(self.dev.read_endpoint, "wMaxPacketSize", 512) * 64
        while time.monotonic() < end:
            try:
                total += len(self.dev.read_endpoint.read(size, timeout=200))
            except USBError:
                pass
        return total

    def close(self):
        pass


def open_port(diag_arg):
    from qcsuper.inputs.usb_modem_argparser import UsbModemArgParser, UsbModemArgType
    if diag_arg.startswith("/dev/"):
        return TtyPort(diag_arg)
    usb_arg = UsbModemArgParser(diag_arg)
    if not usb_arg.arg_type:
        raise OSError(f"argomento DIAG non valido: {diag_arg!r}")
    if usb_arg.arg_type == UsbModemArgType.pyserial_dev:
        return TtyPort(usb_arg.pyserial_device)
    from qcsuper.inputs.usb_modem_pyusb_devfinder import PyusbDevInterface
    dev_intf = PyusbDevInterface.from_arg(usb_arg)
    if dev_intf.not_found_reason:
        raise OSError(f"interfaccia DIAG non trovata ({dev_intf.not_found_reason})")
    if dev_intf.chardev_if_mounted:
        return TtyPort(dev_intf.chardev_if_mounted)
    return UsbPort(dev_intf)


def main():
    if len(sys.argv) != 3:
        print("uso: diag_mask_reset.py QCSUPER_BIN DIAG_ARG", file=sys.stderr)
        return 2
    sys.path.insert(0, os.path.dirname(os.path.realpath(sys.argv[1])))
    from qcsuper.inputs._hdlc_mixin import HdlcMixin

    try:
        port = open_port(sys.argv[2])
    except Exception as e:  # porta assente/occupata/libusb: mai fatale per mdtcap
        print(f"reset errore: {e}")
        return 2

    try:
        pre = port.drain(MEASURE_SECONDS) / MEASURE_SECONDS
        frames = build_frames(HdlcMixin())
        for _ in range(ATTEMPTS):
            for frame in frames:
                port.write(frame)
            port.drain(0.5)
        post = port.drain(MEASURE_SECONDS) / MEASURE_SECONDS
    except Exception as e:
        print(f"reset errore: {e}")
        return 2
    finally:
        port.close()

    ok = post < OK_THRESHOLD_BPS
    print(f"reset pre={pre:.0f} post={post:.0f} ok={int(ok)} via={port.via}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
