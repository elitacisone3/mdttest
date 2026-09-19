"""Reset automatico di sicurezza quando mdtcap gira su un device diverso
da quello con cui e' stato configurato l'ultima volta (es. scheda SD/
immagine clonata su un'altra Raspberry Pi): vedi apply()."""
import os

from . import constants, contract, mdtmain_config, syslog_log


def apply():
    """Da chiamare una volta sola all'avvio di mdtmain, PRIMA che il
    resto del programma legga la configurazione. Se autoConfig=1:
    confronta l'id hardware del device attuale (contract.get_devid(),
    stessa risoluzione usata per il contractId) con quello salvato in
    mdt_configs/system_id; se diverso (o il file manca), lo aggiorna e
    forza disableSend=1, startDisclaim=0, dataDisclaim=0. Se autoConfig=0,
    svuota invece mdt_configs/system_id (se non lo e' gia') senza toccare
    il resto della configurazione."""
    config = mdtmain_config.load()
    if not mdtmain_config.get_bool(config, "autoConfig"):
        _clear_system_id_if_needed()
        return
    try:
        current_id = contract.get_devid()
    except contract.ContractError as e:
        syslog_log.warning(f"autoConfig: id hardware del device non determinabile: {e}")
        return
    if _read_system_id() == current_id:
        return
    _write_system_id(current_id)
    mdtmain_config.update(disableSend="1", startDisclaim="0", dataDisclaim="0")
    syslog_log.info("autoConfig: nuovo id hardware rilevato, invio dati disabilitato e disclaimer da riaccettare")


def _read_system_id():
    if not os.path.isfile(constants.SYSTEM_ID_FILE):
        return None
    with open(constants.SYSTEM_ID_FILE) as f:
        return f.read().strip()


def _write_system_id(value):
    os.makedirs(os.path.dirname(constants.SYSTEM_ID_FILE), exist_ok=True)
    with open(constants.SYSTEM_ID_FILE, "w") as f:
        f.write(value + "\n")


def _clear_system_id_if_needed():
    if os.path.isfile(constants.SYSTEM_ID_FILE) and os.path.getsize(constants.SYSTEM_ID_FILE) > 0:
        with open(constants.SYSTEM_ID_FILE, "w"):
            pass
