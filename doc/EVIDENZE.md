# Interpretare le evidenze raccolte da mdtcap

Guida tecnica per leggere e interpretare l'output di una cattura
`mdtcap` (live o replay via `--analyze-dlf`/`--analyze-pcap`). Presuppone
familiarità con RRC/LTE (TS 36.331) e con l'uso base di `tshark`/Wireshark;
per l'elenco completo e autoritativo dei file prodotti vedi la sezione 4
di [GUIDA_MDTCAP.md](GUIDA_MDTCAP.md), qui ci si concentra su come
leggerli e su cosa concludere (o non concludere) da ciascuno.

## Il meccanismo osservato: gli IE RRC legati all'MDT

L'MDT (Minimization of Drive Tests) attraversa due fasi distinte nel
traffico RRC, ed è importante non confonderle quando si legge una
cattura:

1. **Configurazione dalla rete**: `LoggedMeasurementConfiguration-r10`
   (dentro `RRCConnectionReconfiguration` o
   `RRCConnectionReconfiguration` con `dedicatedInfoNAS`, a seconda del
   release). Contiene `traceReference`, `traceRecordingSessionRef`,
   `tce-Id`, `loggingDuration`, `loggingInterval`, ed eventualmente
   `areaConfiguration` nelle release successive. **Non contiene un
   campo "posizione"**: configura solo i parametri del logging, non
   richiede esplicitamente coordinate GPS.
2. **Richiesta/risposta successiva**: la rete può poi chiedere
   esplicitamente l'invio delle misure registrate con
   `UEInformationRequest` (campo `logMeasReportReq`); l'UE risponde con
   `UEInformationResponse`, che porta `logMeasReport` e, se disponibile,
   un IE di posizione: `locationInfo-r10`/`r11`/`r16` o, nelle release
   più recenti, `coarseLocationInfo-r17`. È l'UE a decidere se includere
   la posizione (tipicamente se il GPS/GNSS era attivo al momento), non
   la rete a "estrarla" direttamente con un flag nella configurazione.

Questo significa che una cattura può mostrare una configurazione MDT
senza nessuna risposta con posizione (perché la finestra di cattura
finisce prima, o perché l'UE non aveva un fix GPS), e viceversa una
risposta con posizione senza aver mai visto la configurazione (se
questa era arrivata prima dell'inizio della cattura). Leggere sempre i
due eventi come **correlati ma distinti**.

## Struttura di una cartella di evidenza

Ogni esecuzione produce una cartella autonoma (una cattura live, o un
replay da `.dlf`/`.pcap`). I file rilevanti per l'interpretazione, in
ordine di lettura consigliato:

| File | Cosa contiene | Come leggerlo |
|---|---|---|
| `manifest.json` | riepilogo strutturato (booleani/contatori) dell'intera esecuzione | punto di partenza: dice subito se c'è qualcosa da approfondire, vedi sotto |
| `logged_measurement_configuration.txt` | dump `tshark -V` isolato al solo `loggedMeasurementConfiguration` | conferma/esclude la fase 1 (configurazione), con tutti i sottocampi |
| `report_mdt_rrc.txt` | superset del precedente: tutti gli IE MDT/RRC (`loggedMeasurementConfiguration`, `locationInfo`, `coarseLocationInfo-r17`, ...) | vista tecnica completa, frame per frame |
| `mdt_location_requests.txt` / `_summary.csv` | filtro più ampio: include anche `ueInformationRequest`/`logMeasReportReq` e la risposta `ueInformationResponse`/`logMeasReport` | ricostruzione cronologica dello scambio rete/UE (fase 1 e fase 2 insieme), il CSV è utile per un timeline rapido (frame, orario UTC, tempo relativo, descrizione) |
| `coordinate_estratte.csv` / `decode_coordinate.log` | coordinate decodificate dagli IE di posizione trovati sopra | se non vuoto, contiene le coordinate **effettivamente inviate dall'UE alla rete** (non quelle del log periodico locale, vedi sotto) |
| `capture_<timestamp>.pcap` | traffico completo in formato GSMTAP | da aprire in Wireshark per ispezionare qualunque frame non coperto dai filtri sopra, o per verificare un IE con un filtro proprio (es. `lte-rrc.loggedMeasurementConfiguration_r10_element`) |
| `capture_<timestamp>.dlf` | cattura Diag grezza (formato QCSuper/QXDM) | sorgente da cui è stato (ri)generato il `.pcap`; utile per rigenerare l'analisi con `--analyze-dlf` dopo un aggiornamento dei filtri |
| `periodic_cell_gps.csv` / `_decoded.csv` | log periodico **indipendente** di cella e GPS (polling AT, non derivato dal traffico RRC) | serve come *ground truth* per sapere dove si trovava fisicamente il dispositivo durante il test, non va confuso con una posizione inviata via MDT: è il modem che chiede la propria posizione (`AT+CGPSINFO`), non la rete che la riceve |
| `context_pre.txt` / `context_post.txt` | contesto AT (IMEI, ICCID, operatore, stato registrazione, qualità segnale) prima/dopo la cattura | verifica che il test sia partito/finito nelle condizioni attese (SIM sbloccata, LTE agganciato, ecc.) |
| `report_finale.txt` | riepilogo Test/Operatore/UE/RRC/MDT/Risultato (solo con `--report`) | lettura rapida, ma per un'analisi rigorosa fare sempre riferimento ai file sopra, non solo a questo riassunto |
| `session.log` | log completo dell'intera esecuzione | traccia ogni passo temporale (utile per correlare un evento RRC con un'azione specifica, es. un ciclo `--reconnect-interval`) |
| `hashes_sha256.txt` | hash SHA-256 di tutti i file prodotti | verifica di integrità, vedi sotto |
| `manifest.txt` / `manifest.json` | riepilogo dell'esecuzione, leggibile da umano/da script | vedi sezione dedicata sotto |
| `extra_scan_report.txt` / `extra_scan*.log` (solo con `--extended`) | indizi di comportamento di rete sospetto/malevolo (IMSI-catcher), per categoria | vedi [GUIDA_MDTCAP.md](GUIDA_MDTCAP.md), sezione "Controlli extra": un indizio da verificare, non un verdetto |

## Leggere `manifest.json`

Campi principali per l'interpretazione, con la loro relazione logica:

```json
{
  "lte": true,
  "hasMDT": false, "numMDT": 0,
  "reqMDTPos": false, "reqMDTGPS": false,
  "hasRRC": false, "hasRRCPos": false,
  "numRRC": 0, "numRRCPox": 0
}
```

- `lte`: se `false`, il resto va letto con cautela: gli IE MDT rilevanti
  sono definiti solo in LTE-RRC (TS 36.331), su GSM/WCDMA la cattura non
  produce dati MDT interpretabili a prescindere da cosa fa la rete.
- `hasMDT` / `numMDT`: presenza e conteggio di
  `loggedMeasurementConfiguration` (fase 1, vedi sopra). `hasMDT: false`
  significa **in questa cattura non è arrivata una configurazione MDT**,
  non che l'operatore non la invii mai (vedi la sezione sui falsi
  negativi sotto).
- `reqMDTPos` / `reqMDTGPS`: `true` se la rete ha esplicitamente
  richiesto l'invio delle misure (`logMeasReportReq`) e/o se la
  configurazione implica una richiesta di posizione. È un segnale più
  forte di `hasMDT` da solo: indica intenzione attiva della rete di
  ottenere un riscontro, non solo di predisporre il logging.
- `hasRRC` / `hasRRCPos`: se l'UE ha effettivamente risposto
  (`ueInformationResponse`/`logMeasReport`) e se quella risposta
  includeva una posizione. `hasRRCPos: true` è l'evidenza più diretta
  possibile: una posizione è stata davvero trasmessa alla rete tramite
  questo meccanismo.
- `numRRC` / `numRRCPox`: quante risposte RRC in totale, e quante di
  queste con posizione: utile per distinguere un singolo evento isolato
  da un pattern ripetuto nella finestra di cattura.

Combinazioni tipiche e come leggerle:

| `hasMDT` | `reqMDTPos`/`reqMDTGPS` | `hasRRCPos` | Interpretazione |
|---|---|---|---|
| `false` | `false` | `false` | nessun segnale MDT in questa finestra: non concludere l'assenza assoluta, vedi durata sotto |
| `true` | `false` | `false` | configurazione ricevuta ma nessuna richiesta/risposta con posizione osservata ancora: la finestra potrebbe essere troppo corta per vedere la fase 2 |
| `true` | `true` | `false` | la rete ha richiesto esplicitamente l'invio delle misure, ma l'UE non ha (ancora) risposto con posizione, o non ne aveva una disponibile (GPS spento) |
| `true`/`false` | `true`/`false` | `true` | evidenza diretta: una posizione è stata effettivamente inviata alla rete tramite un meccanismo RRC legato all'MDT |

## Falsi negativi: la durata conta

Una cattura breve (es. il profilo `quick`, pensato solo per verifica
funzionale) **non è probante sull'assenza di MDT**: se l'operatore invia
la configurazione a intervalli (es. ogni N minuti/ore, o legata a eventi
di rete come un nuovo attach), una finestra di pochi minuti può
semplicemente non includere l'evento. Per una conclusione difendibile
sull'assenza di richieste MDT servono, come minimo, catture nell'ordine
delle decine di minuti (vedi i profili `standard`/`reconnect-trap` in
`mdt_configs/profile/`), idealmente ripetute in momenti diversi. Un
singolo `hasMDT: false` da solo dimostra "non osservato in questa
sessione", non "mai inviato da questo operatore".

Viceversa, un singolo `hasRRCPos: true` è già evidenza sufficiente:
un evento positivo non ha bisogno di essere ripetuto per essere valido,
a differenza di un'assenza.

## Catena di custodia

```bash
cd <outdir>
sha256sum -c hashes_sha256.txt
```

Verifica che nessun file sia stato alterato dopo la fine della cattura.
`manifest.txt`/`manifest.json` registrano inoltre host, porte (o
modalità replay), versione di `qcsuper`, timestamp e hash: sufficienti a
ricostruire in quali condizioni è stata prodotta l'evidenza. Il campo
`contractId` (hash RIPEMD-160, vedi `./mdtcontract --help`) lega insieme
in modo verificabile il device di test e l'ICCID della SIM usata, utile
se l'evidenza deve essere associata a una specifica richiesta/pratica
senza dover conservare l'ICCID in chiaro altrove.

## Cosa viene inviato al server (invio dati/test continuato)

Nelle due modalità che inviano dati (vedi [PRIVACY.md](PRIVACY.md)), non
viene sempre trasmessa l'evidenza completa: se il test è `OK`, non ci
sono avvisi/errori diag (`diagWarn`/`diagError` nel manifest, vedi
sezione 4 di [GUIDA_MDTCAP.md](GUIDA_MDTCAP.md)) e non è attivo
`--extended` con `extraLevel` diverso da `I`, viene inviato solo il
riepilogo tecnico `manifest.json`, per limitare il traffico quando non
c'è nulla da approfondire.

In tutti gli altri casi (test non riuscito, presenza di
`diagWarn`/`diagError` anche con test riuscito, o controlli extra con un
livello superiore a `I`) viene inviata l'evidenza completa (pcap, dlf,
qcsuper.log, i report testuali, ecc.). Un `diagError`, in particolare,
può significare che un'intera categoria di traffico è mancante dal
`.dlf` senza che `OK`/`hasMDT`/`hasRRC` se ne accorgano da soli (vedi
sezione 3 di [GUIDA_MDTCAP.md](GUIDA_MDTCAP.md)): merita comunque
l'evidenza intera, per poterlo diagnosticare in un secondo momento.

## Usare l'evidenza a supporto di una richiesta verso l'operatore

Un operatore, se interpellato con una richiesta di accesso ai dati (es.
ex art. 15 GDPR) o nell'ambito di un reclamo, può descrivere in termini
generali come tratta i dati di geolocalizzazione derivati dalla propria
rete radiomobile. Il progetto [diritti.xyz](https://diritti.xyz/)
raccoglie guide pratiche per formulare questo tipo di richiesta, e
pubblica esempi reali di risposte ottenute. Un estratto di una risposta
realmente ricevuta da un operatore italiano (riportato su
<https://diritti.xyz/risposta_TIM.html>), a titolo di esempio del tipo
di formulazione che ci si può aspettare in questo ambito:

> "TIM inoltre tratta i dati di geolocalizzazione (diversi dai dati di
> traffico), senza storicizzazione dei dati stessi, per il
> funzionamento del servizio radiomobile [...] fermo restando quanto
> riportato al successivo punto 2., potrebbero essere trattati da TIM
> per l'erogazione di servizi di geolocalizzazione richiesti da propri
> Clienti business; nell'ambito di tali servizi TIM raccoglie dalla
> propria rete radiomobile i dati di geolocalizzazione, procedendo alla
> loro anonimizzazione e aggregazione prima di renderli disponibili ai
> suddetti Clienti."

Una formulazione di questo tipo (dati di geolocalizzazione "per il
funzionamento del servizio radiomobile", distinti dai dati di traffico,
senza storicizzazione) è generica e non specifica se comprenda anche
richieste MDT con posizione dell'utente finale, né in quali circostanze
vengano attivate. È esattamente qui che l'evidenza tecnica raccolta con
`mdtcap` diventa rilevante, a prescindere dall'operatore: un
`hasRRCPos: true` in una cattura propria, con timestamp e hash
verificabili, permette di chiedere puntualmente se quella specifica
trasmissione di posizione rientri nella descrizione generica fornita
dall'operatore, o di corroborare/contestare quanto dichiarato con un
riscontro tecnico indipendente invece di doversi limitare a quanto
l'operatore sceglie di rendere noto.

## Limiti da tenere presenti

- L'evidenza riguarda **una singola sessione, su un singolo
  device/SIM**: non generalizza automaticamente al comportamento
  dell'operatore verso altri utenti o in altri momenti.
- La decodifica dei valori di qualità segnale (RSRQ/RSRP/RSSI/RSSNR in
  `periodic_cell_gps_decoded.csv`) segue il formato SIMCom documentato
  ma non è verificata al 100% in scala/unità su ogni firmware: in caso
  di dubbio fare riferimento al campo `cpsi_raw`/`cgpsinfo_raw`
  (risposta AT integrale) nello stesso file.
- In modalità `--analyze-dlf`/`--analyze-pcap` valgono le stesse regole
  di interpretazione di una cattura live: cambia solo l'assenza dei file
  legati al device (`context_*.txt`, `periodic_cell_gps*.csv`,
  `qcsuper.log`), non la logica di lettura degli IE RRC.
- Un `manifest.json` con `OK: false` o `miss: true` segnala un problema
  nella cattura stessa (es. divergenza tra pcap live e pcap rigenerato
  dal `.dlf`, vedi sezione 3 di [GUIDA_MDTCAP.md](GUIDA_MDTCAP.md)): va
  risolto/verificato prima di trarre conclusioni sul contenuto MDT.
