# `mdtmain`: interfaccia guidata

Interfaccia testuale in stile `raspi-config` (libreria `dialog`/
`pythondialog`) che orchestra `mdtcap` senza dover ricordare le opzioni a
riga di comando. Richiede root, come `mdtcap`/`mdtcontract`:

```bash
sudo ./mdtmain
```

Parametri opzionali, combinabili fra loro (tranne `--run-local`, vedi
sotto):

| Parametro | Effetto |
|---|---|
| `--main` | salta la configurazione di rete anche senza Internet, va dritto al menu principale |
| `--net-menu` | avvia direttamente sulla configurazione di rete, anche con Internet già presente o con `disableNet=1` |
| `--auto-start` | se `autoStart=1` e un test continuato è completamente configurato (`testSim`/`mdtcapProfile`/`schedulerProfile` non vuoti) in `main_configs/mdtmain.conf`, verifica l'ICCID della SIM inserita e, se corrisponde, salta rete e menu principale riprendendo direttamente il test continuato, senza richiedere PIN né altri parametri (usa quelli salvati); se l'ICCID non corrisponde mostra "Errore sim non corrispondente" e prosegue con il menu normale (`autoStart` resta invariato: si disattiva solo dalla schermata Impostazioni) |
| `--screen` | usa lo schermo HDMI e la tastiera collegati direttamente al dispositivo invece del terminale di lancio (console fisica `/dev/tty1`), con suoni di avviso via `aplay`, vedi sotto |
| `--run-local --profile NOME [--sim-pin PIN] [--duration MINUTI]` | salta **tutte** le schermate e lancia subito il test in locale con l'output di mdtcap grezzo (senza `--tui`), per debug |

All'avvio verifica la connessione a Internet del Raspberry Pi (non
quella della SIM sotto test): se assente (e `disableNet` non è `1`
in `main_configs/mdtmain.conf`), offre di configurare Ethernet o WiFi
(DHCP o statica, rilevando automaticamente se il sistema usa
NetworkManager o dhcpcd+wpa_supplicant): da lì si può anche scegliere
**"Salta"** e andare comunque al menu principale. La riga in alto
mostra sempre `MDTCap <versione>` a sinistra e hostname/IP (o
`NO INTERNET`) a destra.

All'avvio, la primissima volta, compare anche un disclaimer generale sul
programma (`startDisclaim` in `main_configs/mdtmain.conf`, vedi sotto):
non si ripete alle esecuzioni successive.

Il menu principale offre **sempre** tutte le opzioni seguenti,
indipendentemente dalla connessione a Internet (le modalità che la
richiedono davvero segnalano l'errore solo se effettivamente provano a
contattare il server) **tranne 3 e 4**, nascoste se `disableSend=1`
(default, vedi [doc/PRIVACY.md](PRIVACY.md) e la tabella `mdtmain.conf` più sotto):

1. **Esegui un test in locale** (senza salvare): sceglie un profilo da
   `mdt_configs/profile/`, chiede il PIN della SIM (facoltativo) e la
   durata in minuti (facoltativa: se vuota, usa quella del profilo),
   mostra il risultato e cancella ogni traccia (gira interamente su
   tmpfs, con un limite di sicurezza di 30&nbsp;minuti/250&nbsp;MB oltre
   il quale si ferma da sé).
2. **Test su chiavetta USB**: come sopra, ma monta una chiavetta su
   `/media/USB` e salva l'evidenza in `/media/USB/Evidenze_MDT/`, poi la
   smonta e chiede di rimuoverla.
3. **Esegui un test inviando i dati**: come il test in locale, ma
   verifica/registra il contratto (device+SIM) sul server e invia
   l'evidenza cifrata a fine test, senza schedulazione: un solo test
   immediato con durata scelta a mano. Vedi [doc/PRIVACY.md](PRIVACY.md)
   per il vincolo di chi può inviare dati a un server.
4. **Imposta test continuato**: stessa verifica/registrazione del
   contratto, ma esegue `mdtcap` secondo una schedulazione letta da
   `main_configs/profile/<nome>.conf`, una piccola DSL con i comandi
   `START`/`IN`/`EVERY ... PAUSE ... IN`/`CHECKPOINT` (vedi i commenti in
   `src/mdtmain_lib/profiles.py` per la sintassi completa), inviando le
   evidenze cifrate dopo ogni cattura; salva PIN/ICCID della SIM e
   profilo mdtcap/schedulazione scelti in `main_configs/mdtmain.conf`
   (`testPin`/`testSim`/`mdtcapProfile`/`schedulerProfile`), così
   `--auto-start` e "Riprendi test continuo" (menu principale, quando un
   test continuato è configurato) possono riprenderlo senza richiedere
   di nuovo nulla.
5. **Test baseband**: lancia `mdtdiag` e mostra identità modulo/SIM
   (Modulo/IMEI/ICCID/IMSI) in una finestra dedicata.
6. **Test GPS**: lancia `mdtgps` e mostra latitudine/longitudine/
   altitudine/velocità del fix ottenuto.
7. **Download certificato identità di rete**: scarica e verifica (con
   `src/testauth`) un'autorizzazione al cambio IMEI dal server,
   installandola come `mdt_configs/imei_auth` se valida.
8. **Identità sistema**: mostra il devId calcolato da
   `mdtcontract --get-devid`.
9. **Impostazioni**: avvio automatico, allarmi attivi/su HDMI e relativa
   fascia oraria, fix GPS forzato prima dei test, test approfonditi
   (`--extended`), modalità test SMS (`--test-sms`, vedi sotto) e
   disabilitazione dell'invio delle evidenze (`disableSend`, vedi sotto
   e [doc/PRIVACY.md](PRIVACY.md): attivandola cancella anche PIN/ICCID del test
   continuato salvato, e la prima volta mostra un avviso dedicato);
   scrive
   `main_configs/mdtmain.conf`.

In ogni test: si conferma sempre l'inserimento della SIM, e un tasto
qualunque durante la cattura vera e propria la ferma (file `mdtStop`
nella directory `--shm`) tornando comunque al menu principale, anche
in caso di errore.

### `main_configs/mdtmain.conf`

Formato `key=value`, creato/aggiornato automaticamente da `mdtmain`
stesso (schermata "Impostazioni", "Imposta test continuato"):

| Chiave | Default | Significato |
|---|---|---|
| `disableNet` | `0` | disabilita la sezione impostazioni di rete (salvo con `--net-menu`) |
| `minAlarmHour` / `maxAlarmHour` | `10` / `23` | fascia oraria in cui è attiva la "sirena" (vedi sotto) |
| `disableIMEI` | `0` | disabilita del tutto la richiesta di cambio IMEI nel test continuato/nell'invio dati |
| `disableAlarm` | `0` | disabilita la sirena |
| `autoStart` | `1` | usata da `--auto-start` (vedi tabella sopra) |
| `testPin` / `testSim` | vuoti | PIN/ICCID della SIM del test continuato configurato (scritti da "Imposta test continuato") |
| `mdtcapProfile` / `schedulerProfile` | vuoti | profilo mdtcap/schedulazione del test continuato configurato (scritti da "Imposta test continuato") |
| `alarmCheckPoint` | `1` | abilita la sirena per il comando `CHECKPOINT` della schedulazione (vedi sopra) |
| `hdmi` | `1` | uscita audio: `1`=HDMI, `0`=Headphones (solo modalità `--screen`) |
| `doGPSFix` | `0` | se `1`, prima di **qualunque** test attende un fix GPS (`mdtgps` in background, "Attesa fix GPS...") così il test parte già con un fix "caldo"; un fix mancato avvisa ma non blocca il test |
| `forceExtended` | `0` | se `1`, aggiunge `--extended` a ogni invocazione di `mdtcap`, anche se il profilo/la schedulazione usata non lo prevede già da solo (vedi "Controlli extra" in [doc/GUIDA_MDTCAP.md](GUIDA_MDTCAP.md)) |
| `testSMS` | `0` | se `1`, aggiunge `--test-sms` a ogni invocazione di `mdtcap` (implica `--extended` da solo, vedi "Trigger di test via SMS" in [doc/GUIDA_MDTCAP.md](GUIDA_MDTCAP.md)); usare solo per verificare la catena di rilevamento, mai in un test reale |
| `disableSend` | `1` | se `1` (default), nasconde dal menu principale "Esegui un test inviando i dati"/"Imposta test continuato" (le uniche due modalità che inviano dati a un server, vedi [doc/PRIVACY.md](PRIVACY.md)); attivandolo da Impostazioni cancella anche `testPin`/`testSim` |
| `startDisclaim` | `0` | diventa `1` dopo il primo avvio, quando compare il disclaimer generale del programma; non si ripete |
| `dataDisclaim` | `0` | diventa `1` la prima volta che si tocca `disableSend` dalla schermata Impostazioni, quando compare il disclaimer sull'invio dati; non si ripete |

### Modalità a schermo intero (`--screen`)

Pensata per un dispositivo installato "da postazione fissa", con
schermo e tastiera collegati direttamente invece che via terminale/SSH:
`mdtmain --screen` prende il controllo della console fisica
(`/dev/tty1`), fermando temporaneamente il login (`getty`) su quella
console e abbassando i messaggi del kernel a schermo (entrambi
ripristinati all'uscita), e carica un font console con pallini/cornici
Unicode corretti (adattando automaticamente la dimensione del carattere
se lo schermo risulta più piccolo di 120×44 caratteri). All'avvio (salvo
`--no-banner`) mostra per un paio di secondi l'immagine
`src/res/mdtcap.png` a schermo intero con `fbi`.

In questa modalità i suoni di avviso (beep di fine test, "sirena" se un
test programmato trova un indizio di MDT/RRC-con-posizione o un livello
massimo nei controlli extra, suono dedicato se un test locale/USB
produce evidenza) vengono riprodotti con `aplay` (file in `src/res/`)
invece del solo carattere BEL del terminale, sull'uscita audio scelta in
`mdtmain.conf` (`hdmi`). Da una sessione terminale/SSH normale (senza
`--screen`), `mdtmain` prova invece a ingrandire la finestra
(sequenza xterm, solo se più piccola di 132×44) e ne imposta il titolo a
"MDTCap", ripristinandolo all'uscita.

Le dipendenze specifiche di questa modalità (`fbi`, `alsa-utils` per
`aplay`/`amixer`, font console) si installano con
`sudo ./install.sh --setup-mdtmain` (vedi [doc/INSTALLAZIONE.md](INSTALLAZIONE.md)).

