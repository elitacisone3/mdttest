# Cambio IMEI (`mdtimei`): SPERIMENTALE, leggere prima di usare

> ⚠️ **`mdtimei` cambia l'IMEI del modulo (`AT+SIMEI`).** A differenza
> di tutto il resto di questo progetto, non è un'operazione di sola
> lettura/diagnostica: modifica un identificativo hardware regolamentato,
> o esplicitamente vietato da modificare, in molte giurisdizioni, e
> può causare il blocco/ban della SIM o del dispositivo lato operatore.
> **Leggere [doc/GUIDA_LEGALE_IMEI.md](GUIDA_LEGALE_IMEI.md) prima di usarlo
> fuori da un banco di prova sperimentale isolato.** Non è pensato per
> uso corrente: è stato aggiunto per essere pronto quando (e se) questo
> tipo di test verrà fatto in un ambiente controllato con celle simulate,
> dopo un vaglio legale specifico.

Impostare un IMEI diverso da quello originale (`--imei`) richiede
un'autorizzazione firmata GPG, verificata con `src/testauth` (vedi la
sezione dedicata più sotto), così "si può fare solo con
autorizzazione". `--restore` (ripristino dell'IMEI **originale**) resta
invece libero, senza alcuna autorizzazione: non è la parte rischiosa da
limitare.

```bash
sudo ./mdtimei --list-ports
sudo ./mdtimei --autodetect --imei 123456789012345   # richiede autorizzazione
sudo ./mdtimei --autodetect --restore                # nessuna autorizzazione
```

Procedura per `--imei` (un IMEI diverso da quello originale), sempre
nello stesso ordine (**la SIM deve essere inserita all'avvio**):

1. legge la porta AT da `--at-port`/`--autodetect`, o da
   `mdt_configs/system.conf` se presente (stesso file di sistema di
   mdtcap/mdtgps/mdtdiag);
2. salva l'IMEI **attuale** in `mdt_configs/imei` se non è già salvato
   (stessa logica/stesso file usato da `mdtcap`/`mdtimei`), usato anche
   da `--restore`;
3. legge l'ICCID della SIM inserita (`AT+CCID`), il DEVID di questa
   macchina e il `contractId` (device + questa SIM, vedi
   `mdtcontract --get-devid` più sotto), e verifica l'autorizzazione con
   `src/testauth`. **Abortisce senza toccare il modulo** se manca, è
   scaduta, o non corrisponde all'IMEI/DEVID/ICCID/CONTRACT richiesti;
4. superata la verifica, chiede di **rimuovere fisicamente la SIM** dal
   modulo e di premere invio per proseguire (così il modulo non ha mai,
   nella stessa sessione, sia una SIM live sia un IMEI appena cambiato);
5. imposta il nuovo IMEI (`AT+SIMEI=...`);
6. riavvia il modulo (`AT+CRESET`) e attende che torni raggiungibile in
   modo stabile;
7. verifica con `AT+SIMEI?` che il nuovo valore sia stato applicato
   davvero.

`--restore` salta i passi 3-4 (nessuna autorizzazione, nessuna richiesta
di rimuovere la SIM) e chiede invece la conferma esplicita `CONFERMO`
(salvo `--yes`): imposta l'IMEI **originale** salvato in
`mdt_configs/imei` (abortisce se quel file non esiste ancora). **Non c'è
ripristino automatico a fine esecuzione** in nessuno dei due casi:
`--restore` va comunque lanciato a parte quando serve tornare indietro.

**`--mock-time yyyy/mm/dd`** (solo per `--imei`): testa l'intera catena
di autorizzazione (lettura ICCID, calcolo contractId, esito di
`src/testauth`), **senza mai rischiare l'hardware**: con questa opzione
lo script si ferma subito dopo aver stampato l'esito (autorizzato o no),
prima di toccare `AT+SIMEI`/`AT+CRESET`, qualunque sia il risultato.

`--auth-file FILE`/`--pubkey FILE` (default `mdt_configs/imei_auth`/
`src/res/auth.pub`): passati così come sono a `src/testauth`, utile per
testare con un'autorizzazione/una chiave radice diverse da quelle reali.

`--yes`, oltre a saltare `CONFERMO` per `--restore`, salta anche il
passo "rimuovi la SIM e premi invio" per `--imei`: pensato solo per un
banco di prova scriptato già controllato/isolato, stampa comunque
un'ATTENZIONE ben visibile quando lo salta, mai in silenzio.

Ogni esecuzione scrive un log completo in `log/mdt_imei_logs/`, oltre a
quanto stampato a schermo. Dettagli completi di ogni opzione:
`./mdtimei --help`.

## Autorizzazione al cambio IMEI (`src/testauth`)

Verificato da `mdtimei` (vedi sopra) prima di impostare un IMEI
diverso da quello originale, utilizzabile
anche da solo per creare/ispezionare un'autorizzazione. Verifica (o
genera) un messaggio di autorizzazione firmato GPG.

**Per sapere il DEVID di QUESTA macchina** (da comunicare a chi deve
firmare un'autorizzazione, campo `DEVID` sotto): `mdtcontract --get-devid`,
stessa identica risoluzione dell'id hardware usata per il `contractId`
(vedi la sezione `manifest.json`/`--shm` in
[doc/GUIDA_MDTCAP.md](GUIDA_MDTCAP.md)), senza bisogno di un ICCID.

Catena di fiducia a due livelli:
- `src/res/auth.pub` è la chiave GPG **radice**;
- `mdt_configs/imei_auth` contiene, in ASCII armor, un messaggio firmato
  in chiaro (`gpg --clearsign`) e, opzionalmente, una chiave **delegata**
  (firmata dalla radice) che in quel caso è l'unica ammessa a firmare il
  messaggio: le due parti si riconoscono dai rispettivi delimitatori
  `-----BEGIN PGP ...-----`, l'ordine nel file non conta.

Il messaggio è testo semplice, una riga `CHIAVE: valore` per campo:
`FROM`/`TO` (intervallo di date `yyyy/mm/dd`, uno dei due o entrambi
opzionali), `AUTH` (la stringa restituita in caso di successo; `*`
stampa una riga vuota), e una qualunque altra chiave (es. `DEVID`,
`ICCID`, `IMEI`, `CONTRACT`, o una scelta liberamente): se compare nel
messaggio (anche più volte), il parametro `--CHIAVE` sulla riga di
comando diventa obbligatorio e deve corrispondere ad **almeno uno** dei
valori elencati.

```bash
# genera mdt_configs/imei_auth (KEYID = chiave GPG, gia' firmata dalla
# radice se si vuole una delegata, nel portachiavi di chi lo esegue)
src/testauth --create KEYID --FROM 2026/01/01 --TO 2026/12/31 \
    --DEVID rig-01 --IMEI 123456789012345 --AUTH "autorizzato" \
    > mdt_configs/imei_auth

# verifica
src/testauth --DEVID rig-01 --IMEI 123456789012345
```

**Uscita**: il valore di `AUTH` su stdout ed exit `0` se tutti i
controlli passano; errore su stderr ed exit `1` altrimenti (`2` per un
errore di sintassi sulla riga di comando, prima ancora di provare a
verificare nulla).

**`--mock-time yyyy/mm/dd`**: forza la data usata per i controlli
`FROM`/`TO` (per i test, invece della data reale). Cambia l'exit code
**solo quando l'autorizzazione viene concessa**: un successo che
sarebbe `0` diventa **`77`**, così uno script chiamante non può
scambiare per errore un'esecuzione di test per un'autorizzazione vera.
Un **fallimento** (data fuori intervallo, parametro mancante o non
corrispondente, firma non valida, ...) resta invece exit `1` **anche
con `--mock-time`**: un fallimento non si presta comunque a essere
scambiato per un successo, quindi non serve offuscarlo.

La verifica gira in un portachiavi GPG temporaneo e isolato (mai quello
di chi esegue lo script): vi si importano solo la chiave radice e
l'eventuale delegata, così l'esito non dipende da cos'altro è già
presente nel portachiavi reale. Dettagli completi: `src/testauth --help`.

