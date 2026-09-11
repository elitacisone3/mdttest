# Guida ai rischi legali del cambio IMEI (`mdtimei`)

**Questo documento non è una consulenza legale.** È un promemoria dei
rischi da tenere presenti, scritto per chi usa `mdtimei` (o valuta se
usarlo), non un parere di un avvocato. Il progetto stesso lo dice
esplicitamente: questa funzionalità **non è pensata per uso corrente**,
è stata predisposta per un eventuale uso futuro in un ambiente
controllato (banco di prova isolato, celle simulate), **dopo** una
verifica da parte di un avvocato competente in materia — non prima, e
non al posto di quella verifica.

Se questo documento e quello che segue non bastano a farti decidere con
sicurezza, la risposta di default è: **non usarlo**, e parlarne prima
con un avvocato.

> Impostare un IMEI diverso da quello originale (`--imei`) richiede un
> cancello di autorizzazione firmata GPG (vedi "Cosa fa `mdtimei` per
> limitare questi rischi" più sotto) — `--restore` (ripristino
> dell'originale) no. Tutti i rischi legali/normativi descritti in
> questo documento restano gli stessi: l'autorizzazione limita
> **chi/quando/per quale device+SIM+IMEI** è tecnicamente possibile
> farlo con questo script, non **se** cambiare l'IMEI sia lecito nella
> propria giurisdizione — quella resta una domanda per un avvocato, non
> per questo tool.

## Cos'è l'IMEI e perché è regolamentato

L'IMEI (International Mobile Equipment Identity) identifica in modo
univoco un apparato radiomobile, non l'utente o la SIM (quello è
compito dell'IMSI/ICCID). Serve a:

- reti mobili e forze dell'ordine per tracciare/bloccare dispositivi
  rubati o coinvolti in reati (tramite le liste EIR/blacklist degli
  operatori e il database centrale GSMA);
- operatori e regolatori per verificare la conformità del dispositivo
  al mercato in cui opera (omologazione, bande supportate, ecc.);
- la telefonia d'emergenza e le intercettazioni legalmente autorizzate,
  che in vari scenari fanno affidamento sulla corrispondenza fra
  identificativo di rete e dispositivo fisico.

Modificarlo rompe queste assunzioni, e per questo la maggior parte degli
ordinamenti tratta la modifica dell'IMEI in modo diverso da una comune
impostazione tecnica.

## Perché può essere illegale (in generale, non solo in Italia)

Molti paesi vietano esplicitamente, o rendono un reato a sé, la
modifica/alterazione dell'IMEI di un apparato mobile — spesso a
prescindere dall'intenzione con cui la si fa, e a volte anche solo il
*possesso* di strumenti pensati per farlo può rilevare. In altri paesi
non esiste un divieto specifico sull'IMEI in sé, ma la stessa condotta
può comunque rientrare in norme più generali su frode, alterazione di
apparati di telecomunicazione, o falsità di identificativi. Il quadro
cambia sensibilmente da un ordinamento all'altro, e anche all'interno
dello stesso paese può dipendere da:

- **intenzione/contesto**: ricerca/didattica su hardware di propria
  proprietà in laboratorio è trattata diversamente da un cambio IMEI
  per eludere un blocco antifurto o rivendere un dispositivo rubato;
- **impatto su terzi**: operare esclusivamente su una cella *simulata*
  (banco di prova isolato, senza mai emettere sulla rete pubblica reale)
  è una situazione ben diversa dal farlo agganciati a una rete
  commerciale in produzione;
- **normativa di settore**: alcuni paesi regolano l'IMEI anche a livello
  di importazione/registrazione dei dispositivi (es. database IMEI
  nazionali), con conseguenze indipendenti dal diritto penale.

Per questo l'unica risposta responsabile è: **verificare la situazione
specifica con un avvocato**, nella giurisdizione rilevante, prima di
usare `mdtimei` — non basarsi su questo documento né su ricerche
informali. A differenza di altri script del progetto, ogni esecuzione
**reale** (senza `--mock-time`) che supera l'autorizzazione cambia
davvero l'IMEI del modulo — `--mock-time` esiste solo per testare la
catena di autorizzazione (lettura ICCID, calcolo del contractId, esito
di `src/testauth`) e non tocca **mai** l'hardware, vedi più sotto: non è
un motivo per abbassare la guardia sull'uso reale.

## Rischi tecnici/operativi (anche a prescindere dal profilo legale)

- **Ban/blocco della SIM**: molti operatori correlano IMEI e IMSI a
  ogni registrazione di rete; un cambio IMEI imprevisto (specie ripetuto
  o verso un valore già noto/pubblico, vedi sotto) può far scattare
  sistemi antifrode e portare al blocco della SIM, non solo del
  dispositivo.
- **IMEI duplicato/già in uso**: un IMEI non è "libero" solo perché
  sintatticamente valido. Un valore preso da un esempio di
  documentazione pubblica è quasi certamente già stato usato da
  innumerevoli altri dispositivi/test, con un rischio concreto di
  comparire come "duplicato" nei sistemi di rete e negli EIR degli
  operatori — tanto più se il valore è scelto a caso invece che
  generato/allocato correttamente per lo scopo. **L'autorizzazione
  firmata non convalida il valore dell'IMEI in sé**: attesta solo che
  qualcuno con la chiave radice ha approvato QUEL valore per QUEL
  device/SIM/periodo — resta responsabilità di chi firma
  l'autorizzazione scegliere un IMEI di test appropriato.
- **Nessun ripristino automatico**: `mdtimei --imei` imposta l'IMEI
  indicato e riavvia, punto — NON torna da sola all'IMEI originale a
  fine esecuzione. Il dispositivo resta con l'IMEI nuovo finché non si
  rilancia esplicitamente `mdtimei --restore` (equivalente
  all'IMEI salvato in `mdt_configs/imei`) — **`--restore` non richiede
  autorizzazione**, vedi sotto.
- **Impatto sulla rete reale**: agganciarsi con un IMEI alterato a una
  rete commerciale in produzione (non simulata) coinvolge l'infrastruttura
  di un operatore terzo, e i suoi sistemi di sicurezza/antifrode, senza
  alcun controllo su come reagiranno.

## Cosa fa `mdtimei` per limitare questi rischi (ma non li elimina)

Per impostare un IMEI diverso da quello originale (`--imei`), `mdtimei`
non permette di procedere senza un'autorizzazione firmata GPG (vedi la
sezione "Autorizzazione al cambio IMEI (`src/testauth`)" nel README per
il formato completo), verificata così:

- legge l'ICCID della SIM **attualmente inserita** (`AT+CCID`) e calcola
  un `contractId` che lega insieme questo device e quella SIM
  (`mdtcontract`) — l'autorizzazione può quindi restringersi a una
  combinazione specifica device+SIM, non solo all'IMEI target;
- verifica con `src/testauth` che un'autorizzazione valida (firmata dalla
  chiave radice del progetto, o da una chiave da questa delegata) esista
  per QUESTO device (`DEVID`), QUESTA SIM (`ICCID`), l'IMEI che si sta
  per impostare e/o il `contractId` calcolato, entro l'eventuale
  finestra di date (`FROM`/`TO`) indicata — **abortisce senza toccare il
  modulo** se manca, è scaduta, o non corrisponde;
- solo dopo un'autorizzazione valida, chiede di rimuovere **fisicamente**
  la SIM appena verificata e di premere invio prima di procedere: il
  modulo non deve mai trovarsi, nella stessa sessione, con sia una SIM
  live sia un IMEI appena cambiato. Non è un controllo tecnico bloccante
  (il modulo può restare temporaneamente "convinto" di avere ancora una
  SIM finché non viene interrogato di nuovo: se `AT+CCID` risponde
  ancora qualcosa a quel punto lo script stampa un'ATTENZIONE ma
  **procede comunque** — verificare a vista, non fidarsi solo
  dell'assenza dell'avviso);
- `--mock-time yyyy/mm/dd` permette di testare l'intera catena sopra
  (lettura ICCID, calcolo contractId, esito dell'autorizzazione) **senza
  mai rischiare l'hardware**: con questa opzione lo script si ferma
  subito dopo aver stampato l'esito, prima di toccare `AT+SIMEI`/
  `AT+CRESET`, qualunque sia il risultato.

A queste si sommano altre protezioni, non legate all'autorizzazione:

- Stampa sempre un avviso di rischio, e per `--restore` richiede
  comunque conferma esplicita (`CONFERMO`, salvo `--yes` per uso
  scriptato già controllato) — mostrando l'IMEI attuale e quello che sta
  per essere impostato, cosi' da accorgersi subito di un valore sbagliato
  prima di applicarlo. Per `--imei`, questa conferma testuale è
  **sostituita** dal cancello di autorizzazione + rimozione SIM sopra
  (due controlli più forti di una semplice parola digitata).
- Salva l'IMEI originale in `mdt_configs/imei` (se non già presente)
  PRIMA di toccarlo, cosi' resta un riferimento per tornare indietro —
  ma **il ripristino va rilanciato a mano** (`mdtimei --restore`,
  nessuna autorizzazione richiesta per questo), non è automatico.
- Dopo `AT+CRESET`, verifica che il modulo torni raggiungibile e che
  `AT+SIMEI?` confermi davvero il nuovo valore, invece di dare per
  scontato che il comando sia andato a buon fine.

Tutto il resto — verificare di essere su una cella simulata, chi ha il
diritto di firmare un'autorizzazione e con quali criteri, ricordarsi di
ripristinare l'IMEI originale a fine test — è **responsabilità di chi
firma l'autorizzazione e di chi lancia lo script**, non del codice.
Nessuna di queste misure sostituisce comunque: (a) l'autorizzazione
**legale** a farlo nella propria giurisdizione (l'autorizzazione firmata
GPG di questo progetto è un controllo TECNICO interno, non ha alcun
valore legale), (b) un ambiente di test realmente isolato dalla rete
pubblica (cella simulata/Faraday), (c) il consenso del proprietario del
dispositivo e della SIM se non coincide con chi esegue il test.

## Prima di un uso reale (IMEI diverso da quello originale)

Checklist minima, non esaustiva:

1. Parere scritto di un avvocato competente in materia, nella
   giurisdizione in cui il test avverrà fisicamente.
2. Ambiente realmente isolato dalla rete pubblica (cella simulata in
   gabbia di Faraday, o equivalente) — mai una rete commerciale reale.
3. Dispositivo e SIM di cui si ha piena proprietà/autorizzazione
   esplicita a modificare, non di terzi.
4. Un IMEI di test allocato/generato correttamente per lo scopo (non un
   valore preso a caso da un esempio pubblico), se lo scenario lo
   richiede — e un'autorizzazione firmata (`src/testauth --create`) che
   lo restringa esplicitamente a questo device/SIM/periodo, per chi ha
   accesso alla chiave radice o a una delegata.
5. Un piano di ripristino verificato prima di iniziare — `mdtimei`
   NON ripristina da solo: assicurarsi che `mdt_configs/imei` contenga
   l'IMEI originale corretto e sapere già come/quando rilanciare
   `mdtimei --restore` per tornare indietro (nessuna autorizzazione
   richiesta per il ripristino).
6. Verificare per davvero, a vista, che la SIM sia stata rimossa quando
   `mdtimei` lo richiede, prima di premere invio: lo script lo
   segnala se rileva ancora una risposta a `AT+CCID`, ma **non blocca**
   l'esecuzione da solo in quel caso (vedi sopra).

Se anche solo uno di questi punti non è soddisfatto, la risposta di
default resta: non procedere.
