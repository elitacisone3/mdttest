# Guida all'uso di mdtcap

Guida completa all'uso di `mdtcap`: dall'individuazione delle porte del
modem alla lettura dei file prodotti da una cattura, passando per tutte
le opzioni principali.

## 1. Individuare le porte

### Automaticamente (`--autodetect`)

```bash
sudo ./mdtcap --autodetect --qcsuper /usr/local/bin/qcsuper --duration 160 [...]
```

Rende `--diag-port`/`--at-port` opzionali: prova `AT` su ogni `ttyUSB*`
del modulo (per default filtrati per vendor "SimTech", che copre l'intera
famiglia SimCom incluso il SIM7600E-H, e non solo `AT`, ma anche capire
*quale* interfaccia tra le tante esposte dal modulo è quella giusta),
usa la prima che risponde `OK` come porta AT, poi individua la porta Diag
tra le interfacce dello stesso dispositivo fisico scegliendo quella con
il numero di interfaccia più basso e verificandola con `qcsuper --info`.
Se `--diag-port`/`--at-port` vengono comunque passati esplicitamente,
quel valore ha la precedenza.

Per un modem di un altro produttore: `--autodetect --autodetect-vendor
Quectel` (o il vendor che compare in `--list-ports`).

**Nota dall'uso reale**: l'autodetect è utile non solo per non dover
cercare le porte a mano, ma anche perché l'assegnazione `ttyUSB0`/`2`
non è sempre stabile: ad es. dopo un evento di sottotensione sul
Raspberry Pi (`dmesg` → `Undervoltage detected`) il modulo può
temporaneamente rispondere su una porta AT diversa da quella abituale;
con le porte fissate a mano la cattura fallisce silenziosamente,
con `--autodetect` viene ritrovata la porta giusta.

### Manualmente

```bash
sudo ./mdtcap --list-ports
```

Mostra le porte `ttyUSB*` disponibili. Serve individuare:
- la **porta Diag** (di solito `ttyUSB0`)
- una **porta AT** (di solito la seconda o terza, es. `ttyUSB2`)

Si può verificare inviando `AT` sulla porta candidata: se risponde `OK`, è
una porta AT valida.

### Senza porte: rianalizzare una cattura già fatta (`--analyze-dlf`)

```bash
sudo ./mdtcap \
  --analyze-dlf /root/mdt_evidence/tim/20260903225740/capture_20260903T225740Z.dlf \
  --qcsuper /usr/local/bin/qcsuper \
  --outdir /root/mdt_evidence_reanalisi \
  --report --parla-chiaro
```

Modalità **replay**: nessun device coinvolto, `--diag-port`/`--at-port`/
`--autodetect` non servono (e vengono ignorati se passati). Rilegge un
file `.dlf` già registrato in una sessione precedente (con questo
script, o con QCSuper/QXDM direttamente) e ripete l'intera analisi da
capo: rigenera il `.pcap`, `report_mdt_rrc.txt`, il log delle richieste
MDT/posizione, e, se richiesti, `--report`/`--parla-chiaro`, con lo
stesso hashing e manifest di una cattura live (che lo segnala
esplicitamente come replay, vedi sezione 4).

Utile per: rianalizzare una cattura dopo un aggiornamento dello script
(es. filtri MDT ampliati in una versione successiva), o per ottenere
`--report`/`--parla-chiaro` su una cattura fatta senza quelle opzioni,
senza dover ripetere l'intera acquisizione (specie se durata 30+ minuti).

### Senza device né qcsuper: analizzare un `.pcap` già pronto (`--analyze-pcap`)

```bash
sudo ./mdtcap \
  --analyze-pcap /percorso/cattura_wireshark.pcap \
  --outdir /root/mdt_evidence_reanalisi \
  --report --parla-chiaro
```

Modalità **replay da pcap**: come `--analyze-dlf`, ma parte direttamente da
un file `.pcap`/`.pcapng` già pronto (esportato da Wireshark, catturato
con QCSuper/QXDM, o prodotto da una sessione mdtcap precedente) invece
che da un `.dlf` grezzo. Nessun device coinvolto e, a differenza di
`--analyze-dlf`, **non serve nemmeno `--qcsuper`**: il file indicato è già
nel formato che `tshark` sa leggere, non va rigenerato da nessun `.dlf`.
Incompatibile con `--analyze-dlf` (va scelta una sola sorgente). Il file
viene copiato dentro l'outdir come `capture_<timestamp>.pcap` (la cartella
di evidenza resta autocontenuta) prima di essere analizzato con la stessa
pipeline di `--analyze-dlf`: `report_mdt_rrc.txt`, log delle richieste
MDT/posizione, `coordinate_estratte.csv`, e, se richiesti,
`--report`/`--parla-chiaro`, con lo stesso hashing e manifest. Non viene
prodotto nessun `capture_<timestamp>.dlf` (non esiste una sorgente Diag
grezza in questa modalità: il manifest lo segnala esplicitamente).

Utile per: analizzare una cattura fatta con Wireshark o un altro
strumento (non necessariamente con questo script o con `qcsuper`), o per
ottenere `--report`/`--parla-chiaro` su un `.pcap` già pronto senza dover
installare/coinvolgere `qcsuper`.

### Senza hardware: testare mdtcap con un dump sintetico

`--analyze-dlf` funziona anche su un file `.dlf` che non viene da nessun
modem reale, generato al volo con `synthetic_test/gen_mdt_dlf.py`:

```bash
python3 synthetic_test/gen_mdt_dlf.py --scenario full -o /tmp/test.dlf
sudo ./mdtcap --analyze-dlf /tmp/test.dlf --qcsuper /usr/local/bin/qcsuper \
  --outdir /tmp/mdt_test_synth --report --parla-chiaro
```

Utile per verificare che l'intera catena (decodifica RRC, filtri MDT,
`--report`/`--parla-chiaro`) funzioni ancora dopo una modifica allo script,
senza aspettare che un operatore attivi davvero l'MDT: vedi la guida
completa in `synthetic_test/README.md` (elenco scenari disponibili e
verdetto atteso per ciascuno).

## 2. Lanciare una cattura base

```bash
sudo ./mdtcap \
  --diag-port /dev/ttyUSB0 \
  --at-port /dev/ttyUSB2 \
  --qcsuper /usr/local/bin/qcsuper \
  --duration 160 \
  --label "descrizione del test"
```

- Senza `--duration`, la cattura resta attiva finché non si preme
  **Ctrl+C**: alla ricezione del segnale lo script chiude `qcsuper` in
  modo pulito, salva il contesto AT post-cattura, calcola gli hash e
  scrive il manifest.
- **Durata minima tecnica: almeno 60–160 secondi.** L'avvio di `qcsuper`
  (import del modulo ASN.1) richiede tipicamente 10–20s; con durate troppo
  brevi lo script è costretto a forzare la chiusura con `SIGKILL`, e il
  file `.pcap` può risultare vuoto o troncato.
- **Durata consigliata per verificare davvero l'MDT: almeno 30 minuti
  (1800s).** Una cattura di 160s è sufficiente per verificare che porte,
  APN, LTE, GPS e attach dati funzionino, ma l'MDT è una funzione
  attivata dall'operatore *a intervalli*, non ad ogni connessione: ad
  esempio TIM Analytics invia le richieste di misura MDT ogni ~15 minuti.
  Una cattura troppo breve può quindi risultare "pulita" (nessuna
  richiesta MDT) semplicemente perché non ha coperto l'intervallo in cui
  l'operatore l'avrebbe inviata, non perché l'MDT non sia attivo. Per un
  test attendibile servono almeno 2 di questi intervalli, quindi 30
  minuti come minimo (meglio 45–60 se l'intervallo dell'operatore non è
  noto).

## 3. Opzioni principali

| Opzione | Descrizione |
|---|---|
| `--outdir DIR` | Cartella di output (default: `./mdt_capture_<timestamp>`) |
| `--outdir-base DIR` | Crea da sola `DIR/<AAAAMMGGhhmmss>` come outdir (vedi sotto). Alternativo a `--outdir`, non usabili insieme. |
| `--duration SECONDS` | Durata della cattura (senza, si ferma con Ctrl+C) |
| `--gps` | Abilita il GPS del modulo e lo registra periodicamente |
| `--gps-interval SECONDS` | Intervallo del log periodico cella/GPS (default 30s) |
| `--baud RATE` | Baud rate "best effort" per la porta AT (default 115200) |
| `--label "testo"` | Etichetta descrittiva salvata nel manifest |
| `--sim-pin PIN` | PIN da inviare se la SIM lo richiede (vedi sotto) |
| `--require-lte` | Verifica che la cella sia LTE prima di avviare la cattura (vedi sotto) |
| `--lte-wait SECONDS` | Tempo massimo di attesa per l'aggancio LTE con `--require-lte` (default 0) |
| `--gps-wait SECONDS` | Attiva il GPS/GNSS (se non già attivo) e attende fino a N secondi un fix valido (vedi sotto). Non bloccante. |
| `--net-attach-wait SECONDS` | Tenta l'attach dati/PDP e attende fino a N secondi che il modem risulti connesso (vedi sotto). Non bloccante. |
| `--lbs` | Interroga il servizio di localizzazione di rete (Cell Location Based Service, vedi sotto). Non bloccante. |
| `--lat-margin GRADI` / `--lon-margin GRADI` | Margine di tolleranza (default `0.02` ciascuno) per il bounding box della scansione posizione `warnPosD`/`warnPosL` (vedi "Warning diag port" sotto) |
| `-v`, `--verbose` | Anteprima "quasi in tempo reale" dei pacchetti decodificati durante la cattura (vedi sotto). |
| `--verbose-interval SECONDS` | Intervallo di aggiornamento dell'anteprima verbose (default 15s) |
| `--tui` | Alternativa a `-v`/`--verbose` (mutualmente esclusive): elenco a righe con lo stato di ogni passo in tempo reale, invece del testo di log (vedi sotto) |
| `--mdt-led` | Con `--tui`: attiva il pallino "Stato MDT" (disattivato di default, ha un costo reale, vedi sotto) |
| `--apn APN` | Imposta l'APN sul contesto PDP 1 (vedi sotto). Non bloccante. |
| `--force-lte` | Forza LTE-only e cicla il radio per un nuovo attach (vedi sotto). Non bloccante di per sé. |
| `--reconnect-interval SECONDS` | Cicla il radio ogni SECONDS secondi durante la cattura, senza fermarla, per osservare più riconnessioni nella stessa sessione (vedi sotto) |
| `--reconnects N` | Tetto massimo di cicli eseguiti da `--reconnect-interval` (di cui non ha effetto senza). Default 0 = nessun tetto |
| `--op OPERATORE` | Legge argomenti da `mdt_configs/op/OPERATORE.conf` (vedi sotto) |
| `--profile PROFILO` | Legge argomenti da `mdt_configs/profile/PROFILO.conf` (vedi sotto) |
| `--config FILE` | Legge argomenti aggiuntivi da un file di testo (vedi sotto) |
| `--report` | Stampa e salva un riepilogo sintetico Test/Operatore/UE/RRC/MDT/Risultato a fine cattura (vedi sotto) |
| `--beep` | Invia un carattere BEL (avviso sonoro) a fine esecuzione, successo o abort (vedi sotto) |
| `--parla-chiaro` | Stampa un "Risultato:" in linguaggio semplice, per chi non deve interpretare i campi tecnici (vedi sotto) |
| `--no-banner` | Disabilita la presentazione iniziale ("MDTCap ver ...", copyright) |
| `--autodetect` | Individua da sola `--diag-port`/`--at-port` (vedi sezione 1) |
| `--autodetect-vendor STRINGA` / `--autodetect-model STRINGA` | Filtro vendor/modello per `--autodetect` (default vendor "SimTech") |
| `--usb-modem` | Passa a `qcsuper --usb-modem` il VID:PID USB invece del device path (facoltativo, richiede `--usb-modem-vid`/`--usb-modem-pid` o `mdt_configs/system.conf`, vedi sotto) |
| `--usb-modem-vid VID` / `--usb-modem-pid PID` | VID/PID USB (4 cifre esadecimali ciascuno) usato da `--usb-modem`, di norma già in `mdt_configs/system.conf` |
| `--analyze-dlf FILE` | Modalità replay: ripete l'analisi su un `.dlf` già registrato, senza device (vedi sotto) |
| `--analyze-pcap FILE` | Modalità replay da pcap: ripete l'analisi su un `.pcap`/`.pcapng` già pronto, senza device né `qcsuper` (vedi sotto) |

### PIN della SIM

Se la SIM richiede il PIN, passarlo con `--sim-pin`:

```bash
sudo ./mdtcap ... --sim-pin 1234
```

**Attenzione:** il PIN sulla riga di comando è visibile a chiunque abbia
accesso a `ps aux` mentre lo script è in esecuzione. Un PIN errato **non**
viene ritentato automaticamente, per non rischiare di bloccare la SIM
dopo 3 tentativi falliti (richiederebbe il PUK).

Se la SIM è già sbloccata (`+CPIN: READY`), lo script lo rileva da solo e
non serve passare `--sim-pin`.

### Verifica del tipo di rete (`--require-lte`)

Gli elementi informativi MDT che lo script estrae a fine cattura
(`loggedMeasurementConfiguration` / `locationInfo`) sono definiti **solo
in LTE-RRC**. Su una cella GSM o WCDMA la cattura funziona comunque, ma
non produce dati MDT utilizzabili.

Con `--require-lte`, prima di avviare `qcsuper` lo script controlla lo
stato della cella (`AT+CPSI?`):

```bash
sudo ./mdtcap ... --require-lte --lte-wait 30
```

- Se la cella è già LTE, procede subito.
- Se non lo è, riprova ogni 5 secondi fino a `--lte-wait` secondi
  (default `0` = un solo controllo, nessuna attesa).
- Se allo scadere del tempo la cella non è ancora LTE, lo script
  **annulla la cattura** (exit code 2) senza avviare `qcsuper`, così da
  non sprecare tempo e spazio su disco per un'acquisizione senza dati MDT.

Senza `--require-lte` il comportamento è quello originale: nessun
controllo, la cattura parte comunque indipendentemente dal tipo di rete.

### Fix GPS/GNSS (`--gps-wait`)

```bash
sudo ./mdtcap ... --gps-wait 60
```

Attiva il GPS/GNSS del modulo (`AT+CGPS=1`, se non già attivo con `--gps`)
e interroga `AT+CGPSINFO` ogni 5 secondi fino a `--gps-wait` secondi, in
cerca di un fix valido (latitudine non vuota). A differenza di
`--require-lte`, **non blocca** la cattura: se allo scadere del tempo non
c'è ancora un fix, lo script logga un'attenzione e procede comunque
(utile per avere un ground-truth di posizione quando disponibile, senza
far fallire l'intera acquisizione se il modulo è al chiuso o non ha
visibilità satellitare).

### Verifica connessione dati (`--net-attach-wait`)

```bash
sudo ./mdtcap ... --net-attach-wait 30
```

Tenta l'attach alla rete dati (`AT+CGATT=1`) e l'attivazione del contesto
PDP 1 (`AT+CGACT=1,1`), poi verifica ogni 5 secondi fino a
`--net-attach-wait` secondi che il modem risulti connesso (`+CGATT: 1` e
contesto PDP 1 attivo, riportando anche l'indirizzo IP se assegnato via
`AT+CGPADDR`). Non serve e non configura uno stack PPP/rete locale sul
Raspberry Pi: verifica solo che il modem **stesso** si dichiari connesso
a livello dati. Anche questa verifica **non blocca** la cattura in caso
di esito negativo.

### Servizio di localizzazione di rete (`--lbs`)

```bash
sudo ./mdtcap ... --net-attach-wait 30 --lbs
```

Interroga `AT+CLBS=4` (Cell Location Based Service): il modulo chiede al
server LBS dell'operatore/SIMCom una stima di latitudine, longitudine,
data, ora e precisione basata sulla cella servente, senza usare il GPS.
Richiede il contesto dati attivo (usa `--net-attach-wait` insieme, oppure
lo script tenta comunque l'attach al volo prima di interrogare). Esito
salvato in `lbs_query.txt` e incluso nell'hashing/manifest. Non blocca la
cattura: se il servizio non è abilitato sul piano/SIM o va in timeout,
viene solo loggata un'attenzione.

### Anteprima verbose dei pacchetti decodificati (`-v` / `--verbose`)

```bash
sudo ./mdtcap ... -v --verbose-interval 15
```

**Limite tecnico:** qcsuper scrive il `.pcap` in modo bufferizzato (i
frame restano in un buffer interno finché non se ne accumulano alcuni KB,
oppure fino alla chiusura pulita del processo). Non esiste quindi un vero
streaming pacchetto-per-pacchetto dalla porta Diag al terminale con
questo strumento.

Per dare comunque una preview utile, `-v` sfrutta il fatto che il file
`.dlf` (a differenza del `.pcap`) **viene scritto incrementalmente** su
disco durante la cattura: ogni `--verbose-interval` secondi (default 15)
lo script ne fa una copia, la converte in un pcap temporaneo con
`qcsuper --dlf-read`, e stampa a terminale via `tshark`, quindi già
decodificati (nome messaggio RRC/NAS, campi principali), solo i
pacchetti apparsi dall'ultimo giro. È quindi un'anteprima **"quasi in
tempo reale"**: la latenza è pari a `--verbose-interval`, e cresce se il
volume di traffico rende la rilettura più lenta dell'intervallo stesso
(la rilettura è sequenziale, non si sovrappone al giro successivo).

Non ha impatto sulla cattura principale (lavora su una copia del `.dlf`,
non tocca la porta Diag) e non blocca nulla: se `tshark` non è
disponibile, la richiesta viene ignorata con un'attenzione in log. Per il
dettaglio completo di un pacchetto (tutti i campi, non solo la riga
riassuntiva) resta il file `.pcap` finale aperto in Wireshark/tshark `-V`
a fine cattura.

### Elenco a righe in tempo reale (`--tui`)

```bash
sudo ./mdtcap ... --tui
```

Alternativa a `-v`/`--verbose` (mutualmente esclusive: usarne solo una)
per capire **a colpo d'occhio** cosa sta facendo lo script, senza dover
leggere il testo di log che scorre. Mostra due sezioni, separate da una
riga vuota, ridisegnate sul posto ad ogni cambio di stato (stessi codici
escape ANSI di `-v`, nessuna libreria esterna):

**`Stato:`**: pallini sempre presenti, indipendenti dalle opzioni attive,
che riflettono cosa sta succedendo **davvero** sulla rete/GPS/RRC in
questo momento, aggiornati periodicamente anche durante un'attesa lunga
come "Cattura in corso", non solo nei passi di pre-cattura che li toccano
direttamente:

| Pallino | Verde | Arancione | Grigio |
|---|---|---|---|
| **Stato rete** | agganciata in LTE | su un altro RAT (2G/3G) o senza servizio | nessun dato ancora |
| **Stato GPS** | fix valido (mostra le coordinate in gradi decimali con segno, "lat, lon", formato Google Maps, non il dato NMEA grezzo) | nessun fix al momento | GPS non richiesto in questa esecuzione, o nessun dato ancora |
| **Warning diag port** | `0`, nessun avviso finora | numero di avvisi non appena ne compare almeno uno | porta diag non ancora aperta |
| **Errori diag port** | `0`, nessun errore finora | numero di errori non appena ne compare almeno uno (usa il rosso, vedi sotto) | porta diag non ancora aperta |
| **GPS in frame scartati/non decodificati** | scansione eseguita, nessun candidato | `diag:N log:N`, almeno un candidato trovato | in attesa di fine cattura |
| **Setup MDT in frame scartati/non decodificati** | scansione eseguita, nessun candidato | `diag:N log:N`, almeno un candidato trovato | in attesa di fine cattura |
| **Stato MDT** (solo con `--mdt-led`) | traffico RRC presente, nessuna richiesta MDT | (usa il rosso, vedi sotto) | nessun traffico RRC ancora |

"Stato rete"/"Stato GPS"/"Warning diag port"/"Errori diag port" sono
alimentati dal logger periodico cella/GPS, già attivo comunque durante la
cattura: costo
aggiuntivo trascurabile, **sempre presenti**, nessuna opzione richiesta. I
due pallini "...in frame scartati/non decodificati" invece, a differenza
di tutti gli altri in questa sezione, **non** si aggiornano in tempo
reale: restano grigi per l'intera cattura e passano al valore finale
tutto in una volta, a fine cattura (vedi paragrafo sotto).

**"Warning diag port"** conta le righe di livello WARNING scritte da
`qcsuper` in `qcsuper.log` durante la cattura: nella pratica quasi
sempre frame HDLC scartati per CRC errato (vedi la nota su "Wrong CRC" in
questa guida), occasionalmente un frame diag vuoto/troppo corto. **Non**
conta avvisi non legati ai dati, come "eseguire come root è pericoloso":
quello lo stampa `tshark` durante l'estrazione successiva, finisce in
`tshark_report.err` (un file diverso), mai in `qcsuper.log`. Un numero
piccolo e stabile durante una cattura lunga è normale (framing seriale
non garantito); un numero che cresce rapidamente in continuazione merita
un controllo (cavo USB, `dmesg -T | grep -i usb`). Lo stesso conteggio
finale, calcolato una volta a fine cattura, è anche in `manifest.json`
(campo `diagWarn`), nel file `--shm diagWarn` e nella riga "Warning diag
port:" di `report_finale.txt`, vedi sotto.

**"Errori diag port"** conta invece le righe di livello ERROR scritte da
`qcsuper` in `qcsuper.log`, un contatore separato da "Warning diag port"
e mai incluso in esso: un ERROR non è un frame scartato per CRC, è un
fallimento più a monte, ad esempio un timeout nella richiesta con cui
`qcsuper` abilita un certo tipo di log sul modem (`DIAG_LOG_CONFIG_F`).
Se capita, quel tipo di traffico può restare **completamente assente**
dal `.dlf` per l'intera cattura, senza che "Warning diag port" se ne
accorga (0 frame scartati, perché non è mai arrivato nulla da scartare).
Un caso concreto osservato sul campo: il traffico NAS-EMM usato da
`SMSSTK.silent_sms` e da `--test-sms` (vedi sotto) non veniva mai
registrato, pur essendo l'SMS arrivato regolarmente al modem, per un
errore proprio di questo tipo. Se "Errori diag port" è maggiore di 0,
controllare `qcsuper.log` per il dettaglio e valutare anche
l'alimentazione del dispositivo: `vcgencmd get_throttled` su Raspberry
Pi, e `dmesg -T | grep -i voltage` per eventuali sottotensioni ricorrenti,
che possono causare esattamente questo tipo di errore in modo
intermittente ma frequente (vedi [doc/HARDWARE.md](HARDWARE.md)). Stesso
conteggio finale anche in `manifest.json` (campo `diagError`), nel file
`--shm diagError` e nella riga "Errori diag port:" di
`report_finale.txt`, vedi sotto.

**"GPS in frame scartati/non decodificati" / "Setup MDT in frame
scartati/non decodificati"**: quando "Warning diag port" è **maggiore di
0** (qualche frame è andato perso per CRC errato), `mdtcap` esegue a fine
cattura una scansione euristica **a livello di bit** del `.dlf` e del
testo di `qcsuper.log` (`src/mdt_bitscan.py`), per cercare posizioni
GPS/setup MDT che potrebbero essere finiti in un frame scartato, quindi
mai arrivati a tshark/al pcap. Se "Warning diag port" resta a `0`, questa
scansione **non viene eseguita** (costerebbe tempo senza che ci sia stato
alcun sospetto di dato perso): entrambi i pallini restano a `diag:0 log:0`.

Perché servono due riletture (`diag`/`D` e `log`/`L`):

- **`diag` (D)**: rilegge il `.dlf` già scritto con un parser proprio,
  completamente indipendente da qcsuper/tshark: un "secondo parere"
  utile anche sui record che NON hanno avuto problemi di CRC, nel caso il
  dissector `lte-rrc` di Wireshark avesse un buco (è già successo in
  passato: lo scenario `r17-only` di `synthetic_test`, vedi sopra, nasce
  proprio da un IE non intercettato da nessun filtro).
- **`log` (L)**: un frame scartato per CRC errato non finisce **mai** nel
  `.dlf`. L'unica traccia che resta è il testo del messaggio WARNING
  stesso in `qcsuper.log`, che include il contenuto grezzo del frame
  (repr Python dei byte, vedi `_hdlc_mixin.py` di qcsuper). Questi byte
  vengono ricostruiti e rianalizzati, ma **senza alcuna garanzia**: il CRC
  è fallito, quindi non si sa quale byte sia effettivamente sbagliato, e
  ogni candidato trovato con questo metodo è un indizio da controllare a
  mano, mai una certezza.

Un dettaglio importante sulla codifica: i campi RRC sono in UPER
(Unaligned PER), quindi **non allineati a un byte**: una regex sui byte
non troverebbe mai una posizione GPS in modo affidabile (verificato
empiricamente contro `synthetic_test`: le stesse coordinate iniettate
compaiono a offset di bit come 163 o 38, mai un multiplo di 8). Per
questo lo scan prova OGNI offset di bit, non solo gli 8 shift di byte, e
tiene solo i risultati (lat/lon per la posizione, o il PLMN della rete
per il setup MDT) dentro un margine di plausibilità:

- il **bounding box per la posizione** viene calcolato dalle coordinate
  GPS **vere** ottenute in questa stessa cattura
  (`periodic_cell_gps_decoded.csv`, se c'è almeno un fix), allargato di
  `--lat-margin`/`--lon-margin` gradi (default **0.02** ciascuno, vedi
  sotto); se in questa cattura non c'è nessun fix GPS, usa invece
  `mdt_configs/gpsBoundingBox/<MCC>.json` (vedi il README in quella
  directory) per l'MCC rilevato. Senza nessuno dei due, la scansione
  posizione resta `0/0` (senza un bounding box il filtro non ha alcun
  effetto: ogni finestra di 48 bit decodifica comunque a una qualche
  coordinata valida);
- il **setup MDT** viene cercato come corrispondenza esatta della
  codifica UPER del PLMN (MCC/MNC) rilevato in questa cattura: indizio
  di un IE che nomina la nostra rete (tipicamente `traceReference-r10`
  dentro `loggedMeasurementConfiguration-r10`), non una prova: è
  deliberatamente un'euristica *best-effort*.

```bash
sudo ./mdtcap ... --lat-margin 0.05 --lon-margin 0.05
```

I candidati trovati (offset di bit, coordinate/posizione del match) sono
elencati in `mdt_bitscan_report.txt` nell'outdir, sempre presente, con
una sola nota se la scansione non è stata eseguita. Gli stessi 4 conteggi
sono anche in `manifest.json` (`warnPosD`/`warnPosL`/`warnMDTD`/
`warnMDTL`), nei file `--shm` omonimi, e in `report_finale.txt`: vedi le
sezioni sotto.

"Stato MDT" invece **non compare per default**: va attivato esplicitamente:

```bash
sudo ./mdtcap ... --tui --mdt-led
```

È **rosso** (non arancione) se compare una richiesta di configurazione
MDT e/o una risposta dell'UE con posizione, stessa logica di
`--report`/`--parla-chiaro`. A differenza degli altri due pallini ha un
**costo reale**: un monitor dedicato rilegge periodicamente il `.dlf` in
crescita (stessa tecnica di `-v`: `qcsuper --dlf-read` su una copia +
`tshark`, mai in conflitto dato che `-v`/`--tui` sono mutualmente
esclusive): il che vuol dire lanciare un intero processo `qcsuper`
(10-20s solo per l'import di pycrate su Raspberry Pi, vedi sezione 2)
più 4 chiamate `tshark` ogni 15s, **in parallelo** al processo di cattura
live vero e proprio. Su un Raspberry Pi questo carico periodico compete
per CPU/IO con `qcsuper` e, se lo affama abbastanza a lungo, può causare
un overrun sul buffer della porta Diag USB: **dati persi nella cattura
per un effetto collaterale della UI**, non per un problema della cattura
in sé. Va quindi attivato solo quando serve davvero vedere l'esito MDT in
tempo reale ed è accettabile il costo aggiuntivo; senza `--mdt-led` (il
default) lo script si comporta come se quel pallino non esistesse, nessun
processo aggiuntivo viene avviato. Senza `--tui`, `--mdt-led` non ha
alcun effetto (ignorato con un avviso).

**`Operazioni:`**: una riga per ogni azione prevista in base alle
opzioni attive per quell'esecuzione (sblocco PIN, APN, forzatura LTE,
verifica rete, GPS, attach dati, LBS, cattura, arresto, estrazione
tshark, report, hash, manifest, ...; con `--reconnect-interval` compare
anche "Test riconnessione", vedi sezione 3), con un pallino colorato a sinistra:

| Colore | Significato |
|---|---|
| ⚪ grigio | da fare (passo non ancora iniziato) |
| 🟡 giallo | in corso, con timer `[MM:SS]` (o `[MM:SS/MM:SS]` se l'attesa ha un tetto massimo noto, es. `--lte-wait`/`--gps-wait`/`--net-attach-wait`/`--duration`) |
| 🟢 verde | completato con successo |
| 🔴 rosso | errore (incluso un esito che fa abortire lo script, es. `--require-lte` non soddisfatto) |
| 🟠 arancione | saltato/non bloccante (es. nessun fix GPS entro `--gps-wait`: lo script prosegue comunque, per costruzione) |

L'LBS (`--lbs`) è invece sempre verde: una risposta assente (servizio non
abilitato sul piano/SIM) è un esito normale, non un problema da segnalare
in arancione.

L'elenco delle operazioni è sempre **completo fin da subito**: un passo
compare solo se l'opzione corrispondente è effettivamente attiva per
quell'esecuzione (nessuna sorpresa a metà cattura), e resta a schermo
(non viene cancellato) come registro visivo di quanto è successo.

Sotto `--tui` il testo di log smette di scorrere a terminale (resta
comunque scritto per intero, invariato, in `session.log`): l'unica
eccezione è l'intestazione iniziale ed eventuali errori fatali. L'output
di `--report`/`--parla-chiaro`, se richiesti, viene comunque stampato per
intero, ma spostato **in fondo**, dopo le due sezioni, invece che
frammisto al log.

Non supportato (e ignorato, con un avviso) in modalità replay
(`--analyze-dlf`/`--analyze-pcap`): esecuzioni troppo brevi perché serva.

### Log delle richieste MDT/posizione fatte dalla rete

Sempre attivo, nessuna opzione richiesta. `report_mdt_rrc.txt` estrae solo
gli IE MDT veri e propri (`loggedMeasurementConfiguration`, `logMeasReport`,
`locationInfo`); questo log dedicato è più ampio e copre l'intero scambio
con cui l'operatore **chiede esplicitamente** all'UE le misure o la
posizione registrate:

- `loggedMeasurementConfiguration`: la rete configura il logging MDT
- `ueInformationRequest` (con il flag `logMeasReportReq`): la rete chiede
  esplicitamente all'UE di inviare le misure/la posizione registrate, ed è
  questa la "richiesta" in senso stretto
- `ueInformationResponse` / `logMeasReport` / `locationInfo`: la risposta
  dell'UE, che può includere la posizione (da GPS/GNSS se il modulo era
  acceso, vedi `--gps`/`--gps-wait`)

Per la sola domanda "è arrivata la configurazione MDT dalla rete, e con
quali parametri (inclusa un'eventuale richiesta di posizione)?", vedi
invece `logged_measurement_configuration.txt`: un dump isolato al solo
`loggedMeasurementConfiguration`, con un'intestazione che dice subito se
sono state trovate 0 o N occorrenze, seguita dal decode completo di ognuna.

Produce due file:

- `mdt_location_requests.txt`: decodifica completa (`tshark -V`) di ogni
  evento che rientra nel filtro sopra
- `mdt_location_requests_summary.csv`: una riga per evento (numero
  frame, orario UTC assoluto, tempo relativo dall'inizio cattura,
  descrizione) per una lettura rapida senza aprire Wireshark

Se non viene rilevato nulla, i due file restano vuoti (o con la sola
intestazione) e nel log compare `Nessuna richiesta di MDT/posizione da
parte della rete rilevata in questa cattura`: è il caso normale finché
l'operatore non abilita il logging MDT per questa SIM.

Se combinato con `-v`, ogni evento di questo tipo viene **anche segnalato
a terminale in tempo (quasi) reale**, con un banner ben visibile:

```
!!! RICHIESTA MDT/POSIZIONE DALLA RETE rilevata:
!!!   UEInformationRequest
```

### Controllo automatico di completezza del pcap

Sempre attivo in cattura live, nessuna opzione richiesta. A fine cattura,
prima di qualunque estrazione MDT, lo script rilegge una seconda volta il
`.dlf` appena registrato (`qcsuper --dlf-read`, lo stesso meccanismo di
`--analyze-dlf`) e confronta il numero di frame LTE-RRC ottenuto con quello
del `.pcap` scritto in diretta da qcsuper durante la cattura.

**Perché**: rianalizzando catture reali con `--analyze-dlf` è emerso che il
`.pcap` live può risultare significativamente meno completo dello stesso
`.dlf` riletto subito dopo. Un caso osservato: 9 frame LTE-RRC nel pcap live
contro 64 rigenerando dal `.dlf` (hash del `.dlf` invariato, quindi non è un
problema del file grezzo ma della scrittura del pcap durante la cattura). Il
`.dlf` resta l'unica fonte grezza davvero affidabile.

Se il pcap rigenerato risulta più completo, lo script:
- lo usa per l'intera analisi che segue (`report_mdt_rrc.txt`,
  `coordinate_estratte.csv`, `mdt_location_requests.txt`,
  `report_finale.txt`/`--parla-chiaro`), evitando di basare il verdetto MDT
  su un pcap incompleto;
- rinomina il pcap live originale in `capture_<timestamp>.live.pcap` (mai
  cancellato: resta nell'hashing/manifest per la catena di custodia);
- lo segnala con un'**ATTENZIONE** a terminale/`session.log`, in coda a
  `report_finale.txt` (sezione "Controllo di completezza pcap") e nel campo
  "Controllo completezza pcap" del manifest.

Se il conteggio coincide, lo script lo registra comunque (log "Controllo di
completezza pcap: OK ..."), senza toccare alcun file.

Non si applica in modalità replay (`--analyze-dlf`): lì il pcap è già
ottenuto direttamente dal `.dlf`, non esiste un "pcap live" con cui
confrontarlo (il manifest riporta "N/D" per questo campo in quel caso).

### Impostare l'APN (`--apn`)

```bash
sudo ./mdtcap ... --apn iliad
```

Imposta l'APN sul contesto PDP 1 (`AT+CGDCONT=1,"IP",APN`), subito dopo
lo sblocco PIN (su questo modem `AT+CGDCONT` in scrittura risponde
`ERROR` se la SIM è ancora bloccata). Utile quando l'APN residuo di
fabbrica o di un uso precedente (es. `CMNET`, il default SIMCom) non è
quello dell'operatore reale: un APN sbagliato causa il rifiuto
dell'attach dati/LTE (`Missing or unknown APN`). Indipendente da
`--force-lte`: può essere usato anche da solo, ad es. insieme a
`--net-attach-wait`/`--lbs`. Non bloccante.

L'APN pubblico va cercato per il proprio operatore (es. per Iliad Italia
è `iliad`); lo si trova nelle pagine di configurazione APN pubblicate
dall'operatore stesso, o si può leggere quello attualmente impostato con
`AT+CGDCONT?` prima di cambiarlo.

### Forzare l'aggancio LTE (`--force-lte`)

```bash
sudo ./mdtcap ... --apn iliad --force-lte --require-lte --lte-wait 30
```

Automatizza la procedura fatta manualmente la prima volta per sbloccare
l'aggancio LTE quando la rete è raggiungibile ma il modem resta su
GSM/WCDMA:

1. forza la modalità **LTE-only** (`AT+CNMP=38`), così il modem non
   ripiega più automaticamente su altri RAT
2. cicla il radio (`AT+CFUN=0` poi `AT+CFUN=1`) per forzare un nuovo
   tentativo di attach
3. il ciclo CFUN richiede di norma un nuovo sblocco PIN: viene ritentato
   automaticamente se è stato passato `--sim-pin`
4. logga lo stato rete (`AT+CPSI?`) dopo l'assestamento

A fine cattura (**anche se lo script esce in anticipo**, es. perché
`--require-lte` aborta o qcsuper non riesce a partire: il cleanup è
agganciato fin dall'inizio proprio per coprire questi casi) il modo di
rete viene **sempre ripristinato su automatico** (`AT+CNMP=2`), per non
lasciare il modem forzato in LTE-only oltre la sessione di test (rischio
di restare senza servizio se la copertura LTE cala).

`--force-lte` da solo non verifica né attende l'esito oltre al log
dello stato rete: per attendere/verificare/abortire esplicitamente in
base al risultato va combinato con `--require-lte --lte-wait SECONDS`,
come nell'esempio sopra. Spesso usato insieme a `--apn`, quando il
motivo per cui l'attach LTE falliva era proprio un APN errato: è
esattamente il caso diagnosticato e risolto manualmente in una sessione
precedente (SIM Iliad con APN residuo `CMNET`).

**La cattura parte prima del ciclo CFUN, non dopo:** la configurazione
MDT (`loggedMeasurementConfiguration`) viaggia tipicamente dentro la
`RRCConnectionReconfiguration` successiva a un nuovo attach, ed è quindi
proprio il momento della riconnessione forzata qui sopra il candidato più
probabile per osservarla. `--force-lte` avvia `qcsuper` **prima** del
ciclo radio (non a riconnessione già avvenuta, come in una versione
precedente di questo script), attendendo prima ~15s che l'avvio di
qcsuper sia concluso (vedi la nota sull'import ASN.1/pycrate in sezione
2), così la cattura è già pronta a registrare pacchetti quando la
riconnessione avviene davvero.

### Trappola per la riconnessione (`--reconnect-interval`)

```bash
sudo ./mdtcap ... --duration 1800 --reconnect-interval 300
```

Stessa logica di `--force-lte` sopra, ma ripetuta più volte nel corso di
un'**unica cattura continua** invece che una sola all'inizio: ogni
`SECONDS` secondi durante "Cattura in corso" (mai in fase di
pre-cattura), cicla il radio (`AT+CFUN=0` poi `AT+CFUN=1`, stessa
procedura di `--force-lte`, incluso il ritentativo del PIN se serve)
forzando un nuovo attach, **senza mai fermare o riavviare `qcsuper`**: la
cattura resta continua, con dentro tutti gli eventi di riconnessione
verificatisi durante il test, utile per aumentare le occasioni di
osservare un eventuale invio della configurazione MDT, invece di
affidarsi a una sola riconnessione a inizio test.

Indipendente da `--force-lte`: funziona anche da solo, ciclando sul RAT
che la rete assegna automaticamente (senza forzare LTE-only). Il
conteggio del tempo usa la stessa granularità di `--gps-interval`
(default 30s): il ciclo scatta al primo giro utile dopo che sono
trascorsi almeno `SECONDS` secondi dal precedente, non esattamente al
secondo. Un valore sotto ai ~15-20s che il solo ciclo CFUN+assestamento
richiede produce un avviso ma non viene bloccato.

Con `--tui` compare come voce **"Test riconnessione"**, che torna in
giallo ad ogni ciclo e riporta in nota quanti cicli sono stati completati
e l'ultimo stato di rete osservato. **Per default (senza
`--reconnect-interval`) questo test non viene mai eseguito**: nessun
ciclo radio aggiuntivo oltre a quello eventuale di `--force-lte`.

**Tetto massimo (`--reconnects N`):**

```bash
sudo ./mdtcap ... --duration 1800 --reconnect-interval 300 --reconnects 5
```

Mette un limite al numero di cicli: raggiunto `N`, il test di
riconnessione smette di ciclare per il resto della cattura (che prosegue
comunque fino alla scadenza di `--duration`), utile per non aumentare
senza controllo il numero di riconnessioni della SIM su catture molto
lunghe con un intervallo basso. Default `0` = nessun tetto (cicla per
tutta la durata). Non ha effetto senza `--reconnect-interval` (ignorato
con un avviso).

### Configurazione di sistema (`mdt_configs/system.conf`)

A differenza di `--op`/`--profile` (sotto), **non c'è un'opzione dedicata
per sceglierlo**: è un solo file, a percorso fisso
(`mdt_configs/system.conf`, relativo alla posizione dello script),
**caricato automaticamente ad ogni esecuzione se presente**, silenziosamente
ignorato se assente (una copia del progetto senza `system.conf` ancora
generato si comporta come prima, nessuna porta/`qcsuper` di default).

Contiene **solo** i parametri legati all'hardware/al collegamento su
*questa macchina*: porta (`--diag-port`/`--at-port`) o `--autodetect`, e
`--qcsuper`. Non ci vanno APN, durata, o qualunque altra cosa dipenda
dall'operatore o dal tipo di test: quelli restano in `--op`/`--profile`
(sotto).

Si genera/aggiorna con:

```bash
sudo ./install.sh --configure-system                    # --autodetect (default)
sudo ./install.sh --configure-system --diag-port /dev/ttyUSB0 --at-port /dev/ttyUSB2
```

Facoltativo di proposito: un semplice `sudo ./install.sh` (senza
`--configure-system`) non tocca mai `mdt_configs/system.conf`, per non
sovrascrivere una configurazione già regolata a mano. Vedi
[doc/INSTALLAZIONE.md](INSTALLAZIONE.md).

### Operatore e profilo di test (`--op` / `--profile`)

```bash
sudo ./mdtcap --op vodafone --profile standard
```

Scorciatoie per `--config` che risolvono da sole il percorso del file,
**relativo alla posizione dello script** (non alla directory da cui si
lancia `mdtcap`):

| Opzione | Percorso risolto | Contenuto tipico |
|---|---|---|
| `--op OPERATORE` | `mdt_configs/op/OPERATORE.conf` | APN, `--outdir-base`, `--force-lte`/`--require-lte`, dipende dall'operatore/SIM |
| `--profile PROFILO` | `mdt_configs/profile/PROFILO.conf` | Durata, GPS, LBS, UI, `--reconnect-interval`, la "forma" del test, indipendente dall'operatore |

Né l'uno né l'altro contengono porte/`--autodetect`/`--qcsuper`: quelli
sono parametri di **sistema**, vivono in `mdt_configs/system.conf` (sopra).
`--op`/`--profile` si possono usare insieme (il caso tipico: operatore +
profilo) o da soli. **Ordine di precedenza completo**, dal meno al più
specifico: ciò che viene dopo vince su quanto si sovrappone,
**indipendentemente** dall'ordine in cui `--op`/`--profile`/`--config`
compaiono fisicamente sulla riga di comando:

```
system.conf  <  --op  <  --profile  <  --config  <  argomenti sulla riga di comando
```

Gli argomenti veri e propri sulla riga di comando vincono sempre su
tutto. Operatore/profilo sconosciuti (file non trovato) fanno abortire
lo script elencando le opzioni disponibili nella rispettiva cartella:

```
$ sudo ./mdtcap --op fastweb ...
Operatore sconosciuto per --op: 'fastweb' (file non trovato: .../mdt_configs/op/fastweb.conf)
Operatori disponibili in .../mdt_configs/op/:
  - iliad
  - tim
  - turktelekom
  - vodafone
  - windtre
```

Profili già pronti in `mdt_configs/profile/`:

| Profilo | Durata | Note |
|---|---|---|
| `quick` | 120s | Solo verifica funzionale (porte/APN/LTE/GPS/report), **non attendibile per l'MDT** |
| `standard` | 1800s (30min) | Test MDT attendibile: GPS, attach dati, LBS, report + parla-chiaro |
| `reconnect-trap` | 3600s (60min) | Come `standard`, con la trappola per la riconnessione (ogni 5min, tetto 10 cicli) e `--mdt-led` |

Nessuno dei quattro livelli (`system.conf`/`--op`/`--profile`/`--config`)
supporta un altro `--op`/`--profile`/`--config` annidato al proprio
interno (stessa restrizione già in vigore per `--config` da solo).

### Autodetect dell'operatore via MCC-MNC (`mdt_configs/mcc-mnc/`)

Se **non** si passa `--op`, prima di qualunque altra cosa (anche prima del
banner iniziale) mdtcap apre brevemente la porta AT, sblocca il PIN se
necessario e disponibile (`--sim-pin` sulla riga di comando), interroga
`AT+CPSI?` e ne legge il campo MCC-MNC (es. `222-10`). Se esiste un file

```
mdt_configs/mcc-mnc/<MCC>-<MNC>
```

lo usa esattamente come un `--op` scelto a mano. Pensato come **symlink
relativo** verso `mdt_configs/op/<operatore>.conf` (funziona comunque
anche con un file vero e proprio):

```bash
cd mdt_configs/mcc-mnc
ln -s ../op/vodafone.conf 222-10
```

Già pronti per gli operatori con `--op` esistenti:

| MCC-MNC | Operatore | -> |
|---|---|---|
| `222-01` | TIM | `op/tim.conf` |
| `222-10` | Vodafone Italia | `op/vodafone.conf` |
| `222-50` | Iliad Italia | `op/iliad.conf` |
| `222-88` | WindTre (ex Wind) | `op/windtre.conf` |
| `222-99` | WindTre (ex Tre/3) | `op/windtre.conf` |
| `286-03` | Turk Telekom | `op/turktelekom.conf` |

**Completamente best-effort e silenzioso in caso di fallimento**: porta AT
non trovata, SIM bloccata senza `--sim-pin`, nessuna registrazione di
rete ancora, o MCC-MNC senza file corrispondente. In tutti questi casi
lo script si comporta esattamente come prima di questa funzione (nessun
operatore applicato, tutti i parametri restano quelli passati a mano).
Nel log/manifest un operatore auto-rilevato compare come
`Operatore (auto MCC-MNC 222-10): vodafone`, non `(--op)`, per lasciare
sempre chiaro se è stato scelto dall'utente o dedotto dalla SIM. Il
tentativo viene saltato del tutto (nessun accesso alla porta) se è già
stato passato `--op` esplicitamente, o in modalità
`--analyze-dlf`/`--analyze-pcap`/`--list-ports`/`--help`.

### File di configurazione (`--config`)

```bash
sudo ./mdtcap --config /root/mdt_lte.conf
```

Legge argomenti aggiuntivi da un file di testo, con la stessa sintassi
della riga di comando: uno o più flag per riga (anche più flag sulla
stessa riga), righe vuote o che iniziano con `#` (dopo eventuali spazi)
ignorate come commenti, solo a riga intera: non sono supportati
commenti in coda alla riga. I valori con spazi vanno tra virgolette
(es. `--label "test alpha"`): il file viene tokenizzato rispettando le
virgolette (via `xargs`, solo come tokenizzatore, nessun `eval`, non
viene eseguito nulla; ciò nonostante non va usato con file di cui non
ci si fida).

Gli argomenti nel file fanno da **default**: quelli passati davvero
sulla riga di comando hanno sempre la precedenza. `--config` annidati
dentro il file non sono supportati.

Esempio di file (riprende il caso Iliad visto sopra):

```
# mdt_lte.conf
--diag-port /dev/ttyUSB0
--at-port /dev/ttyUSB2
--qcsuper /usr/local/bin/qcsuper
--duration 160
--sim-pin 1234
--apn iliad
--force-lte
--require-lte --lte-wait 30
--gps-wait 30
--net-attach-wait 30
-v
--label "test MDT automatizzato"
```

eseguito poi semplicemente con:

```bash
sudo ./mdtcap --config mdt_lte.conf
```

(si può comunque aggiungere o sovrascrivere qualunque opzione anche
sulla riga di comando, es. `--config mdt_lte.conf --duration 300`).

### Report finale sintetico (`--report`)

```bash
sudo ./mdtcap ... --report
```

A fine cattura stampa a terminale (e salva in `report_finale.txt`,
incluso nell'hashing) un riepilogo ricavato analizzando il `.pcap` con
tshark:

```
Test: OK
Operatore: MDT, GPS, Attiva
UE: GPS
RRC: 3 (2 con posizione GPS, 1 senza)
MDT: 1
Warning diag port: 0
Errori diag port: 0
Warning posizione (diag): 0
Warning posizione (log): 0
Warning MDT (diag): 0
Warning MDT (log): 0
Risultato: L'operatore richiede MDT (con posizione). L'UE risponde con la posizione.
```

Significato dei campi:

- **Test**: `OK` se è stato rilevato traffico LTE-RRC nella cattura:
  condizione necessaria perché il test sia considerato superato,
  altrimenti `ERRORE (nessun traffico LTE-RRC rilevato nella cattura)`.
- **Operatore**: cosa ha chiesto la rete. `OK` se non è arrivata nessuna
  richiesta MDT; altrimenti una lista tra `MDT` (richiesta presente),
  `GPS` (la risposta dell'UE include una posizione), `Attiva` (la rete
  ha esplicitamente richiesto l'invio delle misure via
  `logMeasReportReq`, non solo configurato il logging).
- **UE**: `GPS` se l'UE ha risposto includendo una posizione, altrimenti
  `OK`.
- **RRC**: numero di risposte RRC dell'UE (`ueInformationResponse`/
  `logMeasReport`), con il dettaglio di quante includono la posizione
  GPS e quante no.
- **MDT**: numero di richieste MDT ricevute dalla rete (le richieste,
  non le risposte dell'UE contate sopra in RRC).
- **Warning diag port**: numero di avvisi (WARNING) scritti da `qcsuper`
  in `qcsuper.log` durante l'intera cattura live, vedi la sezione sulla
  TUI più sopra per il criterio esatto e cosa NON viene contato. `0` in
  modalità replay (`qcsuper.log` non esiste).
- **Errori diag port**: come sopra, ma per le righe di livello ERROR,
  contate separatamente perché un errore (ad esempio un timeout nella
  richiesta con cui `qcsuper` abilita un tipo di log sul modem) può
  lasciare "Warning diag port" a `0` pur avendo impedito la cattura di un
  intero tipo di traffico per tutta la sessione. Se maggiore di `0`,
  controllare `qcsuper.log` e l'alimentazione del dispositivo, vedi la
  sezione sulla TUI più sopra per il dettaglio. `0` in modalità replay,
  stesso motivo di "Warning diag port".
- **Warning posizione (diag)/(log)**, **Warning MDT (diag)/(log)**:
  risultato della scansione euristica a livello di bit descritta nella
  sezione sulla TUI più sopra (`warnPosD`/`warnPosL`/`warnMDTD`/
  `warnMDTL`): candidati di posizione/setup MDT trovati in frame diag
  scartati per CRC errato o comunque non passati da tshark. Tutti a `0`
  se "Warning diag port" è `0` (nessun sospetto di dato perso, scansione
  non eseguita). Dettaglio dei candidati in `mdt_bitscan_report.txt`.
- **Autorizzazione IMEI** (riga presente **solo se applicabile**, non
  nell'esempio sopra): compare quando l'IMEI letto in questa cattura è
  diverso da quello **originale** salvato in `mdt_configs/imei` (segno
  che è stato cambiato, presumibilmente con `mdtimei`) **e** esiste
  un'autorizzazione valida per questo device/ICCID/IMEI/contractId,
  verificata con `src/testauth`, stessa logica/stessi criteri di
  `mdtimei` (vedi [doc/CAMBIO_IMEI.md](CAMBIO_IMEI.md)). Il valore
  è la stringa `AUTH` dell'autorizzazione trovata, per legare
  l'evidenza di questa cattura all'autorizzazione che ha permesso
  l'IMEI in uso. Puramente informativo: **mdtcap non blocca mai la
  cattura in base a questo**, né se l'IMEI risulta cambiato senza
  un'autorizzazione valida (in quel caso non compare nessuna riga, solo
  un'ATTENZIONE in `session.log`) né altrimenti: non è il suo compito
  imporlo (quello è `mdtimei`), solo documentarlo quando c'è.
- **Risultato**: descrizione testuale che combina quanto sopra: test non
  riuscito, oppure dati insufficienti (nessuna risposta RRC di alcun
  tipo), oppure presenza/assenza di richiesta MDT ed eventuale risposta
  dell'UE con o senza posizione.

**Nota sull'interpretazione**: durante lo sviluppo nessun operatore
disponibile ha mai attivato realmente l'MDT in questa sessione, quindi
la classificazione `GPS`/`Attiva` per il campo Operatore è basata sugli
IE RRC verificabili (`locationInfo`, `logMeasReportReq`) e non su un
test empirico con richieste MDT vere: verificare che corrisponda a
quanto atteso se/quando si osserva traffico MDT reale.

### Controlli extra: indizi di IMSI-catcher/sorveglianza (`--extended`)

```bash
sudo ./mdtcap ... --extended [--ext-profile standard]
```

Seconda analisi opzionale, **indipendente** da MDT/RRC: cerca nella
stessa cattura indizi di comportamento di rete sospetto/malevolo tipico
degli IMSI-catcher, ispirata a SnoopSnitch (SRLabs)/Darshak/AIMSICD:
cifratura nulla, richieste di identità non sollecitate, SMS/STK sospetti,
downgrade forzato, incoerenza cella/GPS. **Un indizio da verificare, non
un verdetto**: è pensata per una prima discriminazione, con regole
configurabili ed estendibili (`extra_configs/`), vedi
`extra_configs/README.md` per il formato completo e `src/extra_scan
--help` per l'implementazione.

Solo se `--extended` è presente, a fine test, **prima** dell'hashing
SHA-256 (così i file scritti finiscono nella catena di custodia), viene
invocato `src/extra_scan` sull'outdir corrente. Indipendentemente da
`--extended`, mdtcap chiama sempre `src/extra_scan --get-defs` all'avvio
(se lo script è presente) per etichettare stabilmente la sezione
"Controlli extra:" di `report_finale.txt`: senza `--extended` quella
sezione mostra solo le intestazioni, mai un livello/conteggio. Nella
TUI (`--tui`) invece la sezione compare **solo** con `--extended`: senza,
sarebbe stata solo una sezione grigia/pending per l'intera cattura,
senza alcuna informazione utile in tempo reale.

`--ext-profile NOME` alimenta il `--profile` di `src/extra_scan` (risolto
in `extra_configs/profile/NOME.conf`), **non** lo stesso `--profile` di
mdtcap (`mdt_configs/profile/`, tutt'altro sistema di configurazione).
L'operatore (`--op` di mdtcap, o quello auto-rilevato via MCC-MNC) viene
passato automaticamente a `extra_scan` per risolvere l'eventuale
`extra_configs/op/<operatore>.conf`.

**Categorie** (chiave, testo, come compaiono in report/TUI/manifest):

| Chiave | Testo | Esempi di cosa cerca |
|---|---|---|
| `SMSSTK` | SMS/STK | SMS silenziose (TP-DCS class 0/2), envelope STK sospetti (SIMjacker/WIB) |
| `NASId` | NAS/Identità | Identity Request IMSI non sollecitate, riallocazione GUTI anomala |
| `RRCCiph` | RRC/Cifratura | Cifratura/integrità nulla (EEA0/EIA0) in Security Mode Command |
| `cellSys` | Cella/Sistema | Downgrade forzato a 2G, assenza neighbor cell list |
| `GPSLoc` | GPS/Localizzazione | Cella incoerente con la traccia GPS registrata |
| `WCDMA3G` | 3G/UMTS | A5/0 su GSM, downgrade forzato a 3G |

(le prime 4 sono quelle esplicitamente richieste; `GPSLoc`/`WCDMA3G` sono
un'estensione aggiunta in fase di progettazione: l'elenco autorevole è
sempre quello di `src/extra_scan --get-defs`, in caso di modifiche
future.)

**Livelli**, in ordine di gravità crescente:

- `I` Ignora: nessun problema (verde in TUI, assente/vuoto nel report).
- `W` Warning: avviso semplice, isolato (arancione).
- `C` Cumulativo: sospetto se ripetuto, se il numero di occorrenze
  supera una soglia configurata (`cum_threshold`), il livello viene
  **promosso** ad `A` (rosso scuro finché non promosso).
- `A` Assoluto: segnala qualcosa di già di per sé malevolo (rosso), es.
  cifratura nulla: un solo evento basta.

Il livello mostrato per ciascuna categoria è il più alto fra le regole
attivate in quella categoria; `extraLevel` è il più alto fra tutte le
categorie.

**Dove finiscono i risultati:**

- `report_finale.txt`: nuova sezione "Controlli extra:" con
  `extraLevel` e livello/conteggio per categoria (solo con `--extended`;
  altrimenti solo le intestazioni, vedi sopra).
- `manifest.json`: campi `extended` (bool), `extraLevel`, `extScanCat`
  (dict per categoria con `level`/`n`), **assenti** (non semplicemente
  vuoti) se `--extended` non è stato usato.
- `--shm DIR` (se presente): `extraLevel` più `extra_<CATEGORIA>_L`/
  `extra_<CATEGORIA>_N` per ciascuna delle 6 categorie (es.
  `extra_NASId_L`, `extra_NASId_N`), stesso stile degli altri file
  `--shm` (vedi sotto).
- `extra_scan_report.txt` (dettaglio esteso, regole valutate/commenti) e
  i log dedicati `extra_scan.log` (generale) + `extra_scan_<CATEGORIA>.log`
  (uno per categoria, sempre creati), un evento per riga, con un codice
  a lunghezza fissa e un hex dump del frame che ha fatto scattare la
  regola, pensati per essere `grep`-abili: `grep NASID_ extra_scan.log`.

**Limiti noti in questa versione** (documentati anche in testa a
`src/extra_scan`): `SMSSTK.simjacker_envelope`, `NASId.attach_identity_release`
e `cellSys.no_neighbor_list` non hanno ancora un rilevatore implementato
(richiedono rispettivamente un decoder degli envelope STK/OTA, la
correlazione di una sequenza di messaggi, e l'analisi dei SIB della
cella servente): restano regole configurabili ma non producono mai
eventi per ora. Come per il resto di questa funzionalità: "i test extra
sono soggetti a modifiche".

### Trigger di test via SMS (`--test-sms`)

```bash
sudo ./mdtcap ... --test-sms
```

Implica `--extended` da solo, non serve passarlo separatamente. Pensato
per verificare l'intera catena di rilevamento (dispositivo, cattura,
`extra_scan`, report) senza dover aspettare un vero evento di rete:
durante la cattura, un altro telefono, in un ambiente controllato, invia
al device di test un normale SMS **visibile** (non silenzioso) con
questo testo esatto, spazi bianchi ignorati:

```
${"37337:H4XOR:MEGAVIRUS:T35T:F4K3:P4YL04D"::do(CATEGORIA)}
```

dove `CATEGORIA` è uno di questi 6 token, esattamente 7 caratteri
ciascuno (maiuscole/minuscole/underscore contano):

| Token | Categoria forzata |
|---|---|
| `RRCCiph` | solo `RRCCiph` |
| `cellSys` | solo `cellSys` |
| `WCDMA3G` | solo `WCDMA3G` |
| `NASId__` | solo `NASId` |
| `SMSSTK_` | solo `SMSSTK` |
| `ALL____` | tutte e 5 insieme (`GPSLoc` esclusa) |

Se il testo combacia, `src/extra_scan` (funzione
`detect_test_sms_trigger`) forza la categoria indicata al livello `A`
(Allarme), a prescindere da `extra_configs/`: un modo per validare
report/manifest/`--shm` con un solo SMS reale, senza dover riprodurre un
vero EEA0 o un vero downgrade forzato. Senza `--test-sms`, questo SMS
non ha **nessun** effetto: `extra_scan` non lo cerca nemmeno, resta
indistinguibile da un SMS qualunque.

Limite noto: funziona solo con un SMS singolo, senza header dati utente
(niente concatenazione multi-parte), sufficiente per un messaggio di
~70 caratteri come questo, ben sotto il limite di un SMS a 7 bit.

**Attenzione**: questo trigger dipende dal traffico NAS-EMM effettivamente
registrato nel `.dlf`, lo stesso usato da `SMSSTK.silent_sms`. Se
"Errori diag port" (vedi sopra) è maggiore di `0` durante la cattura,
`--test-sms` può non rilevare nulla anche se l'SMS è arrivato
regolarmente al modem: controllare prima quello, non il contenuto
dell'SMS.

Anche `mdtmain` (vedi più sotto) espone questa modalità come checkbox
"Modalità test SMS" nella schermata Impostazioni (parametro `testSMS` in
`main_configs/mdtmain.conf`, default disattivato): se attivo, aggiunge
`--test-sms` a ogni invocazione di `mdtcap`, allo stesso modo di "Imposta
i test approfonditi"/`forceExtended` per `--extended`.

### Beep di fine esecuzione (`--beep`)

```bash
sudo ./mdtcap ... --beep
```

Invia un carattere BEL (codice 7) al terminale come ultima cosa che fa
lo script, sia in caso di successo sia in caso di abort, utile per non
dover restare a guardare il terminale durante catture lunghe.

### Risultato in linguaggio semplice (`--parla-chiaro`)

```bash
sudo ./mdtcap ... --parla-chiaro
```

Pensato per chi usa lo script senza conoscere l'MDT/RRC e non deve
interpretare i campi tecnici di `--report`: stampa (e scrive in
`report_finale.txt`) un'unica riga `Risultato:` in linguaggio semplice:

| Frase | Quando |
|---|---|
| `Qualcosa è andato storto.` | errori, o rete non LTE durante la cattura |
| `Non lo so, mi serve più tempo.` | nessun traffico RRC catturato |
| `Stacca, stacca, stacca, ti stanno tracciando!` | l'UE ha inviato coordinate GPS, oppure la rete ha chiesto esplicitamente la posizione |
| `Tutto bene.` | nessuna coordinata GPS richiesta o inviata |
| `Sembra tutto apposto, ma c'è tanto rumore.` | come sopra ("Tutto bene"), MA `qcsuper` ha scartato almeno un frame per CRC errato durante questa cattura ("Warning diag port" > 0) |

L'ultima frase sostituisce `Tutto bene.` (mai le altre tre) quando c'è
stato un avviso diag: il verdetto "tutto bene" si basa solo su cosa
tshark è riuscito a decodificare dal pcap, e non tiene conto di quanto
possa essere sfuggito nei frame scartati. Compare **indipendentemente**
dal fatto che la scansione bit-a-bit descritta più sopra abbia poi
trovato qualcosa o no: conta il rischio di aver perso dati, non il
risultato della scansione (per quello ci sono i campi "Warning posizione"/
"Warning MDT" e `mdt_bitscan_report.txt`).

Funziona anche **senza** `--report` (autonomo: fa la propria piccola
analisi del `.pcap`). Se usato insieme a `--report`, la riga viene
accodata a `report_finale.txt` con un separatore, senza toccare il campo
tecnico `Risultato:` già scritto da `--report` (le due righe convivono,
una tecnica e una in linguaggio semplice).

### Cartella di output automatica (`--outdir-base`)

```bash
sudo ./mdtcap ... --outdir-base /root/mdt_evidence
```

Alternativa a `--outdir` (non usabili insieme: lo script si rifiuta di
partire se vengono passati entrambi): invece di comporre a mano l'intero
path con il timestamp, si indica solo la cartella "contenitore" e lo
script crea da solo (se non esiste) una sottodirectory con nome
**puramente numerico** `AAAAMMGGhhmmss` (anno, mese, giorno, ore, minuti,
secondi UTC, stesso istante usato per timestampare i file della
cattura), e la usa come outdir effettivo. Esempio:

```bash
sudo ./mdtcap ... --outdir-base /root/mdt_evidence
# → crea ed usa /root/mdt_evidence/20260903225740
```

**Default (senza né `--outdir` né `--outdir-base`)**: si comporta come
se fosse stato passato `--outdir-base log/data` (`log/data/` accanto a
`mdtcap`, vedi anche [doc/STRUTTURA_PROGETTO.md](STRUTTURA_PROGETTO.md)): le catture
finiscono quindi in un posto prevedibile del progetto invece che nella
directory da cui è stato lanciato lo script. Un `--outdir`/`--outdir-base`
esplicito (riga di comando, o nei file in `mdt_configs/op|profile/`,
vedi sezione 3) vince sempre su questo default.

## 4. Struttura delle directory di output

Per una guida tecnica su come interpretare il contenuto di questi file
(quali IE RRC cercare, come leggere `manifest.json`, rischio di falsi
negativi su catture brevi, catena di custodia) vedi
[doc/EVIDENZE.md](EVIDENZE.md).

### Layout con `--outdir-base` (consigliato, usato dai file in `mdt_configs/`)

```
/root/mdt_evidence/                  ← DIR passato a --outdir-base: contenitore,
│                                       lo script non ci scrive mai file direttamente
└── tim/                             ← sottocartella scelta liberamente nel valore di
│                                       --outdir-base (es. --outdir-base /root/mdt_evidence/tim)
    └── 20260903225740/              ← creata IN AUTOMATICO da --outdir-base:
        │                               nome puramente numerico AAAAMMGGhhmmss (UTC),
        │                               un istante = una cartella = una esecuzione
        ├── capture_<timestamp>.dlf
        ├── capture_<timestamp>.pcap
        ├── context_pre.txt
        ├── context_post.txt
        ├── periodic_cell_gps.csv
        ├── periodic_cell_gps_decoded.csv
        ├── report_mdt_rrc.txt
        ├── logged_measurement_configuration.txt
        ├── mdt_location_requests.txt
        ├── mdt_location_requests_summary.csv
        ├── coordinate_estratte.csv
        ├── decode_coordinate.log
        ├── lbs_query.txt
        ├── report_finale.txt
        ├── qcsuper.log
        ├── qcsuper_dlf_replay.log
        ├── mdt_bitscan_report.txt
        ├── tshark_report.err
        ├── session.log
        ├── hashes_sha256.txt
        ├── manifest.txt
        └── manifest.json
```

Con `--outdir DIR` invece (alternativo, non usabile insieme a
`--outdir-base`) la cartella indicata **è** già quella dove finiscono
tutti i file sopra: nessuna sottocartella con timestamp viene creata
automaticamente: se si eseguono più catture con lo stesso `--outdir`, i
file si mischiano (usare un `--outdir` diverso per ognuna, o passare a
`--outdir-base`).

In **modalità replay** (`--analyze-dlf`, vedi sezione 1) la struttura è
identica: `capture_<timestamp>.dlf` è una copia del file dato in
ingresso (così la cartella resta autocontenuta), `capture_<timestamp>.pcap`
è (ri)generato da quello, e tutti i report derivati vengono ricalcolati
allo stesso modo di una cattura live.

In **modalità replay da pcap** (`--analyze-pcap`, vedi sezione 1) la
struttura è più snella: `capture_<timestamp>.pcap` è una copia diretta
del file dato in ingresso (nessuna rigenerazione), **non** viene prodotto
nessun `capture_<timestamp>.dlf` (non esiste una sorgente Diag grezza),
e non ci sono `context_*.txt`/`periodic_cell_gps.csv`/`periodic_cell_gps_decoded.csv`/`qcsuper.log`
(nessun device né `qcsuper` coinvolti). Tutti i report derivati
(`report_mdt_rrc.txt`, `logged_measurement_configuration.txt`,
`mdt_location_requests.txt`/`_summary.csv`,
`coordinate_estratte.csv`, ed eventualmente `report_finale.txt`) vengono
comunque calcolati allo stesso modo.

### Funzione dei singoli file

| File | Prodotto da | Contenuto |
|---|---|---|
| `capture_<timestamp>.dlf` | sempre, tranne in `--analyze-pcap` | cattura grezza Diag (formato QCSuper/QXDM); in `--analyze-dlf` è una copia del file di input; assente in `--analyze-pcap` (nessuna sorgente Diag grezza in quella modalità) |
| `capture_<timestamp>.pcap` | sempre (se `tshark`/qcsuper disponibili) | stessa cattura in formato GSMTAP, apribile in Wireshark; se il controllo di completezza (vedi sezione 3) rileva una divergenza, questo è il pcap rigenerato dal `.dlf` (più completo), non quello scritto in diretta |
| `capture_<timestamp>.live.pcap` | solo in cattura live, solo se il controllo di completezza rileva una divergenza | pcap originale scritto in diretta da qcsuper durante la cattura, conservato per la catena di custodia dopo essere stato sostituito da `capture_<timestamp>.pcap` (vedi sezione 3) |
| `context_pre.txt` / `context_post.txt` | sempre | contesto AT (IMEI, ICCID, operatore, stato registrazione, qualità segnale) prima e dopo la cattura; assenti in entrambe le modalità replay (nessun device) |
| `periodic_cell_gps.csv` | sempre in cattura live | log periodico di cella (e GPS, se abilitato) durante la cattura, righe grezze `"timestamp","CPSI/CGPSINFO","risposta AT completa"`; assente in entrambe le modalità replay |
| `periodic_cell_gps_decoded.csv` | sempre in cattura live | stesso log, ma con ogni campo separato in una colonna propria (mode/stato/MCC/MNC/TAC/cell ID/PCI/banda/EARFCN/bandwidth/RSRQ-RSRP-RSSI-RSSNR grezzi per la cella, e per il GPS latitudine/longitudine in gradi decimali con segno, formato Google Maps, non NMEA grezzo, più altitudine/velocità/direzione/data-ora); include comunque `cpsi_raw`/`cgpsinfo_raw` con la risposta AT per intero, per non perdere nulla. La decodifica dei 4 valori di segnale (RSRQ/RSRP/RSSI/RSSNR) segue il formato SIMCom documentato ma non è verificata al 100% in scala/unità su ogni firmware: usare `cpsi_raw` come riferimento in caso di dubbio. Solo per RAT LTE (unico rilevante per l'MDT): su altri RAT le colonne decodificate restano vuote, il dato resta comunque intero in `cpsi_raw`; assente in entrambe le modalità replay |
| `report_mdt_rrc.txt` | sempre (se `tshark`) | estrazione degli IE MDT/RRC veri e propri (`loggedMeasurementConfiguration`, `locationInfo`, `coarseLocationInfo-r17`, ...) |
| `logged_measurement_configuration.txt` | sempre (se `tshark`) | dump isolato al solo IE `loggedMeasurementConfiguration` (sottoinsieme di `report_mdt_rrc.txt`): intestazione con conteggio occorrenze ("arrivata o no la configurazione MDT dalla rete") seguita dal decode `-V` completo di ogni occorrenza, per ispezionarne tutti i sotto-campi (compreso un eventuale campo legato alla posizione); se vuoto/0 occorrenze, la rete non ha inviato nessuna configurazione di logging MDT in questo test |
| `mdt_location_requests.txt` / `_summary.csv` | sempre (se `tshark`) | log dedicato delle richieste MDT/posizione dalla rete (filtro più ampio del precedente, vedi sezione 3) |
| `coordinate_estratte.csv` / `decode_coordinate.log` | sempre (se `tshark` + `decode_mdt_location.py`) | coordinate GPS/GNSS decodificate dagli IE `locationInfo` / `coarseLocationInfo-r17` |
| `lbs_query.txt` | solo con `--lbs` | esito dell'interrogazione del servizio di localizzazione di rete |
| `report_finale.txt` | solo con `--report` e/o `--parla-chiaro` | riepilogo Test/Operatore/UE/RRC/MDT/Risultato, ed eventualmente la riga "Risultato" in linguaggio semplice |
| `qcsuper.log` | solo in cattura live | output grezzo del processo `qcsuper` durante la cattura; assente in entrambe le modalità replay; le righe WARNING che contiene sono la fonte del campo `diagWarn`/riga "Warning diag port", le righe ERROR quella di `diagError`/"Errori diag port" (vedi sotto) |
| `qcsuper_dlf_replay.log` | solo se il `.pcap` va (ri)generato dal `.dlf` | output di `qcsuper --dlf-read`: succede sempre in `--analyze-dlf`, oppure in cattura live se `qcsuper` è stato chiuso in modo non pulito (vedi sezione 2); assente in `--analyze-pcap` (non coinvolge mai `qcsuper`) |
| `tshark_report.err` | sempre (se `tshark`) | stderr di tutte le chiamate `tshark` (di norma solo l'avviso "running as root") |
| `mdt_bitscan_report.txt` | sempre in cattura live | dettaglio della scansione bit-a-bit (`src/mdt_bitscan.py`, campi `warnPosD`/`warnPosL`/`warnMDTD`/`warnMDTL`): candidati trovati, o una sola nota se non eseguita perché `diagWarn` era `0`; vedi "Warning diag port" più sopra |
| `session.log` | sempre | intero log dell'esecuzione (stesso testo stampato a terminale) |
| `hashes_sha256.txt` | sempre | hash SHA-256 di tutti i file prodotti, per la catena di custodia |
| `manifest.txt` | sempre | riepilogo dell'esecuzione (host, porte o modalità replay, versione qcsuper, timestamp, hash), per la lettura umana |
| `manifest.json` | sempre | stesso riepilogo, ma STRUTTURATO per consumo automatico da script esterni, vedi sotto |

File temporanei creati e rimossi durante l'esecuzione (non presenti a
fine cattura): `.verbose_snapshot.dlf` / `.verbose_snapshot.pcap` (solo
con `-v`, ricreati ad ogni ciclo dell'anteprima).

Verifica integrità dei file in un secondo momento:

```bash
cd <outdir>
sha256sum -c hashes_sha256.txt
```

### `manifest.json` e `--shm` (consumo automatico da script esterni)

A differenza di `manifest.txt`/`report_finale.txt` (pensati per la
lettura umana), **ogni** esecuzione di `mdtcap` (anche senza `--report`/
`--parla-chiaro`, anche in modalità replay) scrive nell'outdir un
`manifest.json` strutturato:

```json
{
  "_type": "MDT/MF", "ver": "1.0",
  "imei": "...", "mcc": "...", "mnc": "...", "iccid": "...",
  "tcr": 1788820314, "lte": true, "gps": true, "OK": true, "miss": false,
  "length": 30, "hasMDT": false, "numMDT": 0,
  "reqMDTPos": false, "reqMDTGPS": false,
  "hasRRC": false, "hasRRCPos": false, "numRRC": 0, "numRRCPox": 0,
  "op": "vodafone", "profile": "",
  "machineId": "...", "hwId": "...", "contractId": "...",
  "diagWarn": 0, "diagError": 0,
  "warnPosD": 0, "warnPosL": 0, "warnMDTD": 0, "warnMDTL": 0
}
```

**`length`**: durata **effettiva** della cattura in secondi (dall'avvio
all'arresto di `qcsuper`), non il tetto massimo eventualmente richiesto
con `--duration`: se la cattura si ferma prima (Ctrl+C, o il file
`mdtStop` con `--shm`, vedi sopra), riflette quella più breve durata
reale. `0` in modalità replay (nessuna cattura live).

`imei`/`mcc`/`mnc`/`iccid` vengono letti da `context_post.txt` (o
`context_pre.txt` se il primo manca); restano vuoti in modalità replay
(nessun device coinvolto). `machineId`/`hwId` identificano invece
**questa macchina di test** (non il modem), stessa fonte usata da
`contractId`, vedi `./mdtcontract --help`.

**`diagWarn`** (intero, non booleano): numero di avvisi WARNING scritti
da `qcsuper` in `qcsuper.log` durante la cattura live (tipicamente frame
scartati per CRC errato, vedi la sezione sulla TUI più sopra per il
criterio esatto e cosa non viene contato). `0` in modalità replay
(`qcsuper.log` non esiste in quel caso).

**`diagError`** (intero, non booleano): come `diagWarn`, ma per le righe
di livello ERROR, sempre separato da `diagWarn` e mai incluso in esso.
Un ERROR (ad esempio un timeout nella richiesta con cui `qcsuper` abilita
un tipo di log sul modem) può lasciare `diagWarn` a `0` pur avendo
impedito la cattura di un intero tipo di traffico per tutta la sessione:
vedi la sezione sulla TUI più sopra per il dettaglio e per cosa
controllare (alimentazione del dispositivo, in particolare). `0` in
modalità replay, stesso motivo di `diagWarn`.

**`warnPosD`/`warnPosL`/`warnMDTD`/`warnMDTL`** (interi, non booleani):
risultato della scansione euristica a livello di bit descritta nella
sezione sulla TUI più sopra (`D` = dal `.dlf`, `L` = dai frame scartati
per CRC errato ricostruiti da `qcsuper.log`; `Pos` = candidati di
posizione GPS, `MDT` = candidati di setup MDT). Tutti a `0` se `diagWarn`
è `0` (scansione non eseguita); vedi `mdt_bitscan_report.txt` nell'outdir
per il dettaglio di ogni candidato trovato.

**`contractId`**: un hash (RIPEMD-160) che lega insieme questo device di
test e la SIM usata, calcolato invocando lo script separato
`mdtcontract <ICCID>`, pensato per essere usato da script **esterni**
per tracciare il consenso al test (vedi `./mdtcontract --help` per i
dettagli: cosa viene incluso nell'hash, e i fallback usati per
determinare modello/id del device). Lo stesso script, con
`mdtcontract --get-devid`, stampa il solo id hardware del device (senza
bisogno di un ICCID), usato da `mdtimei` per il campo `DEVID` di
un'autorizzazione (vedi [doc/CAMBIO_IMEI.md](CAMBIO_IMEI.md)).
Con `mdtcontract --get-sim-user` l'ICCID non va passato a mano: viene
letto da solo con `mdtdiag --get-sim` (che stampa una riga
`ICCID:<iccid>`, vedi `./mdtdiag --help`), utile per ottenere il
`contractId` in un solo comando, senza dover prima leggere l'ICCID a
parte. A differenza delle altre due modalità (`<ICCID>`/`--get-devid`,
un solo valore su stdout), `--get-sim-user` stampa **due righe**:

```
ICCID:1234567890123456789
CONTRACT:365d6341a1c5a5f8f9460036e9ef1423875af905
```

A differenza di `--get-devid` (che legge solo file locali), sia
`--get-sim-user` che `mdtdiag --get-sim` richiedono root e un modem
raggiungibile.

**`extended`/`extraLevel`/`extScanCat`** (solo con `--extended`, vedi
"Controlli extra" più sopra): `extended` è sempre `true` quando presenti,
`extraLevel` il livello I/W/C/A più alto fra tutte le categorie,
`extScanCat` un dict per categoria (`SMSSTK`/`NASId`/`RRCCiph`/`cellSys`/
`GPSLoc`/`WCDMA3G`) con `level`/`n`. **Assenti** dal JSON (non
semplicemente vuoti/a zero) quando `--extended` non è stato usato.

**`--shm DIR`**: oltre a `manifest.json`, scrive anche una serie di file
di stato "piatti" (un valore per file: `0`/`1` per i booleani) in `DIR`,
pensato per un percorso in tmpfs (es. `/dev/shm/mdtcap`), da cui un
altro processo può leggere l'esito senza fare I/O su disco né parsare
JSON: `lte`, `gps`, `mdt`, `mdtPos`, `rrc`, `rrcPos`, `contract` (il
`contractId`), `path` (l'outdir di questa esecuzione), `ok`, `diagWarn`,
`diagError`, `warnPosD`, `warnPosL`, `warnMDTD`, `warnMDTL`, e, solo con
`--extended`, `extraLevel` più `extra_<CATEGORIA>_L`/
`extra_<CATEGORIA>_N` per ciascuna delle 6 categorie (es.
`extra_NASId_L`)
(queste ultime, `extraLevel` escluso, sono l'**eccezione** al formato
booleano: gli stessi interi/lettere dei campi omonimi di
`manifest.json`, non `0`/`1`). Le
directory mancanti vengono create; eventuali file di una esecuzione
precedente vengono cancellati subito all'avvio, e riscritti solo a fine
esecuzione. **Con `--tui` insieme**, `--shm` cambia anche la TUI stessa:
dopo l'elenco delle azioni non viene più stampato nulla a schermo (né
l'elenco file dell'outdir né l'eventuale "Report finale"): il consumo
dei risultati è demandato ai file in `DIR`.

**`mdtStop`** (in `DIR`, stesso `--shm DIR`): l'unico file **letto** da
`mdtcap` invece che scritto. Un altro processo lo crea (es. `touch
DIR/mdtStop`) per chiedere l'interruzione **anticipata** della cattura.
Controllato una volta al secondo durante "Cattura in corso" (funziona
anche **senza** `--tui`): se compare, la cattura si ferma lì, con la
stessa identica analisi/report/manifest che si avrebbe a scadenza
naturale di `--duration` o con un Ctrl+C manuale, solo più breve.
Cancellato non appena rilevato (il segnale è "consumato" una volta
agito), e comunque ripulito se trovato residuo all'avvio di una nuova
esecuzione. Non ha effetto durante le attese di pre-cattura
(`--lte-wait`/`--gps-wait`/`--net-attach-wait`): riguarda solo la
cattura vera e propria.

```bash
sudo ./mdtcap --autodetect --duration 60 --tui --shm /dev/shm/mdtcap
```

## Esempio completo

```bash
sudo ./mdtcap \
  --diag-port /dev/ttyUSB0 \
  --at-port /dev/ttyUSB2 \
  --qcsuper /usr/local/bin/qcsuper \
  --outdir /root/mdt_test_$(date -u +%Y%m%dT%H%M%SZ) \
  --duration 160 \
  --require-lte --lte-wait 60 \
  --label "acquisizione MDT con verifica cella LTE"
```

