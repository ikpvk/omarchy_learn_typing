"""Colours and fonts for the interface, taken from the active Omarchy theme and font when there are ones."""
from __future__ import annotations

import colorsys
import ctypes
import ctypes.util
import os
from pathlib import Path
import subprocess
import tomllib

# Omarchy swaps this folder's theme/ directory, then rewrites theme.name, on every theme change.
OMARCHY_CURRENT = Path.home() / ".local/state/omarchy/current"
# `omarchy font set` rewrites fonts.conf here to make its font the system monospace font.
FONTCONFIG_DIR = Path.home() / ".config/fontconfig"

# Used when Omarchy is absent, matching the app's original look.
DEFAULT = {
    "mode": "dark", "background": "#101519", "foreground": "#e1e9ec", "accent": "#83e5c0",
    "red": "#ff8c91", "bright_red": "#ff8c91", "yellow": "#f4c784", "bright_yellow": "#f4c784",
}
# JetBrains Mono ships in fonts/, so other distros get it without installing anything.
BUNDLED_FONT = Path(__file__).resolve().parent / "fonts" / "JetBrainsMono[wght].ttf"
DEFAULT_FONTS = {"ui": "JetBrains Mono", "mono": "JetBrains Mono"}
# Used on Omarchy until `omarchy font set` has been run; Omarchy ships it as JetBrainsMono Nerd Font.
OMARCHY_FALLBACK_FONT = "JetBrainsMono Nerd Font, JetBrains Mono"


def _rgb(value: str) -> tuple[float, float, float]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Not a #rrggbb colour: {value!r}")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{round(min(1, max(0, c)) * 255):02x}" for c in rgb)


def mix(a: str, b: str, amount: float) -> str:
    """Blend amount of b into a."""
    return _hex(x + (y - x) * amount for x, y in zip(_rgb(a), _rgb(b)))


def _luminance(value: str) -> float:
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in _rgb(value)]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _saturation(value: str) -> float:
    return colorsys.rgb_to_hls(*_rgb(value))[2]


def palette(colors: dict) -> dict[str, str]:
    """Map an Omarchy colors.toml onto the roles the interface draws with."""
    bg, fg = colors["background"], colors["foreground"]
    dark = colors.get("mode", "dark") != "light"
    # Monochrome themes may make red grey and keep a colourful bright_red, or the reverse.
    red = max(colors["red"], colors.get("bright_red", colors["red"]), key=_saturation)
    yellow = max(colors["yellow"], colors.get("bright_yellow", colors["yellow"]), key=_saturation)
    accent = colors["accent"]
    on = lambda fill: max((bg, fg, "#000000", "#ffffff"), key=lambda c: contrast(c, fill))
    result = {
        "mode": "dark" if dark else "light",
        "bg": bg,
        "text": fg,
        "panel": mix(bg, fg, 0.04),
        "key": mix(bg, fg, 0.09),
        "hover": mix(bg, fg, 0.15),
        "border": mix(bg, fg, 0.18),
        "line": mix(bg, fg, 0.12),
        "muted": mix(bg, fg, 0.6),
        "shadow": mix(bg, "#000000", 0.45 if dark else 0.18),
        "accent": accent,
        "on_accent": on(accent),
        "accent_hover": mix(accent, fg, 0.25),
        "badge": mix(bg, accent, 0.18),
        "error": red,
        "on_error": on(red),
        "modifier": yellow,
        "modifier_fill": mix(bg, yellow, 0.25),
    }
    for value in result.values():
        if value.startswith("#"):
            _rgb(value)
    return result


def load(directory: Path = OMARCHY_CURRENT) -> dict[str, str] | None:
    """Return the current Omarchy palette, or None when there is no readable theme."""
    try:
        with open(directory / "theme" / "colors.toml", "rb") as file:
            return palette(tomllib.load(file))
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError, ValueError, AttributeError):
        return None


def register_bundled_font(path: Path = BUNDLED_FONT) -> bool:
    """Make the bundled font available to this process only. Call before GTK draws any text."""
    library = ctypes.util.find_library("fontconfig")
    if not library or not path.is_file():
        return False
    try:
        fontconfig = ctypes.CDLL(library)
    except OSError:
        return False
    fontconfig.FcConfigAppFontAddFile.argtypes = (ctypes.c_void_p, ctypes.c_char_p)
    return bool(fontconfig.FcConfigAppFontAddFile(None, os.fsencode(path)))


def fonts(omarchy: Path = OMARCHY_CURRENT, config_file: Path | None = None,
          fontconfig_dir: Path = FONTCONFIG_DIR) -> dict[str, str]:
    """Use the Omarchy font for all text, as the Omarchy shell does; otherwise the app's own fonts."""
    if not omarchy.is_dir():
        return dict(DEFAULT_FONTS)
    if not (config_file or fontconfig_dir / "fonts.conf").is_file():
        return {"ui": OMARCHY_FALLBACK_FONT, "mono": OMARCHY_FALLBACK_FONT}
    # Ask a fresh fontconfig, as a running Pango keeps the aliases it read at startup.
    env = os.environ | ({"FONTCONFIG_FILE": str(config_file)} if config_file else {})
    try:
        result = subprocess.run(["fc-match", "monospace", "-f", "%{family}"], env=env,
                                capture_output=True, text=True, timeout=3, check=True)
        family = result.stdout.split(",")[0].strip()
    except (OSError, subprocess.SubprocessError):
        family = ""
    family = family or OMARCHY_FALLBACK_FONT
    return {"ui": family, "mono": family}


def _families(families: str) -> str:
    """Quote a comma-separated family list for CSS."""
    names = (name.strip().replace("\\", "").replace('"', "") for name in families.split(","))
    return ", ".join(f'"{name}"' for name in names if name)


def css(p: dict[str, str], f: dict[str, str] = DEFAULT_FONTS) -> str:
    return f"""
window, popover, tooltip {{ font-family: {_families(f['ui'])}; }}
label.metric, textview {{ font-family: {_families(f['mono'])}; }}
window {{ background: {p['bg']}; color: {p['text']}; }}
headerbar {{ background: {p['bg']}; color: {p['text']}; box-shadow: none; border-bottom: 1px solid {p['line']}; }}
label.title {{ font-size: 23px; font-weight: 800; letter-spacing: -0.5px; }}
label.subtitle, label.muted {{ color: {p['muted']}; }}
label.eyebrow {{ font-size: 11px; font-weight: bold; letter-spacing: 1.5px; color: {p['muted']}; }}
label.metric {{ font-size: 28px; font-weight: 700; }}
label.accent {{ color: {p['accent']}; }}
label.hint {{ font-size: 15px; }}
label.error {{ color: {p['error']}; }}
label.badge {{ background: {p['badge']}; color: {p['accent']}; padding: 5px 10px; border-radius: 15px; font-size: 11px; }}
button, dropdown {{ background: {p['key']}; color: {p['text']}; border: 1px solid {p['border']}; border-radius: 9px; box-shadow: none; min-height: 30px; }}
button {{ padding: 5px 14px; }}
button:hover {{ background: {p['hover']}; }}
button.primary {{ background: {p['accent']}; color: {p['on_accent']}; border-color: {p['accent']}; font-weight: bold; }}
button.primary:hover {{ background: {p['accent_hover']}; }}
entry, textview, textview text {{ background: {p['panel']}; color: {p['text']}; border-radius: 8px; }}
entry {{ border: 1px solid {p['border']}; min-height: 32px; }}
textview {{ padding: 16px; font-size: 16px; }}
popover > contents, popover > arrow {{ background: {p['panel']}; color: {p['text']}; border: 1px solid {p['border']}; }}
popover modelbutton:hover, popover row:hover, popover row:selected {{ background: {p['hover']}; }}
selection {{ background: {p['accent']}; color: {p['on_accent']}; }}
.card {{ background: {p['panel']}; border: 1px solid {p['line']}; border-radius: 14px; padding: 14px 20px; }}
.practice {{ background: {p['panel']}; border: 1px solid {p['line']}; border-radius: 16px; }}
separator {{ background: {p['line']}; }}
progressbar trough {{ background: {p['line']}; border: none; min-height: 4px; border-radius: 3px; }}
progressbar progress {{ background: {p['accent']}; min-height: 4px; border-radius: 3px; }}
"""
