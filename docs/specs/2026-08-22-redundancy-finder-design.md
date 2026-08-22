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

## External dependencies & capability check

| Tool / lib | Used by | If missing |
|---|---|---|
| pip: `blake3`, `Pillow` | exact pass; image decode | app cannot start (hard deps) |
| pip: `py7zr` | .7z content-listing hashes | .7z falls back to exact-hash only |
| pip: PyMuPDF | PDF text extraction + rendering | doc pass falls back to exact-hash only |
|---|---|---|
| `ffmpeg` + `ffprobe` (one install) | video pass (frame extraction, probe) | video pass disabled |
| `fpcalc` (chromaprint) | audio fingerprints (audio files + video audio tracks) | audio matching disabled |

pip dependencies are pinned in `pyproject.toml`; the three optional capabilities above
degrade individually as shown. Startup runs a capability check and reports which detectors are active and how to
install what's missing; the exact pass always works. Packaging bundles or documents
all of the above on both platforms.

## Architecture

New standalone project `redundex/`, its own git repository. The core package has
**no Qt dependency** so all detection logic is testable headless and runnable from CLI.

```
redundex/
├── redundex/
│   ├── core/
│   │   ├── scan.py         # folder walk, classification, detector dispatch
│   │   ├── hashstore.py    # SQLite fingerprint cache (single-writer, WAL)
│   │   ├── detectors/
│   │   │   ├── exact.py    # BLAKE3 exact duplicates (all file types)
│   │   │   ├── image.py    # pHash/dHash + BK-tree neighbor search
│   │   │   ├── video.py    # ffmpeg frame sampling → hash sequences, sliding-window match
│   │   │   ├── audio.py    # chromaprint (fpcalc) fingerprints
│   │   │   └── docs.py     # PDF normalized-text hash, rendered-pHash fallback
│   │   ├── match.py        # union-find grouping from pairwise matches
│   │   ├── trash.py        # move-to-collection, collision-safe rename, undo manifest
│   │   └── cli.py          # headless entry point
│   └── gui/
│       ├── main_window.py  # folder pick, options, progress, results
│       ├── results_model.py# virtualized grouping/sorting/filtering model
│       └── preview.py      # image preview, video thumbnail strip, side-by-side
├── tests/
└── pyproject.toml
```

**Execution model:** CPU-bound work (hashing, ffmpeg extraction) runs in a
`ProcessPoolExecutor` sized to the CPU count. Workers only compute and return
fingerprints/matches; the **coordinator in the main process is the sole writer** to
SQLite (batched inserts, one transaction per detector stage), eliminating
multi-process write contention. WAL mode is enabled so the GUI can read progress
concurrently. The GUI layer observes progress via a callback/queue and can cancel
cooperatively (workers check a cancel flag between work items; in-flight ffmpeg jobs
are terminated).

## Detection pipeline

### 1. Walk & classify
Recursive walk (subfolders on by default). Symlinks are skipped by default (option to
follow); directory cycles therefore cannot occur. Extension matching is
case-insensitive. On Windows, long paths are handled via the `\\?\` prefix when needed.
Files classified by extension/MIME into image / video / audio / document / archive /
other. Unreadable entries go to a "problems" list; the scan never aborts on a bad file.

### 2. Exact pass — every file type
Group by size, then BLAKE3 (only within equal-size groups) → exact duplicate groups.
Archives (.zip/.7z/.tar) additionally get a **content-listing hash** (sorted
name+size+CRC of members) so re-packed archives with identical contents match.

### 3. Image pass
64-bit pHash + dHash computed on a normalized 32×32 grayscale. All near-neighbor
queries answered by two BK-trees (one per hash type); a pair matches when **either**
tree yields Hamming distance ≤ threshold (default 8, configurable). This catches
resizes, re-compression, watermarks, minor edits. Results show resolution/format
side-by-side so "same content, lower resolution" is obvious. (BK-trees make image
search near-linear in practice at this scale; exact asymptotics depend on threshold.)

### 4. Video pass
Per video, `ffprobe` supplies duration/streams. Frame grid: sample at a fixed
fractional timeline — one frame every 5 s by default (configurable), capped at 200
frames; when the cap binds, the interval stretches so every video's fingerprint is a
uniform sampling of **its own timeline**. Each extracted 160×90 frame gets a 64-bit
pHash. Fingerprint = ordered frame-hash sequence + duration + audio fingerprint (if
`fpcalc` present).

**Matching semantics:**
- Two frames *agree* when Hamming distance ≤ 6 (configurable).
- Sequence similarity of two same-length sequences = fraction of agreeing frames.
- **Same content, different resolution/encode:** sequences are resampled onto a common
  timeline — nearest-neighbor frame selection at each common timeline position (no
  interpolation of hash values) — and compared position-aligned; match when
  similarity ≥ 0.90 (configurable).
- **Containment (clip inside a longer video):** *contiguous sliding-window (substring)*
  search — the shorter sequence is compared against every equal-length window of the
  longer one; a window with ≥ 0.85 agreeing frames is a match. The offset of the best
  window is reported ("clip appears inside X at 02:14"). Robust to offsets, intros,
  and slight trims at either end.
- **Candidate prefilter (bounds the O(V²) pair space):** every video also gets a
  *coarse signature* — 16 pHashes at fixed fractional positions (0/16…15/16 of the
  timeline), independent of duration and resolution. Each 64-bit coarse hash is split
  into 4 bands of 16 bits; videos sharing ≥ 2 identical bands (inverted index over
  band values) become candidate pairs. Only candidate pairs run the full
  resample-and-compare step. Containment checks additionally require the shorter
  video's duration ≤ the longer's duration (with 5% tolerance).

### 5. Audio pass
`fpcalc -raw` produces an array of 32-bit subfingerprints. Matching: decode both
arrays; align by sliding the shorter across the longer (allows intro/outro offsets);
per alignment offset compute the mean bit-error rate over aligned subfingerprint
pairs; best-offset BER ≤ 0.30 (configurable) is a *same-track* match. Duration-ratio
sanity (> 0.5) gates the comparison, and an inverted index over 16-bit bands of each
audio file's subfingerprints (candidate pairs share ≥ 2 bands, mirroring the video
prefilter) bounds the pair space before any sliding comparison. The same algorithm
links an audio file to a **video's audio track** (grouped with reason "same track"),
so a music file embedded in a video is still caught.

### 6. Document pass
PDFs (via PyMuPDF): extracted text normalized (case-, whitespace-,
punctuation-insensitive) and hashed → same-document-different-render matches.
Image-only/scanned PDFs (no extractable text) fall back to a rendered first-page
pHash matched with the image-pass threshold. Plain-text files (`.txt`, `.md`, source
code, etc.) use the normalized-text hash. Other formats (`.docx`, `.odt`) are
explicitly out of scope for v1 and match via exact hash only.

### 7. Grouping
Union-find merges all pairwise matches across every detector into final groups.
Each group entry records **why** files were grouped (exact / perceptual /
contained-in / same-track / same-text). **Redundancy size** = total group size minus
the *best* file's size, where best = highest quality proxy (images: pixel count;
videos: pixel count × duration; audio: bitrate; others: file size), ties broken by
newest mtime.

## Caching (critical for TB libraries)
SQLite, single-writer (coordinator), WAL mode. Schema sketch:
`files(path PRIMARY KEY, size, mtime, kind)`, `fp_exact(file_hash)`,
`fp_image(phash, dhash)`, `fp_video(duration, frame_hashes BLOB, coarse_bands BLOB)`,
`fp_audio(raw_fp BLOB)`, `fp_doc(text_hash, page1_phash NULL)`,
`fp_archive(listing_hash)` — all keyed through `files`. An entry is valid while
`(size, mtime)` is unchanged; anything else is recomputed. Entries for vanished
files are pruned each scan. The cache lives next to the scanned folder
(`.redundex.cache.sqlite`) or at a user-configured location; an advisory lock
(preferred-writer lock file) prevents two app instances from scanning into the same
cache concurrently.

## GUI design (PySide6)

- **Main window:** folder picker; detector toggles and thresholds; `Scan` button.
  During scan: per-stage progress (files found → exact → image → video → audio →
  docs), live group counter, cancel button.
- **Results view:** tree grouped by similarity group, backed by a **virtualized
  model** (rows materialized on demand) so 100k files stay responsive. Columns:
  name, folder, size, resolution/duration, modified date, match-reason badge.
  Sortable; filterable (e.g. only groups freeing > X MB). Group header shows
  redundancy size.
- **Preview pane:** image preview or video thumbnail strip (from cached sampled
  frames); two files in a group can be compared side-by-side.
- **Selection helpers (never automatic):** per-group one-click rules such as
  "mark all but largest / newest / highest resolution". The user reviews the resulting
  selection before any action.
- **Cleanup:** `Move marked to collection folder` moves selected files into a
  user-chosen trash-collection directory preserving relative subpaths
  (`collection/<original parent>/file`), collision-safe renaming (`name (2).ext`).
  A manifest is written per move batch (`undo_YYYYMMDD-NNN.json`, unique sequence
  number per batch) recording every (source → destination) pair. `Undo last move`
  reverses the newest batch; if an original path has been reoccupied since, the file
  restores to `restored/name (restored-N).ext` instead. If an undo itself fails
  midway, the manifest is rewritten with the remaining unrestored pairs so the undo
  can be re-run. The tool never deletes.

## Error handling
- Startup capability check (table above); missing tools disable only their detector.
- Corrupt/unreadable files are listed in a problems section of the results, never
  abort the scan.
- Moves are transactional per file: if a move fails mid-batch, already-moved files
  remain logged in the manifest and are undoable.

## Performance
- BLAKE3 (~1 GB/s/core); exact pass parallel and I/O-bound.
- Video pass is the bottleneck: parallel workers, low-res extraction, SQLite cache,
  and the band-index coarse prefilter before any full sequence comparison.
- Pre-scan estimate ("video analysis: ~2,400 videos, est. 40 min") so cost is visible
  before committing.

## Testing
- Synthetic fixtures: resized image, re-encoded video, trimmed clip, re-packed zip,
  same-text PDF, same audio in two formats.
- Property tests for the sliding-window matcher (offset/trim/noise robustness) and
  the audio BER alignment.
- `pytest-qt` smoke tests for the GUI; full headless test suite for core (no Qt).

## Packaging
- `pyproject.toml`, installable via pip; PySide6 and PyMuPDF from wheels.
- Windows: PyInstaller one-folder build; ffmpeg/fpcalc bundled (LGPL/GPL notes in
  README) or documented.
- Linux: pip install + system ffmpeg/fpcalc documented in README.

## Implementation phasing
The plan should sequence in phases, each independently verifiable:
1. Core skeleton + exact pass + SQLite cache + CLI.
2. Image pass + grouping + GUI shell (scan/progress/results/move).
3. Video pass (fingerprints, prefilter, sliding window, containment).
4. Audio pass + document pass.
5. Packaging (Windows/Linux builds).
