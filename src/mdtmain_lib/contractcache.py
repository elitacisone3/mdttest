"""Cache locale (log/cache, JSON: mappa contractId -> True) dei
contratti verificati con successo tramite /api/check/<CONTRATTO> (vedi
httpclient.verify_contract_with_cache). Usata SOLO come fallback quando
quella verifica fallisce per un problema di CONNESSIONE (server
irraggiungibile): una risposta ESPLICITA del server (200 o no) resta
sempre l'autorita' e aggiorna questa cache di conseguenza, mai il
contrario."""
import json
import os

from . import constants


def _load():
    try:
        with open(constants.CONTRACT_CACHE_FILE, "r") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data):
    os.makedirs(os.path.dirname(constants.CONTRACT_CACHE_FILE), exist_ok=True)
    with open(constants.CONTRACT_CACHE_FILE, "w") as f:
        json.dump(data, f)


def is_cached(contract):
    return bool(_load().get(contract))


def remember(contract):
    data = _load()
    if not data.get(contract):
        data[contract] = True
        _save(data)


def forget(contract):
    data = _load()
    if contract in data:
        del data[contract]
        _save(data)
