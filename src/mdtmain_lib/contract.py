"""Wrapper subprocess attorno a ./mdtcontract."""
import subprocess

from . import constants


class ContractError(Exception):
    pass


def _run_mdtcontract(args, timeout=60):
    try:
        proc = subprocess.run(
            [constants.MDTCONTRACT, *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise ContractError(str(e))
    if proc.returncode != 0:
        raise ContractError(proc.stderr.decode(errors="replace").strip() or "mdtcontract ha restituito un errore")
    return proc.stdout.decode(errors="replace").strip()


def get_devid():
    return _run_mdtcontract(["--get-devid"])


def get_sim_user():
    """Ritorna (iccid, contract). Solleva ContractError se manca la SIM/il
    modem non risponde (mdtdiag --get-sim fallisce)."""
    out = _run_mdtcontract(["--get-sim-user"])
    iccid, contract = None, None
    for line in out.splitlines():
        if line.startswith("ICCID:"):
            iccid = line[len("ICCID:"):].strip()
        elif line.startswith("CONTRACT:"):
            contract = line[len("CONTRACT:"):].strip()
    if not iccid or not contract:
        raise ContractError("output inatteso da mdtcontract --get-sim-user")
    return iccid, contract


def get_keys():
    """Ritorna un dict con le cinque chiavi AUTH/IMEI/DATA/DVID/CODE
    stampate da "mdtcontract --get-keys" (stringa vuota per AUTH/IMEI/
    DATA se il rispettivo file GPG manca/non contiene una chiave)."""
    out = _run_mdtcontract(["--get-keys"])
    keys = {}
    for line in out.splitlines():
        name, _, value = line.partition(":")
        keys[name] = value
    return keys


def get_imei_token():
    """Token per le funzionalita' sperimentali di download configurazione
    IMEI: e' l'output di "mdtcontract IMEI_FILE" — la stringa letterale
    "IMEI_FILE" passata al posto di un ICCID vero, cosi' il risultato e'
    legato al device ma sempre distinguibile da un vero contractId (che
    userebbe l'ICCID reale della SIM). Voluto: permette al server di
    tracciare separatamente l'uso di questa funzionalita' sperimentale."""
    return _run_mdtcontract(["IMEI_FILE"])
