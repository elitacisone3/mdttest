"""Rilevamento/mount/umount di una chiavetta USB, per il test 'su chiavetta'."""
import json
import os
import subprocess

from . import constants


def list_removable_unmounted(lsblk_json=None):
    """Ritorna una lista di dict {name, path, fstype} per le partizioni
    USB non ancora montate. lsblk_json e' iniettabile per i test (stringa
    JSON gia' pronta), altrimenti richiama davvero 'lsblk'."""
    if lsblk_json is None:
        try:
            proc = subprocess.run(
                ["lsblk", "-J", "-o", "NAME,TRAN,MOUNTPOINT,TYPE,FSTYPE"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
            )
            lsblk_json = proc.stdout.decode(errors="replace")
        except (OSError, subprocess.SubprocessError):
            return []
    try:
        data = json.loads(lsblk_json)
    except (ValueError, TypeError):
        return []

    out = []

    def walk(devices, is_usb_ancestor=False):
        for dev in devices:
            is_usb = is_usb_ancestor or dev.get("tran") == "usb"
            children = dev.get("children") or []
            if is_usb and dev.get("type") == "part" and not dev.get("mountpoint") and dev.get("fstype"):
                out.append({
                    "name": dev.get("name"),
                    "path": "/dev/" + dev.get("name", ""),
                    "fstype": dev.get("fstype"),
                })
            walk(children, is_usb_ancestor=is_usb)

    walk(data.get("blockdevices", []))
    return out


def mount_usb(devpath, mountpoint=None):
    mountpoint = mountpoint or constants.USB_MOUNTPOINT
    os.makedirs(mountpoint, exist_ok=True)
    try:
        proc = subprocess.run(
            ["mount", devpath, mountpoint],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    if proc.returncode != 0:
        return False, proc.stderr.decode(errors="replace").strip()
    return True, mountpoint


def umount_usb(mountpoint=None):
    mountpoint = mountpoint or constants.USB_MOUNTPOINT
    try:
        proc = subprocess.run(
            ["umount", mountpoint],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    if proc.returncode != 0:
        return False, proc.stderr.decode(errors="replace").strip()
    return True, ""
