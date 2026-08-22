# Redundex — Media & File Redundancy Finder

**Date:** 2026-08-22
**Status:** Approved design, pre-implementation

## Problem

A folder-scanning GUI tool that finds not just exact duplicates but *all* redundant
files: images and videos with the same content at different resolutions or in
different formats, re-encodes, video clips contained inside longer videos, the same
audio track in different formats/bitrates, and documents with the same content.
Everything redundant or wasteful gets listed, reviewed, and moved (never auto-deleted)
to a trash collection folder.

## Goals

- Cross-platform desktop app: **Windows and Linux**.
- Handles **large media libraries**: 10k–100k files, multiple TB. Incremental rescans
  via fingerprint caching are a first-class requirement.
- Covers **all file types**: images, videos, audio, documents/PDFs, archives, and
  everything else at least via exact-hash matching.
- **Review + move** workflow: the user reviews groups and moves selected files to a
  collection folder. The tool never deletes and never selects files automatically.
- Python 3 + PySide6 (Qt) GUI, with a Qt-free core library usable headless from CLI.

## Non-goals

- Semantic/near-topic similarity ("images of beaches") — only *redundant* content.
- Automatic deletion or automatic selection-and-cleanup without user confirmation.
- Cloud/network storage scanning.

## Architecture

New standalone project `redundex/`, its own git repository. The core package has
**no Qt dependency** so all detection logic is testable headless and runnable from CLI.

```
redundex/
├── redundex/
│   ├── core/
│   │   ├── scan.py         # folder walk, classification, detector dispatch
│   │   ├── hashstore.py    # SQLite fingerprint cache
│   │   ├── detectors/
│   │   │   ├── exact.py    # BLAKE3 exact duplicates (all file types)
│   │   │   ├── image.py    # pHash/dHash + BK-tree neighbor search
│   │   │   ├── video.py    # ffmpeg frame sampling → hash sequences, subsequence match
│   │   │   ├── audio.py    # chromaprint (fpcalc) fingerprints
│   │   │   └── docs.py     # PDF normalized-text hash, rendered-pHash fallback
│   │   ├── match.py        # union-find grouping from pairwise matches
│   │   ├── trash.py        # move-to-collection, collision-safe rename, undo manifest
│   │   └── cli.py          # headless entry point
│   └── gui/
│       ├── main_window.py  # folder pick, options, progress, results
│       ├── results_model.py# grouping/sorting/filtering
│       └── preview.py      # image preview, video thumbnail strip, side-by-side
├── tests/
└── pyproject.toml
```

**Execution model:** CPU-bound work (hashing, ffmpeg extraction) runs in a
`ProcessPoolExecutor` sized to the CPU count. The GUI layer observes progress via a
callback/queue and can cancel cooperatively (workers check a cancel flag between work
items; in-flight ffmpeg jobs are terminated).

## Detection pipeline

### 1. Walk & classify
Recursive walk (subfolders on by default). Files classified by extension/MIME into
image / video / audio / document / archive / other. Unreadable entries go to a
"problems" list; the scan never aborts on a bad file.

### 2. Exact pass — every file type
Group by size, then BLAKE3 (only within equal-size groups) → exact duplicate groups.
Archives (.zip/.7z/.tar) additionally get a **content-listing hash** (sorted
name+size+CRC of members) so re-packed archives with identical contents match.

### 3. Image pass
64-bit pHash + dHash computed on a normalized 32×32 grayscale. All near-neighbor
queries answered by a **BK-tree** (no n² comparisons). Pairs with Hamming distance
≤ threshold (default 8, configurable) are matches. Catches resizes, re-compression,
watermarks, minor edits. Results show resolution/format side-by-side so
"same content, lower resolution" is obvious.

### 4. Video pass
Per video: extract ~1 frame every N seconds (default 5 s, configurable) via ffmpeg at
160×90, capped at ~200 frames. Fingerprint = ordered frame-hash sequence + duration
+ (optionally) the audio fingerprint.

Matching:
- **Same content, different resolution/encode:** aligned sequence comparison;
  match when similarity ≥ threshold (default 0.9, configurable).
- **Containment (clip inside a longer video):** the shorter video's hash sequence is
  searched as a subsequence of the longer one's via sliding window. Reports
  "clip appears inside X at 02:14". Robust to offsets, intros, slight trims.
- **Screening before heavy comparison:** duration-ratio plausibility check and a
  cheap coarse-hash prefilter decide whether the full subsequence comparison runs.

### 5. Audio pass
Chromaprint fingerprints via the `fpcalc` utility. Same track in MP3/FLAC/OGG matches
regardless of bitrate/container.

### 6. Document pass
PDFs: extracted text normalized (case-, whitespace-, punctuation-insensitive) and
hashed → same-document-different-render matches. Image-only/scanned PDFs fall back to
a rendered first-page pHash. Other documents (txt, etc.) use normalized-text hash.

### 7. Grouping
Union-find merges all pairwise matches across every detector into final groups.
Each group entry records **why** files were grouped (exact / perceptual / contained-in /
same-track / same-text) and a computed **redundancy size**: bytes freed if the single
best file in the group were kept.

## Caching (critical for TB libraries)
SQLite database keyed by `(path, size, mtime)`. Fingerprints, frame sequences, and
probe metadata are stored so rescans of unchanged libraries skip all heavy work.
The cache lives next to the scanned folder (e.g. `.redundex.cache.sqlite`) or at a
user-configured location. Cache entries for vanished files are pruned each scan.

## GUI design (PySide6)

- **Main window:** folder picker; detector toggles and thresholds; `Scan` button.
  During scan: per-stage progress (files found → exact → image → video → audio →
  docs), live group counter, cancel button.
- **Results view:** tree grouped by similarity group. Columns: name, folder, size,
  resolution/duration, modified date, match-reason badge. Sortable; filterable
  (e.g. only groups freeing > X MB). Group header shows redundancy size.
- **Preview pane:** image preview or video thumbnail strip (from cached sampled
  frames); two files in a group can be compared side-by-side.
- **Selection helpers (never automatic):** per-group one-click rules such as
  "mark all but largest / newest / highest resolution". The user reviews the resulting
  selection before any action.
- **Cleanup:** `Move marked to collection folder` moves selected files into a
  user-chosen trash-collection directory preserving relative subpaths
  (`collection/<original parent>/file`), collision-safe renaming (`name (2).ext`).
  An undo manifest (`undo_YYYYMMDD.json`) is written; `Undo last move` restores files.

## Error handling
- Startup capability check for `ffmpeg` and `fpcalc`. Missing tools produce a clear
  message (install instructions) and disable only the affected detectors; the exact
  pass always works.
- Corrupt/unreadable files are listed in a problems section of the results, never
  abort the scan.
- Moves are transactional per file: if a move fails mid-batch, already-moved files
  remain logged in the manifest and are undoable.

## Performance
- BLAKE3 (~1 GB/s/core); exact pass parallel and I/O-bound.
- Video pass is the bottleneck: parallel workers, low-res extraction, SQLite cache,
  and two-phase screening (metadata prefilter before subsequence matching).
- Pre-scan estimate ("video analysis: ~2,400 videos, est. 40 min") so cost is visible
  before committing.
- BK-tree keeps image comparisons ≈ O(n log n).

## Testing
- Synthetic fixtures: resized image, re-encoded video, trimmed clip, re-packed zip,
  same-text PDF, same audio in two formats.
- Property tests for the subsequence matcher (offset/trim/noise robustness).
- `pytest-qt` smoke tests for the GUI; full headless test suite for core (no Qt).

## Packaging
- `pyproject.toml`, installable via pip; PySide6 from wheels.
- Windows: PyInstaller one-folder build; ffmpeg/fpcalc either bundled or documented.
- Linux: pip install + system ffmpeg/fpcalc documented in README.
