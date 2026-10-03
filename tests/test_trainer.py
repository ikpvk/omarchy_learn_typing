import json
from pathlib import Path
import random
import tempfile
import unittest

from trainer import (Session, decode_value, load_settings, make_lesson, preset,
                     resolve, save_settings, validate_keymap)


class GuidanceTests(unittest.TestCase):
    def test_qwerty_finger_and_base_guidance(self):
        keys = preset()
        guide = resolve(keys, "f")
        self.assertEqual(guide.key.id, "L24")
        self.assertEqual(guide.key.finger, "Left index finger")
        self.assertEqual(guide.modifiers, ())
        self.assertEqual(resolve(keys, " ").key.finger, "Right thumb")
        self.assertEqual(resolve(keys, "\n").key.id, "L44")
        self.assertEqual(resolve(keys, "\t").key.id, "L20")

    def test_qwerty_matches_stock_qmk_lower_layer(self):
        keys = preset()
        for char, key_id, field in (("=", "L31", "layer"), ("_", "L32", "layer_shifted"),
                                    ("|", "R25", "layer"), ("\\", "R34", "layer")):
            guide = resolve(keys, char)
            self.assertEqual((guide.key.id, guide.field), (key_id, field), char)

    def test_uppercase_uses_opposite_shift(self):
        guide = resolve(preset(), "F")
        self.assertEqual(guide.key.id, "L24")
        self.assertEqual(guide.field, "shifted")
        self.assertEqual(guide.modifiers[0].id, "R35")

    def test_symbol_layer_chord_and_shifted_layer(self):
        keys = preset()
        guide = resolve(keys, "[")
        self.assertEqual(guide.field, "layer")
        self.assertEqual(guide.modifiers[0].role, "Layer")
        keys[1].layer_shifted = "é"
        guide = resolve(keys, "é")
        self.assertEqual([k.role for k in guide.modifiers], ["Layer", "Shift"])

    def test_missing_modifier_does_not_claim_usable_chord(self):
        keys = [k for k in preset() if k.role != "Layer"]
        self.assertIsNone(resolve(keys, "["))

    def test_all_printable_ascii_has_guidance(self):
        for name in ("QWERTY", "Colemak-DH"):
            keys = preset(name)
            self.assertEqual(len(keys), 58)
            for char in map(chr, range(32, 127)):
                self.assertIsNotNone(resolve(keys, char), (name, char))

    def test_lessons_follow_custom_home_row(self):
        keys = preset()
        for key in keys:
            if key.row == 2 and key.role == "Character":
                key.base = "é"
        target = make_lesson("Letters", keys, rng=random.Random(1))
        self.assertEqual(set(target), {"é", " "})

    def test_generated_modes_only_use_mapped_characters(self):
        keys = preset()
        for mode in ("Letters", "Words", "Sentences", "Symbols"):
            target = make_lesson(mode, keys, rng=random.Random(1))
            self.assertTrue(all(resolve(keys, c) for c in target), mode)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.session = Session("a b\n", clock=lambda: self.now)

    def test_errors_do_not_advance_and_count_against_accuracy(self):
        self.assertFalse(self.session.type("z"))
        self.assertEqual(self.session.index, 0)
        self.assertTrue(self.session.type("a"))
        self.assertEqual(self.session.expected, " ")
        self.assertEqual(self.session.accuracy, 50)
        self.assertEqual(self.session.per_key["a"], [2, 1])

    def test_completion_freezes_time_and_wpm(self):
        self.session.type("a")
        self.now += 12
        for char in " b\n":
            self.session.type(char)
        self.assertTrue(self.session.complete)
        self.assertEqual(self.session.wpm, 4)
        self.now += 60
        self.assertEqual(self.session.elapsed, 12)
        self.assertIsNone(self.session.type("x"))

    def test_pause_excluded_from_elapsed(self):
        self.session.type("a")
        self.now += 5
        self.session.toggle_pause()
        self.now += 30
        self.assertEqual(self.session.elapsed, 5)
        self.assertIsNone(self.session.type(" "))
        self.session.toggle_pause()
        self.now += 5
        self.assertEqual(self.session.elapsed, 10)

    def test_pause_before_start_does_not_affect_clock(self):
        self.session.toggle_pause()
        self.now += 50
        self.session.toggle_pause()
        self.session.type("a")
        self.now += 5
        self.assertEqual(self.session.elapsed, 5)

    def test_backspace_rewinds_without_erasing_error_history(self):
        self.session.type("z")
        self.session.type("a")
        self.session.backspace()
        self.assertEqual(self.session.index, 0)
        self.assertEqual(self.session.accuracy, 50)
        self.session.backspace()
        self.assertEqual(self.session.index, 0)


class SettingsTests(unittest.TestCase):
    def test_custom_keymap_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keymap.json"
            keys = preset()
            keys[1].base = "é"
            save_settings(path, keys, "My Sofle")
            loaded, name, error = load_settings(path)
            self.assertEqual(name, "My Sofle")
            self.assertEqual(loaded, keys)
            self.assertIsNone(error)

    def test_corrupt_settings_fall_back_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keymap.json"
            content = '{"keys": [null]}'
            path.write_text(content)
            keys, name, error = load_settings(path)
            self.assertEqual(len(keys), 58)
            self.assertIsNotNone(error)
            self.assertEqual(path.read_text(), content)

    def test_duplicate_positions_rejected(self):
        from dataclasses import asdict
        raw = [asdict(k) for k in preset()]
        raw[-1] = raw[0]
        with self.assertRaises(ValueError):
            validate_keymap(raw)

    def test_entry_aliases_and_invalid_values(self):
        self.assertEqual(decode_value("SPACE"), " ")
        self.assertEqual(decode_value("Enter"), "\n")
        self.assertEqual(decode_value("TAB"), "\t")
        self.assertEqual(decode_value("é"), "é")
        with self.assertRaises(ValueError):
            decode_value("hello")


if __name__ == "__main__":
    unittest.main()
