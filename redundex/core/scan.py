import functools
import multiprocessing as mp
import struct
import time

from . import match as matching
from . import tools
from .detectors import exact
from .detectors.audio import fpcalc_job, match_audio, unpack_subs
from .detectors.docs import doc_job, match_docs
from .detectors.image import match_images
from .detectors.imagehash import from_signed64, image_job, to_signed64
from .detectors.video import coarse_signature, match_videos, video_job
from .hashstore import HashStore
from .pool import CancelledScan, run_jobs
from .types import FileKind, ScanConfig, ScanResult
from .walk import walk_folder


class _StageWriter:
    def __init__(self, store, entries, table, to_row, batch=100):
        self.store = store
        self.entries = entries
        self.table = table
        self.to_row = to_row
        self.batch = batch
        self.rows = []
        self._flushed = 0

    def add(self, result):
        self.rows.append(result)
        if len(self.rows) - self._flushed >= self.batch:
            self.flush()

    def flush(self):
        chunk = self.rows[self._flushed :]
        if not chunk:
            return
        self.store.put(self.table, [self.to_row(r) for r in chunk])
        subset = {r[0]: self.entries[r[0]] for r in chunk if r[0] in self.entries}
        if subset:
            self.store.save_files(subset)
        self._flushed += len(chunk)


class Scan:
    def __init__(self, root, config=None, progress_cb=None, cancel_event=None):
        self.root = str(root)
        self.config = config or ScanConfig()
        self.progress_cb = progress_cb
        self.cancel_event = cancel_event if cancel_event is not None else mp.Event()

    def _progress(self, stage, done, total):
        if self.progress_cb is not None:
            self.progress_cb(stage, done, total)

    def _cancelled(self):
        return self.cancel_event.is_set()

    def _pending(self, cached, wanted):
        limit = self.config.batch_limit
        missing = sorted(p for p in wanted if p not in cached)
        if limit:
            missing = missing[:limit]
        return missing

    def run(self) -> ScanResult:
        result = ScanResult()
        cfg = self.config
        try:
            store = HashStore(self.root, cfg.cache_path)
        except Exception as exc:
            result.problems.append({"path": "cache", "error": str(exc)})
            return result
        entries = None
        stages_done = False
        try:
            self._progress("walk", 0, 1)
            if self._cancelled():
                result.cancelled = True
                return result
            entries_list, problems = walk_folder(
                self.root, follow_symlinks=cfg.follow_symlinks
            )
            result.problems.extend(problems)
            entries = {e.path: e for e in entries_list}
            store.prune(set(entries))
            self._progress("walk", 1, 1)
            if self._cancelled():
                result.cancelled = True
                return result

            matches = []
            quality = {}
            meta = {}
            if cfg.exact:
                self._exact_stage(store, entries, matches, result)
            if self._cancelled():
                result.cancelled = True
                return result

            if cfg.image:
                self._image_stage(store, entries, matches, quality, meta, result)
                if self._cancelled():
                    result.cancelled = True
                    return result

            if cfg.video:
                self._video_stage(store, entries, matches, quality, meta, result)
                if self._cancelled():
                    result.cancelled = True
                    return result

            if cfg.audio:
                self._audio_stage(store, entries, matches, quality, meta, result)
                if self._cancelled():
                    result.cancelled = True
                    return result
            if cfg.docs:
                self._docs_stage(store, entries, matches, quality, meta, result)
                if self._cancelled():
                    result.cancelled = True
                    return result

            stages_done = True
            self._progress("group", 0, 1)
            result.meta = meta
            result.groups = matching.build_groups(entries, matches, quality)
            result.stats["groups"] = len(result.groups)
            self._progress("group", 1, 1)
            return result
        except CancelledScan:
            result.cancelled = True
            return result
        finally:
            if entries is not None and stages_done:
                store.save_files(entries)
            store.close()

    def _exact_stage(self, store, entries, matches, result):
        cfg = self.config
        t0 = time.monotonic()
        by_size = {}
        for e in entries.values():
            by_size.setdefault(e.size, []).append(e)
        wanted = {
            e.path
            for group in by_size.values()
            if len(group) > 1
            for e in group
        }
        wanted.update(e.path for e in entries.values() if e.kind is FileKind.ARCHIVE)
        cached = store.load("fp_exact", entries)
        missing = self._pending(cached, wanted)
        self._progress("exact", 0, max(len(missing), 1))
        writer = _StageWriter(
            store,
            entries,
            "fp_exact",
            lambda r: {"path": r[0], "file_hash": r[1], "listing_hash": r[2]},
        )
        try:
            _rows, problems = run_jobs(
                exact.hash_job,
                missing,
                workers=cfg.workers,
                cancel_event=self.cancel_event,
                progress_cb=lambda d, t: self._progress("exact", d, t),
                result_cb=writer.add,
            )
        finally:
            writer.flush()
        result.problems.extend(problems)
        fps = {p: (r["file_hash"], r["listing_hash"]) for p, r in cached.items()}
        fps.update({p: (fh, listing) for p, fh, listing in writer.rows})
        stage_matches = exact.match_from_fingerprints(fps)
        matches.extend(stage_matches)
        result.stats["exact"] = {
            "candidates": len(wanted),
            "cached": len(cached),
            "hashed": len(writer.rows),
            "matches": len(stage_matches),
            "seconds": round(time.monotonic() - t0, 3),
        }

    def _image_stage(self, store, entries, matches, quality, meta, result):
        cfg = self.config
        t0 = time.monotonic()
        images = [e for e in entries.values() if e.kind is FileKind.IMAGE]
        cached = store.load("fp_image", entries)
        missing = self._pending(cached, (e.path for e in images))
        self._progress("image", 0, max(len(missing), 1))
        writer = _StageWriter(
            store,
            entries,
            "fp_image",
            lambda r: {
                "path": r[0],
                "phash": to_signed64(r[1]),
                "dhash": to_signed64(r[2]),
                "width": r[3],
                "height": r[4],
            },
        )
        try:
            _rows, problems = run_jobs(
                image_job,
                missing,
                workers=cfg.workers,
                cancel_event=self.cancel_event,
                progress_cb=lambda d, t: self._progress("image", d, t),
                result_cb=writer.add,
            )
        finally:
            writer.flush()
        result.problems.extend(problems)
        fps = {
            p: (
                from_signed64(r["phash"]),
                from_signed64(r["dhash"]),
                r["width"],
                r["height"],
            )
            for p, r in cached.items()
        }
        fps.update({p: (ph, dh, w, h) for p, ph, dh, w, h in writer.rows})
        stage_matches = match_images(fps, cfg.image_threshold)
        matches.extend(stage_matches)
        for p, (_ph, _dh, w, h) in fps.items():
            quality[p] = float(w * h)
            meta[p] = {"width": w, "height": h}
        result.stats["image"] = {
            "files": len(images),
            "cached": len(cached),
            "hashed": len(writer.rows),
            "matches": len(stage_matches),
            "seconds": round(time.monotonic() - t0, 3),
        }

    def _video_stage(self, store, entries, matches, quality, meta, result):
        cfg = self.config
        t0 = time.monotonic()
        videos = [e for e in entries.values() if e.kind is FileKind.VIDEO]
        if tools.which("ffmpeg") is None or tools.which("ffprobe") is None:
            result.stats["video"] = {
                "files": len(videos),
                "hashed": 0,
                "matches": 0,
                "skipped": "ffmpeg/ffprobe not installed",
            }
            return
        cached = store.load("fp_video", entries)
        missing = self._pending(cached, (e.path for e in videos))
        self._progress("video", 0, max(len(missing), 1))

        def pack(hashes):
            return struct.pack(f"<{len(hashes)}Q", *hashes) if hashes else b""

        def to_row(r):
            p, duration, hashes, w, h = r
            return {
                "path": p,
                "duration": duration,
                "frame_hashes": pack(hashes),
                "coarse": pack(coarse_signature(hashes)),
                "width": w,
                "height": h,
                "audio_fp": None,
            }

        writer = _StageWriter(store, entries, "fp_video", to_row)
        job = functools.partial(
            video_job, interval=cfg.video_interval, max_frames=cfg.video_max_frames
        )
        try:
            _rows, problems = run_jobs(
                job,
                missing,
                workers=cfg.workers,
                cancel_event=self.cancel_event,
                progress_cb=lambda d, t: self._progress("video", d, t),
                result_cb=writer.add,
            )
        finally:
            writer.flush()
        result.problems.extend(problems)
        fps = {}
        for p, r in cached.items():
            n = len(r["frame_hashes"]) // 8
            hashes = list(struct.unpack(f"<{n}Q", r["frame_hashes"])) if n else []
            fps[p] = {
                "duration": r["duration"],
                "hashes": hashes,
                "width": r["width"],
                "height": r["height"],
            }
        for p, duration, hashes, w, h in writer.rows:
            fps[p] = {"duration": duration, "hashes": hashes, "width": w, "height": h}
        stage_matches = match_videos(
            fps,
            video_similarity=cfg.video_similarity,
            containment_similarity=cfg.containment_similarity,
            frame_threshold=cfg.video_frame_threshold,
        )
        matches.extend(stage_matches)
        for p, v in fps.items():
            quality[p] = float(v["width"] * v["height"] * max(v["duration"], 1.0))
            meta[p] = {
                "width": v["width"],
                "height": v["height"],
                "duration": v["duration"],
            }
        result.stats["video"] = {
            "files": len(videos),
            "cached": len(cached),
            "hashed": len(writer.rows),
            "matches": len(stage_matches),
            "pending_files": len(missing),
            "seconds": round(time.monotonic() - t0, 3),
        }

    def _audio_stage(self, store, entries, matches, quality, meta, result):
        cfg = self.config
        t0 = time.monotonic()
        targets = [
            e.path
            for e in entries.values()
            if e.kind in (FileKind.AUDIO, FileKind.VIDEO)
        ]
        if tools.which("fpcalc") is None:
            result.stats["audio"] = {
                "files": len(targets),
                "hashed": 0,
                "matches": 0,
                "skipped": "fpcalc not installed",
            }
            return
        cached = store.load("fp_audio", entries)
        missing = self._pending(cached, targets)
        self._progress("audio", 0, max(len(missing), 1))
        writer = _StageWriter(
            store,
            entries,
            "fp_audio",
            lambda r: {"path": r[0], "raw": r[1], "duration": r[2]},
        )
        try:
            _rows, problems = run_jobs(
                fpcalc_job,
                missing,
                workers=cfg.workers,
                cancel_event=self.cancel_event,
                progress_cb=lambda d, t: self._progress("audio", d, t),
                result_cb=writer.add,
            )
        finally:
            writer.flush()
        for prob in problems:
            if prob["path"] is None or entries[prob["path"]].kind is not FileKind.VIDEO:
                result.problems.append(prob)
        fps = {p: (unpack_subs(r["raw"]), r["duration"]) for p, r in cached.items()}
        fps.update(
            {p: (unpack_subs(raw), duration) for p, raw, duration in writer.rows}
        )
        stage_matches = match_audio(fps, ber_threshold=cfg.audio_ber)
        matches.extend(stage_matches)
        for p, (_subs, duration) in fps.items():
            if entries[p].kind is not FileKind.AUDIO:
                continue
            quality[p] = float(entries[p].size / max(duration, 1.0))
            meta[p] = {"duration": duration}
        result.stats["audio"] = {
            "files": len(targets),
            "cached": len(cached),
            "hashed": len(writer.rows),
            "matches": len(stage_matches),
            "seconds": round(time.monotonic() - t0, 3),
        }

    def _docs_stage(self, store, entries, matches, quality, meta, result):
        cfg = self.config
        t0 = time.monotonic()
        docs = [e for e in entries.values() if e.kind is FileKind.DOC]
        cached = store.load("fp_doc", entries)
        missing = self._pending(cached, (e.path for e in docs))
        self._progress("docs", 0, max(len(missing), 1))

        def to_row(r):
            p, th, ph = r
            return {
                "path": p,
                "text_hash": th,
                "page1_phash": to_signed64(ph) if ph is not None else None,
            }

        writer = _StageWriter(store, entries, "fp_doc", to_row)
        try:
            _rows, problems = run_jobs(
                doc_job,
                missing,
                workers=cfg.workers,
                cancel_event=self.cancel_event,
                progress_cb=lambda d, t: self._progress("docs", d, t),
                result_cb=writer.add,
            )
        finally:
            writer.flush()
        result.problems.extend(problems)
        fps = {}
        for p, r in cached.items():
            ph = from_signed64(r["page1_phash"]) if r["page1_phash"] is not None else None
            if r["text_hash"] or ph is not None:
                fps[p] = (r["text_hash"], ph)
        for p, th, ph in writer.rows:
            if th or ph is not None:
                fps[p] = (th, ph)
        stage_matches = match_docs(fps, phash_threshold=cfg.image_threshold)
        matches.extend(stage_matches)
        result.stats["docs"] = {
            "files": len(docs),
            "cached": len(cached),
            "hashed": len(writer.rows),
            "matches": len(stage_matches),
            "seconds": round(time.monotonic() - t0, 3),
        }
