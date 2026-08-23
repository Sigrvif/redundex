# Redundex

Find redundant files in a folder: exact duplicates, images/videos with the same
content at different resolutions, re-encodes, video clips contained inside longer
videos, the same audio track in different formats, and same-content documents.
Review groups in a GUI and move what you don't want to a collection folder.
Nothing is ever deleted automatically.

## Install

Requires Python 3.10+.

```bash
python3 -m venv .venv
.venv/bin/pip install .
```

Optional external tools (enable more detectors):

| Tool | Enables | Install |
|---|---|---|
| ffmpeg + ffprobe | video detector, previews | https://ffmpeg.org (Windows: add to PATH) |
| fpcalc (chromaprint) | audio same-track detector | https://acoustid.org/chromaprint |

Without them Redundex still finds exact duplicates, image resizes/re-encodes,
and same-text documents (PyMuPDF is bundled via pip).

## GUI

```bash
redundex
```

Pick a folder, Scan, review groups (reason badges explain why files were grouped),
mark files (right-click a group for "mark all but ..." helpers), then
"Move marked..." to a collection folder. "Undo last move" restores the last batch.

## CLI

```bash
python -m redundex.core.cli scan /path/to/folder --cache /path/cache.sqlite --json
python -m redundex.core.cli move /path/to/collection file1 file2
python -m redundex.core.cli undo /path/to/collection
```

## Offline, self-contained bundles

Prebuilt bundles ship with ffmpeg, ffprobe, and fpcalc included — no Python, no
tools on PATH, no internet connection needed on the target machine:

- `redundex-0.2.0-linux-x86_64.tar.gz` — PyInstaller one-folder build with
  statically linked tools. Runs on any x86_64 Linux with glibc >= the build
  host's (Arch Linux included). Extract, then run
  `./redundex-0.2.0-linux-x86_64/redundex` (GUI) or
  `./redundex-0.2.0-linux-x86_64/redundex-cli scan ...`.
- `redundex-0.2.0-win64.zip` — portable folder with an embeddable Python,
  all dependencies, and bundled `ffmpeg.exe`/`ffprobe.exe`/`fpcalc.exe`.
  Extract anywhere, then double-click `Redundex.bat` (GUI) or run
  `RedundexCLI.bat scan ...` for the CLI.

Bundled tools are found automatically next to the executable; a custom tools
directory can be forced with the `REDUNDEX_TOOLS` environment variable. The
bundles contain GPL/LGPL builds of ffmpeg and chromaprint — keep that in mind
when redistributing.

## Fingerprints and caching

Perceptual fingerprints are cached in a SQLite database next to the scanned folder
(`.redundex.cache.sqlite`); unchanged files are never re-analyzed. Delete the file
to force a full rescan.

## Windows build (optional)

```bash
.venv/bin/pip install pyinstaller
.venv/bin/pyinstaller packaging/redundex.spec
```

Bundle `ffmpeg.exe`, `ffprobe.exe`, `fpcalc.exe` next to the built executable or
keep them on PATH. Note ffmpeg/fpcalc licensing (GPL/LGPL) when distributing.
