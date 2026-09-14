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

