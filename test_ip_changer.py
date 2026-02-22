from pathlib import Path

from ip_changer import (
    NetworkProfile,
    _decode_output,
    _data_dir,
    _is_portable_mode,
    _unique,
    append_history_entry,
    build_netsh_commands,
    compute_history_stats,
    check_ip_conflict,
    get_last_successful_profile_snapshot,
    rollback_last_successful_profile,
    export_profiles,
    import_profiles,
    parse_netsh_interfaces,
    run_dns_check,
    run_netstat,
    run_ping,
    load_settings,
    save_settings,
    parse_current_wifi_ssid,
    parse_visible_wifi_networks,
    resolve_profile_for_ssid,
)


def test_static_ip_and_dns_commands():
    profile = NetworkProfile(
        name="Office",
        adapter="Ethernet",
        dhcp_ip=False,
        ip="10.10.10.5",
        mask="255.255.255.0",
        gateway="10.10.10.1",
        dhcp_dns=False,
        dns_primary="8.8.8.8",
        dns_secondary="1.1.1.1",
    )

    commands = build_netsh_commands(profile)
    assert len(commands) == 3
    assert "interface ipv4 set address" in commands[0]
    assert "address=10.10.10.5" in commands[0]
    assert "gwmetric=1" in commands[0]
    assert "set dnsservers" in commands[1]
    assert "add dnsservers" in commands[2]


def test_dhcp_commands():
    profile = NetworkProfile(name="DHCP", adapter="Wi-Fi", dhcp_ip=True, dhcp_dns=True)
    commands = build_netsh_commands(profile)
    assert len(commands) == 2
    assert "set address" in commands[0] and "source=dhcp" in commands[0]
    assert "set dnsservers" in commands[1] and "source=dhcp" in commands[1]


def test_parse_netsh_interfaces_en_and_ru_headers():
    sample_en = """
Admin State    State          Type             Interface Name
-------------------------------------------------------------------------
Enabled        Connected      Dedicated        Ethernet
Enabled        Disconnected   Wireless         Wi-Fi
"""
    sample_ru = """
Состояние админ.  Состояние     Тип             Имя интерфейса
-------------------------------------------------------------------------
Включен          Подключен      Выделенный      Ethernet 2
Включен          Отключен       Беспроводной    Беспроводная сеть
"""
    assert parse_netsh_interfaces(sample_en) == ["Ethernet", "Wi-Fi"]
    assert parse_netsh_interfaces(sample_ru) == ["Ethernet 2", "Беспроводная сеть"]


def test_unique_adapters_preserves_order_and_deduplicates_case_insensitive():
    items = ["Ethernet", "Wi-Fi", "ethernet", "", "  Wi-Fi  ", "VPN"]
    assert _unique(items) == ["Ethernet", "Wi-Fi", "VPN"]


def test_decode_output_handles_non_utf_cp866():
    raw = "Беспроводная сеть".encode("cp866")
    assert _decode_output(raw) == "Беспроводная сеть"


def test_export_and_import_profiles_roundtrip(tmp_path: Path):
    profiles = {
        "Office": NetworkProfile(name="Office", adapter="Ethernet", dhcp_ip=True, dhcp_dns=True),
    }
    export_path = tmp_path / "profiles_export.json"
    export_profiles(export_path, profiles)

    merged, report = import_profiles(export_path, {}, strategy="rename")
    assert "Office" in merged
    assert report.imported == 1


def test_import_profiles_rename_conflict(tmp_path: Path):
    existing = {"Office": NetworkProfile(name="Office", adapter="Wi-Fi", dhcp_ip=True, dhcp_dns=True)}
    export_path = tmp_path / "profiles_export.json"
    export_profiles(export_path, {"Office": NetworkProfile(name="Office", adapter="Ethernet", dhcp_ip=True, dhcp_dns=True)})

    merged, report = import_profiles(export_path, existing, strategy="rename")
    assert "Office" in merged
    assert any(name.startswith("Office (") for name in merged)
    assert report.renamed == 1


def test_append_history_entry_writes_file(tmp_path: Path, monkeypatch):
    history_path = tmp_path / "history.json"
    monkeypatch.setattr("ip_changer.HISTORY_FILE", history_path)

    profile = NetworkProfile(name="Home", adapter="Ethernet", dhcp_ip=True, dhcp_dns=True)
    entry = append_history_entry(
        profile=profile,
        commands=["netsh ..."],
        output=["ok"],
        success=True,
        duration_ms=123,
    )

    assert entry.profile_name == "Home"
    assert history_path.exists()
    payload = history_path.read_text(encoding="utf-8")
    assert "Home" in payload


def test_run_ping_invokes_capture(monkeypatch):
    captured = {}

    def fake_run_capture(cmd):
        captured["cmd"] = cmd
        return "pong"

    monkeypatch.setattr("ip_changer._run_capture", fake_run_capture)
    out = run_ping("8.8.8.8", count=2)
    assert out == "pong"
    assert captured["cmd"][0] == "ping"


def test_run_dns_check_fallback_socket(monkeypatch):
    def fake_run_capture(_cmd):
        raise RuntimeError("no powershell")

    monkeypatch.setattr("ip_changer._run_capture", fake_run_capture)
    monkeypatch.setattr("socket.getaddrinfo", lambda *_args, **_kwargs: [(None, None, None, None, ("1.1.1.1", 0))])
    out = run_dns_check("example.com")
    assert "1.1.1.1" in out


def test_run_netstat_invokes_capture(monkeypatch):
    monkeypatch.setattr("ip_changer._run_capture", lambda cmd: "ok" if cmd[0] == "netstat" else "bad")
    assert run_netstat() == "ok"


def test_settings_roundtrip(tmp_path: Path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr("ip_changer.SETTINGS_FILE", settings_path)

    payload = {"wifi_mappings": [{"ssid": "OfficeWiFi", "profile": "Office"}]}
    save_settings(payload)
    loaded = load_settings()
    assert loaded["wifi_mappings"][0]["ssid"] == "OfficeWiFi"


def test_parse_current_wifi_ssid():
    sample = """
    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi
    SSID                   : OfficeWiFi
    BSSID                  : 11:22:33:44:55:66
    """
    assert parse_current_wifi_ssid(sample) == "OfficeWiFi"


def test_resolve_profile_for_ssid_case_insensitive():
    settings = {"wifi_mappings": [{"ssid": "OfficeWiFi", "profile": "Office"}]}
    assert resolve_profile_for_ssid(settings, "officewifi") == "Office"
    assert resolve_profile_for_ssid(settings, "unknown") is None


def test_parse_visible_wifi_networks():
    sample = """
    SSID 1 : OfficeWiFi
        Network type            : Infrastructure
    SSID 2 : GuestNet
        Network type            : Infrastructure
    SSID 3 : OfficeWiFi
    """
    assert parse_visible_wifi_networks(sample) == ["OfficeWiFi", "GuestNet"]


def test_load_settings_defaults_include_wifi_auto_fields(tmp_path: Path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr("ip_changer.SETTINGS_FILE", settings_path)
    loaded = load_settings()
    assert loaded["wifi_mappings"] == []
    assert loaded["wifi_auto_apply"] is False
    assert loaded["wifi_auto_interval_sec"] == 5
    assert loaded["ui_theme"] == "light"


def test_resolve_profile_for_ssid_prefers_auto_mapping():
    settings = {
        "wifi_mappings": [
            {"ssid": "OfficeWiFi", "profile": "OfficeManual", "auto": False},
            {"ssid": "OfficeWiFi", "profile": "OfficeAuto", "auto": True},
        ]
    }
    assert resolve_profile_for_ssid(settings, "officewifi") == "OfficeAuto"


def test_compute_history_stats():
    entries = [
        type("E", (), {"success": True, "duration_ms": 100})(),
        type("E", (), {"success": False, "duration_ms": 300})(),
        type("E", (), {"success": True, "duration_ms": 200})(),
    ]
    stats = compute_history_stats(entries)
    assert stats.total == 3
    assert stats.success == 2
    assert stats.failed == 1
    assert stats.avg_duration_ms == 200


def test_check_ip_conflict_detects_reachable_static_ip(monkeypatch):
    profile = NetworkProfile(name="Office", adapter="Ethernet", dhcp_ip=False, ip="10.0.0.55", mask="255.255.255.0")
    monkeypatch.setattr("ip_changer._ping_once", lambda host, timeout_ms=900: host == "10.0.0.55")

    conflict, message = check_ip_conflict(profile)
    assert conflict is True
    assert "10.0.0.55" in message


def test_check_ip_conflict_skips_dhcp_profiles(monkeypatch):
    profile = NetworkProfile(name="DHCP", adapter="Ethernet", dhcp_ip=True)

    def fail_ping(*_args, **_kwargs):
        raise AssertionError("_ping_once should not be called for DHCP")

    monkeypatch.setattr("ip_changer._ping_once", fail_ping)
    conflict, message = check_ip_conflict(profile)
    assert conflict is False
    assert message == ""


def test_get_last_successful_profile_snapshot_returns_latest(tmp_path: Path, monkeypatch):
    history_path = tmp_path / "history.json"
    monkeypatch.setattr("ip_changer.HISTORY_FILE", history_path)

    p1 = NetworkProfile(name="Office", adapter="Ethernet", dhcp_ip=True, dhcp_dns=True)
    p2 = NetworkProfile(name="Office", adapter="Ethernet", dhcp_ip=False, ip="10.0.0.10", mask="255.255.255.0")
    append_history_entry(p1, ["cmd1"], ["ok"], True, 10)
    append_history_entry(p2, ["cmd2"], ["ok"], True, 15)

    snap = get_last_successful_profile_snapshot("Office")
    assert snap is not None
    assert snap.ip == "10.0.0.10"


def test_rollback_last_successful_profile_restores_and_applies(tmp_path: Path, monkeypatch):
    history_path = tmp_path / "history.json"
    profiles_path = tmp_path / "profiles.json"
    monkeypatch.setattr("ip_changer.HISTORY_FILE", history_path)
    monkeypatch.setattr("ip_changer.PROFILES_FILE", profiles_path)

    old = NetworkProfile(name="Office", adapter="Ethernet", dhcp_ip=False, ip="10.0.0.10", mask="255.255.255.0")
    append_history_entry(old, ["cmd"], ["ok"], True, 20)

    applied = {}

    def fake_apply(profile):
        applied["name"] = profile.name
        return type("R", (), {"commands": [], "output": []})()

    monkeypatch.setattr("ip_changer.apply_profile", fake_apply)

    profiles = {"Office": NetworkProfile(name="Office", adapter="Ethernet", dhcp_ip=True, dhcp_dns=True)}
    restored = rollback_last_successful_profile(profiles, profile_name="Office")

    assert restored.ip == "10.0.0.10"
    assert profiles["Office"].ip == "10.0.0.10"
    assert applied["name"] == "Office"


def test_is_portable_mode_true_when_flag_in_cwd(tmp_path: Path, monkeypatch):
    (tmp_path / "portable.flag").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert _is_portable_mode() is True


def test_data_dir_uses_localappdata_on_windows(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("ip_changer._is_portable_mode", lambda: False)
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert _data_dir() == tmp_path / "Quick-IP-change"
