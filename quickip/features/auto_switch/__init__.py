"""Auto-switch feature — automatically apply a network profile when joining a Wi-Fi network.

Usage:
  1. Set profile.auto_switch_ssid = "MyNetwork" on any IP profile.
  2. NetworkMonitorService polls the active SSID every N seconds.
  3. When SSID changes, AutoSwitchService finds a matching profile and applies it.

Wire-up in bootstrap.py:
  monitor = NetworkMonitorService(container)
  auto    = AutoSwitchService(container)
  monitor.start()
"""
