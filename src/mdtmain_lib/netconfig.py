"""Applicazione della configurazione di rete (Ethernet/WiFi, DHCP/statica),
per i due stack rilevati da netinfo.detect_network_stack()."""
import os
import shutil
import subprocess

CON_NAME_ETH = "mdtmain-eth"
CON_NAME_WIFI_PREFIX = "mdtmain-wifi-"
DHCPCD_CONF = "/etc/dhcpcd.conf"
WPA_SUPPLICANT_CONF_TPL = "/etc/wpa_supplicant/wpa_supplicant-{iface}.conf"
MARK_BEGIN = "# BEGIN mdtmain {iface}"
MARK_END = "# END mdtmain {iface}"


def _run(cmd, timeout=30):
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        ok = proc.returncode == 0
        msg = proc.stdout.decode(errors="replace") + proc.stderr.decode(errors="replace")
        return ok, msg.strip()
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)


def _backup_once(path):
    backup = path + ".mdtmain.bak"
    if os.path.isfile(path) and not os.path.isfile(backup):
        shutil.copy2(path, backup)


# ---- NetworkManager --------------------------------------------------------

def configure_ethernet_nm(iface, mode, ip=None, prefix=None, gw=None, dns=None):
    _run(["nmcli", "con", "delete", CON_NAME_ETH])
    ok, msg = _run(["nmcli", "con", "add", "type", "ethernet", "ifname", iface,
                     "con-name", CON_NAME_ETH, "con.autoconnect", "yes"])
    if not ok:
        return False, f"Creazione connessione fallita: {msg}"
    if mode == "static":
        args = ["nmcli", "con", "modify", CON_NAME_ETH,
                 "ipv4.method", "manual",
                 "ipv4.addresses", f"{ip}/{prefix}",
                 "ipv4.gateway", gw]
        if dns:
            args += ["ipv4.dns", dns]
        ok, msg = _run(args)
        if not ok:
            return False, f"Configurazione IP statico fallita: {msg}"
    else:
        _run(["nmcli", "con", "modify", CON_NAME_ETH, "ipv4.method", "auto"])
    ok, msg = _run(["nmcli", "con", "up", CON_NAME_ETH])
    if not ok:
        return False, f"Attivazione connessione fallita: {msg}"
    return True, "Ethernet configurata."


def configure_wifi_nm(iface, ssid, password, mode, ip=None, prefix=None, gw=None, dns=None):
    con_name = CON_NAME_WIFI_PREFIX + ssid
    _run(["nmcli", "con", "delete", con_name])
    args = ["nmcli", "dev", "wifi", "connect", ssid, "ifname", iface]
    if password:
        args += ["password", password]
    ok, msg = _run(args, timeout=60)
    if not ok:
        return False, f"Connessione WiFi fallita: {msg}"
    # nmcli crea la connessione con il nome dello SSID stesso di default.
    if mode == "static":
        set_args = ["nmcli", "con", "modify", ssid,
                     "ipv4.method", "manual",
                     "ipv4.addresses", f"{ip}/{prefix}",
                     "ipv4.gateway", gw]
        if dns:
            set_args += ["ipv4.dns", dns]
        ok, msg = _run(set_args)
        if not ok:
            return False, f"Configurazione IP statico fallita: {msg}"
        ok, msg = _run(["nmcli", "con", "up", ssid])
        if not ok:
            return False, f"Riattivazione connessione fallita: {msg}"
    return True, "WiFi configurato."


# ---- dhcpcd + wpa_supplicant ------------------------------------------------

def _dhcpcd_remove_block(lines, iface):
    begin, end = MARK_BEGIN.format(iface=iface), MARK_END.format(iface=iface)
    out, skip = [], False
    for line in lines:
        if line.strip() == begin:
            skip = True
            continue
        if line.strip() == end:
            skip = False
            continue
        if not skip:
            out.append(line)
    return out


def _dhcpcd_write_block(iface, ip, prefix, gw, dns):
    begin, end = MARK_BEGIN.format(iface=iface), MARK_END.format(iface=iface)
    block = [begin, f"interface {iface}", f"static ip_address={ip}/{prefix}"]
    if gw:
        block.append(f"static routers={gw}")
    if dns:
        block.append(f"static domain_name_servers={dns}")
    block.append(end)
    return block


def configure_ethernet_dhcpcd(iface, mode, ip=None, prefix=None, gw=None, dns=None):
    if not os.path.isfile(DHCPCD_CONF):
        return False, f"{DHCPCD_CONF} non trovato."
    _backup_once(DHCPCD_CONF)
    with open(DHCPCD_CONF, "r") as f:
        lines = [l.rstrip("\n") for l in f.readlines()]
    lines = _dhcpcd_remove_block(lines, iface)
    if mode == "static":
        lines += _dhcpcd_write_block(iface, ip, prefix, gw, dns)
    with open(DHCPCD_CONF, "w") as f:
        f.write("\n".join(lines) + "\n")
    ok, msg = _run(["systemctl", "restart", "dhcpcd"])
    if not ok:
        return False, f"Riavvio dhcpcd fallito: {msg}"
    return True, "Ethernet configurata."


def configure_wifi_wpa_supplicant(iface, ssid, password, mode, ip=None, prefix=None, gw=None, dns=None):
    conf_path = WPA_SUPPLICANT_CONF_TPL.format(iface=iface)
    os.makedirs(os.path.dirname(conf_path), exist_ok=True)
    if not os.path.isfile(conf_path):
        with open(conf_path, "w") as f:
            f.write("ctrl_interface=/run/wpa_supplicant\nupdate_config=1\ncountry=IT\n")
    else:
        _backup_once(conf_path)
    ok, msg = _run(["wpa_passphrase", ssid, password])
    if not ok:
        return False, f"Generazione PSK fallita: {msg}"
    with open(conf_path, "a") as f:
        f.write("\n" + msg + "\n")
    ok, msg = _run(["wpa_cli", "-i", iface, "reconfigure"])
    if not ok:
        ok, msg = _run(["systemctl", "restart", f"wpa_supplicant@{iface}"])
    if not ok:
        return False, f"Riavvio wpa_supplicant fallito: {msg}"
    ok, msg = configure_ethernet_dhcpcd(iface, mode, ip, prefix, gw, dns)
    if not ok:
        return False, f"WiFi associato ma configurazione IP fallita: {msg}"
    return True, "WiFi configurato."
