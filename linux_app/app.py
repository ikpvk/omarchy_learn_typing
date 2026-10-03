#!/usr/bin/env python3
"""Sofle Studio: an offline GTK 4 typing trainer."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import tempfile
import traceback

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo
    import cairo
except (ImportError, ValueError) as exc:
    sys.exit(f"GTK 4 bindings are required: {exc}\nOn Arch/Omarchy: sudo pacman -S gtk4 python-gobject python-cairo")

from trainer import (Key, LESSONS, MODES, PRESETS, ROLES, Session, decode_value,
                     encode_value, load_settings, make_lesson, preset, resolve,
                     save_json, save_settings)

SMOKE_TEST = "--smoke-test" in sys.argv
if SMOKE_TEST:
    sys.argv.remove("--smoke-test")
DATA = Path(tempfile.mkdtemp(prefix="sofle-studio-test-")) if SMOKE_TEST else Path(__file__).resolve().parent / ".data"
BG = "#101519"
PANEL = "#192126"
KEY_BG = "#222d34"
BORDER = "#36444d"
TEXT = "#e1e9ec"
MUTED = "#8799a3"
TEAL = "#83e5c0"
AMBER = "#f4c784"
RED = "#ff8c91"

CSS = """
window { background: #101519; color: #e1e9ec; }
headerbar { background: #101519; box-shadow: none; border-bottom: 1px solid #28343b; }
label.title { font-size: 23px; font-weight: 800; letter-spacing: -0.5px; }
label.subtitle, label.muted { color: #8799a3; }
label.eyebrow { font-size: 11px; font-weight: bold; letter-spacing: 1.5px; color: #8799a3; }
label.metric { font-size: 28px; font-weight: 700; font-family: monospace; }
label.accent { color: #83e5c0; }
label.hint { font-size: 15px; }
label.error { color: #ff8c91; }
label.badge { background: #203a32; color: #83e5c0; padding: 5px 10px; border-radius: 15px; font-size: 11px; }
button, dropdown { background: #222d34; color: #e1e9ec; border: 1px solid #36444d; border-radius: 9px; box-shadow: none; min-height: 30px; }
button { padding: 5px 14px; }
button:hover { background: #30414a; }
button.primary { background: #83e5c0; color: #11241d; border-color: #83e5c0; font-weight: bold; }
button.primary:hover { background: #a2efd4; }
entry, textview { background: #192126; color: #e1e9ec; border-radius: 8px; }
entry { border: 1px solid #36444d; min-height: 32px; }
textview { padding: 16px; font-family: monospace; font-size: 16px; }
.card { background: #192126; border: 1px solid #2b3941; border-radius: 14px; padding: 14px 20px; }
.practice { background: #192126; border: 1px solid #2b3941; border-radius: 16px; }
separator { background: #2b3941; }
progressbar trough { background: #26333b; min-height: 4px; border-radius: 3px; }
progressbar progress { background: #83e5c0; min-height: 4px; border-radius: 3px; }
"""


def color(ctx, value, alpha=1):
    ctx.set_source_rgba(*(int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)), alpha)


def rounded(ctx, x, y, w, h, radius=10):
    r = min(radius, w / 2, h / 2)
    ctx.new_sub_path()
    for cx, cy, begin in ((x+w-r, y+r, -90), (x+w-r, y+h-r, 0),
                          (x+r, y+h-r, 90), (x+r, y+r, 180)):
        ctx.arc(cx, cy, r, math.radians(begin), math.radians(begin+90))
    ctx.close_path()


def text(ctx, value, x, y, size=15, tint=TEXT, center=False, mono=False, bold=False):
    layout = PangoCairo.create_layout(ctx)
    font = Pango.FontDescription("DejaVu Sans Mono" if mono else "DejaVu Sans")
    font.set_absolute_size(size * Pango.SCALE)
    if bold:
        font.set_weight(Pango.Weight.BOLD)
    layout.set_font_description(font)
    layout.set_text(value, -1)
    w, h = layout.get_pixel_size()
    color(ctx, tint)
    ctx.move_to(x - w / 2 if center else x, y - h / 2 if center else y)
    PangoCairo.show_layout(ctx, layout)
    ctx.new_path()
    return w, h


def label(value, cls=None, xalign=0):
    widget = Gtk.Label(label=value, xalign=xalign)
    if cls:
        widget.add_css_class(cls)
    return widget


def button(value, callback, primary=False):
    widget = Gtk.Button(label=value)
    if primary:
        widget.add_css_class("primary")
    widget.connect("clicked", callback)
    return widget


def display_char(char):
    return {" ": "Space", "\n": "Enter", "\t": "Tab"}.get(char, char)


def key_label(key, field="base"):
    if key.role != "Character":
        return {"Backspace": "⌫", "Control": "Ctrl", "Super": "Super", "Layer": "Layer"}.get(key.role, key.role)
    char = getattr(key, field)
    if not char:
        return "Esc" if key.id in ("L00", "L20") else "—"
    return display_char(char).upper() if char.isalpha() else display_char(char)


class Keyboard(Gtk.DrawingArea):
    def __init__(self, get_keys, get_guidance=lambda: None, select=None):
        super().__init__()
        self.get_keys, self.get_guidance, self.select = get_keys, get_guidance, select
        self.selected = None
        self.flash = None
        self.regions = []
        self.set_content_height(350)
        self.set_hexpand(True)
        self.set_draw_func(self.draw)
        if select:
            gesture = Gtk.GestureClick()
            gesture.connect("pressed", self.clicked)
            self.add_controller(gesture)
            self.set_cursor_from_name("pointer")

    def clicked(self, gesture, count, x, y):
        for key, cx, cy, size, angle in self.regions:
            dx, dy = x - cx, y - cy
            lx = dx * math.cos(angle) + dy * math.sin(angle)
            ly = -dx * math.sin(angle) + dy * math.cos(angle)
            if abs(lx) <= size / 2 and abs(ly) <= size / 2:
                self.selected = key.id
                self.select(key)
                self.queue_draw()
                return

    def draw(self, area, ctx, width, height):
        scale = min((width - 32) / 940, (height - 12) / 365)
        unit, size = 64 * scale, 55 * scale
        offset = (width - 940 * scale) / 2
        guidance = self.get_guidance()
        modifier_ids = {k.id for k in guidance.modifiers} if guidance else set()
        field = guidance.field if guidance else "base"
        shown = "layer" if field.startswith("layer") else "base"
        self.regions = []
        for key in self.get_keys():
            left = key.hand == "Left"
            origin = offset + (0 if left else 550 * scale)
            angle = 0.0
            if key.row < 4:
                stagger = [26, 15, 5, 0, 6, 12]
                column = key.col if left else 5 - key.col
                x = origin + key.col * unit + size/2
                y = 18*scale + key.row*unit + stagger[column]*scale + size/2
            else:
                thumb_col = key.col if left else 4-key.col
                thumb_x = [1, 2, 3, 4.1, 5.1][thumb_col]
                x = origin + (thumb_x if left else 5-thumb_x)*unit + size/2
                y = (284 + [0, 0, 0, 8, 29][thumb_col])*scale + size/2
                angle = math.radians([0, 0, 0, 12, 24][thumb_col] * (1 if left else -1))
            self.regions.append((key, x, y, size, angle))
            ctx.save()
            ctx.translate(x, y)
            ctx.rotate(angle)
            active = bool(guidance and guidance.key.id == key.id)
            modifier = key.id in modifier_ids
            selected = key.id == self.selected
            error = key.id == self.flash
            fill = RED if error else TEAL if active else "#463b2c" if modifier else KEY_BG
            outline = AMBER if modifier else TEAL if selected else BORDER
            rounded(ctx, -size/2, -size/2 + 3*scale, size, size, 9*scale)
            color(ctx, "#090e11")
            ctx.fill()
            rounded(ctx, -size/2, -size/2, size, size-3*scale, 9*scale)
            color(ctx, fill)
            ctx.fill_preserve()
            color(ctx, outline)
            ctx.set_line_width(2*scale if modifier or selected else scale)
            ctx.stroke()
            value = key_label(key, shown)
            if active:
                value = display_char(getattr(key, field))
                if len(value) == 1 and value.isalpha():
                    value = value.upper()
            text(ctx, value, 0, -2*scale, (12 if len(value) > 3 else 19)*scale,
                 "#13271f" if active or error else AMBER if modifier else TEXT,
                 center=True, bold=active or modifier)
            if key.base.lower() in ("f", "j") and key.row == 2 and shown == "base":
                color(ctx, "#13271f" if active else MUTED)
                ctx.set_line_width(2*scale)
                ctx.move_to(-5*scale, 15*scale)
                ctx.line_to(5*scale, 15*scale)
                ctx.stroke()
            ctx.restore()
        for cx in (offset + 425*scale, offset + 507*scale):
            ctx.new_path()
            color(ctx, BORDER)
            ctx.arc(cx, 172*scale, 16*scale, 0, math.tau)
            ctx.set_line_width(2*scale)
            ctx.stroke()
            color(ctx, MUTED)
            ctx.move_to(cx, 159*scale)
            ctx.line_to(cx, 165*scale)
            ctx.stroke()
        text(ctx, "L", offset + 200*scale, 5*scale, 10*scale, MUTED, center=True)
        text(ctx, "R", offset + 735*scale, 5*scale, 10*scale, MUTED, center=True)


class Practice(Gtk.DrawingArea):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.set_focusable(True)
        self.set_content_height(174)
        self.set_hexpand(True)
        self.set_draw_func(self.draw)
        self.add_css_class("practice")
        gesture = Gtk.GestureClick()
        gesture.connect("pressed", self.clicked)
        self.add_controller(gesture)
        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self.key_pressed)
        self.add_controller(controller)

    def clicked(self, *_):
        self.grab_focus()
        if self.owner.session.paused_at is not None:
            self.owner.session.toggle_pause()
        self.owner.refresh()

    def key_pressed(self, controller, keyval, keycode, state):
        session = self.owner.session
        if state & Gdk.ModifierType.CONTROL_MASK:
            if keyval in (Gdk.KEY_r, Gdk.KEY_R):
                self.owner.restart()
                return True
            return False
        if state & (Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SUPER_MASK):
            return False
        if keyval == Gdk.KEY_Escape:
            session.toggle_pause()
            self.owner.refresh()
            return True
        if keyval == Gdk.KEY_BackSpace:
            session.backspace()
            self.owner.error_active = False
            self.owner.last_error = ""
            self.owner.refresh()
            return True
        if session.complete:
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                self.owner.new_lesson()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            char = "\n"
        elif keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            if session.expected != "\t":
                return False
            char = "\t"
        else:
            codepoint = Gdk.keyval_to_unicode(keyval)
            if not codepoint or codepoint < 32:
                return False
            char = chr(codepoint)
        expected = session.expected
        correct = session.type(char)
        if correct is False:
            self.owner.last_error = f"Try {display_char(expected)!r} again — take your time."
            guidance = resolve(self.owner.keys, char)
            self.owner.keyboard.flash = guidance.key.id if guidance else None
            self.owner.error_active = True
            if self.owner.flash_timer:
                GLib.source_remove(self.owner.flash_timer)
            self.owner.flash_timer = GLib.timeout_add(250, self.owner.clear_flash)
        elif correct:
            self.owner.error_active = False
            self.owner.last_error = ""
            self.owner.keyboard.flash = None
            if session.complete:
                self.owner.record_session()
        self.owner.refresh()
        return True

    def draw(self, area, ctx, width, height):
        session = self.owner.session
        size = 23
        char_width, _ = text(ctx, "", 0, 0, size, mono=True)
        layout = PangoCairo.create_layout(ctx)
        font = Pango.FontDescription("DejaVu Sans Mono")
        font.set_absolute_size(size * Pango.SCALE)
        layout.set_font_description(font)
        layout.set_text("M", -1)
        char_width = layout.get_pixel_size()[0]
        columns = max(12, int((width - 64) / char_width))
        lines = []
        start = 0
        while start < len(session.target):
            end = min(start + columns, len(session.target))
            newline = session.target.find("\n", start, end)
            if newline >= 0:
                end = newline + 1
            elif end < len(session.target):
                space = session.target.rfind(" ", start + 1, end)
                if space > start:
                    end = space + 1
            lines.append((start, end))
            start = end
        current_line = next((i for i, (a, b) in enumerate(lines) if a <= session.index < b), len(lines)-1)
        first = max(0, current_line - 1)
        if first + 3 > len(lines):
            first = max(0, len(lines)-3)
        top = (height - min(3, len(lines))*37) / 2
        for line_no, (a, b) in enumerate(lines[first:first+3]):
            y = top + line_no*37
            for offset, i in enumerate(range(a, b)):
                x = 32 + offset*char_width
                char = session.target[i]
                show = {"\n": "↵", "\t": "⇥"}.get(char, char)
                tint = TEAL if i < session.index else MUTED
                if i == session.index:
                    rounded(ctx, x-1, y-2, char_width+2, 32, 4)
                    color(ctx, RED if self.owner.error_active else TEAL)
                    ctx.fill()
                    tint = "#11241d"
                    if char == " ":
                        show = "·"
                text(ctx, show, x, y, size, tint, mono=True)
        if session.paused_at is not None:
            rounded(ctx, 1, 1, width-2, height-2, 15)
            color(ctx, BG, .93)
            ctx.fill()
            text(ctx, "Paused", width/2, height/2-14, 25, TEAL, center=True, bold=True)
            text(ctx, "Click here or press Esc to continue", width/2, height/2+21, 14, MUTED, center=True)


class TrainerWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Sofle Studio")
        self.set_default_size(1120, 830)
        self.set_size_request(1000, 760)
        self.keys, self.keymap_name, load_error = load_settings(DATA / "keymap.json")
        self.session = Session(make_lesson("Letters", self.keys))
        self.last_error = load_error or ""
        self.error_active = False
        self.flash_timer = None
        self.dialog_open = False
        self.auto_paused = False
        self.custom_target = None
        self.history = []
        try:
            raw = json.loads((DATA / "history.json").read_text())
            if isinstance(raw, list):
                self.history = [entry for entry in raw if isinstance(entry, dict) and isinstance(entry.get("wpm"), (int, float))][-100:]
        except (OSError, ValueError):
            pass

        header = Gtk.HeaderBar()
        brand = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        brand.append(label("Sofle Studio", "title"))
        brand.append(label("Find your rhythm, one key at a time.", "subtitle"))
        header.set_title_widget(brand)
        header.pack_start(label("SOFLE / 58", "badge"))
        header.pack_end(label("OFFLINE", "badge"))
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        for setter in (root.set_margin_start, root.set_margin_end, root.set_margin_top, root.set_margin_bottom):
            setter(24)
        self.set_child(root)

        toolbar = Gtk.Box(spacing=10)
        self.mode = Gtk.DropDown.new_from_strings(MODES)
        self.mode.set_tooltip_text("Choose what to practise")
        self.lesson = Gtk.DropDown.new_from_strings(LESSONS)
        self.lesson.set_tooltip_text("Letters to practise on your keymap")
        toolbar.append(self.mode)
        toolbar.append(self.lesson)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)
        toolbar.append(button("Custom text", self.open_custom))
        toolbar.append(button("Edit keymap", self.open_editor))
        toolbar.append(button("Restart", lambda *_: self.restart()))
        self.next_button = button("New lesson →", lambda *_: self.new_lesson(), True)
        toolbar.append(self.next_button)
        root.append(toolbar)

        stats = Gtk.Box(spacing=12, homogeneous=True)
        self.metrics = {}
        for name, initial in (("SPEED / WPM", "0"), ("ACCURACY", "100%"), ("TIME", "0:00"), ("PROGRESS", "0 / 71")):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            box.add_css_class("card")
            box.append(label(name, "eyebrow"))
            value = label(initial, "metric")
            if name == "SPEED / WPM":
                value.add_css_class("accent")
            box.append(value)
            self.metrics[name] = value
            stats.append(box)
        root.append(stats)

        section = Gtk.Box(spacing=10)
        self.lesson_title = label("HOME ROW", "eyebrow")
        section.append(self.lesson_title)
        self.status = label("Start typing when you’re ready.", "muted")
        self.status.set_hexpand(True)
        self.status.set_xalign(1)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        section.append(self.status)
        root.append(section)
        self.practice = Practice(self)
        root.append(self.practice)
        self.progress = Gtk.ProgressBar()
        root.append(self.progress)

        guidance_box = Gtk.Box(spacing=12)
        guidance_box.append(label("NEXT KEY", "eyebrow"))
        self.hint = label("", "hint")
        self.hint.set_hexpand(True)
        guidance_box.append(self.hint)
        self.layer_badge = label("BASE", "badge")
        guidance_box.append(self.layer_badge)
        root.append(guidance_box)
        self.keyboard = Keyboard(lambda: self.keys, lambda: resolve(self.keys, self.session.expected))
        self.keyboard.set_vexpand(True)
        root.append(self.keyboard)

        footer = Gtk.Box(spacing=12)
        self.map_label = label("", "muted")
        self.map_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.map_label.set_max_width_chars(25)
        footer.append(self.map_label)
        legend = label("● Next key    ● Hold modifier", "muted")
        legend.set_markup('<span foreground="#83e5c0">●</span> Next key    <span foreground="#f4c784">●</span> Hold modifier')
        legend.set_hexpand(True)
        legend.set_xalign(.5)
        footer.append(legend)
        footer.append(label("Esc pause  ·  Ctrl+R restart", "muted"))
        root.append(footer)
        self.mode.connect("notify::selected", self.selection_changed)
        self.lesson.connect("notify::selected", self.selection_changed)
        self.connect("notify::is-active", self.activation_changed)
        self.connect("close-request", self.closing)
        self.tick_id = GLib.timeout_add(250, self.tick)
        self.refresh()
        GLib.idle_add(self.practice.grab_focus)

    def closing(self, *_):
        GLib.source_remove(self.tick_id)
        if self.flash_timer:
            GLib.source_remove(self.flash_timer)
        return False

    def activation_changed(self, *_):
        if self.dialog_open:
            return
        if not self.is_active() and self.session.paused_at is None and not self.session.complete:
            self.session.toggle_pause()
            self.auto_paused = True
        elif self.is_active() and self.auto_paused:
            if self.session.paused_at is not None:
                self.session.toggle_pause()
            self.auto_paused = False
        self.refresh()

    def clear_flash(self):
        self.keyboard.flash = None
        self.flash_timer = None
        self.keyboard.queue_draw()
        return False

    def tick(self):
        self.update_metrics()
        return True

    def update_metrics(self):
        session = self.session
        self.metrics["SPEED / WPM"].set_text(str(round(session.wpm)))
        self.metrics["ACCURACY"].set_text(f"{session.accuracy:.0f}%")
        seconds = int(session.elapsed)
        self.metrics["TIME"].set_text(f"{seconds//60}:{seconds%60:02}")
        self.metrics["PROGRESS"].set_text(f"{session.index} / {len(session.target)}")
        self.progress.set_fraction(session.index / len(session.target))

    def refresh(self):
        self.update_metrics()
        session = self.session
        guidance = resolve(self.keys, session.expected)
        if session.complete:
            self.status.set_text(self.last_error or "Complete! Press Enter for your next lesson.")
            self.hint.set_text(f"Nice work. {session.wpm:.0f} WPM · {session.accuracy:.0f}% accuracy")
        elif session.paused_at is not None:
            self.status.set_text("Paused")
            self.hint.set_text("Your practice will continue where you left off.")
        else:
            self.status.set_text(self.last_error or ("Start typing when you’re ready." if session.started is None else "Accuracy first. Speed will follow."))
            if guidance:
                chord = " + ".join([k.role for k in guidance.modifiers] + [display_char(session.expected)])
                self.hint.set_text(f"{chord}  ·  {guidance.key.finger}")
            else:
                self.hint.set_text(f"{display_char(session.expected)}  ·  Add this character in Edit keymap to see its key.")
        self.status.remove_css_class("error")
        if self.last_error:
            self.status.add_css_class("error")
        self.layer_badge.set_text("SYMBOL LAYER" if guidance and guidance.field.startswith("layer") else "BASE + SHIFT" if guidance and guidance.field == "shifted" else "BASE")
        self.map_label.set_text(f"{self.keymap_name} · Sofle 58")
        self.practice.queue_draw()
        self.keyboard.queue_draw()

    def selection_changed(self, *_):
        self.custom_target = None
        self.lesson.set_visible(MODES[self.mode.get_selected()] == "Letters")
        self.new_lesson()

    def reset_to(self, target):
        self.session = Session(target)
        self.last_error = ""
        self.error_active = False
        self.keyboard.flash = None
        self.auto_paused = False
        self.refresh()
        GLib.idle_add(self.practice.grab_focus)

    def restart(self):
        self.reset_to(self.session.target)

    def new_lesson(self):
        mode = MODES[self.mode.get_selected()]
        lesson = LESSONS[self.lesson.get_selected()]
        try:
            target = self.custom_target or make_lesson(mode, self.keys, lesson)
        except ValueError as exc:
            self.last_error = str(exc)
            self.refresh()
            return
        self.lesson_title.set_text("CUSTOM TEXT" if self.custom_target else lesson.upper() if mode == "Letters" else mode.upper())
        self.reset_to(target)

    def record_session(self):
        session = self.session
        self.history.append({"date": datetime.now(timezone.utc).isoformat(),
                             "mode": "Custom" if self.custom_target else MODES[self.mode.get_selected()],
                             "keymap": self.keymap_name, "characters": len(session.target),
                             "wpm": round(session.wpm, 2), "accuracy": round(session.accuracy, 2),
                             "seconds": round(session.elapsed, 2), "per_key": session.per_key})
        self.history = self.history[-100:]
        try:
            save_json(DATA / "history.json", self.history)
        except OSError as exc:
            self.last_error = f"Practice finished, but results could not be saved: {exc}"

    def dialog(self, title, width=700, height=400):
        self.dialog_open = True
        was_paused = self.session.paused_at is not None
        if not was_paused:
            self.session.toggle_pause()
        dialog = Gtk.Window(title=title, transient_for=self, modal=True)
        dialog.set_default_size(width, height)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for setter in (box.set_margin_start, box.set_margin_end, box.set_margin_top, box.set_margin_bottom):
            setter(24)
        dialog.set_child(box)
        def closed(*_):
            self.dialog_open = False
            if not was_paused and self.session.paused_at is not None:
                self.session.toggle_pause()
            self.refresh()
            GLib.idle_add(self.practice.grab_focus)
            return False
        dialog.connect("close-request", closed)
        return dialog, box

    def open_custom(self, *_):
        dialog, box = self.dialog("Practise your own text")
        box.append(label("Words that matter to you", "title"))
        note = label("Paste a paragraph, symbols, or code. Line breaks are practised with Enter.", "muted")
        note.set_wrap(True)
        box.append(note)
        view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        view.get_buffer().set_text(self.custom_target or "The quick brown fox jumps over the lazy dog.")
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(view)
        box.append(scroll)
        error = label("", "error")
        error.set_wrap(True)
        box.append(error)
        row = Gtk.Box(spacing=12)
        row.append(button("Cancel", lambda *_: dialog.close()))
        def apply(*_):
            buffer = view.get_buffer()
            content = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True).replace("\r\n", "\n").replace("\r", "\n")
            if not content.strip():
                error.set_text("Add some text to practise.")
                return
            if len(content) > 10000:
                error.set_text("Use up to 10,000 characters per lesson.")
                return
            invalid = [c for c in content if ord(c) < 32 and c not in ("\n", "\t")]
            if invalid:
                error.set_text("Remove unsupported control characters from the text.")
                return
            self.custom_target = content
            self.lesson_title.set_text("CUSTOM TEXT")
            self.reset_to(content)
            missing = sorted({display_char(c) for c in content if not resolve(self.keys, c)})
            if missing:
                self.last_error = "Missing from guide: " + ", ".join(missing[:8]) + ". Add them in Edit keymap."
            dialog.close()
        row.append(button("Start practising →", apply, True))
        box.append(row)
        dialog.present()

    def open_editor(self, *_):
        dialog, box = self.dialog("Your Sofle keymap", 1020, 780)
        draft = deepcopy(self.keys)
        box.append(label("Make the guide match your Sofle", "title"))
        note = label("Click a key to edit it. These changes update the trainer’s guide, not your keyboard firmware.", "muted")
        note.set_wrap(True)
        box.append(note)
        row = Gtk.Box(spacing=12)
        name = Gtk.Entry(text=self.keymap_name, hexpand=True)
        name.set_placeholder_text("Name your keymap")
        row.append(name)
        choice = Gtk.DropDown.new_from_strings(PRESETS)
        row.append(choice)
        fields = {}
        selected = [draft[0]]
        error = label("", "error")
        error.set_wrap(True)
        title = label("", "hint")
        def select(key):
            selected[0] = key
            title.set_text(f"{key.hand} · row {key.row+1} · key {key.col+1} · {key.finger}")
            for field, entry in fields.items():
                entry.set_text(encode_value(getattr(key, field)))
            role.set_selected(ROLES.index(key.role))
            error.set_text("")
        keyboard = Keyboard(lambda: draft, select=select)
        keyboard.set_content_height(345)
        keyboard.selected = draft[0].id
        def reset(*_):
            draft[:] = preset(PRESETS[choice.get_selected()])
            name.set_text(PRESETS[choice.get_selected()])
            select(draft[0])
            keyboard.selected = draft[0].id
            keyboard.queue_draw()
        row.append(button("Load preset", reset))
        box.append(row)
        box.append(keyboard)
        box.append(title)
        grid = Gtk.Grid(column_spacing=14, row_spacing=7)
        for col, (field, heading) in enumerate((("base", "Base"), ("shifted", "With Shift"), ("layer", "Symbol layer"), ("layer_shifted", "Layer + Shift"))):
            grid.attach(label(heading, "eyebrow"), col, 0, 1, 1)
            entry = Gtk.Entry(hexpand=True)
            entry.set_width_chars(9)
            entry.set_placeholder_text("Character")
            fields[field] = entry
            grid.attach(entry, col, 1, 1, 1)
        grid.attach(label("KEY ROLE", "eyebrow"), 4, 0, 1, 1)
        role = Gtk.DropDown.new_from_strings(ROLES)
        grid.attach(role, 4, 1, 1, 1)
        box.append(grid)
        box.append(label("Use one character, SPACE, ENTER or TAB. Leave unused mappings blank.", "muted"))
        def update(*_):
            try:
                values = {field: decode_value(entry.get_text()) for field, entry in fields.items()}
            except ValueError as exc:
                error.set_text(str(exc))
                return
            for field, value in values.items():
                setattr(selected[0], field, value)
            selected[0].role = ROLES[role.get_selected()]
            error.set_text("Key updated. Save keymap to apply your changes.")
            keyboard.queue_draw()
        box.append(button("Update selected key", update))
        box.append(error)
        buttons = Gtk.Box(spacing=12)
        buttons.append(button("Cancel", lambda *_: dialog.close()))
        def save(*_):
            # Commit the currently displayed fields too, even without Update.
            try:
                values = {field: decode_value(entry.get_text()) for field, entry in fields.items()}
                for field, value in values.items():
                    setattr(selected[0], field, value)
                selected[0].role = ROLES[role.get_selected()]
                map_name = name.get_text().strip()[:50] or "Custom QWERTY"
                save_settings(DATA / "keymap.json", draft, map_name)
            except (ValueError, OSError) as exc:
                error.set_text(str(exc))
                return
            self.keys = deepcopy(draft)
            self.keymap_name = map_name
            self.new_lesson()
            dialog.close()
        buttons.append(button("Save keymap", save, True))
        box.append(buttons)
        select(draft[0])
        dialog.present()


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.local.SofleStudio.Test" if SMOKE_TEST else "io.local.SofleStudio")
        self.smoke_failed = False

    def do_activate(self):
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        window = self.get_active_window()
        if window is None:
            window = TrainerWindow(self)
        window.present()
        if SMOKE_TEST:
            GLib.timeout_add(600, self.smoke_checks, window)

    def smoke_checks(self, window):
        try:
            window.reset_to("fF [\n")
            window.session.paused_at = None
            # Go through the same input controller used by the desktop window.
            window.practice.key_pressed(None, Gdk.KEY_x, 0, Gdk.ModifierType(0))
            assert window.session.index == 0 and window.error_active
            window.practice.key_pressed(None, Gdk.KEY_f, 0, Gdk.ModifierType(0))
            assert window.session.index == 1
            assert window.layer_badge.get_text() == "BASE + SHIFT"
            window.practice.key_pressed(None, Gdk.KEY_F, 0, Gdk.ModifierType.SHIFT_MASK)
            window.practice.key_pressed(None, Gdk.KEY_space, 0, Gdk.ModifierType(0))
            assert window.layer_badge.get_text() == "SYMBOL LAYER"
            window.practice.key_pressed(None, Gdk.KEY_bracketleft, 0, Gdk.ModifierType(0))
            window.practice.key_pressed(None, Gdk.KEY_Return, 0, Gdk.ModifierType(0))
            assert window.session.complete and len(window.history) == 1
            assert (DATA / "history.json").exists()
            window.restart()
            assert window.session.index == 0
            for index in range(4):
                window.mode.set_selected(index)
                assert window.session.target
            window.open_custom()
            assert window.dialog_open
            GLib.timeout_add(350, self.smoke_editor, window)
        except Exception:
            traceback.print_exc()
            self.smoke_failed = True
            self.quit()
        return False

    def smoke_editor(self, window):
        try:
            self.close_dialogs(window)
            assert not window.dialog_open
            window.open_editor()
            assert window.dialog_open
            GLib.timeout_add(350, self.smoke_save_editor, window)
        except Exception:
            traceback.print_exc()
            self.smoke_failed = True
            self.quit()
        return False

    def smoke_save_editor(self, window):
        try:
            editor = next(w for w in Gtk.Window.get_toplevels() if w != window)
            self.save_snapshot(editor, "/tmp/sofle-studio-keymap-preview.png")
            # Check the edit controls and persist a changed thumb mapping.
            widgets = list(self.walk(editor))
            keyboard = next(w for w in widgets if isinstance(w, Keyboard))
            thumb = next(k for k in keyboard.get_keys() if k.id == "R40")
            keyboard.select(thumb)
            entries = [w for w in widgets if isinstance(w, Gtk.Entry)]
            assert len(entries) == 5
            entries[1].set_text("SPACE")
            save = next(w for w in widgets if isinstance(w, Gtk.Button) and w.get_label() == "Save keymap")
            save.emit("clicked")
            assert not window.dialog_open
            assert next(k for k in window.keys if k.id == "R40").base == " "
            assert (DATA / "keymap.json").exists()
            window.keys = preset()
            window.keymap_name = "QWERTY"
            window.mode.set_selected(0)
            window.lesson_title.set_text("HOME ROW")
            window.reset_to("fff jjj ddd kkk sss lll aaa ;;; fff jjj ddd kkk sss lll aaa ;;;")
            window.session.paused_at = None
            window.refresh()
            GLib.timeout_add(400, self.smoke_snapshot, window)
        except Exception:
            traceback.print_exc()
            self.smoke_failed = True
            self.quit()
        return False

    @staticmethod
    def walk(widget):
        yield widget
        child = widget.get_first_child()
        while child:
            yield from App.walk(child)
            child = child.get_next_sibling()

    @staticmethod
    def close_dialogs(window):
        for widget in Gtk.Window.get_toplevels():
            if widget != window:
                widget.close()

    def smoke_snapshot(self, window):
        try:
            self.save_snapshot(window, "/tmp/sofle-studio-preview.png")
            print("Native UI checks passed. Preview: /tmp/sofle-studio-preview.png", flush=True)
        except Exception:
            traceback.print_exc()
            self.smoke_failed = True
        self.quit()
        return False

    @staticmethod
    def save_snapshot(window, path):
        paintable = Gtk.WidgetPaintable.new(window)
        snapshot = Gtk.Snapshot.new()
        paintable.snapshot(snapshot, window.get_width(), window.get_height())
        node = snapshot.to_node()
        texture = window.get_native().get_renderer().render_texture(node, None)
        assert texture.save_to_png(path)


if __name__ == "__main__":
    app = App()
    status = app.run(sys.argv)
    raise SystemExit(1 if app.smoke_failed else status)
