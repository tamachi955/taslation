"""Writing a file all or nothing, for every file TASlation keeps: caches, exports, notes, glossaries, the reader's
annotations and the legal notice's choices. Standard library only, so the lightest module can use it without
loading anything else."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

REPLACE_TRIES, REPLACE_PAUSE = 10, 0.05  # Windows refuses to replace a file another process is reading meanwhile


def write_atomic(path: Path | str, data: bytes) -> None:
    """*data* as the file at *path*, all or nothing, even when the computer stops halfway: written to a new file of
    its own beside it (so two processes saving at once never write into the same one, and no file of the reader's
    is taken for a temporary one), flushed to the disk, then put in place of the old one. While another process has
    the old file open (reading it, or a virus scanner), Windows refuses the swap, so it is tried again for a moment.
    The new file is readable by its owner only where the system has such permissions."""
    path = Path(path)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(REPLACE_TRIES):
            try:
                os.replace(name, path)
                return
            except PermissionError:
                if attempt == REPLACE_TRIES - 1:
                    raise
                time.sleep(REPLACE_PAUSE)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


__all__ = ["write_atomic"]
