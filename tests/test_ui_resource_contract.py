"""Packaging and localisation resource contracts."""

from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _locale(name: str) -> dict[str, str]:
    path = ROOT / "data" / "locales" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_ru_and_en_locales_have_matching_nonempty_keys() -> None:
    ru = _locale("ru")
    en = _locale("en")

    assert set(ru) == set(en)
    assert all(str(value).strip() for value in ru.values())
    assert all(str(value).strip() for value in en.values())


def test_tool_static_labels_exist_in_both_locales() -> None:
    keys = {
        "tools_ping_placeholder",
        "tools_ping_count",
        "tools_dns_type",
        "tools_dns_server",
        "tools_arp_col_ip",
        "tools_arp_col_mac",
        "tools_arp_col_type",
        "tools_arp_col_iface",
        "tools_signal_title",
        "tools_signal_roaming_log",
    }

    assert keys <= set(_locale("ru"))
    assert keys <= set(_locale("en"))


def _literal_ui_translation_keys() -> set[str]:
    """Collect literal keys passed to the application's translation helpers."""
    keys: set[str] = set()
    source_root = ROOT / "quickip"

    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue

            function = node.func
            is_translation_call = False
            if isinstance(function, ast.Attribute):
                if function.attr == "_tr":
                    is_translation_call = True
                elif function.attr == "get" and isinstance(function.value, ast.Attribute):
                    is_translation_call = function.value.attr in {"i18n", "_i18n"}
                elif function.attr == "get" and isinstance(function.value, ast.Name):
                    is_translation_call = function.value.id == "i18n"

            first_arg = node.args[0]
            if (
                is_translation_call
                and isinstance(first_arg, ast.Constant)
                and isinstance(first_arg.value, str)
            ):
                keys.add(first_arg.value)

    return keys


def test_literal_ui_translation_keys_exist_in_both_locales() -> None:
    used_keys = _literal_ui_translation_keys()

    assert used_keys <= set(_locale("ru"))
    assert used_keys <= set(_locale("en"))


def test_dynamic_ip_batch_translation_families_are_complete() -> None:
    keys = {
        *(f"tools_batch_filter_{name}" for name in (
            "all", "reachable", "unreachable", "invalid", "pending"
        )),
        *(f"tools_batch_status_{name}" for name in (
            "reachable", "unreachable", "invalid", "pending", "error"
        )),
    }

    assert keys <= set(_locale("ru"))
    assert keys <= set(_locale("en"))


def test_pyinstaller_bundle_contains_qt_ui_assets() -> None:
    spec = (ROOT / "NetConneXion.spec").read_text(encoding="utf-8")

    assert "'quickip/ui_qt/assets'" in spec
    assert (ROOT / "quickip" / "ui_qt" / "assets").is_dir()
