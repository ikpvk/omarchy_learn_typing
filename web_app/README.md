# Sofle Trainer (web app)

A typing trainer for the **Sofle** split keyboard. The text to type sits on top
and a drawing of the Sofle sits below it. The next key lights up, along with any
layer key or Shift you need to hold.

It is a single HTML file (`sofle-trainer.html`) with no build step, no server
and nothing to install from a package manager.

## Requirements

- A modern browser (Chromium, Chrome, Brave or Firefox).
- An internet connection is optional. Without one, the page falls back to
  system fonts and everything else still works.

## Run it

From this folder:

```sh
xdg-open sofle-trainer.html
```

Or open the file from your browser with **Ctrl+O**.

## Install as an app launcher (optional, Omarchy)

This adds **Sofle Trainer** to the app launcher (**Super + Space**). It opens in
its own window without browser tabs or an address bar, the same way Omarchy's
other web apps do. Run it from this folder:

```sh
cat > ~/.local/share/applications/"Sofle Trainer.desktop" <<EOF
[Desktop Entry]
Version=1.0
Name=Sofle Trainer
Comment=Typing trainer for the Sofle keyboard
Exec=omarchy-launch-webapp "file://$PWD/sofle-trainer.html"
Terminal=false
Type=Application
Icon=input-keyboard
StartupNotify=true
EOF
update-desktop-database ~/.local/share/applications
```

The launcher points at the file's current location. If you move this folder,
uninstall it and run the install step again from the new location.

`omarchy-launch-webapp` uses your default browser if it is Chromium-based
(Chrome, Brave, Edge, Vivaldi and others), and otherwise uses Chromium.

### Uninstall the launcher

```sh
omarchy-webapp-remove "Sofle Trainer"
```

Or remove it by hand:

```sh
rm ~/.local/share/applications/"Sofle Trainer.desktop"
update-desktop-database ~/.local/share/applications
```

### Remove the app completely

Uninstall the launcher (above), then delete this folder. Your practice stats are
stored by the browser (see [Your data](#your-data)). To clear them first, open
**Settings → Reset progress** in the app.

## How to use it

Click the page, then start typing. You must press the correct key to move on. A
wrong key flashes red and counts against your accuracy. Press **Esc** for a new
lesson.

| Mode | What it practices |
|---|---|
| **Learn** | Letters, a few at a time. You start with 6 letters. A new one unlocks when every unlocked letter reaches your target speed with few misses. Lessons focus on your weakest letter (the outlined one). Click a letter to skip ahead to it. |
| **Words** | Common English words, with optional capitals and punctuation. |
| **Sentences** | Full sentences. |
| **Symbols** | Numbers, brackets and code or terminal snippets, which is where layer keys get practiced. |

The line above the keyboard names the finger to use and anything to hold, for
example `( right ring + Shift (left pinky)` or `| hold LOWER (left thumb)`. The
keyboard switches to the layer the next character lives on. Use the layer
buttons on the right to look at any layer yourself.

### Settings

- **Target speed** is the speed (WPM) each letter must reach before the next
  one unlocks in Learn mode. The default is 30.
- **Next-key highlight** can be *Always*, *After a 1 second pause* or *Off*.
  Switch to the pause option once you're comfortable, so you recall keys before
  the app shows them.
- **Finger colors** tints each key by the finger that should press it.
- **Key labels** can be turned off to practice as if on blank keycaps.
- **Mistake heatmap** tints keys red by how often you miss them.

## Matching your own keymap

The app starts with the stock QMK Sofle keymap. If your firmware (QMK or Vial)
is different, edit the keymap in **Settings → Keymap** and click **Apply
keymap**. This only changes what the trainer shows; it does not reprogram the
keyboard.

Format:

```
[base]
`    1    2    3    4    5    |  6    7    8    9    0    `
ESC  q    w    e    r    t    |  y    u    i    o    p    BSPC
TAB  a    s    d    f    g    |  h    j    k    l    ;    '
LSFT z    x    c    v    b    |  n    m    ,    .    /    RSFT
GUI  ALT  CTRL LOWER ENT      |  SPC  RAISE CTRL ALT GUI

[lower]
...
```

- Each layer starts with a header such as `[base]` or `[lower]`. The first
  layer is the base layer.
- Each layer has 4 key rows (6 keys, an optional `|`, then 6 keys) and one thumb
  row (5 + 5).
- A single character is typed as-is. Letters are written in lowercase, and
  Shift is worked out automatically.
- Named keys: `SPC ENT BSPC TAB ESC LSFT RSFT CTRL ALT GUI DEL`, plus any other
  label you like (it is only displayed).
- `___` means "same as the base layer". `XXX` means no key.
- A key named after a layer (for example `LOWER` for `[lower]`) is the key that
  switches to it. The hint tells you to hold it for characters on that layer.
- Lines starting with `//` are comments.

If a character can be typed more than one way, the trainer prefers the base
layer, then base + Shift, then the other layers in order.

## Your data

Progress, settings and your keymap are saved in the browser's local storage on
this computer. Nothing is sent anywhere.

- Each browser keeps its own copy, and so does each way of opening the app.
  Opening the file directly and opening the published link have separate stats.
- Clearing the browser's site data erases your progress.

## Limitations

- The app only sees the characters your keyboard sends. It cannot tell which
  physical key or finger you used, or whether you really held the layer key.
- The keyboard drawing approximates the Sofle's shape (column stagger, rotated
  thumb keys, encoders). It is not an exact PCB outline.
- Only US-style Shift pairs are understood (for example `1` → `!`). Other OS
  layouts need their shifted characters written out on a layer.
