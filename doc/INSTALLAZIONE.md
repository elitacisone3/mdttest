# Installazione

```bash
sudo ./install.sh
```

Verifica e installa le dipendenze mancanti (`python3`, `pip3`, `tshark`,
`qcsuper`, `dialog`/`pythondialog`), controlla
`udevadm`/`sha256sum`/`stty`/`timeout` e rende eseguibili `mdtcap` e
`mdtmain`. Vedi i dettagli più sotto in questo documento.

## Prerequisiti

- Eseguire come **root** (serve accesso raw alla porta Diag).
- Modulo USB collegato e riconosciuto (porte `/dev/ttyUSB*`).
- `qcsuper` installato (eseguibile o script `.py`).
- `python3`, `sha256sum`, `stty` disponibili (verificati automaticamente).
- `tshark` opzionale: se presente, lo script estrae anche i report
  MDT/RRC e le coordinate decodificate a fine cattura.
- `dialog` (binario) e `pythondialog` (pacchetto pip, import Python
  `dialog`) opzionali: richiesti solo da `mdtmain`, l'interfaccia guidata
  in stile raspi-config (vedi [doc/MDTMAIN.md](MDTMAIN.md)), non servono
  per usare `mdtcap` direttamente da riga di comando.

(`./install.sh` verifica e installa tutto questo automaticamente, vedi
sopra.)

## Dettagli e dipendenze (`install.sh`)

```bash
sudo ./install.sh
```

Verifica, e installa se mancante, ciascuna di queste dipendenze:

| Dipendenza | Come viene installata se manca | Obbligatoria? |
|---|---|---|
| `python3` | `apt-get install python3` | sì |
| `pip3` | `apt-get install python3-pip` | sì (serve per installare qcsuper) |
| `qcsuper` | `pip3 install --upgrade qcsuper --break-system-packages` | sì (fa la cattura vera e propria) |
| `tshark` | `apt-get install tshark` | no, ma senza niente report MDT derivati (solo `.dlf`/`.pcap` grezzi) |
| `udevadm`, `sha256sum`, `stty`, `date`, `timeout` | solo verificati, non installati (fanno parte di `udev`/`coreutils`, praticamente sempre già presenti) | sì |
| `openssl` (con supporto RIPEMD-160) | solo verificato, non installato | no, ma senza `mdtcontract` non può calcolare il `contractId` (vedi `manifest.json` in mdtcap) |

Rende anche eseguibili `mdtcap`/`mdtgps`/`mdtdiag`/`mdtimei`/
`mdtcontract` e `src/decode_mdt_location.py`/`src/mdt_bitscan.py`/
`src/testauth`, poi stampa un
riepilogo con cosa è stato installato, cosa è fallito e cosa resta da
sistemare a mano.

**Cosa `install.sh` non fa** (dipende dall'hardware/dall'uso specifico,
non è un problema di dipendenze software):
- non verifica/installa driver USB né tocca la configurazione del
  modulo: se il modulo non compare in `/dev/ttyUSB*`, vedi [doc/GUIDA_MDTCAP.md](GUIDA_MDTCAP.md), sezione 1;
- non gestisce PIN della SIM o APN dell'operatore: vanno passati a
  `mdtcap` con `--sim-pin`/`--apn` (o messi nei file in `mdt_configs/`);
- non richiede né presume che un modem sia collegato: verifica solo le
  dipendenze software, si può eseguire anche senza hardware collegato.

Uscita: `0` se tutto è pronto, `1` se c'è stato almeno un problema
(installazione fallita, o una dipendenza non installabile
automaticamente); i dettagli sono nel riepilogo stampato a schermo.

### Generare `mdt_configs/system.conf` (`--configure-system`)

```bash
sudo ./install.sh --configure-system
sudo ./install.sh --configure-system --diag-port /dev/ttyUSB0 --at-port /dev/ttyUSB2
sudo ./install.sh --configure-system --qcsuper /percorso/qcsuper.py
sudo ./install.sh --configure-system --usb-modem-vid 1e0e --usb-modem-pid 9000
```

Genera/aggiorna `mdt_configs/system.conf` (vedi [doc/GUIDA_MDTCAP.md](GUIDA_MDTCAP.md), sezione 3) con:
- `--autodetect` di default, oppure `--diag-port`/`--at-port` se passati
  insieme a `--configure-system` (individuarli prima con
  `sudo ./mdtcap --list-ports`);
- `--qcsuper PATH`: quello rilevato automaticamente da `install.sh`
  (`command -v qcsuper`), oppure il valore passato esplicitamente;
- `--usb-modem-vid`/`--usb-modem-pid`: il VID:PID USB del modem (4 cifre
  esadecimali ciascuno, es. `1e0e`/`9000`, le stesse di `lsusb`),
  rilevato automaticamente interrogando via `udevadm` la prima porta
  `ttyUSB*` il cui `ID_VENDOR` contiene "SimTech" (**servono un modem
  collegato al momento di `--configure-system`**: se assente, questi due
  restano fuori da `system.conf`, si può rilanciare a modem collegato),
  oppure il valore passato esplicitamente. Usati da `mdtcap` **solo** se
  lanciato con `--usb-modem` (facoltativo, vedi sotto): senza
  quell'opzione restano scritti nel file ma inutilizzati.

**Facoltativo di proposito**: un `sudo ./install.sh` normale (senza
questo flag) **non tocca mai** `mdt_configs/system.conf`, per non
sovrascrivere una configurazione già regolata a mano solo perché si è
rilanciato il controllo delle dipendenze. Il file viene rigenerato per
intero ad ogni uso di `--configure-system`: non aggiungere lì altro
oltre a porte/`--autodetect`/`--qcsuper`/VID:PID USB, andrebbe perso al
giro successivo.

### Usare il VID:PID USB invece del device path (`--usb-modem`)

```bash
sudo ./mdtcap --autodetect --usb-modem --duration 1800 ...
```

Con questa opzione, invece di passare a `qcsuper --usb-modem` il device
path della porta Diag (`--diag-port`, o quello risolto da
`--autodetect`), `mdtcap` gli passa il **VID:PID** letto da
`mdt_configs/system.conf` (formato `vvvv:pppp`, sintassi già supportata
nativamente da `qcsuper --usb-modem`, vedi il suo `--help`). `--diag-port`/
`--at-port`/`--autodetect` restano comunque necessari: la porta AT
continua a servire per PIN/APN/CPSI/GPS, e la porta Diag resta nei log/
nel manifest: `--usb-modem` cambia **solo** l'argomento passato a
qcsuper al momento di avviare la cattura.

**Perché può interessare**: un device path fa scegliere a `qcsuper`,
internamente, il connettore `UsbModemPyserialConnector`, che legge la
porta seriale un **byte alla volta** (`serial.read()` senza argomento in
`read_loop()`, in `qcsuper/inputs/usb_modem_pyserial.py`); un VID:PID fa
scegliere invece `UsbModemPyusbConnector`, che legge **a blocchi**
(`wMaxPacketSize`, tipicamente 512 byte) via `pyusb`/`libusb`. Nessuna
delle due modalità è implementata da `mdtcap`: sono due percorsi già
presenti in `qcsuper`, `mdtcap` si limita a scegliere quale dei due
usare.

**Verificato sul campo** (due catture LTE reali da ~200s su Vodafone
Italia, stesso SIM7600E-H, una dopo l'altra): il risultato è
**l'opposto** dell'ipotesi iniziale.

| Modalità | Avvisi "Wrong CRC" | `.dlf` catturato | Frame LTE-RRC validi |
|---|---|---|---|
| path (default) | 0 | 460 KB | 15 |
| `--usb-modem` (VID:PID) | 962 | 3,95 MB | **39** |

`--usb-modem` **non riduce** gli avvisi, li **aumenta**, ma cattura anche
~8,5 volte più dati grezzi e, nonostante i frame scartati per CRC, porta a
casa più del doppio dei frame LTE-RRC validi. La modalità path a lettura
byte-a-byte non risulta "pulita": sembra perdere molto più traffico
ancora più a monte, in modo silenzioso (mai un frame abbastanza intatto
da arrivare a fallire il CRC e generare un avviso: zero avvisi lì non
vuol dire zero perdita).

⚠️ **Ma**: durante entrambe le catture di questo test la macchina
risultava in **undervoltage permanente** (`vcgencmd get_throttled`
con i bit under-voltage/throttling attivi, dal boot in poi), un fattore
di confondimento reale (assorbimenti di picco in TX del modem che possono
superare un alimentatore/cavo USB marginale, causando instabilità USB
indipendente dal connettore usato). Prima di trarre una conclusione
definitiva su quale modalità sia preferibile in generale, vale la pena
sistemare l'alimentazione (alimentatore ufficiale ≥3A, cavo corto/di
qualità, o hub USB alimentato per il modem) e ripetere il confronto.

Se `--usb-modem` è passato senza `--usb-modem-vid`/`--usb-modem-pid` **e**
senza che siano già in `mdt_configs/system.conf`, `mdtcap` si ferma con un
errore chiaro (niente ripiego silenzioso sul device path).

