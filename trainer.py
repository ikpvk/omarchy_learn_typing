"""Typing state and Sofle keymaps, independent of the desktop interface."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import random
import time


@dataclass
class Key:
    id: str
    hand: str
    row: int
    col: int
    base: str = ""
    shifted: str = ""
    layer: str = ""
    layer_shifted: str = ""
    role: str = "Character"

    @property
    def finger(self) -> str:
        if self.row == 4:
            return f"{self.hand} thumb"
        col = self.col if self.hand == "Left" else 5 - self.col
        return f"{self.hand} {['little finger', 'little finger', 'ring finger', 'middle finger', 'index finger', 'index finger'][col]}"


PRESETS = ("QWERTY", "Colemak-DH")
ROLES = ("Character", "Shift", "Layer", "Backspace", "Control", "Alt", "Super")


def preset(name: str = "QWERTY") -> list[Key]:
    if name not in PRESETS:
        raise ValueError("Unknown keymap preset")
    # Base and LOWER layers follow the stock QMK Sofle keymap.
    left = ["`12345", "\x1bqwert", "\tasdfg", "\x00zxcvb"]
    right = ["67890`", "yuiop\b", "hjkl;'", "nm,./\x00"]
    if name == "Colemak-DH":
        left[1:] = ["\x1bqwfpb", "\tarstg", "\x00zxcdv"]
        right[1:] = ["jluy;\b", "mneio'", "kh,./\x00"]
    shift = dict(zip("1234567890`-=[]\\;',./", "!@#$%^&*()~_+{}|:\"<>?"))
    layer_left = ["", "`12345", "\x00!@#$%", "\x00=-+{}"]
    layer_right = ["", "67890\x00", "^&*()|", "[];:\\\x00"]
    keys = []
    for hand, rows, layers in (("Left", left, layer_left), ("Right", right, layer_right)):
        for row, chars in enumerate(rows):
            for col, char in enumerate(chars):
                role = "Shift" if char == "\x00" else "Backspace" if char == "\b" else "Character"
                base = "" if char in "\x00\x1b\b" else char
                layer_char = layers[row][col] if len(layers[row]) > col else ""
                layer_char = "" if layer_char == "\x00" else layer_char
                keys.append(Key(f"{hand[0]}{row}{col}", hand, row, col, base,
                                base.upper() if base.isalpha() else shift.get(base, ""),
                                layer_char, shift.get(layer_char, ""), role=role))
        thumbs = [("", "Super"), ("", "Alt"), ("", "Control"), ("", "Layer"), ("\n", "Character")]
        if hand == "Right":
            thumbs = [(" ", "Character"), ("", "Layer"), ("", "Control"), ("", "Alt"), ("", "Super")]
        for col, (base, role) in enumerate(thumbs):
            keys.append(Key(f"{hand[0]}4{col}", hand, 4, col, base, role=role))
    return keys


@dataclass
class Guidance:
    key: Key
    modifiers: tuple[Key, ...]
    field: str


def resolve(keys: list[Key], char: str) -> Guidance | None:
    """Prefer a base key over a chord; guide modifiers on the other hand."""
    if not char:
        return None
    for field, required in (("base", ()), ("shifted", ("Shift",)),
                            ("layer", ("Layer",)), ("layer_shifted", ("Layer", "Shift"))):
        for key in keys:
            if key.role != "Character" or getattr(key, field) != char:
                continue
            modifiers = []
            for role in required:
                options = [k for k in keys if k.role == role]
                if not options:
                    break
                modifiers.append(next((k for k in options if k.hand != key.hand), options[0]))
            else:
                return Guidance(key, tuple(modifiers), field)
    return None


WORDS = "the and you that with this have from your for will can learn practice type hand home small split space right left every word letter make time good quiet focus slow calm clear soft light water river green blue day night look read write move just keep steady take each step build trust start again both fingers more there these when then while first next work well think feel find new way how now down up on in is it to of a at as be do go we my so".split()
SENTENCES = [
    "Take your time and let each finger find its key.",
    "A little practice every day builds a steady rhythm.",
    "Keep your hands relaxed as you type each word.",
    "The quiet river flows under the old stone bridge.",
    "Small steps can make a big difference over time.",
    "Your left and right hands work together on the split keyboard.",
    "Focus on accuracy and let your speed grow with practice.",
    "The morning light fills the room with a soft glow.",
]
MODES = ("Letters", "Words", "Sentences", "Symbols")
LESSONS = ("Home row", "Upper row", "Lower row", "All letters")


def make_lesson(mode: str, keys: list[Key], lesson: str = "Home row", rng=None) -> str:
    rng = rng or random
    if mode == "Letters":
        rows = {"Home row": (2,), "Upper row": (1,), "Lower row": (3,), "All letters": (1, 2, 3)}[lesson]
        chars = [k.base for k in keys if k.row in rows and k.role == "Character" and k.base.isalpha()]
        if not chars:
            raise ValueError("This row has no letters. Add letters in Edit keymap.")
        return " ".join("".join(rng.choice(chars) for _ in range(3)) for _ in range(18))
    if mode == "Words":
        available = [word for word in WORDS if all(resolve(keys, c) for c in word)]
        if not available:
            raise ValueError("Your keymap needs more letters for word practice.")
        return " ".join(rng.choice(available) for _ in range(22))
    if mode == "Sentences":
        available = [s for s in SENTENCES if all(resolve(keys, c) for c in s)]
        if not available:
            raise ValueError("Add uppercase letters and punctuation in Edit keymap, or use custom text.")
        return " ".join(rng.sample(available, min(2, len(available))))
    if mode == "Symbols":
        groups = ["()", "[]", "{}", "<>" , "12345", "67890", "=+", "-_", "/\\", ":;", "!@#", "$%&", "*^"]
        available = [g for g in groups if all(resolve(keys, c) for c in g)]
        if not available:
            raise ValueError("Add numbers or symbols in Edit keymap first.")
        return " ".join(rng.choice(available) for _ in range(22))
    raise ValueError("Unknown practice mode")


class Session:
    def __init__(self, target: str, clock=time.monotonic):
        if not target:
            raise ValueError("A lesson must contain text")
        self.target = target
        self.clock = clock
        self.index = 0
        self.attempts = 0
        self.correct_attempts = 0
        self.started = None
        self.finished = None
        self.paused_at = None
        self.pause_duration = 0.0
        self.per_key: dict[str, list[int]] = {}

    @property
    def complete(self):
        return self.index == len(self.target)

    @property
    def expected(self):
        return self.target[self.index] if not self.complete else ""

    def type(self, char: str) -> bool | None:
        if self.complete or self.paused_at is not None or len(char) != 1:
            return None
        now = self.clock()
        if self.started is None:
            self.started = now
        expected = self.expected
        self.attempts += 1
        counts = self.per_key.setdefault(expected, [0, 0])
        counts[0] += 1
        correct = char == expected
        if correct:
            self.correct_attempts += 1
            counts[1] += 1
            self.index += 1
            if self.complete:
                self.finished = now
        return correct

    def backspace(self):
        if not self.complete and self.paused_at is None:
            self.index = max(0, self.index - 1)

    def toggle_pause(self):
        if self.complete:
            return
        if self.paused_at is None:
            self.paused_at = self.clock()
        else:
            if self.started is not None:
                self.pause_duration += self.clock() - self.paused_at
            self.paused_at = None

    @property
    def elapsed(self):
        if self.started is None:
            return 0.0
        end = self.finished if self.finished is not None else self.paused_at if self.paused_at is not None else self.clock()
        return max(0.0, end - self.started - self.pause_duration)

    @property
    def accuracy(self):
        return 100 * self.correct_attempts / self.attempts if self.attempts else 100.0

    @property
    def wpm(self):
        return self.index / 5 / (self.elapsed / 60) if self.elapsed >= 1 else 0.0


def decode_value(value: str) -> str:
    aliases = {"SPACE": " ", "ENTER": "\n", "TAB": "\t"}
    result = aliases.get(value.upper(), value)
    if len(result) > 1:
        raise ValueError("Enter one character, SPACE, ENTER, TAB, or leave blank.")
    if result and ord(result) < 32 and result not in ("\n", "\t"):
        raise ValueError("Unsupported control character")
    return result


def encode_value(value: str) -> str:
    return {" ": "SPACE", "\n": "ENTER", "\t": "TAB"}.get(value, value)


def validate_keymap(raw) -> list[Key]:
    if not isinstance(raw, list) or len(raw) != 58:
        raise ValueError("A Sofle keymap must contain 58 keys")
    reference = {k.id: k for k in preset()}
    result = []
    seen = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Invalid key entry")
        key = Key(**entry)
        if key.id not in reference or key.id in seen:
            raise ValueError("Invalid or duplicate key position")
        original = reference[key.id]
        if (key.hand, key.row, key.col) != (original.hand, original.row, original.col):
            raise ValueError("Key geometry must match the Sofle")
        if key.role not in ROLES:
            raise ValueError("Unknown key role")
        for field in ("base", "shifted", "layer", "layer_shifted"):
            value = getattr(key, field)
            if not isinstance(value, str):
                raise ValueError("Key values must be text")
            decode_value(value if value not in (" ", "\t", "\n") else encode_value(value))
        seen.add(key.id)
        result.append(key)
    return result


def save_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def load_settings(path: Path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return validate_keymap(raw["keys"]), str(raw.get("name", "Custom Sofle"))[:50], None
    except FileNotFoundError:
        return preset(), "QWERTY", None
    except (ValueError, TypeError, KeyError, OSError) as exc:
        return preset(), "QWERTY", f"Saved keymap could not be loaded: {exc}. Using QWERTY; your file has not been changed."


def save_settings(path: Path, keys: list[Key], name: str):
    validate_keymap([asdict(k) for k in keys])
    save_json(path, {"version": 1, "name": name, "keys": [asdict(k) for k in keys]})
