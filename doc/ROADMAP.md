# Roadmap: rete di sensori EDGE

Il passo successivo del progetto è piazzare più dispositivi come
questo, **server EDGE su Raspberry Pi**, distribuiti in più punti, per
controllare le reti mobili **a campione** e verificare non solo se il
fenomeno del tracciamento via MDT esiste e in quali forme, ma anche se
fenomeni analoghi sono messi in atto da **altri attori**, diversi
dall'operatore di rete legittimo. Le categorie già cercate oggi da
`--extended` (sezione "Controlli extra" di
[doc/GUIDA_MDTCAP.md](GUIDA_MDTCAP.md)) sono pensate fin da
ora come base di analisi anche per questo scenario distribuito, non solo
per un test singolo da banco:

- **celle fittizie (IMSI-catcher)**: stazioni radio che si spacciano per
  una cella legittima dell'operatore per intercettare/localizzare i
  telefoni nei paraggi. Indizi cercati nelle categorie `cellSys`
  (downgrade forzato a 2G, assenza della lista celle vicine),
  `RRCCiph` (cifratura/integrità nulla imposta dalla rete) e `GPSLoc`
  (cella dichiarata incoerente con la posizione GPS osservata);
- **SMS nascosti con codici**: SMS silenziose/"stealth" (classe
  TP-DCS 0/2, mai mostrate all'utente) e comandi STK/OTA sospetti tipo
  SIMjacker/WIB inviati alla SIM, usati per triangolare/interrogare un
  telefono senza che il proprietario se ne accorga. Categoria
  `SMSSTK`;
- **richieste di identità non sollecitate**: la rete chiede all'IMSI
  del telefono di identificarsi (o forza una riallocazione del GUTI)
  fuori dal normale procedimento di attach/registrazione, un
  comportamento tipico di chi cerca di correlare un IMSI a una persona.
  Categoria `NASId`;
- **altri downgrade/attacchi di rete**: forzatura verso reti meno
  sicure (2G/3G) per abbassare le difese crittografiche prima di un
  attacco. Categoria `WCDMA3G`.

Come per un singolo test oggi, resta valido il principio **"un indizio
da verificare, non un verdetto"**: un campionamento distribuito su più
punti e più tempo serve proprio a distinguere un singolo evento isolato
da un pattern sistematico, prima di trarre conclusioni.


## Fatto: esito della sessione e report di copertura

Implementato il 2026-10-05 (era stato sospeso il 2026-10-04). Uso e
risultati sono descritti in [doc/GUIDA_MDTCAP.md](GUIDA_MDTCAP.md), sezione
"Esito della sessione e report di copertura". Qui resta la specifica di
partenza.

Obiettivo: distinguere "la rete non ha chiesto nulla" da "il test non
era in grado di vederlo". Sempre attivo, per ogni sessione.

**`src/coverage_report.py`**, chiamato da `run_analysis_and_report()`
in `mdtcap` dopo `compute_full_scan`. Legge il `.dlf` (record come in
`src/mdt_bitscan.py:iter_dlf_records`) e il pcap (`tshark -T fields`),
scrive `coverage_report.txt` e stampa un JSON su stdout letto da
`mdtcap`. Contenuto del report:

- **log code ricevuti** con i conteggi (0xB0C0, 0xB0EC/ED, 0xB0E2/E3):
  evidenzia firmware che filtrano o troncano dei log;
- **buchi DIAG**: intervalli senza record, frame CRC scartati
  (`diagWarn`), errori (`diagError`), timeout di `DIAG_LOG_CONFIG_F`;
- **RAT e celle**: da `periodic_cell_gps_decoded.csv` e dalle SIB1
  (`cellIdentity`, TAC, PLMN);
- **stati RRC attraversati**: transizioni connected/idle ricostruite da
  Setup/Release, cicli completi connected → idle → connected e durata
  delle fasi idle;
- **contesto**: capability dichiarate (`loggedMeasurementsIdle`,
  `standaloneGNSS`), stato GNSS (`GNSS_STATE`), mobilità
  (`src/mdt_mobility.py:classify()`), durata, esito del self-test
  (`SELF_TEST_RESULT`).

**Esito**, con l'elenco dei motivi:

- `rilevato`: almeno un indicatore forte (metriche MDT esistenti `MET_*`,
  oppure `MDTExt`/`LPP` a livello A in `FULL_L`);
- `non_verificabile`: nessun indicatore e cattura "cieca": nessun record
  0xB0C0 o NAS OTA, log non abilitati (errore `DIAG_LOG_CONFIG_F`),
  self-test fallito, durata sotto il minimo, nessuna connessione RRC
  osservata;
- `non_rilevato`: tutto il resto.

Limitazioni da elencare senza cambiare l'esito: nessun ciclo idle
completo, frame DIAG scartati, mobilità sconosciuta, UE che non dichiara
il Logged MDT.

**Dove va il risultato**: riga `Esito:` e sezione "Copertura" in
`report_finale.txt`; frase di `--parla-chiaro` (un caso non verificabile
non deve dire "Tutto bene."); manifest via `manifest_extra` (`esito`,
`esitoMotivi`, `coverage`, utile anche alla modalità federata); `--shm`
(`esito`, da aggiungere a `SHM_FIELDS` in
`src/mdtmain_lib/runner.py`); `coverage_report.txt` nella lista degli hash.
Verifica: scenari sintetici (`nasid-identity-imsi`, senza RRC, deve dare
`non_verificabile`; `full` deve dare `rilevato`; il nuovo
`coverage-idle-cycle` deve dare `non_rilevato`).

Scelte fatte in implementazione:

- durata minima 120 s, soglia degli intervalli senza record DIAG 60 s
  (`--min-duration`/`--gap` di `src/coverage_report.py`);
- in modalità replay la durata è l'arco dei record del `.dlf`; con
  `--analyze-pcap` (nessun `.dlf`) si contano i messaggi RRC e NAS
  decodificati al posto dei log code;
- l'esito resta `rilevato` anche se la cattura era in parte cieca: i
  motivi di cecità finiscono fra le limitazioni;
- `--parla-chiaro` ha una frase propria per un esito `rilevato` senza
  posizione ("Occhio: la rete sta raccogliendo misure su di te, per ora
  senza posizione.");
- in mdtmain l'esito compare accanto al pallino "Campionamento", che
  diventa arancione per `non_verificabile`; l'allarme resta legato ai
  soli indicatori forti.

Da verificare su catture reali: le soglie di durata e di intervallo, e
se il timeout di `DIAG_LOG_CONFIG_F` debba contare anche quando i record
`0xB0C0` arrivano comunque.
