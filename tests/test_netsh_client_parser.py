"""Locale-aware parser contracts for the Windows netsh client."""

from quickip.infrastructure.system.netsh_client import NetshClient


def test_parse_adapter_list_english_and_names_with_spaces() -> None:
    output = """
Admin State    State          Type             Interface Name
-------------------------------------------------------------------------
Enabled        Connected      Dedicated        Ethernet
Enabled        Disconnected   Dedicated        Local Area Connection 2
"""

    assert NetshClient()._parse_adapter_list(output) == [
        "Ethernet",
        "Local Area Connection 2",
    ]


def test_parse_adapter_list_russian_and_deduplicates_case_insensitively() -> None:
    output = """
Состояние адм.  Состояние      Тип              Имя интерфейса
-------------------------------------------------------------------------
Включен         Подключен       Выделенный       Беспроводная сеть
Включен         Подключен       Выделенный       беспроводная сеть
"""

    assert NetshClient()._parse_adapter_list(output) == ["Беспроводная сеть"]


def test_parse_adapter_config_english_static_and_multiline_dns() -> None:
    output = """
Configuration for interface "Ethernet"
    DHCP enabled:                         No
    IP Address:                           192.168.10.25
    Subnet Prefix:                        192.168.10.0/24 (mask 255.255.255.0)
    Default Gateway:                      192.168.10.1
    Statically Configured DNS Servers:    1.1.1.1
                                           8.8.8.8
"""

    config = NetshClient()._parse_adapter_config("Ethernet", output)

    assert config is not None
    assert not config.dhcp_enabled
    assert config.ip == "192.168.10.25"
    assert config.mask == "255.255.255.0"
    assert config.gateway == "192.168.10.1"
    assert config.dns_servers == ["1.1.1.1", "8.8.8.8"]


def test_parse_adapter_config_russian_dhcp_and_cidr_mask() -> None:
    output = """
Конфигурация интерфейса "Беспроводная сеть"
    DHCP включен:                         Да
    IP-адрес:                             10.20.30.40
    Префикс подсети:                      10.20.30.0/23
    Основной шлюз:                        10.20.30.1
    DNS-серверы, настроенные через DHCP:  10.20.30.1
"""

    config = NetshClient()._parse_adapter_config("Беспроводная сеть", output)

    assert config is not None
    assert config.dhcp_enabled
    assert config.ip == "10.20.30.40"
    assert config.mask == "255.255.254.0"
    assert config.gateway == "10.20.30.1"
    assert config.dns_servers == ["10.20.30.1"]


def test_parse_adapter_config_rejects_invalid_ipv4_values() -> None:
    output = """
    DHCP enabled: No
    IP Address: 999.1.1.1
    Subnet Prefix: 192.168.1.0/99
    Default Gateway: none
    DNS Servers: 300.2.2.2
"""

    config = NetshClient()._parse_adapter_config("Ethernet", output)

    assert config is not None
    assert config.ip == ""
    assert config.mask == ""
    assert config.gateway == ""
    assert config.dns_servers == []
