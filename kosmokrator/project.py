"""Project layout, metadata, guarded patching and ID reservation."""

from __future__ import annotations

import contextlib
import datetime as _dt
import difflib
import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from . import DEFAULT_TARGET_GAME_VERSION, MANUAL_VERSION, __version__
from . import commands as cmdreg
from .catalog import Catalog
from .dmparse import decode_dm, definitions, newline_style, parse
from .errors import KosmoError
from .paths import SLUG_RE, atomic_write_bytes, contained, is_link

META_FILE = "kosmokrator.json"
STATE_DIR = ".kosmokrator"
PROJECT_GITIGNORE = "# Kosmokrator local state (backups) and exports\n.kosmokrator/\nexports/\n"

# Documented modding ranges (Modding Number Limits, p.64, plus per-command text).
ID_KINDS: dict[str, dict[str, Any]] = {
    "monster": {"range": (5000, 8999), "catalog": "units", "openers": ("newmonster", "selectmonster"),
                "source": "#newmonster (p.13) says 5000-8999; Modding Number Limits (p.64) says 5000+ of 0-19999. "
                          "Kosmokrator allocates inside the narrower 5000-8999."},
    "site": {"range": (1700, 3999), "catalog": "sites", "openers": ("newsite", "selectsite"),
             "source": "#newsite (p.37) and Modding Number Limits (p.64): 1700-3999."},
    "nation": {"range": (150, 499), "catalog": "nations", "openers": ("selectnation",),
               "source": "#selectnation (p.41): 150+ creates new nations; Modding Number Limits (p.64): 0-499, 150+."},
    "weapon": {"range": (1000, 3999), "catalog": "weapons", "openers": ("newweapon", "selectweapon"),
               "source": "Modding Number Limits (p.64): weapons 0-3999, 1000+ for modding."},
    "armor": {"range": (400, 1999), "catalog": "armors", "openers": ("newarmor", "selectarmor"),
              "source": "Modding Number Limits (p.64): armor 0-1999, 400+ for modding."},
}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Project:
    workspace: Path
    slug: str
    root: Path
    meta_path: Path
    mod_dir: Path
    dm_path: Path
    state_dir: Path
    meta: dict[str, Any]

    def rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()


def _check_slug(slug: str) -> None:
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise KosmoError("bad_slug", "Slug must be 2-48 chars: lowercase letter first, then lowercase "
                                     "letters, digits or underscore (no spaces/special characters).", slug=slug)


def _paths(workspace: Path, slug: str) -> dict[str, Path]:
    root = contained(workspace, slug, what="project directory")
    return {
        "root": root,
        "meta": root / META_FILE,
        "mod_dir": root / "mod" / slug,
        "dm": root / "mod" / slug / f"{slug}.dm",
        "state": root / STATE_DIR,
    }


def open_project(workspace: Path, slug: str) -> Project:
    _check_slug(slug)
    p = _paths(workspace, slug)
    if not p["meta"].is_file():
        raise KosmoError("project_missing", f"No Kosmokrator project {slug!r} in workspace", path=str(p["root"]))
    for key in ("meta", "mod_dir", "dm", "state"):
        contained(workspace, p[key], what=key)
    return Project(workspace, slug, p["root"], p["meta"], p["mod_dir"], p["dm"], p["state"],
                   _read_meta(p["meta"], slug))


def _read_meta(meta_path: Path, slug: str) -> dict[str, Any]:
    if is_link(meta_path):
        raise KosmoError("symlink_rejected", "Project metadata is a symlink or junction", path=str(meta_path))
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise KosmoError("bad_metadata", f"Cannot read project metadata: {exc}") from exc
    if not isinstance(meta, dict) or meta.get("slug") != slug:
        raise KosmoError("bad_metadata", "Metadata slug does not match project directory",
                         slug=meta.get("slug") if isinstance(meta, dict) else None)
    return meta


def reload_meta(project: Project) -> None:
    """Re-read metadata from disk (call while holding project_lock before read-modify-write)."""
    contained(project.workspace, project.meta_path, what="meta")
    project.meta = _read_meta(project.meta_path, project.slug)


def state_subdir(project: Project, name: str) -> Path:
    """A directory under .kosmokrator/, created if needed; refuses links/junctions before and after creation."""
    contained(project.root, project.state_dir, what="state directory")
    sub = contained(project.root, project.state_dir / name, what=f"state {name} directory")
    sub.mkdir(parents=True, exist_ok=True)
    return contained(project.root, sub, what=f"state {name} directory")


def _clean_text_arg(value: str, what: str) -> str:
    if '"' in value or "\n" in value or "\r" in value:
        raise KosmoError("bad_text", f"{what} must not contain double quotes or newlines")
    return value


def create_project(workspace: Path, slug: str, name: str | None = None, description: str | None = None,
                   target_game_version: str | None = None) -> dict[str, Any]:
    _check_slug(slug)
    p = _paths(workspace, slug)
    if p["root"].exists() or is_link(p["root"]):
        raise KosmoError("project_exists", f"Refusing to overwrite existing path {p['root']}")
    name = _clean_text_arg(name or slug.replace("_", " ").title(), "name")
    description = _clean_text_arg(description or f"{name} (authored with Kosmokrator).", "description")
    os.mkdir(p["root"])  # exclusive: fails if it appeared meanwhile
    p["mod_dir"].mkdir(parents=True)
    (p["state"] / "backups").mkdir(parents=True)
    with open(p["root"] / ".gitignore", "x", encoding="utf-8", newline="\n") as fh:
        fh.write(PROJECT_GITIGNORE)
    dm_text = (f"-- {name}: authoritative source for this Kosmokrator project.\n"
               f"#modname \"{name}\"\n#description \"{description}\"\n#icon \"mod_banner.tga\"\n#version 0.10\n")
    from .tga import default_mod_banner
    (p["mod_dir"] / "mod_banner.tga").write_bytes(default_mod_banner())
    with open(p["dm"], "xb") as fh:
        fh.write(dm_text.encode("utf-8"))
    meta = {
        "schema": 1, "tool": "kosmokrator", "tool_version": __version__,
        "slug": slug, "name": name, "created_utc": _now(),
        "target_game_version": target_game_version or DEFAULT_TARGET_GAME_VERSION,
        "manual_version": MANUAL_VERSION,
        "dm_path": f"mod/{slug}/{slug}.dm",
        "dependencies": [],
        "reservations": {},
    }
    with open(p["meta"], "x", encoding="utf-8", newline="\n") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")
    return {"project": slug, "root": str(p["root"]), "dm_path": meta["dm_path"],
            "sha256": sha256_bytes(dm_text.encode("utf-8")), "metadata": meta}


@contextlib.contextmanager
def project_lock(project: Project) -> Iterator[None]:
    """Exclusive lock file so concurrent writers cannot interleave metadata or .dm writes.

    A stale lock is never repaired automatically, and on exit the lock is removed only if it still
    holds this operation's token (so a lock created by someone else is left alone).
    """
    contained(project.root, project.state_dir, what="state directory")
    project.state_dir.mkdir(exist_ok=True)
    contained(project.root, project.state_dir, what="state directory")
    lock = project.state_dir / "lock"
    token = f"{os.getpid()}-{secrets.token_hex(8)}".encode()
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise KosmoError("project_locked", "Another Kosmokrator operation holds the project lock",
                         lock=str(lock), hint="Delete the lock file only if no other operation is running.") from exc
    try:
        try:
            os.write(fd, token)
        finally:
            os.close(fd)
        yield
    finally:
        with contextlib.suppress(OSError):
            if not is_link(lock) and lock.read_bytes() == token:
                os.unlink(lock)


def _save_meta(project: Project) -> None:
    data = (json.dumps(project.meta, indent=2) + "\n").encode("utf-8")
    atomic_write_bytes(project.meta_path, data)


def resolve_dm_target(project: Project, file: str | None) -> Path:
    if not file:
        # Re-check the default source at use time: no link components, still inside the mod folder.
        return contained(project.mod_dir, project.dm_path, what="project .dm")
    target = contained(project.mod_dir, file, what="patch target")
    if target.suffix != ".dm":
        raise KosmoError("bad_target", "Only .dm files inside the project's mod folder can be patched", file=file)
    return target


def read_dm(path: Path) -> tuple[bytes, str, str]:
    if is_link(path):
        raise KosmoError("symlink_rejected", ".dm file is a symlink or junction", path=str(path))
    if not path.is_file():
        raise KosmoError("dm_missing", f".dm file not found: {path}")
    data = path.read_bytes()
    text, enc = decode_dm(data)
    return data, text, enc


def inspect_mod(workspace: Path, slug: str, file: str | None = None) -> dict[str, Any]:
    project = open_project(workspace, slug)
    path = resolve_dm_target(project, file)
    data, text, enc = read_dm(path)
    pr = parse(text)
    blocks = []
    unknown: list[dict[str, Any]] = []

    def status(ctx: str, cmd: str) -> str:
        if cmdreg.get(ctx, cmd):
            return "curated"
        if cmd in cmdreg.DOCUMENTED.get(ctx, ()):
            return "documented_uncurated"
        return "unverified"

    for st in pr.toplevel:
        if status("top", st.command) == "unverified":
            unknown.append({"line": st.line, "context": "top", "raw": st.raw})
    for b in pr.blocks:
        cmds = []
        for st in [b.opener, *b.statements]:
            s = status(b.context, st.command)
            cmds.append({"line": st.line, "command": f"#{st.command}", "status": s,
                         "args": [a.raw for a in st.args]})
            if s == "unverified":
                unknown.append({"line": st.line, "context": b.context, "raw": st.raw})
        blocks.append({"context": b.context, "opener": f"#{b.opener.command}",
                       "id": b.opener.args[0].value if b.opener.args else None,
                       "line": b.opener.line, "end_line": b.end.line if b.end else None,
                       "closed": b.end is not None, "commands": cmds})
    return {
        "project": slug, "file": project.rel(path), "sha256": sha256_bytes(data), "bytes": len(data),
        "encoding": enc, "newlines": newline_style(text),
        "statement_count": len(pr.statements),
        "toplevel": [{"line": s.line, "command": f"#{s.command}", "args": [a.raw for a in s.args]} for s in pr.toplevel],
        "blocks": blocks,
        "definitions": definitions(pr),
        "syntax_issues": pr.issues,
        "stray_text": pr.stray,
        "unverified_commands": unknown,
        "limitations": [
            "Static parse only; Dominions itself is the authority on load behaviour.",
            "Unknown/uncurated commands are retained verbatim and reported, never removed.",
            "References are only resolved by validate_mod (needs a catalog for vanilla objects).",
        ],
    }


def _normalize_newlines(text: str, style: str) -> str:
    if style == "crlf":
        return text.replace("\r\n", "\n").replace("\n", "\r\n")
    if style == "lf":
        return text.replace("\r\n", "\n")
    return text


def apply_mod_patch(workspace: Path, slug: str, expected_sha256: str, *, old: str | None = None,
                    new: str | None = None, insert_line: int | None = None, text: str | None = None,
                    file: str | None = None) -> dict[str, Any]:
    """Exactly one replacement of `old` by `new`, or one insertion of `text` before `insert_line`."""
    project = open_project(workspace, slug)
    path = resolve_dm_target(project, file)
    replace_mode = old is not None
    if replace_mode == (insert_line is not None):
        raise KosmoError("bad_patch", "Give either old/new (replace once) or insert_line/text (single insertion)")
    if not expected_sha256 or len(expected_sha256) != 64:
        raise KosmoError("bad_patch", "expected_sha256 (64 hex chars of the current file) is required")
    with project_lock(project):
        backups = state_subdir(project, "backups")  # refuse linked backup dirs before any write
        path = resolve_dm_target(project, file)
        data, src, enc = read_dm(path)
        before = sha256_bytes(data)
        if before.lower() != expected_sha256.lower():
            raise KosmoError("sha_mismatch", "File changed since it was inspected; re-read before patching",
                             expected=expected_sha256, actual=before)
        style = newline_style(src)
        if replace_mode:
            if not old:
                raise KosmoError("bad_patch", "old text must not be empty")
            if new is None:
                raise KosmoError("bad_patch", "new text is required for a replacement (use \"\" to delete)")
            count = src.count(old)
            if count != 1:
                lines = []
                pos = src.find(old)
                while pos != -1 and len(lines) < 10:
                    lines.append(src.count("\n", 0, pos) + 1)
                    pos = src.find(old, pos + 1)
                raise KosmoError("patch_not_unique" if count else "patch_not_found",
                                 f"old text occurs {count} times; it must occur exactly once", lines=lines)
            start = src.index(old)
            replacement = _normalize_newlines(new, style)
            out = src[:start] + replacement + src[start + len(old):]
            removed_end = start + len(old)
        else:
            if text is None or text == "":
                raise KosmoError("bad_patch", "text is required for an insertion")
            lines = src.splitlines(keepends=True)
            if not isinstance(insert_line, int) or not 1 <= insert_line <= len(lines) + 1:
                raise KosmoError("bad_patch", f"insert_line must be between 1 and {len(lines) + 1}")
            nl = "\r\n" if style == "crlf" else "\n"
            replacement = _normalize_newlines(text, style)
            start = sum(len(x) for x in lines[:insert_line - 1])
            if insert_line == len(lines) + 1 and src and not src.endswith(("\n", "\r")):
                replacement = nl + replacement  # keep the old last line intact; separate new text
            if insert_line <= len(lines) and not replacement.endswith("\n"):
                replacement += nl
            out = src[:start] + replacement + src[start:]
            removed_end = start
        try:
            new_data = out.encode(enc)
        except UnicodeEncodeError as exc:
            raise KosmoError("encoding", f"New text cannot be encoded as {enc} like the existing file") from exc
        # Self-check: untouched prefix/suffix bytes are identical to the original.
        prefix = src[:start].encode(enc)
        suffix = src[removed_end:].encode(enc)
        if not (data.startswith(prefix) and data.endswith(suffix) and new_data.startswith(prefix)
                and new_data.endswith(suffix)):
            raise KosmoError("internal", "Lossless patch self-check failed; nothing was written")
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = backups / f"{stamp}-{before[:12]}-{path.name}"
        with open(backup, "xb") as fh:
            fh.write(data)
        atomic_write_bytes(path, new_data)
    after = sha256_bytes(new_data)
    diff = list(difflib.unified_diff(src.splitlines(), out.splitlines(), fromfile=f"a/{project.rel(path)}",
                                     tofile=f"b/{project.rel(path)}", lineterm="", n=2))
    truncated = len(diff) > 400
    return {
        "project": slug, "file": project.rel(path), "mode": "replace" if replace_mode else "insert",
        "before_sha256": before, "after_sha256": after, "changed": before != after, "backup": project.rel(backup),
        "encoding": enc, "newlines": style, "diff": "\n".join(diff[:400]), "diff_truncated": truncated,
        "note": "Only the patched span changed; run validate_mod before export.",
    }


def dependency_texts(workspace: Path, deps: list[str] | None) -> list[tuple[str, str]]:
    """Read explicit dependency .dm files (must live inside the workspace)."""
    out = []
    for dep in deps or []:
        p = contained(workspace, dep, what="dependency")
        if p.suffix != ".dm" or not p.is_file():
            raise KosmoError("bad_dependency", "Dependencies must be existing .dm files inside the workspace", path=dep)
        out.append((p.relative_to(workspace).as_posix(), decode_dm(p.read_bytes())[0]))
    return out


def allocate_ids(workspace: Path, slug: str, kind: str, count: int = 1, labels: list[str] | None = None,
                 dependencies: list[str] | None = None, catalog: Catalog | None = None) -> dict[str, Any]:
    if kind not in ID_KINDS:
        raise KosmoError("bad_kind", f"Cannot allocate ids for {kind!r}", allowed=sorted(ID_KINDS),
                         note="#newspell and #newitem take no number in the manual; reference them by name.")
    if not isinstance(count, int) or not 1 <= count <= 100:
        raise KosmoError("bad_count", "count must be 1-100")
    labels = labels or []
    if len(labels) > count:
        raise KosmoError("bad_labels", "More labels than ids requested")
    project = open_project(workspace, slug)
    with project_lock(project):
        # The snapshot from open_project may predate another writer; re-read under the lock.
        reload_meta(project)
        ids, info = free_ids_locked(project, kind, count, dependencies, catalog)
        record_reservations_locked(project, kind, ids, labels)
    caveats = info["caveats"]
    if kind == "nation":
        caveats.append("#newnation without a number auto-picks a free nation (manual text says 120+, limits "
                       "table says 150+); that path is unverified. Use #selectnation <id> with these ids.")
    lo, hi = ID_KINDS[kind]["range"]
    return {"project": slug, "kind": kind, "ids": ids, "range": [lo, hi], "range_source": ID_KINDS[kind]["source"],
            "checked": info["checked"], "caveats": caveats}


def free_ids_locked(project: Project, kind: str, count: int, dependencies: list[str] | None,
                    catalog: Catalog | None) -> tuple[list[int], dict[str, Any]]:
    """The first `count` free ids of `kind` (catalog, .dm, dependencies and reservations considered).

    Call while holding project_lock after reload_meta; nothing is written here.
    """
    spec = ID_KINDS[kind]
    lo, hi = spec["range"]
    deps = list(project.meta.get("dependencies") or []) + list(dependencies or [])
    caveats = [
        f"Ranges follow manual {MANUAL_VERSION}; target game version is "
        f"{project.meta.get('target_game_version')}. Check after game updates.",
        "Conflicts with mods that were not provided as dependencies cannot be ruled out.",
    ]
    used: dict[int, str] = {}
    if catalog is not None:
        for i in catalog.ids(spec["catalog"]):
            used.setdefault(i, "catalog")
    else:
        caveats.append("No catalog supplied: vanilla ids were not checked (allocation stays inside the "
                       "documented modding range).")
    dm_path = resolve_dm_target(project, None)
    sources = [(project.rel(dm_path), read_dm(dm_path)[1])]
    sources += dependency_texts(project.workspace, deps)
    for label, text in sources:
        for d in definitions(parse(text)):
            if d["kind"] == kind and d["id"] is not None:
                used.setdefault(d["id"], label)
    for r in project.meta.get("reservations", {}).get(kind, []):
        used.setdefault(int(r["id"]), "reserved")
    ids = []
    cur = lo
    while len(ids) < count and cur <= hi:
        if cur not in used:
            ids.append(cur)
        cur += 1
    if len(ids) < count:
        raise KosmoError("range_exhausted", f"Not enough free {kind} ids in {lo}-{hi}")
    return ids, {"caveats": caveats, "checked": {"catalog": catalog is not None, "dependencies": deps,
                                                  "used_ids_considered": len(used)}}


def record_reservations_locked(project: Project, kind: str, ids: list[int], labels: list[str | None] | None) -> None:
    """Append reservations to the metadata and save it (call while holding project_lock)."""
    labels = labels or []
    res = project.meta.setdefault("reservations", {}).setdefault(kind, [])
    stamp = _now()
    for n, i in enumerate(ids):
        res.append({"id": i, "label": labels[n] if n < len(labels) else None, "reserved_utc": stamp})
    _save_meta(project)


def write_dm_locked(project: Project, path: Path, data: bytes, new_data: bytes) -> str:
    """Back up `data` and atomically replace the .dm with `new_data` (call while holding project_lock)."""
    backups = state_subdir(project, "backups")
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = backups / f"{stamp}-{sha256_bytes(data)[:12]}-{path.name}"
    with open(backup, "xb") as fh:
        fh.write(data)
    atomic_write_bytes(path, new_data)
    return project.rel(backup)
