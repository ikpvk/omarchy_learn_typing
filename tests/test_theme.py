import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import theme

STOCK_THEMES = Path("/usr/share/omarchy/themes")


def write_theme(directory, text):
    (directory / "theme").mkdir()
    (directory / "theme" / "colors.toml").write_text(text)


class PaletteTests(unittest.TestCase):
    def test_reads_omarchy_colors(self):
        with tempfile.TemporaryDirectory() as directory:
            write_theme(Path(directory), 'mode = "light"\nbackground = "#eff1f5"\nforeground = "#4c4f69"\n'
                                         'accent = "#1e66f5"\nred = "#d20f39"\nyellow = "#df8e1d"\n')
            p = theme.load(Path(directory))
        self.assertEqual((p["mode"], p["bg"], p["text"], p["accent"]), ("light", "#eff1f5", "#4c4f69", "#1e66f5"))
        self.assertEqual((p["error"], p["modifier"]), ("#d20f39", "#df8e1d"))

    def test_missing_or_broken_theme_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(theme.load(Path(directory)))
            write_theme(Path(directory), 'background = "#000000"\n')
            self.assertIsNone(theme.load(Path(directory)))
            (Path(directory) / "theme" / "colors.toml").write_text('accent = "not a colour"')
            self.assertIsNone(theme.load(Path(directory)))

    def test_prefers_saturated_red_in_monochrome_themes(self):
        p = theme.palette(theme.DEFAULT | {"red": "#565d60", "bright_red": "#de6145"})
        self.assertEqual(p["error"], "#de6145")

    def test_default_palette_is_dark(self):
        p = theme.palette(theme.DEFAULT)
        self.assertEqual(p["mode"], "dark")
        self.assertIn(p["accent"], theme.css(p))

    @unittest.skipUnless(STOCK_THEMES.is_dir(), "Omarchy themes are not installed")
    def test_every_stock_theme_is_readable(self):
        for directory in sorted(STOCK_THEMES.iterdir()):
            with self.subTest(directory.name), tempfile.TemporaryDirectory() as temp:
                write_theme(Path(temp), (directory / "colors.toml").read_text())
                p = theme.load(Path(temp))
                self.assertIsNotNone(p)
                # Text drawn on highlighted keys must stay readable.
                self.assertGreaterEqual(theme.contrast(p["accent"], p["on_accent"]), 3)
                self.assertGreaterEqual(theme.contrast(p["error"], p["on_error"]), 3)


class FontTests(unittest.TestCase):
    def test_without_omarchy_uses_app_fonts(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(theme.fonts(Path(directory) / "missing"), theme.DEFAULT_FONTS)

    def test_omarchy_without_font_setting_uses_jetbrains_mono(self):
        with tempfile.TemporaryDirectory() as directory:
            fonts = theme.fonts(Path(directory), fontconfig_dir=Path(directory) / "fontconfig")
        self.assertEqual(fonts["ui"], theme.OMARCHY_FALLBACK_FONT)
        css = theme.css(theme.palette(theme.DEFAULT), fonts)
        self.assertIn('font-family: "JetBrainsMono Nerd Font", "JetBrains Mono";', css)

    @unittest.skipUnless(shutil.which("fc-list"), "fontconfig tools are not installed")
    def test_uses_omarchy_monospace_font_everywhere(self):
        listed = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout
        family = sorted(line.split(",")[0] for line in listed.splitlines() if line)[-1]
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "fonts.conf"
            config.write_text('<?xml version="1.0"?><fontconfig>'
                              '<include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
                              '<match target="pattern"><test name="family" qual="any"><string>monospace</string></test>'
                              f'<edit name="family" mode="prepend_first" binding="strong"><string>{family}</string></edit>'
                              '</match></fontconfig>')
            fonts = theme.fonts(Path(directory), config)
        self.assertEqual(fonts, {"ui": family, "mono": family})
        self.assertIn(f'font-family: "{family}"', theme.css(theme.palette(theme.DEFAULT), fonts))


class BundledFontTests(unittest.TestCase):
    def test_bundled_font_and_license_are_present(self):
        self.assertTrue(theme.BUNDLED_FONT.is_file())
        self.assertTrue((theme.BUNDLED_FONT.parent / "OFL.txt").is_file())

    def test_bundled_font_is_used_on_other_distros(self):
        # A plain fontconfig, without Omarchy's rules or a system JetBrains Mono.
        script = """
import gi
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0")
import theme
from gi.repository import Pango, PangoCairo
assert theme.register_bundled_font()
font_map = PangoCairo.FontMap.get_default()
description = Pango.FontDescription.from_string(theme.DEFAULT_FONTS["ui"] + " Bold 12")
print(font_map.load_font(font_map.create_context(), description).describe().get_family())
"""
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "fonts.conf"
            config.write_text(f'<?xml version="1.0"?><fontconfig><cachedir>{directory}</cachedir></fontconfig>')
            result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                                    cwd=Path(theme.__file__).parent,
                                    env=os.environ | {"FONTCONFIG_FILE": str(config)})
        if "No module named 'gi'" in result.stderr:
            self.skipTest("PyGObject is not installed")
        self.assertEqual(result.stdout.strip(), "JetBrains Mono", result.stderr)



def charset(font_file):
    ranges = subprocess.run(["fc-query", "--format=%{charset}\n", str(font_file)],
                            capture_output=True, text=True, check=True).stdout.split()
    covered = set()
    for item in ranges:
        start, _, end = item.partition("-")
        covered.update(range(int(start, 16), int(end or start, 16) + 1))
    return covered


@unittest.skipUnless(shutil.which("fc-query"), "fontconfig tools are not installed")
class GlyphTests(unittest.TestCase):
    """Symbols a font lacks are drawn from another font, which looks out of place."""
    symbols = sorted({c for c in (Path(theme.__file__).parent / "app.py").read_text(encoding="utf-8") if ord(c) > 127})

    def test_bundled_font_has_every_symbol(self):
        covered = charset(theme.BUNDLED_FONT)
        self.assertEqual([c for c in self.symbols if ord(c) not in covered], [])

    @unittest.skipUnless(shutil.which("omarchy"), "Omarchy is not installed")
    def test_every_omarchy_font_has_every_symbol(self):
        families = subprocess.run(["omarchy", "font", "list"], capture_output=True, text=True).stdout.split("\n")
        for family in filter(None, map(str.strip, families)):
            files = subprocess.run(["fc-list", f"{family}:style=Regular", "file"], capture_output=True,
                                   text=True).stdout.split()
            covered = set().union(*(charset(f.rstrip(":")) for f in files)) if files else set()
            with self.subTest(family):
                self.assertTrue(covered, "font files not found")
                self.assertEqual([c for c in self.symbols if ord(c) not in covered], [])


if __name__ == "__main__":
    unittest.main()
