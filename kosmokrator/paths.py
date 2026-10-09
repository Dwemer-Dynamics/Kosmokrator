"""Path containment helpers: keep every read/write inside an explicit root and refuse links."""

from __future__ import annotations

import contextlib
import os
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath

from .errors import KosmoError

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
# The manual forbids spaces/special characters in mod and image filenames (Filenames, p.3).
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")


def is_link(p: Path) -> bool:
    """True for symlinks and Windows reparse points (junctions)."""
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def resolve_workspace(root: str | os.PathLike[str] | None) -> Path:
    if not root:
        raise KosmoError("workspace_required", "An explicit workspace root is required (--workspace).")
    p = Path(root).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.is_dir():
        raise KosmoError("workspace_missing", f"Workspace root does not exist or is not a directory: {p}")
    return p.resolve()


def _within(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def contained(root: Path, candidate: str | os.PathLike[str], *, what: str = "path") -> Path:
    """Resolve candidate (absolute or root-relative) and require it inside root with no link components."""
    raw = Path(candidate)
    p = raw if raw.is_absolute() else root / raw
    lexical = Path(os.path.normpath(p))
    if not _within(root, lexical):
        raise KosmoError("path_escape", f"{what} escapes the allowed root", path=str(candidate), root=str(root))
    # Walk existing components below root and reject any symlink/junction.
    cur = root
    for part in lexical.relative_to(root).parts:
        cur = cur / part
        if is_link(cur):
            raise KosmoError("symlink_rejected", f"{what} traverses a symlink or junction", path=str(cur))
        if not cur.exists():
            break
    resolved = lexical.resolve()
    if not _within(root, resolved):
        raise KosmoError("path_escape", f"{what} resolves outside the allowed root", path=str(candidate))
    return lexical


def mod_relpath_problems(ref: str) -> list[str]:
    """Problems with a path string as written inside a .dm file (relative, forward slashes)."""
    problems: list[str] = []
    if not ref:
        return ["empty path"]
    if "\\" in ref:
        problems.append("backslash used; the manual requires forward slashes")
    if ref.startswith("/") or re.match(r"^[A-Za-z]:", ref):
        problems.append("absolute path; asset paths must be relative to the mod folder")
    parts = PurePosixPath(ref.replace("\\", "/")).parts
    if any(part == ".." for part in parts):
        problems.append("path traversal ('..') is not allowed")
    for part in parts:
        if part in ("/", "."):
            continue
        if part != ".." and not SAFE_NAME_RE.match(part):
            problems.append(f"name component {part!r} contains spaces or special characters")
    return problems


def exact_case_lookup(base: Path, ref: str) -> tuple[Path | None, str | None]:
    """Find ref under base requiring exact case for every component.

    Returns (path, None) on success, otherwise (None, reason). Rejects links.
    """
    cur = base
    for part in PurePosixPath(ref).parts:
        if part == ".":
            continue
        try:
            entries = os.listdir(cur)
        except (FileNotFoundError, NotADirectoryError):
            return None, "missing"
        if part not in entries:
            if any(e.lower() == part.lower() for e in entries):
                return None, "case_mismatch"
            return None, "missing"
        cur = cur / part
        if is_link(cur):
            return None, "symlink"
    if not cur.is_file():
        return None, "not_a_file"
    return cur, None


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via an exclusively created sibling temp file and os.replace so readers never see partial content.

    The temp name is random and created with O_EXCL (tempfile.mkstemp), so a preplanted file or link at a
    predictable name is never opened. Callers must have checked that ``path.parent`` is contained and not a link.
    """
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
