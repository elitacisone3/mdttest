"""Rilevamento hostname/IP, connettivita' Internet e stack di rete host."""
import os
import shutil
import socket
import subprocess

# IP letterali (non nomi) apposta: distingue "manca la rotta di
# default/WAN" da "manca solo il DNS" (il fallback sotto copre quel caso).
_INTERNET_CHECK_TARGETS = [("1.1.1.1", 443), ("8.8.8.8", 443), ("9.9.9.9", 443)]
_DNS_FALLBACK_HOST = "connectivitycheck.gstatic.com"


def get_hostname():
    return socket.gethostname()


def get_primary_ip():
    """IP della rotta di default, senza inviare traffico reale (connect()
    su UDP non genera pacchetti finche' non si scrive sul socket)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def has_internet(timeout=3.0):
    for host, port in _INTERNET_CHECK_TARGETS:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    try:
        socket.getaddrinfo(_DNS_FALLBACK_HOST, 443, proto=socket.IPPROTO_TCP)
        return True
    except socket.gaierror:
        return False


def _systemctl_is_active(unit):
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", unit],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        )
        return proc.stdout.decode().strip() == "active"
    except (OSError, subprocess.SubprocessError):
        return False


def detect_network_stack():
    """"networkmanager" | "dhcpcd" | "unknown"."""
    if shutil.which("nmcli") and _systemctl_is_active("NetworkManager"):
        return "networkmanager"
    if shutil.which("wpa_cli") or os.path.exists("/etc/dhcpcd.conf"):
        return "dhcpcd"
    if shutil.which("nmcli"):
        return "networkmanager"
    return "unknown"


def _iface_type_wireless(iface):
    return os.path.exists(f"/sys/class/net/{iface}/wireless")


def _list_interfaces():
    try:
        proc = subprocess.run(
            ["ip", "-o", "link"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    names = []
    for line in proc.stdout.decode(errors="replace").splitlines():
        # "N: <iface>: <flags> ..."
        parts = line.split(":", 2)
        if len(parts) < 2:
            continue
        name = parts[1].strip().split("@")[0]
        if name and name != "lo":
            names.append(name)
    return names


def list_ethernet_interfaces():
    return [i for i in _list_interfaces() if not _iface_type_wireless(i)]


def list_wifi_interfaces():
    return [i for i in _list_interfaces() if _iface_type_wireless(i)]


def scan_wifi_ssids(iface, stack=None):
    """Best-effort: una lista vuota (mai un'eccezione) se la scansione
    fallisce, cosi' il chiamante puo' sempre offrire l'inserimento manuale."""
    stack = stack or detect_network_stack()
    try:
        if stack == "networkmanager" and shutil.which("nmcli"):
            proc = subprocess.run(
                ["nmcli", "-t", "-f", "SSID", "dev", "wifi", "list", "ifname", iface],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
            )
            ssids = [l.strip() for l in proc.stdout.decode(errors="replace").splitlines() if l.strip()]
        else:
            proc = subprocess.run(
                ["iw", "dev", iface, "scan"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
            )
            ssids = []
            for line in proc.stdout.decode(errors="replace").splitlines():
                line = line.strip()
                if line.startswith("SSID:"):
                    ssid = line[len("SSID:"):].strip()
                    if ssid:
                        ssids.append(ssid)
        # dedup mantenendo l'ordine
        seen = set()
        out = []
        for s in ssids:
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out
    except (OSError, subprocess.SubprocessError):
        return []
