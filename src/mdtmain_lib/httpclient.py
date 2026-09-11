"""Client HTTP verso il server MDT (solo stdlib, urllib.request).

Endpoint (vedi main_configs/server.conf per l'host):
  GET  /api/check/<CONTRACT>                 200 = contratto registrato
  GET  /api/register/<token>/<CONTRACT>      200 = registrazione riuscita
  GET  /api/imei/<token>                     200 = file allegato, 404 = assente
  POST /api/imeiRequest/<token>/<devId>      raw octet-stream, max 512 byte
  POST /api/push/<CONTRACT>/<nomeDirectory>  raw octet-stream (evidenza cifrata)
                                              risposta: sha256 esadecimale
  POST /api/masterLog                        raw ndjson (vedi srv/scanlogs,
                                              src/mdtmain_lib/masterlog.py)
                                              200/400: {"inserted": N}
"""
import os
import urllib.error
import urllib.parse
import urllib.request

from . import constants, contractcache

TIMEOUT = 15
MAX_IMEI_REQUEST_BYTES = 512

# Richiesto per tutte le chiamate HTTP/HTTPS verso il server MDT.
USER_AGENT = f"MDTCap/{constants.VERSION}"


class ServerError(Exception):
    pass


def load_server_conf():
    """Legge main_configs/server.conf (formato key=value, solo 'host' e'
    usato). Solleva ServerError se il file manca o 'host' e' assente."""
    if not os.path.isfile(constants.SERVER_CONF_FILE):
        raise ServerError(f"file di configurazione server non trovato: {constants.SERVER_CONF_FILE}")
    values = {}
    with open(constants.SERVER_CONF_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    if "host" not in values or not values["host"]:
        raise ServerError("main_configs/server.conf: manca 'host='")
    return values


def _url(host, *segments):
    base = host.rstrip("/")
    path = "/".join(urllib.parse.quote(str(s), safe="") for s in segments)
    return f"{base}/{path}"


def _request(url, data=None, method="GET", headers=None):
    """Wrapper su urllib.request.Request che aggiunge sempre lo User-Agent
    "MDTCap/{versione}" — usato da TUTTE le chiamate verso il server, cosi'
    non si puo' dimenticarlo aggiungendone una nuova."""
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    return urllib.request.Request(url, data=data, method=method, headers=hdrs)


def _open(req):
    try:
        return urllib.request.urlopen(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as e:
        return e  # ha comunque .status/.read(), gestito dal chiamante
    except urllib.error.URLError as e:
        raise ServerError(f"connessione al server fallita: {e.reason}")


def check_server_reachable(host):
    """GET {host}/CHECK — endpoint di health-check del server (risponde
    "OK" in chiaro, non JSON, indipendente da qualunque contractId):
    True solo se risponde 200 con corpo "OK". Pensato per un controllo
    di raggiungibilita' rapido, prima delle chiamate piu' specifiche
    (verifica/registrazione contratto), cosi' un server irraggiungibile
    da' subito un messaggio chiaro invece di un errore piu' indiretto
    alla prima chiamata "vera"."""
    req = _request(_url(host, "CHECK"), method="GET")
    resp = _open(req)
    status = getattr(resp, "status", getattr(resp, "code", None))
    if status != 200:
        return False
    return resp.read().decode(errors="replace").strip() == "OK"


def check_contract(host, contract):
    req = _request(_url(host, "api", "check", contract), method="GET")
    resp = _open(req)
    return getattr(resp, "status", getattr(resp, "code", None)) == 200


def verify_contract_with_cache(host, contract):
    """Come check_server_reachable + check_contract insieme, ma con un
    fallback alla cache locale (log/cache, vedi contractcache.py)
    quando il server non e' raggiungibile per un problema di
    CONNESSIONE (mai quando risponde ma dice "non registrato" — quella
    resta un'autorita' esplicita, e ripulisce la cache): pensato per
    non bloccare la ripresa di un test continuato gia' registrato in
    passato solo perche' il dispositivo non ha ancora connettivita' (es.
    --edge-mode avviato prima di agganciare la cella). Ritorna
    (registrato, raggiungibile): "registrato" e' l'esito da usare,
    "raggiungibile" dice se viene da una risposta fresca del server
    (False = si sta usando la cache, o non c'e' nulla in cache)."""
    try:
        reachable = check_server_reachable(host)
    except ServerError:
        reachable = False
    if reachable:
        try:
            registered = check_contract(host, contract)
        except ServerError:
            reachable = False
        else:
            if registered:
                contractcache.remember(contract)
            else:
                contractcache.forget(contract)
            return registered, True
    return contractcache.is_cached(contract), False


def register_token(host, token, contract):
    req = _request(_url(host, "api", "register", token, contract), method="GET")
    resp = _open(req)
    return getattr(resp, "status", getattr(resp, "code", None)) == 200


def download_imei_auth(host, token):
    """Ritorna i byte del file scaricato, oppure None su 404. Solleva
    ServerError per qualunque altro errore (rete, altri status)."""
    req = _request(_url(host, "api", "imei", token), method="GET")
    resp = _open(req)
    status = getattr(resp, "status", getattr(resp, "code", None))
    if status == 404:
        return None
    if status != 200:
        raise ServerError(f"download configurazione IMEI: risposta HTTP {status}")
    return resp.read()


def submit_imei_request(host, token, devid, text):
    """text: str o bytes, motivazione della richiesta. Troncata a
    MAX_IMEI_REQUEST_BYTES byte UTF-8 se piu' lunga."""
    data = text.encode("utf-8") if isinstance(text, str) else text
    if len(data) > MAX_IMEI_REQUEST_BYTES:
        data = data[:MAX_IMEI_REQUEST_BYTES]
    req = _request(
        _url(host, "api", "imeiRequest", token, devid),
        data=data, method="POST",
        headers={"Content-Type": "application/octet-stream"},
    )
    resp = _open(req)
    return getattr(resp, "status", getattr(resp, "code", None)) == 200


def push_masterlog(host, data):
    """POST raw di data (bytes, il contenuto di log/masterSpool.ndjson)
    a {host}/api/masterLog. A differenza di push_evidence NON solleva
    per uno status HTTP di errore: il chiamante (masterlog.flush_masterlog)
    deve poter distinguere 200/400 (che consumano lo spool) da
    qualunque altro esito (che lo lascia intatto) — ritorna l'oggetto
    risposta cosi' com'e' (._open() lascia gia' passare gli HTTPError
    invece di sollevarli, sollevando ServerError SOLO per un fallimento
    di rete/connessione, senza risposta HTTP alcuna)."""
    req = _request(
        _url(host, "api", "masterLog"),
        data=data, method="POST",
        headers={"Content-Type": "application/octet-stream"},
    )
    return _open(req)


def push_evidence(host, contract, dirname, filepath):
    """Invia il file (tar.gz cifrato gpg) come corpo raw della POST.
    Ritorna lo sha256 esadecimale (minuscolo) restituito dal server, o
    solleva ServerError se l'invio fallisce."""
    with open(filepath, "rb") as f:
        data = f.read()
    req = _request(
        _url(host, "api", "push", contract, dirname),
        data=data, method="POST",
        headers={"Content-Type": "application/octet-stream"},
    )
    resp = _open(req)
    status = getattr(resp, "status", getattr(resp, "code", None))
    if status != 200:
        raise ServerError(f"invio evidenza: risposta HTTP {status}")
    return resp.read().decode(errors="replace").strip().lower()
