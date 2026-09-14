# mdtcap: Minimization of Drive Tests Capture.

![mdtcap](src/res/mdtcap.png)

**Versione beta (2.0-beta)**

Tool per rilevare le evidenze di tracciamento/utilizzo dell'MDT
(Minimization of Drive Tests) con posizione dell'utente o del terminale:
acquisisce in modo forense il traffico Diag/RRC da un modulo
Qualcomm-based (es. SIM7600E-H) tramite `qcsuper`, con log del contesto AT
prima/dopo la cattura, log periodico di cella/posizione e hash SHA-256 dei
file prodotti per la catena di custodia.

## Perché esiste

Nasce dall'esigenza pratica di verificare se l'esercizio dei propri
diritti verso un operatore telefonico (vedi [diritti.xyz](https://diritti.xyz/),
comitato di cittadini attivo su tracciamento e diritti digitali) abbia
avuto un effetto reale, cioè se l'operatore ha davvero smesso di
richiedere configurazioni MDT con posizione, oppure se alcuni operatori
tracciano gli utenti in modo surrettizio, senza che sia mai evidente
dall'esterno.
Invece di doversi fidare di quello che un operatore dichiara nella
propria informativa, con un modem e una SIM proprie si osserva
direttamente cosa arriva davvero sul canale di servizio della rete.

**Cosa permette di fare, oggi:**

- verificare se il proprio operatore telefonico usa l'MDT per tracciare
  la posizione dell'utente/del terminale (vedi sopra);
- una segnalazione di base su altre minacce di rete, cioè indizi di
  IMSI-catcher/sorveglianza (celle fittizie, SMS nascosti con codici di
  comando, downgrade forzato di cifratura/rete), analizzando lo stesso
  traffico già catturato, con l'opzione `--extended` (sezione "Controlli
  extra" di [doc/GUIDA_MDTCAP.md](doc/GUIDA_MDTCAP.md));
- installazione con un'interfaccia testuale guidata comoda su Raspberry
  Pi (`mdtmain`, in stile raspi-config), anche a schermo intero con
  monitor/tastiera collegati direttamente al dispositivo, senza terminale
  remoto (`mdtmain --screen`, vedi [doc/MDTMAIN.md](doc/MDTMAIN.md));
- una schedulazione oraria con invio periodico delle evidenze e una
  "sirena" che avvisa con un allarme sonoro se durante un test
  programmato emerge un indizio di MDT/RRC con posizione, o una minaccia
  di livello massimo nei controlli extra (vedi [doc/MDTMAIN.md](doc/MDTMAIN.md)).

**Il passo successivo** del progetto è piazzare più dispositivi come
questo, ovvero server EDGE su Raspberry Pi, per controllare le reti a
campione in più punti, verificare se questi fenomeni di tracciamento
esistono e in quali forme, e se sono messi in atto anche da altri
soggetti (non l'operatore stesso) con celle fittizie, SMS nascosti o
altri attacchi malevoli. Vedi [doc/ROADMAP.md](doc/ROADMAP.md).

**Il progetto dipende dall'hardware**, in questa versione (un modem USB
Qualcomm-based specifico, vedi [doc/HARDWARE.md](doc/HARDWARE.md)): non
è un tool puramente software eseguibile su qualunque macchina. I test
effettuati finora sono stati condotti nelle condizioni descritte in
questa guida (vedi anche il caso di *undervoltage* persistente
documentato in `install.sh --help`) e **vanno considerati preliminari**:
riscontri tecnici da validare ulteriormente, non un responso già
certificato.

**Licenza:** [GNU General Public License v3.0](LICENSE) (GPLv3)
**Autore:** EPTO Tramaci

## Indice

Questa guida introduttiva si ferma qui. I capitoli tecnici sono stati
raccolti in `doc/`, uno per argomento:

1. [Struttura del progetto](doc/STRUTTURA_PROGETTO.md): mappa dei file e
   delle cartelle del repository.
2. [Hardware richiesto](doc/HARDWARE.md): modem, SIM, alimentazione e
   accessori necessari.
3. [Installazione](doc/INSTALLAZIONE.md): `install.sh`, prerequisiti e
   configurazione di sistema.
4. [Guida all'uso di mdtcap](doc/GUIDA_MDTCAP.md): individuare le porte,
   lanciare una cattura, tutte le opzioni principali, la struttura dei
   file prodotti e un esempio completo.
5. [Cambio IMEI](doc/CAMBIO_IMEI.md): `mdtimei` e l'autorizzazione firmata
   GPG richiesta per usarlo (**sperimentale**, leggere prima di usare).
6. [`mdtmain`: interfaccia guidata](doc/MDTMAIN.md): il menu testuale
   stile raspi-config che orchestra `mdtcap`.
7. [Privacy](doc/PRIVACY.md): dove vanno i dati raccolti, spiegato senza
   tecnicismi.
8. [Roadmap](doc/ROADMAP.md): la rete di sensori EDGE, il passo
   successivo del progetto.

Altri documenti di riferimento in `doc/`:

- [Guida legale al cambio IMEI](doc/GUIDA_LEGALE_IMEI.md): rischi legali
  specifici di `mdtimei`.
- [Interpretare le evidenze raccolte](doc/EVIDENZE.md): guida tecnica per
  leggere l'output di una cattura.

## Note

Versione beta (2.0-beta): interfaccia a riga di comando e formato dei
file di output possono ancora cambiare tra una versione e l'altra. I
test funzionali effettuati finora (manuali, sull'hardware descritto in
[doc/HARDWARE.md](doc/HARDWARE.md)) vanno considerati preliminari:
risultati da validare ulteriormente, non un responso già certificato.
