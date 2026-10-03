# Sofle Studio

A native, offline Linux typing trainer for a **58-key Sofle**. Practice text sits
above a split, column-staggered keyboard. The next character lights up its key;
Shift and symbol-layer buttons light up when a chord is needed.

![Sofle Studio typing trainer](preview.png)

## Install on Omarchy / Arch Linux

Sofle Studio runs directly from this folder. No build, Python virtual environment,
pip packages, background service or system-wide app installation is required.
It needs Python 3, GTK 4, PyGObject and Cairo.

1. Install any missing dependencies using the system package manager:

   ```sh
   sudo pacman -S --needed python gtk4 python-gobject python-cairo
   ```

   All four dependencies were already installed on the machine where this app
   was created. The command above skips packages that are already up to date.

2. Clone or download this repository and enter its folder.

3. Make the launcher executable if its permissions were lost when copying the
   project, then launch the app:

   ```sh
   chmod +x run.sh
   ./run.sh
   ```

Keep this folder in a location you can write to: saved settings and results are
stored alongside the app. You can move or copy the whole folder elsewhere and
run its `run.sh` there.

## Run after installation

From inside this folder:

```sh
./run.sh
```

The launcher locates the app relative to itself, so it also works when called
using an absolute path. Run it in your graphical desktop session; it needs an
available Wayland or X11 display. A KDE desktop is not required.

The app works offline. Dependency installation may need an internet connection.

## Match your keyboard

The starting **QWERTY** preset follows the stock QMK Sofle keymap: its base
layer, thumb keys, and LOWER layer as the symbol layer. An alternative Colemak-DH preset uses the same thumb keys and
symbol layer. If your firmware differs, edit the keymap to match it.

1. Choose **Edit keymap**.
2. Click a key on the diagram.
3. Enter its base character, shifted character and optional symbol-layer
   characters. Use `SPACE`, `ENTER` or `TAB` for those keys.
4. Set its role: Character, Shift, Layer, Backspace, Control, Alt or Super.
5. Use **Update selected key** before moving to another key, then **Save keymap**.

The editor changes the guide only; it does not reprogram your Sofle. Give a
tap-hold key the role corresponding to what you want to practise: Character for
its tap output, or a modifier role for its hold behavior. This first version
models one symbol layer and Shift; it does not model multiple layers, combos,
macros or simultaneous tap-and-hold roles. Its diagram approximates Sofle
geometry and includes decorative encoders, not an exact PCB rendering.

The app receives characters from Linux. It can guide the chord represented in
your keymap, but it cannot verify which physical switch, finger or firmware
layer produced a character. Configure your existing keyboard firmware to
produce the characters you expect; this app performs no layout emulation.

## Theme

On Omarchy, the app uses the colours of your current theme, including light
themes. Change the theme with `omarchy theme set` or the Omarchy menu, and the
open app restyles itself within a moment; no restart is needed.

All text uses your Omarchy font, as the Omarchy bar and menus do. Change it
with `omarchy font set` or the Omarchy menu, and the open app switches to it as
well.

The colours come from `~/.local/state/omarchy/current/theme/colors.toml`, and the
font is your system monospace font, which `omarchy font set` writes to
`~/.config/fontconfig/fonts.conf`. Until a font has been set there, the app uses
JetBrains Mono, Omarchy's default font.

Without Omarchy, the app uses its own dark theme and JetBrains Mono. The font
ships in `fonts/` and is loaded by the app itself, so nothing needs installing.
JetBrains Mono is licensed under the SIL Open Font License; see `fonts/OFL.txt`.

## Practice

- **Letters:** home, upper, lower row or all letters, using your saved keymap.
- **Words:** common English words.
- **Sentences:** capitalization and punctuation.
- **Symbols:** numbers, brackets and punctuation.
- **Custom text:** paste your own sentences or code, including line breaks.

Click the practice text and start typing. Mistakes stay on the current
character until you press it correctly. Your theme's red marks an error, its
accent colour marks the next key, and its yellow marks a modifier to hold.
Finger guidance is shown above the keyboard. Backspace rewinds one correctly
typed character. Press **Esc** to pause, **Ctrl+R** to restart, **Ctrl+Q** to
quit, and **Enter** after finishing to start the next lesson. Switching away
from the app pauses the timer automatically.

WPM is completed characters divided by five, per active minute. Accuracy counts
all character attempts, including retries. Backspacing does not erase error
history. The timer starts with your first character and stops on completion.

The keymap and the last 100 completed sessions are saved locally in
`.data/keymap.json` and `.data/history.json` beside the app. The history includes
per-character attempt counts for reviewing which letters need practice.

To preserve your keymap and progress when moving the app, copy the `.data`
folder too. It is hidden in most file managers. It is created when a keymap or
completed session is saved.

## Uninstall

There is no system-installed app, desktop launcher, service or server to remove.

1. Close Sofle Studio.
2. If you want to retain your keymap and history, copy the app folder's `.data`
   to a backup location before deleting the app folder.
3. Delete the app folder (this repository's folder), for example from its
   parent folder:

   ```sh
   rm -r -- learn_typing
   ```

   Replace `learn_typing` with the folder's name if you cloned it under another
   name.

This removes the source, launcher, tests, preview, caches and any saved settings
and history inside that folder. If you copied the app elsewhere, remove that
copy instead.

Python, GTK 4, PyGObject and Cairo are shared system dependencies. Removing this
app does not require removing them; other desktop applications may use them.

To reset only the app's saved settings and history while keeping the app, close
it and run this from inside the app folder:

```sh
rm -r -- .data
```

Run that reset command only if `.data` exists. The app will use the default
QWERTY keymap next time.

## Project files

```text
.
├── app.py                 GTK interface and native UI checks
├── trainer.py             Typing logic, lessons and keymaps
├── theme.py               Omarchy theme colours and font
├── fonts/                 Bundled JetBrains Mono and its licence
├── run.sh                 App launcher
├── README.md              Installation and usage instructions
├── preview.png            App screenshot
├── tests/                 Automated logic and theme tests
├── .github/workflows/     Runs the unit tests on GitHub Actions
├── .gitignore             Excludes local data and Python caches
└── .data/                 Local settings and history (created on use)
```

## Verify

From inside this folder:

```sh
python3 -m unittest discover -s tests -v
./run.sh --smoke-test
```

The smoke test opens a temporary window, exercises native UI flows, switches
between two temporary themes and two installed fonts to check live reloading,
saves previews to `/tmp/sofle-studio-preview.png` and
`/tmp/sofle-studio-theme-preview.png`, checks that the app uses almost no CPU
while idle, and exits. It uses temporary settings,
themes and font settings, and leaves your saved keymap and practice history and
your desktop theme and font alone.

If your screen is off or asleep, the compositor stops drawing windows, so the
smoke test skips its previews and says so; its other checks still run.

## Troubleshooting

- **Missing `gi`, GTK or Cairo:** install the dependencies listed above and run
  `./run.sh`. The launcher uses `/usr/bin/python3`, matching Arch's system
  packages, rather than a virtual environment or another Python installation.
- **No display / window does not open:** launch from a terminal in your Linux
  desktop session, rather than a headless SSH session.
- **Permission denied for `run.sh`:** run `chmod +x run.sh` in this folder.
- **Highlighted keys differ from your Sofle:** use **Edit keymap** to match your
  actual firmware mapping, especially thumb keys and symbols.
- **Settings or results cannot be saved:** check that this folder is writable
  by your user. Launch the app as your normal desktop user, without `sudo`.
