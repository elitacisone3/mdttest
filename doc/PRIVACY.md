# Privacy, spiegata senza tecnicismi

**Questa non è un'informativa conforme al GDPR.** Spiega, in parole
semplici, cosa fa questo strumento con i dati durante un test e perché,
per chi non ha un background tecnico. Per i dettagli tecnici vedi il
[README](../README.md); per i rischi legali specifici del cambio IMEI
vedi [GUIDA_LEGALE_IMEI.md](GUIDA_LEGALE_IMEI.md).

## In breve

- Questo strumento serve a **scoprire se il tuo operatore telefonico sta
  tracciando la posizione del tuo telefono/SIM** usando una funzione di
  rete chiamata MDT (spiegata sotto).
- Durante un test, il programma **ascolta** i messaggi che la rete manda
  al modem collegato al Raspberry Pi, senza però entrare nei sistemi
  dell'operatore, né modificare o intercettare nulla che riguardi altre
  persone.
- Per un singolo test (locale o su chiavetta USB), tutti i dati raccolti
  restano **esclusivamente sul Raspberry Pi** (o sulla chiavetta): non
  viene inviato nulla su internet, nessun account, nessuna "app"
  collegata. Se non copi tu stesso i file altrove, restano solo lì.
- Esistono anche due modalità facoltative, **"Esegui un test inviando i
  dati"** e **"Imposta test continuato"** (avviate esplicitamente da
  `mdtmain`, mai attive di default): in questi soli casi le evidenze
  vengono cifrate e inviate a un server scelto da chi gestisce il
  Raspberry Pi, e solo per SIM/device già registrati per il progetto,
  o registrati al momento con un token di verifica fornito da chi gestisce
  il server (vedi più sotto "Modalità con invio dati").

## A cosa serve: cos'è l'MDT

MDT sta per **Minimization of Drive Tests** ("minimizzazione dei test
su strada"). È una funzione prevista dagli standard delle reti mobili
(LTE e successive) che permette all'operatore di chiedere al tuo
telefono di registrare informazioni sulla qualità del segnale, e
opzionalmente anche **la tua posizione GPS**, per poi rimandargliele
indietro. È nata per uno scopo legittimo: aiutare l'operatore a capire
dove il segnale è debole, senza dover mandare fisicamente un tecnico in
giro con un furgone a fare misurazioni (da qui il nome).

Il problema è che questa stessa funzione, se usata per raccogliere
anche la posizione GPS, **può diventare uno strumento di
localizzazione** del dispositivo (e quindi, indirettamente, della
persona che lo porta con sé), attivabile dalla rete stessa, senza che
sia necessariamente evidente all'utente che sta succedendo. Questo
progetto esiste per rendere quella cosa **visibile e verificabile**:
invece di doversi fidare di quello che un operatore dichiara nella
propria informativa privacy, un tecnico può collegare un modem a un suo
banco di prova (SIM propria, dispositivo proprio) e osservare
direttamente, nel traffico di rete, se e quando arriva una richiesta di
questo tipo.

## Come funziona, senza tecnicismi

Il Raspberry Pi è collegato via USB a un modulo modem (lo stesso tipo di
componente che c'è dentro un telefono), con dentro una SIM. Durante un
test, il programma:

1. si mette in ascolto sul canale "di servizio" con cui il modem parla
   con la rete, lo stesso canale che userebbe qualunque telefono con
   quella SIM dentro;
2. registra, in un file, tutti i messaggi che la rete manda al modem e
   che il modem manda alla rete durante quella finestra di tempo;
3. a fine test, guarda dentro quei messaggi cercando in particolare
   quelli legati all'MDT: la rete ha chiesto la configurazione MDT? Ha
   chiesto esplicitamente l'invio delle misure? Il modem ha risposto
   includendo una posizione?
4. produce un riepilogo leggibile ("è successo o no", e se sì cosa
   esattamente) invece di lasciare solo il file tecnico grezzo.

Non c'è nessuna "intrusione": è concettualmente equivalente a mettersi
in ascolto su una conversazione a cui il proprio stesso dispositivo sta
già partecipando, con la SIM e il modem di proprietà di chi fa il test.
Non vengono toccati dati di altri utenti della rete, né sistemi
dell'operatore: si osserva solo quello che arriva a **questo** modem, su
**questa** SIM.

## Che dati vengono raccolti durante un test

Un test produce una cartella con diversi file. Tra le informazioni che
possono comparire, alcune sono dati che identificano il dispositivo/la
SIM usati per il test, non te come persona in astratto, ma sono comunque
dati personali/identificativi a tutti gli effetti:

- **IMEI** del modem (identifica l'apparecchio);
- **ICCID e IMSI** della SIM (identificano la SIM/il contratto);
- informazioni sulla cella di rete a cui ci si è agganciati (operatore,
  zona geografica approssimativa);
- **posizione GPS**, ma solo se il test è stato lanciato con l'opzione
  che accende il GPS, altrimenti non viene mai richiesta;
- il traffico di rete "di servizio" catturato (i messaggi di cui sopra),
  incluse le eventuali risposte con posizione se la rete le ha davvero
  richieste;
- un'impronta (hash) di ogni file prodotto, per poter dimostrare in un
  secondo momento che il file non è stato alterato dopo il test.

Nessuno di questi dati riguarda persone diverse da chi possiede il
dispositivo e la SIM usati per il test.

Con l'opzione facoltativa `--extended` (analisi aggiuntiva di indizi di
comportamento di rete sospetto/malevolo, vedi
[GUIDA_MDTCAP.md](GUIDA_MDTCAP.md) sezione "Controlli extra") non viene
raccolto **nessun dato in più**: si limita
ad analizzare più a fondo lo stesso traffico già catturato per il test
MDT, producendo file di log/report aggiuntivi nella stessa cartella.

## Dove vanno questi dati

**Da nessuna parte, se non lo decidi tu.** Per un singolo test (in
locale o su chiavetta USB), mdtcap:

- non ha nessuna funzione di invio automatico (niente upload, niente
  telemetria, niente "phone home" verso l'autore del progetto o
  chiunque altro);
- non richiede una connessione internet per funzionare (a parte, ovviamente, la
  connessione dati della SIM sotto test, che è necessaria perché è
  proprio quella rete a dover essere osservata);
- salva tutto in una cartella sul disco/scheda SD del Raspberry Pi (o
  sulla chiavetta USB, se scelto).

Sei tu a decidere se, quando e con chi condividere i risultati di un
test (ad esempio per usarli come prova concreta in una richiesta verso
il tuo operatore, vedi sotto). Proprio perché quei file contengono dati
identificativi reali (IMEI/ICCID/IMSI, eventuale posizione), trattali
con la stessa cura con cui tratteresti un qualunque altro documento
riservato: non caricarli su servizi pubblici, non condividerli con chi
non ne ha bisogno.

### Modalità con invio dati (opzionali)

`mdtmain` (l'interfaccia guidata del progetto) offre, in aggiunta ai
test singoli descritti sopra, due modalità che inviano dati a un
server: **"Esegui un test inviando i dati"** (un singolo test, invio a
fine test) e **"Imposta test continuato"** (esegue mdtcap
ripetutamente secondo una schedulazione oraria, inviando periodicamente
le evidenze, per un monitoraggio prolungato non presidiato). Entrambe:

- vanno **avviate esplicitamente** da chi usa il dispositivo (non sono
  mai attive di default, richiedono di inserire la SIM e confermare a
  video), e sono disponibili solo quando il Raspberry Pi ha una
  connessione a Internet propria (oltre a quella della SIM sotto test);
- invia l'evidenza (o, quando non emergono anomalie, solo il riepilogo
  tecnico `manifest.json`) **cifrata con GPG** verso l'host indicato in
  `main_configs/server.conf`, scelto da chi gestisce il dispositivo,
  non un server gestito dall'autore del progetto;
- conserva comunque una copia locale (o su chiavetta USB) delle
  evidenze per 7 giorni, poi le elimina automaticamente;
- non riguarda in nessun modo i test singoli (in locale o su chiavetta
  USB), che restano interamente offline come descritto sopra.

**Chi può inviare dati a un server**: l'invio non è pensato come un
canale aperto a chiunque. Prima di inviare qualunque evidenza,
`mdtmain` verifica se il contratto device+SIM (vedi `mdtcontract`) è
già registrato sul server; se non lo è, chiede un **token di verifica
remoto** (fornito da chi gestisce il server, tipicamente a chi
partecipa attivamente al progetto) e lo usa per registrarsi. Senza un
token valido accettato dal server, l'invio non procede. In pratica:
l'invio dei dati fuori dal Raspberry Pi esiste solo se qualcuno lo
attiva deliberatamente, verso un server di cui ha scelto l'indirizzo, e
solo per SIM effettivamente arruolate nel progetto.

## Cosa NON fa questo strumento

- Non traccia te: sei tu che decidi quando lanciare un test, su quale
  SIM/dispositivo, e per quanto tempo.
- Non intercetta le comunicazioni di altre persone, né altro traffico
  della rete mobile: osserva solo il canale di servizio del proprio
  modem.
- Non modifica il comportamento della rete né forza l'operatore a fare
  o non fare qualcosa: registra semplicemente cosa succede.
- Non è pensato per un uso nascosto su un dispositivo/una SIM che non
  siano di chi esegue il test.

## A cosa può servirti il risultato

Se un test mostra che la rete ha effettivamente richiesto
configurazioni MDT con posizione, o l'invio esplicito delle misure, hai
in mano una prova tecnica concreta, non solo un sospetto, da poter
usare per esercitare i tuoi diritti verso l'operatore (ad esempio,
secondo il GDPR, il diritto di sapere quali dati di geolocalizzazione
vengono trattati su di te, e di chiederne la cancellazione o
l'opposizione al trattamento per quella finalità).

Per un esempio concreto di come impostare una richiesta di questo tipo
a un operatore, e di come un operatore italiano (TIM) vi ha risposto in
un caso reale, inclusa la parte in cui TIM descrive come tratta i dati
di geolocalizzazione della propria rete, vedi le risorse del progetto
**Diritti.xyz** (comitato di cittadini attivo su tracciamento e diritti
digitali):

- <https://diritti.xyz/>, con una guida pratica ed esempi per esercitare
  i propri diritti su geolocalizzazione/tracciamento verso operatori
  telefonici e altri soggetti;
- <https://diritti.xyz/risposta_TIM.html>, un esempio reale di risposta
  di TIM a una richiesta di questo tipo.

Questo progetto (mdtcap) è pensato per fornire proprio il tipo di
riscontro tecnico che serve per dare peso a una richiesta di questo
tipo: invece di basarsi solo su quello che un operatore dichiara,
permette di verificare direttamente cosa succede sul proprio
dispositivo.

## Nota finale

Versione beta (2.0-beta): formato dei file e dettagli di quello che
viene registrato possono ancora cambiare tra una versione e l'altra. I
risultati dei test effettuati finora sono da considerarsi preliminari,
in attesa di validazione ulteriore. Questo documento descrive il
comportamento del progetto così com'è oggi, non un impegno formale né
un'informativa privacy conforme al GDPR.
