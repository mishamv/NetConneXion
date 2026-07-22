"""Tests for quickip.features.wifi.netsh_parser — pure parsing functions, no I/O."""

from __future__ import annotations

import unittest

from quickip.features.wifi.netsh_parser import (
    channel_to_freq,
    parse_networks,
    parse_interface_status,
    parse_saved_profiles,
)


# ── channel_to_freq ───────────────────────────────────────────────────────────

class TestChannelToFreq(unittest.TestCase):

    def test_channel_1(self):
        self.assertAlmostEqual(channel_to_freq(1), 2.412, places=3)

    def test_channel_6(self):
        self.assertAlmostEqual(channel_to_freq(6), 2.437, places=3)

    def test_channel_13(self):
        self.assertAlmostEqual(channel_to_freq(13), 2.472, places=3)

    def test_channel_14(self):
        self.assertAlmostEqual(channel_to_freq(14), 2.484, places=3)

    def test_channel_36_5ghz(self):
        self.assertAlmostEqual(channel_to_freq(36), 5.180, places=3)

    def test_channel_149_5ghz(self):
        self.assertAlmostEqual(channel_to_freq(149), 5.745, places=3)

    def test_unknown_channel_returns_0(self):
        self.assertEqual(channel_to_freq(0), 0.0)
        self.assertEqual(channel_to_freq(200), 0.0)


# ── parse_networks ────────────────────────────────────────────────────────────

_NETSH_NETWORKS_EN = """\
Interface name : Wi-Fi
There are 2 networks currently visible.

SSID 1 : HomeNetwork
Network type            : Infrastructure
Authentication          : WPA2-Personal
Encryption              : AES
 BSSID 1                : aa:bb:cc:dd:ee:ff
      Signal             : 85%
      Radio type         : 802.11n
      Channel            : 6
      Basic rates (Mbps) : 1 2 5.5 11
      Other rates (Mbps) : 6 9 12 18 24 36 48 54

SSID 2 : OfficeWiFi
Network type            : Infrastructure
Authentication          : WPA3-Personal
Encryption              : AES
 BSSID 1                : 11:22:33:44:55:66
      Signal             : 60%
      Radio type         : 802.11ax
      Channel            : 36
      Basic rates (Mbps) : 6 12 24
      Other rates (Mbps) : 36 48 54
"""

_NETSH_NETWORKS_RU = """\
Интерфейс: Wi-Fi
Видимых сетей: 1.

SSID 1 : РабочаяСеть
Тип сети                : Инфраструктура
Проверка подлинности    : WPA2-Персональная
Шифрование              : AES
 BSSID 1                : ff:ee:dd:cc:bb:aa
      Сигнал             : 70%
      Тип радио          : 802.11n
      Канал              : 11
"""


class TestParseNetworks(unittest.TestCase):

    def test_empty_input_returns_empty(self):
        self.assertEqual(parse_networks(""), [])

    def test_parses_two_english_networks(self):
        result = parse_networks(_NETSH_NETWORKS_EN)
        self.assertEqual(len(result), 2)

    def test_first_network_fields(self):
        result = parse_networks(_NETSH_NETWORKS_EN)
        n = result[0]
        self.assertEqual(n.ssid, "HomeNetwork")
        self.assertEqual(n.bssid, "aa:bb:cc:dd:ee:ff")
        self.assertEqual(n.signal_pct, 85)
        self.assertEqual(n.auth, "WPA2-Personal")
        self.assertEqual(n.channel, 6)
        self.assertAlmostEqual(n.freq_ghz, 2.437, places=3)

    def test_second_network_ax_protocol(self):
        result = parse_networks(_NETSH_NETWORKS_EN)
        n = result[1]
        self.assertEqual(n.ssid, "OfficeWiFi")
        self.assertEqual(n.channel, 36)
        # 802.11ax → proto_mbps fallback ≥ 1200
        self.assertGreaterEqual(n.mbps, 1200)

    def test_russian_locale_network(self):
        result = parse_networks(_NETSH_NETWORKS_RU)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ssid, "РабочаяСеть")
        self.assertEqual(result[0].signal_pct, 70)
        self.assertEqual(result[0].channel, 11)

    def test_mbps_extracted_from_other_rates(self):
        result = parse_networks(_NETSH_NETWORKS_EN)
        # "Other rates (Mbps) : 6 9 12 18 24 36 48 54" → max = 54
        # но протокол 802.11n → proto_mbps = 300 > 54, значит mbps = 300
        self.assertEqual(result[0].mbps, 300)

    def test_hidden_ssid_skipped(self):
        # SSID с пустым именем должен игнорироваться (flush условие)
        raw = "SSID 1 : \nAuthentication : Open\n BSSID 1 : aa:bb:cc:dd:ee:ff\n"
        result = parse_networks(raw)
        self.assertEqual(len(result), 0)


# ── parse_interface_status ────────────────────────────────────────────────────

_IFACE_STATUS_EN = """\
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wireless-AC 9560
    GUID                   : abcdef-1234
    Physical address        : ab:cd:ef:01:23:45
    State                  : connected
    SSID                   : HomeNetwork
    BSSID                  : aa:bb:cc:dd:ee:ff
    Network type            : Infrastructure
    Radio type              : 802.11n
    Authentication          : WPA2-Personal
    Cipher                  : CCMP
    Connection mode         : Auto Connect
    Channel                 : 6
    Receive rate (Mbps)     : 144
    Transmit rate (Mbps)    : 144
    Signal                  : 85%
    Profile                 : HomeNetwork
"""

_IFACE_STATUS_DISCONNECTED = """\
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wireless-AC 9560
    State                  : disconnected
"""


class TestParseInterfaceStatus(unittest.TestCase):

    def test_empty_returns_empty_dict(self):
        self.assertEqual(parse_interface_status(""), {})

    def test_connected_fields(self):
        result = parse_interface_status(_IFACE_STATUS_EN)
        self.assertEqual(result["name"], "Wi-Fi")
        self.assertEqual(result["ssid"], "HomeNetwork")
        self.assertEqual(result["state"], "connected")
        self.assertEqual(result["signal"], 85)
        self.assertEqual(result["channel"], 6)

    def test_disconnected_no_ssid(self):
        result = parse_interface_status(_IFACE_STATUS_DISCONNECTED)
        self.assertEqual(result["state"], "disconnected")
        self.assertNotIn("ssid", result)

    def test_signal_parsed_as_int(self):
        result = parse_interface_status(_IFACE_STATUS_EN)
        self.assertIsInstance(result["signal"], int)

    def test_channel_parsed_as_int(self):
        result = parse_interface_status(_IFACE_STATUS_EN)
        self.assertIsInstance(result["channel"], int)


# ── parse_saved_profiles ──────────────────────────────────────────────────────

_SAVED_PROFILES_EN = """\
Profiles on interface Wi-Fi:

Group policy profiles (read only)
---------------------------------
    <None>

User profiles
-------------
    All User Profile     : HomeNetwork
    All User Profile     : OfficeWiFi
    All User Profile     : CafeHotspot
"""

_SAVED_PROFILES_RU = """\
Профили на интерфейсе Wi-Fi:

Профили групповой политики (только чтение)
-------------------------------------------
    <Нет>

Профили пользователей
---------------------
    Профиль всех пользователей : Домашняя
    Профиль всех пользователей : Рабочая
"""


class TestParseSavedProfiles(unittest.TestCase):

    def test_empty_returns_empty(self):
        self.assertEqual(parse_saved_profiles(""), [])

    def test_english_three_profiles(self):
        result = parse_saved_profiles(_SAVED_PROFILES_EN)
        self.assertEqual(result, ["HomeNetwork", "OfficeWiFi", "CafeHotspot"])

    def test_russian_two_profiles(self):
        result = parse_saved_profiles(_SAVED_PROFILES_RU)
        self.assertEqual(result, ["Домашняя", "Рабочая"])

    def test_no_profiles_section_returns_empty(self):
        result = parse_saved_profiles("No profiles found.\n")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
