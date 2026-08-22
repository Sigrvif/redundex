import argparse
import dataclasses
import json
import sys

from .scan import Scan
from .types import ScanConfig


def _progress(stage, done, total):
    sys.stderr.write(f"\r{stage}: {done}/{total}")
    sys.stderr.flush()


def _format_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


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
    for det in ("image", "video", "audio", "docs"):
        p.add_argument(f"--no-{det}", action="store_true")
    args = parser.parse_args(argv)

    cfg = ScanConfig(cache_path=args.cache)
    for det in ("image", "video", "audio", "docs"):
        if getattr(args, f"no_{det}"):
            setattr(cfg, det, False)
    result = Scan(args.folder, cfg, progress_cb=_progress).run()
    sys.stderr.write("\n")

    if args.json:
        print(json.dumps(_result_to_dict(result), default=str))
        return 0

    total = sum(g.redundancy for g in result.groups)
    print(f"{len(result.groups)} groups, {_format_size(total)} redundant")
    for i, g in enumerate(result.groups, 1):
        reasons = ", ".join(sorted({m.reason.value for m in g.matches}))
        print(f"[{i}] {len(g.members)} files, {_format_size(g.redundancy)} redundant ({reasons})")
        for m in g.members:
            print(f"    {m.path}")
    if result.problems:
        print(f"{len(result.problems)} problems:")
        for p in result.problems:
            print(f"    {p}")
    if result.cancelled:
        print("scan cancelled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
