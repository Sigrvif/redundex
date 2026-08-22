import json
import os
import shutil
import tempfile
import time


def _atomic_write_json(path, data):
    fd, tmp = tempfile.mkstemp(
        dir=os.path.dirname(path), prefix=".undo-tmp-", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _unique_dest(dest):
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    i = 2
    while True:
        candidate = f"{base} ({i}){ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def _manifest_path(collection_dir):
    today = time.strftime("%Y%m%d")
    seq = 1
    while True:
        p = os.path.join(collection_dir, f"undo_{today}-{seq:03d}.json")
        if not os.path.exists(p):
            return p
        seq += 1


def latest_manifest(collection_dir):
    if not os.path.isdir(collection_dir):
        return None
    manifests = sorted(
        f
        for f in os.listdir(collection_dir)
        if f.startswith("undo_") and f.endswith(".json")
    )
    return os.path.join(collection_dir, manifests[-1]) if manifests else None


def move_batch(paths, collection_dir, root=None):
    os.makedirs(collection_dir, exist_ok=True)
    manifest_path = _manifest_path(collection_dir)
    moved = []
    failed = []
    for src in paths:
        try:
            rel = os.path.relpath(src, root) if root else os.path.basename(src)
            if os.path.isabs(rel) or rel == ".." or rel.startswith(".." + os.sep):
                failed.append({"path": src, "error": "source outside root"})
                continue
            dest = os.path.join(collection_dir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            dest = _unique_dest(dest)
            shutil.move(src, dest)
            moved.append({"src": src, "dst": dest})
        except OSError as exc:
            failed.append({"path": src, "error": str(exc)})
    _atomic_write_json(
        manifest_path,
        {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "moves": moved},
    )
    return manifest_path, moved, failed


def _restore_target(collection_dir, src):
    d = os.path.join(collection_dir, "restored")
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, os.path.basename(src))
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    i = 1
    while True:
        candidate = f"{base} (restored-{i}){ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def undo_last(collection_dir):
    manifest_path = latest_manifest(collection_dir)
    if manifest_path is None:
        return {"restored": 0, "remaining": 0, "manifest": None}
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    remaining = []
    restored = 0
    for move in data.get("moves", []):
        src, dst = move["src"], move["dst"]
        try:
            if not os.path.exists(dst):
                continue
            target = src
            if os.path.exists(target):
                target = _restore_target(collection_dir, src)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(dst, target)
            restored += 1
        except OSError:
            remaining.append(move)
    if remaining:
        data["moves"] = remaining
        _atomic_write_json(manifest_path, data)
    else:
        os.remove(manifest_path)
    return {
        "restored": restored,
        "remaining": len(remaining),
        "manifest": manifest_path,
    }
