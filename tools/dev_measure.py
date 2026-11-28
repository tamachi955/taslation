"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the kept sessions of developer measuring (`taslation.devmeasure`,
``<state dir>/dev-measure``), as the Menu's Developer measuring has them.

    python tools/dev_measure.py list                 # each session: its name, its pages, its size
    python tools/dev_measure.py delete NAME [NAME..] # those sessions deleted
    python tools/dev_measure.py delete --all         # all of them
    python tools/dev_measure.py open                 # the folder in Explorer
    python tools/dev_measure.py --state DIR ...      # another state folder
                                                     # (default: TASLATION_STATE_DIR, else ~/.taslation)

Nothing of a session is opened or read: its pages are counted by their files' names, its size by the files' sizes."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from taslation import devmeasure  # noqa: E402

PAGE_FILE = re.compile(r"p\d{4}\.json")


def listing(state_dir: Path) -> list[str]:
    out = []
    for folder in devmeasure.sessions(state_dir):
        files = [p for p in folder.rglob("*") if p.is_file()]
        pages = sum(1 for p in files if PAGE_FILE.fullmatch(p.name))
        size = sum(p.stat().st_size for p in files) / 2 ** 20
        out.append(f"{folder.name}  {pages} page(s)  {size:.1f} MB")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", help="the state folder (default: TASLATION_STATE_DIR, else ~/.taslation)")
    parser.add_argument("command", choices=("list", "delete", "open"))
    parser.add_argument("names", nargs="*")
    parser.add_argument("--all", action="store_true", help="delete: every session")
    args = parser.parse_args(argv)
    if args.state:
        state = Path(args.state)
    else:
        from taslation.config import default_state_dir

        state = default_state_dir()
    if args.command == "list":
        lines = listing(state)
        print("\n".join(lines) if lines else f"no session kept in {devmeasure.base_folder(state)}")
        return 0
    if args.command == "open":
        folder = devmeasure.base_folder(state)
        folder.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(folder))  # noqa: S606 - the developer's own folder
        else:
            print(folder)
        return 0
    if not args.all and not args.names:
        parser.error("delete: name the sessions, or --all")
    gone = devmeasure.delete_sessions(state, None if args.all else list(args.names))
    print(f"{gone} session(s) deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
