#!/usr/bin/env bash
# Test automatico di regressione per gli scenari extra_scan/--test-sms
# generati da synthetic_test/gen_mdt_dlf.py (vedi synthetic_test/README.md,
# sezioni "Scenari per mdtcap --extended"/"--test-sms"). Per ciascuno
# scenario: lancia "mdtcap --analyze-dlf", legge manifest.json
# (extScanCat.<CAT>.level, popolato solo con --extended - vedi
# mdtcap:generate_manifest_json) e confronta col livello atteso. Esce non
# zero se almeno uno scenario non corrisponde - pensato per essere
# rilanciato dopo ogni modifica a src/extra_scan o mdtcap (stesso spirito
# "rieseguire dopo ogni modifica ai filtri" gia' raccomandato per lo
# scenario MDT r17-only nel README).
#
# Uso: synthetic_test/test/run_scenarios.sh [--keep-outdirs]
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
QCSUPER_BIN="${QCSUPER_BIN:-/usr/local/bin/qcsuper}"
KEEP_OUTDIRS=0
[[ "${1:-}" == "--keep-outdirs" ]] && KEEP_OUTDIRS=1

# nome_dlf | argomenti mdtcap | categoria attesa ("ALL5" = tutte e 5
# RRCCiph/cellSys/WCDMA3G/NASId/SMSSTK) | livello atteso
SCENARIOS=(
    "rrcciph-eea0|--extended|RRCCiph|A"
    "cellsys-2g-downgrade|--extended|cellSys|C"
    "wcdma3g-3g-downgrade|--extended|WCDMA3G|W"
    "nasid-identity-imsi|--extended|NASId|C"
    "nasid-guti-realloc-frequent|--extended|NASId|W"
    "smsstk-silent-sms|--extended|SMSSTK|W"
    "testsms-rrcciph|--test-sms|RRCCiph|A"
    "testsms-cellsys|--test-sms|cellSys|A"
    "testsms-wcdma3g|--test-sms|WCDMA3G|A"
    "testsms-nasid|--test-sms|NASId|A"
    "testsms-smsstk|--test-sms|SMSSTK|A"
    "testsms-all|--test-sms|ALL5|A"
    # controllo negativo: lo stesso .dlf di testsms-rrcciph, MA senza
    # --test-sms - il trigger non deve avere alcun effetto.
    "testsms-rrcciph|--extended|RRCCiph|I"
)

pass=0
fail=0

check_level() {
    local manifest="$1" cat="$2" expected="$3"
    python3 -c "
import json, sys
with open('$manifest') as f:
    data = json.load(f)
cats = data.get('extScanCat', {})
if '$cat' == 'ALL5':
    keys = ['RRCCiph', 'cellSys', 'WCDMA3G', 'NASId', 'SMSSTK']
    levels = {k: cats.get(k, {}).get('level', '?') for k in keys}
    ok = all(v == '$expected' for v in levels.values())
    print(','.join(f'{k}={v}' for k, v in levels.items()))
    sys.exit(0 if ok else 1)
else:
    level = cats.get('$cat', {}).get('level', '?')
    print(f'$cat={level}')
    sys.exit(0 if level == '$expected' else 1)
"
}

for entry in "${SCENARIOS[@]}"; do
    IFS='|' read -r dlf_name mdtcap_args category expected <<< "$entry"
    label="$dlf_name [$mdtcap_args] -> $category=$expected"
    dlf_path="$SCRIPT_DIR/${dlf_name}.dlf"
    if [[ ! -f "$dlf_path" ]]; then
        echo "FAIL  $label (file mancante: $dlf_path — rigenerare con gen_mdt_dlf.py)"
        fail=$((fail + 1))
        continue
    fi

    outdir="/tmp/mdt_scenario_test_${dlf_name}_${mdtcap_args//[^a-zA-Z]/}_$$"
    rm -rf "$outdir"
    log="$outdir.log"
    if ! sudo "$REPO_ROOT/mdtcap" --analyze-dlf "$dlf_path" \
            --qcsuper "$QCSUPER_BIN" --outdir "$outdir" --report \
            $mdtcap_args > "$log" 2>&1; then
        echo "FAIL  $label (mdtcap terminato con errore, vedi $log)"
        fail=$((fail + 1))
        continue
    fi

    manifest="$outdir/manifest.json"
    if [[ ! -f "$manifest" ]]; then
        echo "FAIL  $label (manifest.json mancante in $outdir)"
        fail=$((fail + 1))
        continue
    fi

    if detail=$(check_level "$manifest" "$category" "$expected"); then
        echo "PASS  $label ($detail)"
        pass=$((pass + 1))
        [[ "$KEEP_OUTDIRS" -eq 1 ]] || rm -rf "$outdir" "$log"
    else
        echo "FAIL  $label (ottenuto: $detail — vedi $outdir/report_finale.txt)"
        fail=$((fail + 1))
    fi
done

echo
echo "Risultato: $pass PASS, $fail FAIL su $((pass + fail)) scenari"
[[ "$fail" -eq 0 ]]
