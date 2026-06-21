from __future__ import annotations

import json
from pathlib import Path

PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "bg":               "#0D0D0F",
        "card_bg":          "#16161E",
        "card_hover":       "#1E1E2A",
        "line":             "#1E1E28",
        "time":             "#555566",
        "title":            "#E0E0EE",
        "muted":            "#888899",
        "kind":             "#44445A",
        "dur":              "#44445A",
        "now":              "#FF3B30",
        "header_bg":        "#0A0A12",
        "done_title":       "#5C5C70",
        "done_card_bg":     "#10141A",
        "check_border":     "#3A3A50",
    },
    "light": {
        "bg":               "#F8F9FA",
        "card_bg":          "#FFFFFF",
        "card_hover":       "#EDEFF3",
        "line":             "#DEE2E6",
        "time":             "#6C757D",
        "title":            "#1A1A2E",
        "muted":            "#6C757D",
        "kind":             "#9099A8",
        "dur":              "#9099A8",
        "now":              "#D62828",
        "header_bg":        "#E9ECEF",
        "done_title":       "#9099A8",
        "done_card_bg":     "#F1F3F5",
        "check_border":     "#CED4DA",
    },
}

_current: str = "dark"


def current_name() -> str:
    return _current


def set_current(name: str) -> None:
    global _current
    if name in PALETTES:
        _current = name


def get(key: str) -> str:
    return PALETTES[_current].get(key, PALETTES["dark"].get(key, "#000000"))


def palette() -> dict[str, str]:
    return PALETTES[_current]


def load_from_config(config_path: Path) -> str:
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = json.load(f)
        name = (raw.get("settings", {}) or {}).get("theme", "dark")
        set_current(name)
    except Exception:
        set_current("dark")
    return current_name()


def save_to_config(config_path: Path, name: str) -> None:
    if name not in PALETTES:
        return
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        raw = {}
    settings = raw.setdefault("settings", {})
    settings["theme"] = name
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    set_current(name)


def toggle(config_path: Path) -> str:
    new = "light" if current_name() == "dark" else "dark"
    save_to_config(config_path, new)
    return new
