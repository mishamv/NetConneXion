"""Wi-Fi feature — WLAN XML profile builder.

Builds Windows WLAN XML profile strings compatible with:
  netsh wlan add profile filename=<path> user=all

Auth → (authentication, encryption) mapping covers all 10 AUTH_OPTIONS.
The decrypted password is written to the XML keyMaterial element and the
temp file is deleted immediately after netsh processes it.
NEVER log or persist the decrypted password.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

_NS = "http://www.microsoft.com/networking/WLAN/profile/v1"

# Auth option → (XML authentication, XML encryption)
# Assumption: WPA3-Enterprise maps to WPA2 XML — not fully supported by Windows netsh
# Assumption: OWE requires Windows 10 build 1903+
# NOTE: WEP намеренно исключён — взломан с 2001 года (FMS/aircrack, секунды).
#       Нарушает PCI DSS 4.0 req 6.4.2, CIS Benchmark L1. Используйте WPA2+ минимум.
AUTH_XML_MAP: dict = {
    "Open":                  ("open",    "none"),
    "WPA-Personal":          ("WPAPSK",  "TKIP"),
    "WPA2-Personal":         ("WPA2PSK", "AES"),
    "WPA3-Personal":         ("WPA3SAE", "AES"),
    "WPA-Enterprise":        ("WPA",     "TKIP"),
    "WPA2-Enterprise":       ("WPA2",    "AES"),
    "WPA3-Enterprise":       ("WPA2",    "AES"),   # fallback — see assumption above
    "WPA2/WPA3-Transition":  ("WPA2PSK", "AES"),
    "OWE":                   ("OWE",     "AES"),   # Win 10 1903+ only
}


def build_profile_xml(
    ssid: str,
    auth: str,
    cipher: str,
    password: str,
    auto_connect: bool = True,
    connect_hidden: bool = False,
    is_adhoc: bool = False,
) -> str:
    """Return a WLANProfile XML string for the given parameters.

    *password* must be the **plaintext** PSK. The caller is responsible
    for decrypting it from the vault before passing it here.
    For open networks pass password="" to omit the sharedKey element.

    Raises:
        ValueError: if auth == "WEP" (insecure, not supported).
    """
    if auth == "WEP":
        raise ValueError(
            "WEP не поддерживается — стандарт взломан с 2001 года и "
            "запрещён политиками безопасности (PCI DSS 4.0, CIS L1). "
            "Используйте WPA2-Personal или выше."
        )
    xml_auth, xml_cipher = AUTH_XML_MAP.get(auth, ("WPA2PSK", "AES"))

    root = ET.Element("WLANProfile", xmlns=_NS)
    ET.SubElement(root, "name").text = ssid

    ssid_cfg = ET.SubElement(root, "SSIDConfig")
    ssid_el = ET.SubElement(ssid_cfg, "SSID")
    ET.SubElement(ssid_el, "name").text = ssid
    ET.SubElement(ssid_cfg, "nonBroadcast").text = str(connect_hidden).lower()

    ET.SubElement(root, "connectionType").text = "IBSS" if is_adhoc else "ESS"
    ET.SubElement(root, "connectionMode").text = "auto" if auto_connect else "manual"

    msm = ET.SubElement(root, "MSM")
    security = ET.SubElement(msm, "security")
    auth_enc = ET.SubElement(security, "authEncryption")
    ET.SubElement(auth_enc, "authentication").text = xml_auth
    ET.SubElement(auth_enc, "encryption").text = xml_cipher
    ET.SubElement(auth_enc, "useOneX").text = "false"

    # Only add sharedKey for personal (PSK) modes that have a password
    is_psk = xml_auth in ("WPA2PSK", "WPAPSK", "WPA3SAE", "WPA2PSK")
    if password and is_psk:
        shared_key = ET.SubElement(security, "sharedKey")
        ET.SubElement(shared_key, "keyType").text = "passPhrase"
        ET.SubElement(shared_key, "protected").text = "false"
        ET.SubElement(shared_key, "keyMaterial").text = password

    ET.indent(root, space="  ")
    xml_str = ET.tostring(root, encoding="unicode", xml_declaration=False)
    return '<?xml version="1.0"?>\n' + xml_str
