# gpsBoundingBox

Bounding box geografiche di riserva, usate da `src/mdt_bitscan.py` (invocato
da `mdtcap`, vedi `compute_bitscan_warnings()`) per filtrare i candidati di
posizione GPS quando la scansione euristica bit-a-bit dei frame diag non ha
a disposizione un fix GPS vero ottenuto durante la cattura (nessuna riga con
`gps_fix=1` in `periodic_cell_gps_decoded.csv` — es. `--gps` non usato, o
nessun fix entro `--gps-wait`).

**Formato**: un file `<MCC>.json` per ogni MCC (il codice paese/rete a 3
cifre di TS 24.008, lo stesso rilevato da `AT+CPSI?` e riportato nel campo
`mcc` di `manifest.json`), contenente un array JSON di 4 numeri, in
quest'ordine:

```json
[minLat, minLon, maxLat, maxLon]
```

Es. `222.json` (Italia): `[35.2, 6.6, 47.1, 18.6]` — copre dalla Sicilia/
Lampedusa (sud) al confine alpino (nord), dalla Sardegna occidentale (ovest)
al Salento (est).

`mdt_bitscan.py` applica comunque `--lat-margin`/`--lon-margin` (default
0.02°) ai 4 numeri di questi file, esattamente come farebbe con un box
derivato dal GPS reale — non serve includere gia' un margine qui dentro.

**MCC coperti**: solo quelli degli operatori gia' configurati in
`mdt_configs/op/`/`mdt_configs/mcc-mnc/` (vedi quelle directory per la
mappa MCC-MNC -> operatore):

| File | MCC | Copertura |
|---|---|---|
| `222.json` | 222 | Italia (Vodafone/TIM/WindTre/Iliad) |
| `286.json` | 286 | Turchia (Turk Telekom) |

Per un MCC non presente qui, la scansione posizione (`warnPosD`/`warnPosL`)
viene saltata (resta a 0) finche' non si aggiunge il file corrispondente:
senza un bounding box il filtro di plausibilita' non ha nessun effetto
(qualunque finestra di 48 bit decodifica sempre a QUALCHE lat/lon valida
nel range ±90°/±180°, per costruzione della codifica Ellipsoid-Point), e la
scansione risulterebbe solo rumore.
