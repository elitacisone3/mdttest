# Hardware richiesto

Questo progetto **dipende dall'hardware**, in questa versione: non è
pensato per girare su una macchina qualunque senza il modem giusto
collegato.

- **Raspberry Pi** (o altro SBC/PC Linux equivalente), sviluppato e
  testato su Raspberry Pi OS (Debian). `mdtmain --screen` (interfaccia a
  schermo intero, vedi sezione dedicata) presuppone in particolare una
  console Linux fisica (`/dev/tty1`) e i comandi `setfont`/`fbi`/`aplay`
  tipici di questa piattaforma (installabili con
  `install.sh --setup-mdtmain`).
- **Modulo modem USB Qualcomm-based**, testato con **SimTech
  SIM7600E-H** (VID:PID `1e0e:9000`), richiesto da `qcsuper` per la
  cattura Diag/RRC. Un altro modem Qualcomm supportato da qcsuper
  potrebbe funzionare, ma non è stato validato da questo progetto.
- **SIM attiva**, con piano dati funzionante nella rete da osservare.
- **Alimentazione adeguata**: un modem USB in cattura assorbe corrente
  non trascurabile. Un caso reale di *undervoltage* persistente
  durante un test lungo (rilevabile con `vcgencmd get_throttled`, o con
  `dmesg -T | grep -i voltage` per vederlo mentre succede), fattore di
  confondimento concreto già osservato, è documentato in
  `install.sh --help`; per un uso prolungato conviene un hub USB
  alimentato. Conseguenza concreta osservata sul campo: un'alimentazione
  marginale può far fallire, in modo intermittente ma ripetibile, la
  richiesta con cui `qcsuper` abilita alcuni tipi di log sul modem,
  facendo sparire silenziosamente interi tipi di traffico dal `.dlf`
  (ad esempio quello NAS-EMM usato da `SMSSTK.silent_sms`/`--test-sms`,
  vedi sopra) senza alcun errore visibile a colpo d'occhio, se non
  controllando `qcsuper.log`, "Errori diag port" (vedi la sezione sulla
  TUI più sopra).
- **Facoltativo**: chiavetta USB (per "Test su chiavetta USB"), schermo
  HDMI + tastiera USB collegati direttamente al dispositivo
  (`mdtmain --screen`), altoparlante/cuffie sull'uscita HDMI o jack
  audio (beep/sirena di avviso, vedi sezione `mdtmain`).

I test effettuati finora (compresi quelli descritti in questa guida)
sono stati condotti su questo specifico hardware, in condizioni non
necessariamente rappresentative di ogni possibile installazione:
**vanno considerati preliminari** e andrebbero validati ulteriormente
prima di trarne conclusioni operative definitive.

