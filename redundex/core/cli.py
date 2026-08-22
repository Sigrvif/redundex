import argparse
import dataclasses
import json
import os
import sys

from .scan import Scan
from .trash import move_batch, undo_last
from .types import ScanConfig, format_size


def _progress(stage, done, total):
    sys.stderr.write(f"\r{stage}: {done}/{total}")
    sys.stderr.flush()


def _result_to_dict(result):
    return {
        "groups": [
            {
                "members": [dataclasses.asdict(m) for m in g.members],
                "reasons": sorted({m.reason.value for m in g.matches}),
                "redundancy": g.redundancy,
            }
            for g in result.groups
        ],
        "problems": result.problems,
        "stats": result.stats,
        "cancelled": result.cancelled,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="redundex")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan", help="scan a folder for redundant files")
    p.add_argument("folder")
    p.add_argument("--cache", default=None)
    p.add_argument("--json", action="store_true")
    for det in ("exact", "image", "video", "audio", "docs"):
        p.add_argument(f"--no-{det}", action="store_true")
    p = sub.add_parser("move", help="move files to the collection folder")
    p.add_argument("collection")
    p.add_argument("paths", nargs="+")
    p = sub.add_parser("undo", help="undo the last move batch")
    p.add_argument("collection")
    args = parser.parse_args(argv)

    if args.cmd == "move":
        paths = [os.path.abspath(p) for p in args.paths]
        try:
            root = os.path.commonpath(paths)
        except ValueError:
            parser.error("paths do not share a common root")
        manifest, moved, failed = move_batch(paths, args.collection, root=root)
        print(f"moved {len(moved)} file(s), {len(failed)} failed")
        print(f"manifest: {manifest}")
        for f in failed:
            print(f"    failed: {f['path']}: {f['error']}")
        return 0 if not failed else 1

    if args.cmd == "undo":
        outcome = undo_last(args.collection)
        print(
            f"restored {outcome['restored']}, remaining {outcome['remaining']}"
        )
        return 0

    if args.cmd == "scan" and not os.path.isdir(args.folder):
        parser.error(f"folder does not exist: {args.folder}")

    cfg = ScanConfig(cache_path=args.cache)
    for det in ("exact", "image", "video", "audio", "docs"):
        if getattr(args, f"no_{det}"):
            setattr(cfg, det, False)
    result = Scan(args.folder, cfg, progress_cb=_progress).run()
    sys.stderr.write("\n")

    if args.json:
        print(json.dumps(_result_to_dict(result), default=str))
        return 0

    total = sum(g.redundancy for g in result.groups)
    print(f"{len(result.groups)} groups, {format_size(total)} redundant")
    for i, g in enumerate(result.groups, 1):
        reasons = ", ".join(sorted({m.reason.value for m in g.matches}))
        print(f"[{i}] {len(g.members)} files, {format_size(g.redundancy)} redundant ({reasons})")
        for m in g.members:
            print(f"    {m.path}")
    if result.problems:
        print(f"{len(result.problems)} problems:")
        for p in result.problems:
            print(f"    {p.get('path', '?')}: {p['error']}")
    if result.cancelled:
        print("scan cancelled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
