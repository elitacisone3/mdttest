# Struttura del progetto

```
mdttest/
├── mdtcap              ← script principale (unico file da eseguire)
├── mdtdiag               ← diagnostica AT/Diag standalone (vedi mdtdiag --help)
├── mdtgps                  ← fix GPS/GNSS standalone (vedi mdtgps --help)
├── mdtcontract               ← genera il "contractId", o il solo DEVID con
│                                --get-devid (vedi doc/GUIDA_MDTCAP.md,
│                                sezione manifest.json/--shm)
├── mdtimei                     ← cambio IMEI SPERIMENTALE, richiede autorizzazione
│                                (vedi doc/CAMBIO_IMEI.md e
│                                doc/GUIDA_LEGALE_IMEI.md; NON per uso ordinario)
├── mdtauth                      ← aggiorna/verifica la chiave GPG di cifratura
│                                evidenze (main_configs/data.pub), vedi
│                                mdtauth --help e doc/MDTMAIN.md
├── mdtmain                      ← interfaccia guidata in stile raspi-config
│                                (vedi doc/MDTMAIN.md)
├── install.sh                  ← verifica/installa le dipendenze
├── README.md                     ← questa guida
├── LICENSE                        ← testo della licenza GPLv3
├── mdt_full_test.conf               ← file di configurazione di esempio, completo
├── doc/                                ← documentazione accessoria
│   ├── GUIDA_LEGALE_IMEI.md               rischi legali del cambio IMEI (mdtimei)
│   ├── PRIVACY.md                         trattamento dei dati, spiegato senza
│   │                                       tecnicismi
│   └── EVIDENZE.md                        guida tecnica per interpretare le
│                                           evidenze raccolte (doc/GUIDA_MDTCAP.md,
│                                           sezione 4)
├── mdt_configs/                        ← file per system.conf/--op/--profile
│                                          (doc/GUIDA_MDTCAP.md, sezione 3)
│   ├── system.conf                        porta/--autodetect/--qcsuper di QUESTA macchina
│   │                                       (generato da install.sh --configure-system)
│   ├── imei                                 backup dell'IMEI ORIGINALE del modulo (creato
│   │                                         da solo da mdtcap/install.sh, usato da
│   │                                         mdtimei per un ripristino manuale)
│   ├── imei_auth                            autorizzazione firmata GPG al cambio IMEI
│   │                                         (usata da mdtimei, vedi src/testauth)
│   ├── system_id                            id hardware del device, salvato da
│   │                                         src/mdtmain_lib/autoconfig.py quando
│   │                                         autoConfig=1 (vedi doc/MDTMAIN.md)
│   ├── op/                                configurazioni per operatore italiano
│   │   ├── tim.conf
│   │   ├── vodafone.conf
│   │   ├── windtre.conf
│   │   ├── iliad.conf
│   │   └── turktelekom.conf
│   ├── profile/                             profili di test (durata/GPS/UI/...)
│   │   ├── quick.conf
│   │   ├── standard.conf
│   │   └── reconnect-trap.conf
│   ├── mcc-mnc/                              symlink <MCC>-<MNC> -> ../op/*.conf,
│   │                                           per l'autodetect operatore (doc/GUIDA_MDTCAP.md, sezione 3)
│   └── gpsBoundingBox/                      bounding box <MCC>.json di riserva per
│                                               warnPosD/warnPosL quando la cattura
│                                               non ha un fix GPS proprio (vedi il
│                                               README in quella directory)
├── main_configs/                        ← configurazione di mdtmain (vedi doc/MDTMAIN.md)
│   ├── server.conf                          host del server per invio dati/download
│   │                                         certificato identità (formato key=value)
│   ├── data.pub                             chiave GPG pubblica per cifrare le evidenze
│   │                                         inviate durante l'invio dati/test continuato,
│   │                                         valida solo se è la stessa chiave di
│   │                                         src/res/auth.pub, o firmata da essa (vedi
│   │                                         src/mdtmain_lib/gpgtrust.py e mdtauth)
│   ├── data.pub.dist                        copia di riferimento di data.pub, usata da
│   │                                         "mdtauth --restore" per tornare alla chiave
│   │                                         di default
│   └── profile/                             schedulazioni del test continuato (DSL
│       └── Default.conf                       START/IN/EVERY/CHECKPOINT, vedi doc/MDTMAIN.md)
├── extra_configs/                      ← regole per src/extra_scan (--extended),
│   ├── main.conf                          vedi extra_configs/README.md e
│   ├── op/                                doc/GUIDA_MDTCAP.md ("Controlli extra"),
│   ├── profile/                           sistema di configurazione SEPARATO da
│   └── mcc-mnc/                           mdt_configs/ (stessa idea, formato INI diverso)
├── log/                                  ← log e dati d'evidenza (doc/GUIDA_MDTCAP.md, sezione 4)
│   ├── mdt_imei_logs/                        log di sessione di mdtimei
│   │                                         (un file per esecuzione)
│   └── data/                                 directory di DEFAULT delle catture
│                                              mdtcap quando ne' --outdir ne'
│                                              --outdir-base sono specificati
│                                              (vedi doc/GUIDA_MDTCAP.md, sezione 4)
├── src/
│   ├── decode_mdt_location.py  ← helper per la decodifica delle coordinate
│   ├── mdt_bitscan.py            scansione bit-a-bit del .dlf/qcsuper.log per
│   │                              posizione/setup MDT sfuggiti (doc/GUIDA_MDTCAP.md,
│   │                              sezione 3, "Warning diag port")
│   ├── testauth                  autorizzazione firmata GPG al cambio IMEI,
│   │                              usata da mdtimei (vedi doc/CAMBIO_IMEI.md,
│   │                              "Autorizzazione al cambio IMEI")
│   ├── extra_scan                 rilevamento IMSI-catcher/sorveglianza,
│   │                              usato da mdtcap --extended (vedi
│   │                              doc/GUIDA_MDTCAP.md, "Controlli extra", ed
│   │                              extra_configs/README.md)
│   ├── mdtmain_lib/                libreria di supporto di mdtmain (rete, HTTP,
│   │                              evidenza, scheduler, verifica chiavi GPG,
│   │                              interfaccia dialog)
│   └── res/
│       └── auth.pub                chiave GPG radice usata da src/testauth
│                                    (mdtimei) e come riferimento di fiducia
│                                    per main_configs/data.pub (vedi mdtauth)
└── synthetic_test/       ← generatore di catture .dlf sintetiche per
    ├── gen_mdt_dlf.py           testare mdtcap senza modem/SIM/rete, vedi
    └── README.md                synthetic_test/README.md
```

Vedi [doc/GUIDA_MDTCAP.md](GUIDA_MDTCAP.md) (sezione 4) per la struttura delle
**cartelle di output** (diversa da quella del progetto: quella descrive dove
vanno a finire le catture, questa dove si trova il programma).
