# Test sintetici per mdtcap

Questa cartella contiene `gen_mdt_dlf.py`, un generatore di file `.dlf`
sintetici (lo stesso formato scritto da `qcsuper`/da una cattura `mdtcap`
reale) che permette di **testare `mdtcap` end-to-end senza modem, SIM o
rete**: niente hardware, niente attesa di un operatore che attivi
davvero l'MDT.

Serve a due scopi:

1. **Verificare che `mdtcap` funzioni** (regressione): ogni scenario produce
   un verdetto atteso e noto in anticipo (tabella sotto) — se dopo una
   modifica allo script il verdetto cambia, c'è un problema.
2. **Testare casi limite** che in una cattura reale potrebbero non
   presentarsi mai (es. una risposta MDT senza posizione, o l'IE
   `coarseLocationInfo-r17` di Release 17): utile per stanare falsi
   negativi nei filtri tshark di `mdtcap` (`MDT_RRC_FILTER` e affini,
   vedi commenti in testa a `mdtcap`) prima che si presentino sul campo.

## Requisiti

- `python3` con `pycrate` installato (è una dipendenza di `qcsuper`, quindi
  se `qcsuper` funziona è già presente).
- `qcsuper` (per convertire il `.dlf` in `.pcap`) e `tshark` (per
  l'estrazione), entrambi già richiesti da `mdtcap` stesso.

## Uso rapido

```bash
# scenario di default ("full": richiesta MDT completa + posizione GPS)
python3 gen_mdt_dlf.py -o test.dlf

# uno scenario specifico
python3 gen_mdt_dlf.py --scenario r17-only -o test.dlf

# parametri personalizzati (posizione, PLMN, qualità radio)
python3 gen_mdt_dlf.py --scenario full --lat 45.4642 --lon 9.1900 \
    --mcc 222 --mnc 10 --rsrp 45 --rsrq 15 -o milano.dlf
```

Poi si analizza il `.dlf` con `mdtcap` in modalità replay, esattamente come
si farebbe con una cattura reale:

```bash
sudo ./mdtcap --analyze-dlf synthetic_test/test.dlf \
    --qcsuper /usr/local/bin/qcsuper \
    --outdir /tmp/mdt_test_synth \
    --report --parla-chiaro
```

(`--analyze-dlf` non richiede root né un device — l'unico motivo per cui
altrove serve `sudo` è l'accesso alla porta Diag durante una cattura live,
qui assente. Vedi la sezione "Senza porte" del `README.md` principale.)

Controllare poi `/tmp/mdt_test_synth/report_finale.txt` e confrontarlo con
la colonna "Verdetto atteso" della tabella sotto.

## Parametri di `gen_mdt_dlf.py`

| Opzione | Default | Significato |
|---|---|---|
| `-o`, `--out` | `synthetic_mdt_capture.dlf` | file `.dlf` di output |
| `--scenario` | `full` | sequenza di messaggi RRC da generare, vedi tabella sotto |
| `--lat`, `--lon` | `41.902782`, `12.496366` (Roma) | coordinate codificate nell'`Ellipsoid-Point` (gradi decimali) |
| `--mcc`, `--mnc` | `222`, `01` (Italia, TIM) | PLMN usato in `traceReference-r10`/`servCellIdentity` |
| `--trace-id` | `010203` | `traceId-r10`, esadecimale |
| `--session-ref` | `0001` | `traceRecordingSessionRef-r10`, esadecimale |
| `--tce-id` | `10` | `tce-Id-r10`, esadecimale |
| `--rsrp` | `60` (≈ -81 dBm) | `rsrpResult-r10`, RSRP-Range 0–97 (TS 36.331) |
| `--rsrq` | `20` (≈ -10 dB) | `rsrqResult-r10`, RSRQ-Range 0–34 (TS 36.331) |
| `--base-time` | `2026-09-05T12:00:00Z` | timestamp UTC (ISO 8601) del primo record diag |

`--rsrp`/`--rsrq` sono usati solo dagli scenari che generano una
`ueInformationResponse` (`full`, `response-no-gps`); `--lat`/`--lon` solo da
quelli con una posizione (`full`, `r17-only`).

## Scenari (`--scenario`) e verdetto atteso

Ogni scenario genera una sequenza diversa di messaggi RRC per esercitare un
ramo diverso della logica di `mdtcap` (`generate_final_report`/
`generate_plain_report` in `mdtcap`). Verdetti verificati eseguendo
realmente `mdtcap --analyze-dlf` su ciascuno scenario:

| `--scenario` | Messaggi generati | `Test` | `Operatore` | `UE` | `RRC` | `MDT` | `--parla-chiaro` |
|---|---|---|---|---|---|---|---|
| `full` (default) | `loggedMeasurementConfiguration` → `ueInformationRequest`+`logMeasReportReq` → `ueInformationResponse`+`logMeasReport`+`locationInfo` (GPS) | OK | MDT, GPS, Attiva | GPS | 1 (1 con GPS) | 2 | *Stacca, stacca, stacca...* |
| `config-only` | solo `loggedMeasurementConfiguration` | OK | MDT | OK | 0 | 1 | *Tutto bene.* |
| `request-only` | `loggedMeasurementConfiguration` → `ueInformationRequest`+`logMeasReportReq` (nessuna risposta UE) | OK | MDT, Attiva | OK | 0 | 2 | *Stacca, stacca, stacca...* |
| `response-no-gps` | `ueInformationRequest`+`logMeasReportReq` → `ueInformationResponse`+`logMeasReport` **senza** `locationInfo` | OK | MDT, Attiva | OK | 1 (0 con GPS, 1 senza) | 1 | *Stacca, stacca, stacca...* |
| `r17-only` | `ueInformationResponse` con **solo** `coarseLocationInfo-r17` (Release 17), nessun altro messaggio | OK | OK | GPS | 1 (1 con GPS) | 0 | *Stacca, stacca, stacca...* |

Note:

- `config-only`/`request-only` non producono una `ueInformationResponse`
  apposta: servono a verificare che `mdtcap` distingua correttamente "la
  rete ha configurato/chiesto l'MDT" (`Operatore`) da "l'UE ha risposto"
  (`RRC`/`UE`), anche quando la risposta non è (ancora) presente nella
  cattura.
- `response-no-gps` verifica il ramo "misure senza posizione": nella
  grammatica ASN.1 `locationInfo-r10` è `OPTIONAL` dentro `LogMeasInfo-r10`
  (`EUTRA-RRC-Definitions.asn`), quindi è una risposta MDT legittima anche
  senza coordinate (es. GPS spento sull'UE). Il campo tecnico `RRC`
  riflette correttamente questo fatto ("0 con GPS, 1 senza"), ma
  `--parla-chiaro` segnala comunque *Stacca, stacca, stacca...*: la rete
  ha comunque chiesto esplicitamente l'invio delle misure
  (`logMeasReportReq`, campo `Attiva`), e questo banco di prova è un
  modem/SIM isolato — non il telefono che userebbe davvero l'utente
  finale. Un UE diverso (uno smartphone reale, con la localizzazione
  attiva) potrebbe rispondere alla STESSA richiesta della rete includendo
  la posizione: è quindi la richiesta esplicita in sé, non il
  comportamento di questo particolare UE di test, il segnale rilevante
  per `--parla-chiaro`.
- `r17-only` è il caso di **regressione**: prima di una fix a `mdtcap`,
  nessuno dei filtri `MDT_*_FILTER` intercettava `coarseLocationInfo-r17`
  (IE fratello di `logMeasReport-r10`, non annidato al suo interno — vedi
  commento su `MDT_RRC_FILTER` in testa a `mdtcap`), e questo scenario
  produceva `Operatore: OK` / *Tutto bene* nonostante l'UE avesse inviato
  una posizione. **Rieseguire questo scenario dopo ogni modifica ai filtri
  `MDT_*_FILTER`** per verificare che il rilevamento non regredisca: se
  `Operatore` torna a `OK` o la frase `--parla-chiaro` torna a *Tutto
  bene*, la fix è stata persa.

## Verificare anche i file di dettaglio

Oltre a `report_finale.txt`, è utile controllare:

- `report_mdt_rrc.txt` — non è mai vuoto per nessuno dei cinque scenari:
  contiene il dump `-V` di `loggedMeasurementConfiguration` (`full`,
  `config-only`, `request-only`), di `logMeasReport-r10` (`full`,
  `response-no-gps`) o di `coarseLocationInfo-r17` (`r17-only`).
- `coordinate_estratte.csv` — deve avere una riga con le coordinate passate
  a `--lat`/`--lon` per gli scenari `full` e `r17-only` (colonna
  `source_field` = `ellipsoid_Point_r10` o `coarseLocationInfo_r17` a
  seconda dello scenario), vuoto per gli altri tre.
- `mdt_location_requests_summary.csv` — una riga per ciascun messaggio RRC
  generato dallo scenario (nomi dei messaggi, non conteggi aggregati).

## Scenari per `mdtcap --extended` (`src/extra_scan`)

Oltre agli scenari MDT sopra, `gen_mdt_dlf.py` genera traffico che esercita
5 delle 6 categorie di "controlli extra" rilevate da `src/extra_scan`
(GPSLoc esclusa per ora: non è diag-based, si basa su
`periodic_cell_gps_decoded.csv` prodotto da `mdtcap` stesso). Vanno
analizzati con `--extended` (altrimenti `mdtcap` non invoca affatto
`extra_scan`):

```bash
sudo ./mdtcap --analyze-dlf synthetic_test/test/rrcciph-eea0.dlf \
    --qcsuper /usr/local/bin/qcsuper \
    --outdir /tmp/mdt_test_rrcciph --extended --report
```

| `--scenario` | Traffico generato | Regola in `extra_configs/main.conf` | Livello atteso |
|---|---|---|---|
| `rrcciph-eea0` | `SecurityModeCommand` con EEA0/EIA0 | `RRCCiph.eea0_eia0` | `RRCCiph=A` (1 evento, nessuna soglia) |
| `cellsys-2g-downgrade` | `RRCConnectionRelease` con `redirectedCarrierInfo=geran` | `cellSys.forced_2g_downgrade` | `cellSys=C` (1 evento, sotto `cum_threshold=2`) |
| `wcdma3g-3g-downgrade` | `RRCConnectionRelease` con `redirectedCarrierInfo=utra-FDD` | `WCDMA3G.forced_3g_downgrade` | `WCDMA3G=W` (1 evento, sotto `cum_threshold=3`) |
| `nasid-identity-imsi` | NAS EMM `Identity Request` (IMSI) | `NASId.unsolicited_identity_imsi` | `NASId=C` (1 evento, sotto `cum_threshold=3`) |
| `nasid-guti-realloc-frequent` | due `GUTI Reallocation Command` a 10s di distanza | `NASId.guti_realloc_anomaly` | `NASId=W` (sotto `min_interval_s=60`) |
| `smsstk-silent-sms` | SMS-DELIVER TP-DCS class 0 (`0xF0`), dentro NAS Downlink Transport | `SMSSTK.silent_sms` | `SMSSTK=W` (1 evento, sotto `cum_threshold=5`) |

Nota: `WCDMA3G.a5_0_2g` (vero Cipher Mode Command GSM, nuovo diag log type
0x512F) resta fuori scope per ora, nessuno scenario nativo lo esercita.
È raggiungibile solo via il trigger `--test-sms` sotto.

## Scenari per `mdtcap --test-sms` (SMS di test)

`mdtcap --test-sms` (implica `--extended`) cerca, nel `.dlf`, un SMS
VISIBILE (non silenzioso) con questo testo esatto, spazi bianchi ignorati:
```
${"37337:H4XOR:MEGAVIRUS:T35T:F4K3:P4YL04D"::do(CATEGORIA)}
```
e forza la categoria indicata al livello A, vedi
`src/extra_scan:detect_test_sms_trigger`. Pensato per un test sul campo:
un operatore invia questo SMS da un altro telefono, in un ambiente
controllato, per validare l'intera catena senza aspettare un vero evento.

```bash
sudo ./mdtcap --analyze-dlf synthetic_test/test/testsms-rrcciph.dlf \
    --qcsuper /usr/local/bin/qcsuper \
    --outdir /tmp/mdt_test_testsms --test-sms --report
```

| `--scenario` | Token nel testo magico | Categoria forzata ad A | Senza `--test-sms` |
|---|---|---|---|
| `testsms-rrcciph` | `RRCCiph` | solo `RRCCiph` | nessun effetto (`extraLevel=I`) |
| `testsms-cellsys` | `cellSys` | solo `cellSys` | nessun effetto |
| `testsms-wcdma3g` | `WCDMA3G` | solo `WCDMA3G` | nessun effetto |
| `testsms-nasid` | `NASId__` | solo `NASId` | nessun effetto |
| `testsms-smsstk` | `SMSSTK_` | solo `SMSSTK` | nessun effetto |
| `testsms-all` | `ALL____` | tutte e 5 (RRCCiph/cellSys/WCDMA3G/NASId/SMSSTK) | nessun effetto |

Importante: **senza `--test-sms`**, `extra_scan` non cerca affatto questo
SMS (nessuna chiamata a `detect_test_sms_trigger`): un `testsms-*.dlf`
analizzato con solo `--extended` produce lo stesso risultato di una
cattura senza traffico rilevante (`extraLevel=I`). Verificato eseguendo
`testsms-rrcciph.dlf` sia con `--test-sms` (RRCCiph=A) sia senza
(RRCCiph=I, nessun evento).

## Aggiungere un nuovo scenario

Per testare un nuovo IE MDT (es. una futura Release 18), seguire lo schema
di `r17-only` in `gen_mdt_dlf.py`:

1. Trovare la posizione esatta dell'IE nella grammatica ASN.1 aggiornata
   (`epan/dissectors/asn1/lte-rrc/EUTRA-RRC-Definitions.asn` nel repo
   [wireshark/wireshark](https://github.com/wireshark/wireshark)) e la
   catena di `nonCriticalExtension` in cui è annidato.
2. Scrivere una funzione `build_...()` che costruisca quel `SEQUENCE` con
   `pycrate` (vedi `build_ue_information_response_r17_only` come esempio).
3. Aggiungere il nome dello scenario a `SCENARIOS` e il ramo corrispondente
   in `build_records()`.
4. Verificare con `tshark -G fields` che il nome di campo usato nei filtri
   `MDT_*_FILTER` di `mdtcap` esista davvero nel dissector installato,
   *prima* di aggiungerlo ai filtri.
5. Eseguire il nuovo scenario con `mdtcap --analyze-dlf` e verificare se
   viene rilevato — se no, è un falso negativo da correggere nei filtri.
