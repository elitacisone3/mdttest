# `extra_configs/` — regole per `src/extra_scan` (`mdtcap --extended`)

Configurazione delle soglie/regole usate da `src/extra_scan` per la
"discriminazione iniziale" di comportamenti di rete sospetti/malevoli
(vedi `--extended`/`--ext-profile` nell'help di `mdtcap` e la sezione
dedicata nel README principale). Analoga nello spirito a `mdt_configs/`
(operatore/profilo di test), ma per un sistema di controlli diverso e
INDIPENDENTE: le due directory non si influenzano a vicenda.

## Struttura

```
extra_configs/
├── main.conf              # base per tutte le categorie/regole
├── op/
│   └── <nome>.conf         # override per operatore (facoltativo)
├── mcc-mnc/
│   └── <mcc>-<mnc> -> ../op/<nome>.conf   # symlink, come mdt_configs/mcc-mnc/
└── profile/
    └── <nome>.conf         # override per profilo di test (facoltativo)
```

## Ordine di lettura

```
main.conf  ->  op/<nome>.conf  ->  profile/<nome>.conf
```

Ognuno dei tre puo' sovrascrivere/aggiungere sezioni o singole chiavi
rispetto al precedente — stessa identica convenzione di
`mdt_configs/system.conf < --op < --profile` gia' in uso dal resto del
progetto: un file "letto dopo" e' una specializzazione via via piu'
vicina al test specifico. `op`/`profile` possono limitarsi alle sole
chiavi che vogliono cambiare, non serve ripetere sezioni intere.

`extra_scan` risolve `op/<nome>.conf` da `--op NOME` (passato da mdtcap,
che a sua volta lo riceve da riga di comando o dall'auto-rilevamento via
MCC-MNC di `mdt_configs/mcc-mnc/`) oppure, se `--op` non e' disponibile,
da `--mcc`/`--mnc` tramite `mcc-mnc/<mcc>-<mnc>` (symlink verso
`../op/<nome>.conf`, stessa idea di `mdt_configs/mcc-mnc/`). `profile/
<nome>.conf` viene risolto da `--profile NOME` (alimentato da
`--ext-profile` di mdtcap).

Nessuno dei tre file e' obbligatorio: se manca `op`/`profile` (o il nome
richiesto non ha un file corrispondente), `extra_scan` prosegue con solo
`main.conf` (o con quanto risolto fino a quel punto), senza errore.

## Formato

INI (Python `configparser`). Una **sezione per singola regola/evento
sospetto**, non per categoria: una categoria (`SMSSTK`, `NASId`,
`RRCCiph`, `cellSys`, `GPSLoc`, `WCDMA3G` — vedi `src/extra_scan
--get-defs` per l'elenco autorevole, sempre aggiornato) puo' avere piu'
regole indipendenti. Nome sezione: `<CATEGORIA>.<evento>`.

Chiavi per sezione (tutte facoltative tranne `level`):

| Chiave | Significato |
|---|---|
| `level` | `I` Ignore / `W` Warning / `C` Cumulativo / `A` Assoluto |
| `enabled` | `true`/`false` (default `true`) |
| `min` | occorrenze grezze minime nella finestra prima che la regola scatti (default 1) |
| `max` | occorrenze grezze oltre le quali il comportamento e' considerato diverso (raro) |
| `window_s` | finestra temporale (secondi) per `min`/`max`/`cum_threshold` (default: intera cattura) |
| `cum_threshold` | soglia di occorrenze a livello `C` oltre la quale la regola viene promossa ad `A` |
| `min_interval_s` / `max_interval_s` | per regole basate sull'intervallo fra un evento e il successivo |
| `mode` | stringa libera, letta dal singolo detector Python |
| `comment` | commento libero, mostrato nel report esteso (`extra_scan_report.txt`) |
| `log_msg` | template `%`-string per il messaggio di log di questa regola |

Vedi `main.conf` per le regole di partenza (una per ciascuna delle 6
categorie) e i relativi commenti — comprese le motivazioni tecniche di
ciascuna soglia.

## Estendere

Aggiungere una nuova regola = aggiungere una nuova sezione INI (in
`main.conf` per una regola generale, o in `op`/`profile` per una
specializzazione) — il motore di aggregazione di `extra_scan` non
richiede modifiche. Se la nuova regola richiede un dato non ancora
estratto dalla cattura, serve anche un piccolo detector Python in
`src/extra_scan` (vedi i commenti in testa a quel file). Aggiungere una
categoria nuova (oltre alle 6 attuali) richiede invece una modifica a
`src/extra_scan` (tabella categorie + `--get-defs`).

Questo intero sistema serve per una discriminazione iniziale, non per un
verdetto definitivo — le regole sono pensate per essere riviste/
corrette nel tempo.
