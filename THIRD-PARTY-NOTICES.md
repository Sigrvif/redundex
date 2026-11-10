# Third-Party Notices

Redundex is licensed under the [MIT License](LICENSE). It bundles and depends
on the third-party software listed below; each project keeps its own license,
and nothing here changes those terms.

## Bundled native tools (shipped in `_internal/tools/`)

| Tool | Version | License | Source |
|---|---|---|---|
| `ffmpeg`, `ffprobe` | 7.0.2-static (johnvansickle.com build) | GPL-2-or-later (GPL build: `--enable-gpl`, `--enable-version3`) | https://johnvansickle.com/ffmpeg/ (build scripts and source offer) · https://ffmpeg.org |
| `fpcalc` | 1.5.1 (Chromaprint) | LGPL-2.1-or-later | https://acoustid.org/chromaprint · https://github.com/acoustid/chromaprint |

License texts shipped in `licenses/`: `COPYING.GPLv2.txt`, `COPYING.GPLv3.txt`
(the ffmpeg build contains both GPL v2 and v3 components),
`COPYING.LGPL-2.1.txt`.

## Python dependencies

License texts for these ship inside each wheel's `.dist-info/licenses` in the
bundle's `_internal/` tree.

| Package | License | Source |
|---|---|---|
| PySide6 | LGPL-3.0 | https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| pypdfium2 | Apache-2.0 OR BSD-3-Clause | https://github.com/pypdfium2-team/pypdfium2 |
| py7zr | LGPL-2.1-or-later | https://github.com/miurahr/py7zr |
| numpy | BSD-3-Clause | https://numpy.org |
| Pillow | MIT-CMU | https://python-pillow.org |
| blake3 | Apache-2.0 OR MIT | https://github.com/BLAKE3-team/BLAKE3 |

PySide6 license texts are also shipped in `licenses/`: `COPYING.LGPL-3.txt`
(plus `COPYING.GPLv3.txt`, which LGPL-3 references).

## Development-only

pytest (MIT), pytest-qt (MIT) — used for testing, never bundled.
