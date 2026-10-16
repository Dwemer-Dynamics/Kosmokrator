"""Local project checkpoints: capture, compare, review baselines and guarded restore.

A checkpoint is an explicit, immutable record of every authored file in one project:

* every regular file under ``mod/<slug>/`` (the owned mod folder: .dm sources and assets),
* every complete map bundle under ``maps/<id>/`` (flat bundles, as the map tools store them),
* the authored metadata allowlist ``kosmokrator.json`` and ``playtests/records.json``.

Local state (``.kosmokrator/``: backups, locks, reference snapshots, map jobs, Workshop records), ``exports/`` and
anything else in the project folder are never captured. Links, junctions, unsafe names, non-regular files and
oversized trees are refused rather than silently skipped. Files are read twice (stat before and after hashing) so
an edit made while a checkpoint is captured is refused, not recorded half-way.

Storage lives in ``<project>/.kosmokrator/revisions/`` and is never exported or pruned:

* ``objects/<sha[:2]>/<sha256>``: content-addressed blobs, written once and verified on every read,
* ``checkpoints/<id>.json``: immutable manifests (schema ``kosmokrator.checkpoint/1``),
* ``reviews/<stamp>.json``: review marks naming a checkpoint and the reviewer kind the caller declared,
* ``journal/<id>/``: restore journals with staged replacement files.

Restore is preview-then-apply. A plan lists add/replace/delete operations from the expected current content
revision to the selected checkpoint and has a hash; applying re-captures the current files under the project lock,
requires the same current revision and plan hash, verifies every historical blob, stores a complete pre-restore
checkpoint, stages all replacement files, journals the plan and only then replaces files one by one, re-checking
each destination. A failure reverts the touched files from the pre-restore checkpoint; an interrupted restore is
reported and can be recovered from its journal. This is not a filesystem-atomic transaction. Metadata keeps the
project identity and current configuration; ID reservations are the union of the checkpoint's and the current
ones, so a restore never frees a reserved ID.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import difflib
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from . import __version__
from . import commands as cmdreg
from .dmparse import block_id, block_name, decode_dm, newline_style, parse
from .errors import KosmoError
from .images import image_info_bytes
from .paths import SAFE_NAME_RE, atomic_write_bytes, contained, is_link
from .project import META_FILE, Project, open_project, project_lock, sha256_bytes, state_subdir

SCHEMA = "kosmokrator.revisions/1"
CHECKPOINT_SCHEMA = "kosmokrator.checkpoint/1"
REVIEW_SCHEMA = "kosmokrator.review/1"
COMPARE_SCHEMA = "kosmokrator.compare/1"
PLAN_SCHEMA = "kosmokrator.restore-plan/1"
JOURNAL_SCHEMA = "kosmokrator.restore-journal/1"

STORE = "revisions"
METADATA_FILES = (META_FILE, "playtests/records.json")
MAP_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,47}$")
MAP_FILE_RE = re.compile(r"^[A-Za-z0-9_]+\.(?:map|tga|d6m|rgb|d3m|png|txt)$", re.I)
CHECKPOINT_RE = re.compile(r"^cp-\d{8}T\d{6}Z-[0-9a-f]{8}$")
JOURNAL_RE = re.compile(r"^rs-\d{8}T\d{6}Z-[0-9a-f]{8}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
KINDS = ("manual", "review", "pre-restore", "restore")
REVIEWER_KINDS = ("human", "agent")
# The metadata keys a restore takes from the checkpoint; every other key keeps its current value (identity and
# configuration), and reservations are merged.
RESTORED_META_KEYS = ("name", "dependencies")

MAX_FILES = 4000
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_LISTED = 500
MAX_TEXT = 400
MAX_DIFF_LINES = 800
MAX_OBJECTS = 400
MAX_CHANGES = 200
MAX_PREVIEW_BYTES = 16 * 1024 * 1024
IMAGE_EXT = (".png", ".tga")

NOTES = [
    "History starts at the first checkpoint: changes made before it cannot be reconstructed. Create a checkpoint "
    "before agent or manual work you may want to review or undo.",
    "Single-file .dm backups under .kosmokrator/backups are safety copies, not checkpoints; they are not listed "
    "here and earlier assets are not guessed.",
    "Reviewer kind is what the caller declared; Kosmokrator records it but cannot verify who reviewed.",
    "Checkpoints are local project state (.kosmokrator/revisions): never exported, never pruned automatically.",
]
LIMITATIONS = [
    "Static comparison of files: it shows authored lines, not resolved in-game values.",
    "Values inherited from donors (#copystats, #copyspr, #clear...) or the catalog are not recomputed for a "
    "checkpoint; only the authored donor lines are compared.",
    "Maps are compared as bundles (files, hashes, image sizes and source lines), not as painted provinces.",
]
DONOR_NOTE = ("Donor or reset lines changed. Inherited values come from the donor or catalog and are not recomputed "
              "for the checkpoint; only authored lines are compared.")
SELECT_NOTE = ("This block modifies an existing object; changes apply on top of donor or catalog values that are not "
               "resolved here.")

# Category of a command for the semantic diff.
DONOR_COMMANDS = {"copystats", "copyspr", "clear", "clearspec", "clearmagic", "clearweapons", "cleararmor",
                  "clearallweapons", "clearallarmor", "clearrec", "clearsites", "clearnation", "cleargods",
                  "clearallgods", "clearheroes", "clearunrest"}
RECRUIT_COMMANDS = {"addrecunit", "addreccom", "addforeignunit", "addforeigncom", "uwrec", "uwcom", "landrec",
                    "landcom", "coastunit1", "coastunit2", "coastunit3", "coastcom1", "coastcom2",
                    "startcom", "startscout", "startunittype1", "startunittype2", "startunitnbrs1",
                    "startunitnbrs2", "addgod", "delgod", "homemon", "homecom", "mon", "com",
                    *(f"{t}rec" for t in ("forest", "mountain", "swamp", "waste", "cave", "coast")),
                    *(f"{t}com" for t in ("forest", "mountain", "swamp", "waste", "cave")),
                    *(f"hero{i}" for i in range(1, 11)), *(f"multihero{i}" for i in range(1, 8)),
                    *(f"defcom{i}" for i in (1, 2)), "defunit1", "defunit1b", "defunit1c", "defunit1d",
                    "defunit2", "defunit2b", "defmult1", "defmult1b", "defmult1c", "defmult1d", "defmult2",
                    "defmult2b", "wallcom", "wallunit", "wallmult"}
DESCRIPTION_COMMANDS = {"name", "descr", "epithet", "summary", "brief", "fixedname", "modname", "description",
                        "version", "domversion", "icon"}
MAGIC_COMMANDS = {"magicskill", "custommagic", "magicboost"}
ASSET_COMMANDS = {"spr", "spr1", "spr2", "xspr1", "xspr2", "unmountedspr1", "unmountedspr2", "flag", "indepflag",
                  "icon", "sample", "copyspr"}


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _stamp(now: _dt.datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%SZ")


def _iso(now: _dt.datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _json_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def content_revision(files: dict[str, str]) -> str:
    """SHA-256 over every captured path and content hash; any added, removed or changed file changes it."""
    return sha256_bytes(_canon(sorted(files.items())))


def map_bundle_revision(files: dict[str, str]) -> str:
    """The same whole-bundle revision the map tools use (file name -> SHA-256)."""
    return sha256_bytes(json.dumps(dict(sorted(files.items())), sort_keys=True).encode())


# ---------- paths and capture ----------

def path_role(slug: str, rel: Any) -> str:
    """Role of a project-relative path (dm, asset, mod, map, metadata); refuse anything outside the scope."""
    if not isinstance(rel, str) or not rel or len(rel) > 400 or "\\" in rel or rel.startswith("/"):
        raise KosmoError("bad_path", "Checkpoint paths are project-relative with forward slashes.", path=str(rel)[:200])
    parts = rel.split("/")
    for part in parts:
        if part in ("", ".", "..") or not SAFE_NAME_RE.match(part) or part.split(".")[0].upper() in RESERVED_NAMES:
            raise KosmoError("bad_path", f"Unsafe name component {part!r} in {rel!r}; rename it before checkpointing.",
                             path=rel)
    if rel in METADATA_FILES:
        return "metadata"
    if len(parts) >= 3 and parts[0] == "mod" and parts[1] == slug:
        low = parts[-1].lower()
        return "dm" if low.endswith(".dm") else "asset" if low.endswith(IMAGE_EXT) else "mod"
    if len(parts) == 3 and parts[0] == "maps" and MAP_ID_RE.match(parts[1]) and MAP_FILE_RE.match(parts[2]):
        return "map"
    raise KosmoError("bad_path", f"{rel} is outside the checkpoint scope (mod/{slug}/, maps/<id>/, metadata).",
                     path=rel)


def _lstat_regular(path: Path, rel: str) -> os.stat_result:
    if is_link(path):
        raise KosmoError("symlink_rejected", f"{rel} is a symlink or junction; checkpoints never follow links.",
                         path=rel)
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode):
        raise KosmoError("bad_path", f"{rel} is not a regular file.", path=rel)
    return st


def _scan(project: Project) -> dict[str, tuple[Path, int, int]]:
    """rel -> (path, size, mtime_ns) for every file in scope; raises on links, unsafe names or limits."""
    root = project.root
    out: dict[str, tuple[Path, int, int]] = {}
    total = 0

    def add(rel: str, path: Path) -> None:
        nonlocal total
        path_role(project.slug, rel)
        st = _lstat_regular(path, rel)
        if st.st_size > MAX_FILE_BYTES:
            raise KosmoError("too_large", f"{rel} exceeds {MAX_FILE_BYTES} bytes.", path=rel)
        total += st.st_size
        if len(out) >= MAX_FILES or total > MAX_TOTAL_BYTES:
            raise KosmoError("too_large", f"The project exceeds {MAX_FILES} files or {MAX_TOTAL_BYTES} bytes in "
                                          "checkpoint scope.")
        out[rel] = (path, st.st_size, st.st_mtime_ns)

    def directory(rel: str) -> Path | None:
        path = contained(root, rel, what=rel)
        if is_link(path):
            raise KosmoError("symlink_rejected", f"{rel} is a symlink or junction.", path=rel)
        if not path.exists():
            return None
        if not path.is_dir():
            raise KosmoError("bad_path", f"{rel} is not a folder.", path=rel)
        return path

    mod = directory("mod")
    if mod is not None and directory(f"mod/{project.slug}") is not None:
        stack = [f"mod/{project.slug}"]
        while stack:
            rel_dir = stack.pop()
            with os.scandir(root / rel_dir) as it:
                entries = sorted(it, key=lambda e: e.name)
            for entry in entries:
                rel = f"{rel_dir}/{entry.name}"
                p = Path(entry.path)
                if is_link(p):
                    raise KosmoError("symlink_rejected", f"{rel} is a symlink or junction.", path=rel)
                if entry.is_dir(follow_symlinks=False):
                    path_role(project.slug, f"{rel}/x")  # validate the folder name itself
                    stack.append(rel)
                else:
                    add(rel, p)
    maps = directory("maps")
    if maps is not None:
        for bundle in sorted(os.listdir(maps)):
            rel_dir = f"maps/{bundle}"
            p = directory(rel_dir)
            if p is None or not MAP_ID_RE.match(bundle):
                raise KosmoError("bad_path", f"{rel_dir} is not a map bundle folder.", path=rel_dir)
            for name in sorted(os.listdir(p)):
                if (p / name).is_dir() and not is_link(p / name):
                    raise KosmoError("bad_path", f"{rel_dir}/{name}: map bundles must be flat.", path=f"{rel_dir}/{name}")
                add(f"{rel_dir}/{name}", p / name)
    for rel in METADATA_FILES:
        parent = rel.rsplit("/", 1)[0] if "/" in rel else None
        if parent and directory(parent) is None:
            continue
        p = contained(root, rel, what=rel)
        if p.exists() or is_link(p):
            add(rel, p)
    return out


def _read_verified(path: Path, rel: str, size: int) -> bytes:
    _lstat_regular(path, rel)
    data = path.read_bytes()
    if len(data) != size:
        raise KosmoError("changed_during_capture", f"{rel} changed while it was read; retry when edits finish.",
                         path=rel)
    return data


def _capture(project: Project, store: Path | None = None) -> dict[str, Any]:
    """Hash every file in scope (storing blobs when store is given) and verify nothing changed meanwhile."""
    before = _scan(project)
    files: dict[str, dict[str, Any]] = {}
    for rel, (path, size, _mtime) in sorted(before.items()):
        data = _read_verified(path, rel, size)
        sha = sha256_bytes(data)
        if store is not None:
            _put_blob(store, sha, data)
        files[rel] = {"path": rel, "role": path_role(project.slug, rel), "sha256": sha, "bytes": len(data)}
    after = _scan(project)
    if {k: v[1:] for k, v in before.items()} != {k: v[1:] for k, v in after.items()}:
        changed = sorted(set(before) ^ set(after) | {k for k in before.keys() & after.keys() if before[k][1:] != after[k][1:]})
        raise KosmoError("changed_during_capture", "Files changed while they were read; retry when edits finish.",
                         paths=changed[:20])
    shas = {rel: f["sha256"] for rel, f in files.items()}
    return {"revision": content_revision(shas), "files": files, "shas": shas, "totals": _totals(files.values())}


def _totals(files: Any) -> dict[str, Any]:
    by_role: dict[str, int] = {}
    count = size = 0
    for f in files:
        count += 1
        size += f["bytes"]
        by_role[f["role"]] = by_role.get(f["role"], 0) + 1
    return {"files": count, "bytes": size, "by_role": dict(sorted(by_role.items()))}


# ---------- blob store ----------

def _store(project: Project, create: bool) -> Path | None:
    if create:
        root = state_subdir(project, STORE)
    else:
        contained(project.root, project.state_dir, what="state directory")
        root = contained(project.root, project.state_dir / STORE, what="revisions directory")
        if not root.exists():
            return None
    if is_link(root) or not root.is_dir():
        raise KosmoError("symlink_rejected", "The revisions folder is a link or not a folder.")
    return root


def _sub(store: Path, *parts: str, create: bool = False) -> Path:
    path = contained(store, store.joinpath(*parts), what="revisions folder")
    if create:
        path.mkdir(parents=True, exist_ok=True)
        path = contained(store, path, what="revisions folder")
    return path


def _put_blob(store: Path, sha: str, data: bytes) -> None:
    folder = _sub(store, "objects", sha[:2], create=True)
    dest = folder / sha
    if dest.exists() or is_link(dest):
        _get_blob(store, sha)  # existing blobs are never overwritten; a damaged one is an error
        return
    fd, tmp = tempfile.mkstemp(prefix=".blob.", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.rename(tmp, dest)  # exclusive on Windows; ids are content hashes, so a winner has the same bytes
        except FileExistsError:
            _get_blob(store, sha)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)


def _get_blob(store: Path, sha: str) -> bytes:
    if not SHA_RE.match(sha or ""):
        raise KosmoError("bad_request", "Blob ids are 64 lower-case hex characters.")
    path = contained(store, store / "objects" / sha[:2] / sha, what="checkpoint blob")
    if is_link(path) or not path.is_file():
        raise KosmoError("blob_missing", f"Checkpoint content {sha[:12]} is missing from local history.", sha256=sha)
    data = path.read_bytes()
    if sha256_bytes(data) != sha:
        raise KosmoError("blob_corrupt", f"Checkpoint content {sha[:12]} does not match its hash.", sha256=sha)
    return data


# ---------- manifests and reviews ----------

def _new_id(prefix: str, now: _dt.datetime) -> str:
    return f"{prefix}-{_stamp(now)}-{secrets.token_hex(4)}"


def _clean_text(value: Any, what: str, limit: int = MAX_TEXT) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise KosmoError("bad_request", f"{what} must be text of at most {limit} characters.")
    return value.strip() or None


def _write_new(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if path.exists() or is_link(path):
            raise KosmoError("dest_exists", "History records are never overwritten.")
        os.rename(tmp, path)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)


def _write_checkpoint(project: Project, store: Path, cap: dict[str, Any], kind: str, *, label: str | None = None,
                      note: str | None = None, actor: str | None = None, via: str = "api",
                      extra: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now()
    cid = _new_id("cp", now)
    meta = project.meta
    dm_rel = f"mod/{project.slug}/{project.slug}.dm"
    manifest = {
        "schema": CHECKPOINT_SCHEMA, "id": cid, "kind": kind, "created_utc": _iso(now), "label": label,
        "note": note, "actor": actor, "via": via, "tool_version": __version__,
        "project": {"slug": project.slug, "name": meta.get("name"), "created_utc": meta.get("created_utc"),
                    "target_game_version": meta.get("target_game_version"), "dm_path": meta.get("dm_path")},
        "revision": cap["revision"], "source_sha256": cap["shas"].get(dm_rel), "totals": cap["totals"],
        "files": [cap["files"][rel] for rel in sorted(cap["files"])], **(extra or {}),
    }
    _write_new(_sub(store, "checkpoints", create=True) / f"{cid}.json", _json_bytes(manifest))
    return manifest


def _load_checkpoint(project: Project, store: Path | None, cid: Any) -> dict[str, Any]:
    if not isinstance(cid, str) or not CHECKPOINT_RE.match(cid):
        raise KosmoError("bad_request", "checkpoint must be a checkpoint id such as cp-20260101T000000Z-0123abcd.")
    if store is None:
        raise KosmoError("checkpoint_missing", "This project has no checkpoints yet.")
    path = contained(store, store / "checkpoints" / f"{cid}.json", what="checkpoint")
    if is_link(path) or not path.is_file():
        raise KosmoError("checkpoint_missing", f"Checkpoint {cid} does not exist.")
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise KosmoError("manifest_corrupt", f"Checkpoint {cid} is too large to read.")
    try:
        m = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise KosmoError("manifest_corrupt", f"Checkpoint {cid} is not valid JSON.") from exc
    if not isinstance(m, dict) or m.get("schema") != CHECKPOINT_SCHEMA or m.get("id") != cid or \
            not isinstance(m.get("files"), list) or m.get("kind") not in KINDS:
        raise KosmoError("manifest_corrupt", f"Checkpoint {cid} has an unexpected shape.")
    if (m.get("project") or {}).get("slug") != project.slug:
        raise KosmoError("manifest_corrupt", f"Checkpoint {cid} belongs to another project.")
    shas: dict[str, str] = {}
    for f in m["files"]:
        if not isinstance(f, dict) or not SHA_RE.match(str(f.get("sha256"))) or type(f.get("bytes")) is not int:
            raise KosmoError("manifest_corrupt", f"Checkpoint {cid} lists an invalid file entry.")
        f["role"] = path_role(project.slug, f.get("path"))
        if f["path"] in shas:
            raise KosmoError("manifest_corrupt", f"Checkpoint {cid} lists {f['path']} twice.")
        shas[f["path"]] = f["sha256"]
    if content_revision(shas) != m.get("revision"):
        raise KosmoError("manifest_corrupt", f"Checkpoint {cid} does not match its recorded revision.")
    m["shas"] = shas
    return m


def _summary(m: dict[str, Any], current: str | None = None) -> dict[str, Any]:
    out = {k: m.get(k) for k in ("id", "kind", "created_utc", "label", "note", "actor", "via", "revision",
                                 "source_sha256", "totals")}
    out.update({k: m[k] for k in ("restored_from", "pre_restore", "restore_target") if k in m})
    if current is not None:
        out["matches_current"] = m.get("revision") == current
    return out


def _list_checkpoints(project: Project, store: Path | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if store is None:
        return [], []
    folder = _sub(store, "checkpoints")
    if not folder.exists():
        return [], []
    good, bad = [], []
    names = sorted((n for n in os.listdir(folder) if n.endswith(".json")), reverse=True)
    for name in names[:MAX_LISTED]:
        try:
            good.append(_load_checkpoint(project, store, name[:-5]))
        except KosmoError as exc:
            bad.append({"file": name, "code": exc.code, "message": exc.message})
    good.sort(key=lambda m: (str(m.get("created_utc")), m["id"]), reverse=True)
    return good, bad


def _list_reviews(store: Path | None) -> list[dict[str, Any]]:
    if store is None:
        return []
    folder = _sub(store, "reviews")
    if not folder.exists():
        return []
    out = []
    for name in sorted(os.listdir(folder), reverse=True)[:MAX_LISTED]:
        path = folder / name
        if not name.endswith(".json") or is_link(path) or not path.is_file() or path.stat().st_size > 65536:
            continue
        try:
            r = json.loads(path.read_bytes().decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            continue
        if isinstance(r, dict) and r.get("schema") == REVIEW_SCHEMA and r.get("reviewer_kind") in REVIEWER_KINDS \
                and CHECKPOINT_RE.match(str(r.get("checkpoint"))):
            out.append({k: r.get(k) for k in ("id", "checkpoint", "reviewer_kind", "reviewer", "note",
                                              "created_utc", "revision", "via")})
    return out


def _baseline(project: Project, store: Path | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    for r in _list_reviews(store):
        try:
            return r, _load_checkpoint(project, store, r["checkpoint"])
        except KosmoError:
            continue
    return None, None


# ---------- journal ----------

def _journals(store: Path | None) -> list[tuple[Path, dict[str, Any]]]:
    if store is None:
        return []
    folder = _sub(store, "journal")
    if not folder.exists():
        return []
    out = []
    for name in sorted(os.listdir(folder)):
        path = folder / name / "journal.json"
        if not JOURNAL_RE.match(name) or is_link(folder / name) or is_link(path) or not path.is_file():
            continue
        try:
            j = json.loads(path.read_bytes().decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            j = {"id": name, "state": "unreadable"}
        out.append((folder / name, j))
    return out


def _interrupted(store: Path | None) -> list[dict[str, Any]]:
    return [{k: j.get(k) for k in ("id", "state", "checkpoint", "pre_restore", "created_utc", "error")}
            for _p, j in _journals(store) if j.get("state") not in ("complete", "rolled_back", "recovered")]


def _write_journal(folder: Path, journal: dict[str, Any]) -> None:
    atomic_write_bytes(folder / "journal.json", _json_bytes(journal))


# ---------- state ----------

def revision_state(workspace: Path, slug: str) -> dict[str, Any]:
    """Checkpoints (newest first), the review baseline, the current content revision and any interrupted restore."""
    project = open_project(workspace, slug)
    store = _store(project, create=False)
    try:
        cap = _capture(project)
        current: dict[str, Any] = {"revision": cap["revision"], "totals": cap["totals"],
                                   "source_sha256": cap["shas"].get(f"mod/{slug}/{slug}.dm")}
    except KosmoError as exc:
        current = {"revision": None, "error": exc.to_dict()}
    checkpoints, unreadable = _list_checkpoints(project, store)
    review, base = _baseline(project, store)
    reviewed = {}
    for r in _list_reviews(store):
        reviewed.setdefault(r["checkpoint"], r)
    items = []
    for m in checkpoints:
        s = _summary(m, current.get("revision"))
        s["review"] = reviewed.get(m["id"])
        items.append(s)
    return {
        "schema": SCHEMA, "project": slug, "current": current, "checkpoints": items,
        "unreadable_checkpoints": unreadable,
        "review_baseline": {**review, "checkpoint_summary": _summary(base, current.get("revision"))} if review else None,
        "interrupted_restores": _interrupted(store),
        "history_starts_utc": checkpoints[-1]["created_utc"] if checkpoints else None,
        "scope": {"captured": [f"mod/{slug}/ (every file)", "maps/<id>/ (complete bundles)", *METADATA_FILES],
                  "excluded": [".kosmokrator/ (backups, locks, reference snapshots, map jobs, Workshop records)",
                               "exports/", "any other file in the project folder"],
                  "limits": {"files": MAX_FILES, "file_bytes": MAX_FILE_BYTES, "total_bytes": MAX_TOTAL_BYTES}},
        "storage": f"{slug}/.kosmokrator/{STORE}", "notes": NOTES,
    }


# ---------- create and review ----------

def _actor(value: Any, what: str = "actor") -> str | None:
    if value is None:
        return None
    if value not in REVIEWER_KINDS:
        raise KosmoError("bad_request", f"{what} must be 'human' or 'agent'.")
    return value


def create_checkpoint(workspace: Path, slug: str, body: dict[str, Any], via: str = "api") -> dict[str, Any]:
    project = open_project(workspace, slug)
    label = _clean_text(body.get("label"), "label", 120)
    note = _clean_text(body.get("note"), "note")
    actor = _actor(body.get("actor"))
    with project_lock(project):
        store = _store(project, create=True)
        cap = _capture(project, store)
        expected = body.get("expected_revision")
        if expected is not None and expected != cap["revision"]:
            raise KosmoError("stale_revision", "The project changed since you looked at it; reload first.",
                             expected=expected, actual=cap["revision"])
        m = _write_checkpoint(project, store, cap, "manual", label=label, note=note, actor=actor, via=via)
    return {"checkpoint": _summary(m, cap["revision"]), "written": True,
            "note": "Every authored file is stored locally; nothing is exported or pruned."}


def mark_review(workspace: Path, slug: str, body: dict[str, Any], via: str = "api") -> dict[str, Any]:
    """Record a review baseline: an existing checkpoint, or a new checkpoint of the current files."""
    project = open_project(workspace, slug)
    kind = body.get("reviewer_kind")
    if kind not in REVIEWER_KINDS:
        raise KosmoError("bad_request", "reviewer_kind is required: 'human' or 'agent'. It is never assumed.")
    reviewer = _clean_text(body.get("reviewer"), "reviewer", 80)
    note = _clean_text(body.get("note"), "note")
    with project_lock(project):
        store = _store(project, create=True)
        if body.get("checkpoint") is not None:
            m = _load_checkpoint(project, store, body["checkpoint"])
        else:
            expected = body.get("expected_revision")
            if not isinstance(expected, str) or not SHA_RE.match(expected):
                raise KosmoError("bad_request", "Give checkpoint, or expected_revision (the current revision you "
                                                "reviewed) to snapshot the current files.")
            cap = _capture(project, store)
            if cap["revision"] != expected:
                raise KosmoError("stale_revision", "The project changed after the reviewed revision; review again.",
                                 expected=expected, actual=cap["revision"])
            m = _write_checkpoint(project, store, cap, "review", label=_clean_text(body.get("label"), "label", 120),
                                  note=note, actor=kind, via=via)
        now = _now()
        rid = f"{now.strftime('%Y%m%dT%H%M%S%fZ')}-{secrets.token_hex(4)}"
        review = {"schema": REVIEW_SCHEMA, "id": rid, "checkpoint": m["id"], "revision": m["revision"],
                  "reviewer_kind": kind, "reviewer": reviewer, "note": note, "created_utc": _iso(now), "via": via}
        _write_new(_sub(store, "reviews", create=True) / f"{rid}.json", _json_bytes(review))
    return {"review": review, "checkpoint": _summary(m), "written": True,
            "note": f"Recorded as a {kind} review as declared by the caller; Kosmokrator does not verify reviewers."}


# ---------- compare ----------

def _category(context: str, cmd: str) -> str:
    from .traits import EXCLUDED, TRAITS
    if context == "unknown":
        return "unknown"
    if cmd in DONOR_COMMANDS:
        return "donor"
    if context == "monster":
        t, e = TRAITS.get(cmd), EXCLUDED.get(cmd)
        section = t.section if t else (e or {}).get("section")
        reason = (e or {}).get("reason")
        if reason == "identity":
            return "description"
        if reason == "visual":
            return "asset"
        if reason == "equipment":
            return "equipment"
        if reason == "reset":
            return "donor"
        if cmd in MAGIC_COMMANDS or section == "Magic Paths":
            return "magic"
        if section == "Recruitment Rules":
            return "recruitment"
        if reason == "field":
            return "stat"
        if t:
            return "trait"
    if context in ("nation", "site", "merc") and cmd in RECRUIT_COMMANDS:
        return "recruitment"
    if cmd in DESCRIPTION_COMMANDS:
        return "description"
    if cmd in ASSET_COMMANDS:
        return "asset"
    if cmd in ("weapon", "armor") and context == "monster":
        return "equipment"
    if cmdreg.get(context, cmd) or cmd in cmdreg.DOCUMENTED.get(context, ()):
        return "other"
    from .manual_commands import CONTEXTS, commands
    if context in CONTEXTS and cmd in commands(context):
        return "other"
    return "unknown"


def _norm(st: Any) -> str:
    return " ".join([f"#{st.command}", *(a.raw.replace("\r\n", "\n") for a in st.args)])


def _objects(text: str) -> dict[str, dict[str, Any]]:
    pr = parse(text)
    out: dict[str, dict[str, Any]] = {"top": {"key": "top", "context": "top", "opener": None, "id": None,
                                              "name": None, "line": 1, "statements": pr.toplevel}}
    seen: Counter = Counter()
    for b in pr.blocks:
        ident = block_id(b)
        name = block_name(b)
        base = f"{b.context}:{b.opener.command}:{ident if ident is not None else (name or '?')}"
        seen[base] += 1
        key = base if seen[base] == 1 else f"{base}#{seen[base]}"
        out[key] = {"key": key, "context": b.context, "opener": b.opener.command, "id": ident, "name": name,
                    "line": b.opener.line, "statements": b.statements}
    return out


def _grouped(obj: dict[str, Any] | None) -> dict[str, list[tuple[str, int]]]:
    g: dict[str, list[tuple[str, int]]] = {}
    for st in (obj or {}).get("statements", []):
        g.setdefault(st.command, []).append((_norm(st), st.line))
    return g


def semantic_diff(old_text: str | None, new_text: str | None) -> dict[str, Any]:
    """Authored definition changes between two .dm texts, keyed by block; unknown commands are kept raw."""
    old = _objects(old_text) if old_text is not None else {}
    new = _objects(new_text) if new_text is not None else {}
    objects = []
    counts: Counter = Counter()
    truncated = False
    for key in sorted(old.keys() | new.keys(), key=lambda k: ((new.get(k) or old.get(k))["line"], k)):
        o, n = old.get(key), new.get(key)
        go, gn = _grouped(o), _grouped(n)
        changes = []
        for cmd in sorted(go.keys() | gn.keys()):
            a, b = go.get(cmd, []), gn.get(cmd, [])
            ra, rb = [x[0] for x in a], [x[0] for x in b]
            if ra == rb:
                continue
            cat = _category((n or o)["context"], cmd)
            src = "donor_reference" if cat == "donor" else "unknown_raw" if cat == "unknown" else "authored"
            base = {"command": f"#{cmd}", "category": cat, "source": src}
            if len(a) <= 1 and len(b) <= 1:
                kind = "added" if not a else "removed" if not b else "changed"
                changes.append({**base, "change": kind, "before": ra[0] if ra else None, "after": rb[0] if rb else None,
                                "line_before": a[0][1] if a else None, "line_after": b[0][1] if b else None})
            elif Counter(ra) == Counter(rb):
                changes.append({**base, "change": "reordered", "before": " | ".join(ra)[:MAX_TEXT],
                                "after": " | ".join(rb)[:MAX_TEXT], "line_before": a[0][1], "line_after": b[0][1]})
            else:
                gone, came = Counter(ra) - Counter(rb), Counter(rb) - Counter(ra)
                for raw, line in a:
                    if gone[raw] > 0:
                        gone[raw] -= 1
                        changes.append({**base, "change": "removed", "before": raw, "after": None,
                                        "line_before": line, "line_after": None})
                for raw, line in b:
                    if came[raw] > 0:
                        came[raw] -= 1
                        changes.append({**base, "change": "added", "before": None, "after": raw,
                                        "line_before": None, "line_after": line})
        status = "added" if o is None else "removed" if n is None else "modified" if changes else None
        if status is None:
            continue
        if len(objects) >= MAX_OBJECTS:
            truncated = True
            continue
        ref = n or o
        cats = sorted({c["category"] for c in changes})
        for c in cats:
            counts[c] += 1
        notes = []
        if "donor" in cats:
            notes.append(DONOR_NOTE)
        if ref["opener"] and ref["opener"].startswith("select") and status == "modified":
            notes.append(SELECT_NOTE)
        objects.append({"key": key, "context": ref["context"], "opener": f"#{ref['opener']}" if ref["opener"] else None,
                        "id": ref["id"], "name": (n or {}).get("name") or (o or {}).get("name"),
                        "name_before": (o or {}).get("name"), "status": status,
                        "line_before": (o or {}).get("line"), "line_after": (n or {}).get("line"),
                        "categories": cats, "changes": changes[:MAX_CHANGES],
                        "changes_truncated": len(changes) > MAX_CHANGES, "notes": notes})
    return {"objects": objects, "objects_truncated": truncated, "category_counts": dict(sorted(counts.items())),
            "status_counts": dict(Counter(x["status"] for x in objects))}


def _text_diff(a: str | None, b: str | None, name: str, limit: int = MAX_DIFF_LINES) -> dict[str, Any]:
    lines = list(difflib.unified_diff((a or "").splitlines(), (b or "").splitlines(), fromfile=f"checkpoint/{name}",
                                      tofile=f"current/{name}", lineterm="", n=2))
    added = sum(1 for x in lines if x.startswith("+") and not x.startswith("+++"))
    removed = sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))
    return {"diff": "\n".join(lines[:limit]), "truncated": len(lines) > limit, "lines_added": added,
            "lines_removed": removed}


def _image(rel: str, data: bytes | None) -> dict[str, Any] | None:
    if data is None:
        return None
    info = image_info_bytes(rel, data)
    return {"format": info["format"], "width": info["width"], "height": info["height"], "depth": info["depth"],
            "problems": info["problems"]}


def _side(f: dict[str, Any] | None) -> dict[str, Any] | None:
    return {"sha256": f["sha256"], "bytes": f["bytes"]} if f else None


def compare(workspace: Path, slug: str, target: Any) -> dict[str, Any]:
    """Compare the current files with a checkpoint id, or 'baseline' for the latest review baseline."""
    project = open_project(workspace, slug)
    store = _store(project, create=False)
    review = None
    if target in (None, "", "baseline"):
        review, m = _baseline(project, store)
        if m is None:
            raise KosmoError("baseline_missing", "No review baseline yet. Mark a checkpoint or the current files as "
                                                 "reviewed first.")
    else:
        m = _load_checkpoint(project, store, target)
    cap = _capture(project)
    old_files = {f["path"]: f for f in m["files"]}
    cur_files = cap["files"]

    def old_bytes(rel: str) -> bytes:
        return _get_blob(store, old_files[rel]["sha256"])  # type: ignore[arg-type]

    def cur_bytes(rel: str) -> bytes:
        path = contained(project.root, rel, what=rel)
        data = _read_verified(path, rel, cur_files[rel]["bytes"])
        if sha256_bytes(data) != cur_files[rel]["sha256"]:
            raise KosmoError("changed_during_capture", f"{rel} changed during the comparison; compare again.")
        return data

    files, counts = [], Counter()
    for rel in sorted(old_files.keys() | cur_files.keys()):
        o, c = old_files.get(rel), cur_files.get(rel)
        status = "added" if o is None else "deleted" if c is None else "unchanged" if o["sha256"] == c["sha256"] \
            else "modified"
        counts[status] += 1
        if status != "unchanged":
            files.append({"path": rel, "role": (c or o)["role"], "status": status, "before": _side(o),
                          "after": _side(c)})
    dm, assets, other, maps, metadata = [], [], [], {}, []
    for f in files:
        rel, role = f["path"], f["role"]
        before = old_bytes(rel) if f["before"] else None
        after = cur_bytes(rel) if f["after"] else None
        if role == "dm":
            bt, be = decode_dm(before) if before is not None else (None, None)
            at, ae = decode_dm(after) if after is not None else (None, None)
            dm.append({"path": rel, "status": f["status"],
                       "encoding": {"before": be, "after": ae},
                       "newlines": {"before": newline_style(bt) if bt is not None else None,
                                    "after": newline_style(at) if at is not None else None},
                       "raw": _text_diff(bt, at, rel), "semantic": semantic_diff(bt, at)})
        elif role == "asset":
            ib, ia = _image(rel, before), _image(rel, after)
            assets.append({**f, "image_before": ib, "image_after": ia,
                           "dimensions_changed": bool(ib and ia and (ib["width"], ib["height"]) != (ia["width"], ia["height"])),
                           "preview": {"checkpoint": {"path": rel, "sha256": f["before"]["sha256"]} if ib else None,
                                       "current": {"path": rel, "sha256": f["after"]["sha256"]} if ia else None}})
        elif role == "map":
            ident = rel.split("/")[1]
            entry = maps.setdefault(ident, {"id": ident, "files": []})
            item = {**f, "name": rel.split("/")[2]}
            if rel.lower().endswith(".tga"):
                item["image_before"], item["image_after"] = _image(rel, before), _image(rel, after)
            elif rel.lower().endswith(".map"):
                bt = decode_dm(before)[0] if before is not None else None
                at = decode_dm(after)[0] if after is not None else None
                item["source"] = _text_diff(bt, at, rel, 300)
            entry["files"].append(item)
        elif role == "metadata":
            metadata.append(_metadata_diff(rel, f, before, after))
        else:
            other.append(f)
    for ident, entry in maps.items():
        prefix = f"maps/{ident}/"
        ob = {p[len(prefix):]: x["sha256"] for p, x in old_files.items() if p.startswith(prefix)}
        cb = {p[len(prefix):]: x["sha256"] for p, x in cur_files.items() if p.startswith(prefix)}
        entry.update(status="added" if not ob else "removed" if not cb else "modified",
                     revision_before=map_bundle_revision(ob) if ob else None,
                     revision_after=map_bundle_revision(cb) if cb else None)
    return {
        "schema": COMPARE_SCHEMA, "project": slug, "target": _summary(m, cap["revision"]),
        "baseline": review, "current_revision": cap["revision"], "target_revision": m["revision"],
        "identical": cap["revision"] == m["revision"], "counts": dict(counts), "files": files,
        "dm": dm, "assets": assets, "maps": list(maps.values()), "metadata": metadata, "other": other,
        "limitations": LIMITATIONS,
    }


def _metadata_diff(rel: str, f: dict[str, Any], before: bytes | None, after: bytes | None) -> dict[str, Any]:
    out: dict[str, Any] = {"path": rel, "status": f["status"]}

    def load(data: bytes | None) -> Any:
        if data is None:
            return None
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return "unreadable"
    a, b = load(before), load(after)
    if rel == META_FILE and isinstance(a, dict) and isinstance(b, dict):
        keys = []
        for k in sorted(a.keys() | b.keys()):
            if k == "reservations" or a.get(k) == b.get(k):
                continue
            keys.append({"key": k, "before": a.get(k), "after": b.get(k)})
        res = []
        ra, rb = a.get("reservations") or {}, b.get("reservations") or {}
        for kind in sorted(set(ra) | set(rb)):
            ia = {r.get("id") for r in ra.get(kind, []) if isinstance(r, dict)}
            ib = {r.get("id") for r in rb.get(kind, []) if isinstance(r, dict)}
            if ia != ib:
                res.append({"kind": kind, "added": sorted(ib - ia, key=str), "removed": sorted(ia - ib, key=str)})
        out.update(keys=keys, reservations=res)
    elif rel == "playtests/records.json":
        out["records"] = {"before": len(a) if isinstance(a, list) else a, "after": len(b) if isinstance(b, list) else b}
    else:
        out["raw"] = _text_diff(before.decode("utf-8", "replace") if before else None,
                                after.decode("utf-8", "replace") if after else None, rel, 200)
    return out


def preview_image(workspace: Path, slug: str, side: str, rel: str, sha: str) -> bytes:
    """PNG preview of a current or checkpoint image whose content must hash to sha (else stale/missing)."""
    from .tga import decode_tga, encode_png
    project = open_project(workspace, slug)
    if side not in ("current", "checkpoint") or not isinstance(sha, str) or not SHA_RE.match(sha):
        raise KosmoError("bad_request", "Use side=current|checkpoint, a path and its sha256.")
    role = path_role(slug, rel)
    if role not in ("asset", "map") or not rel.lower().endswith(IMAGE_EXT):
        raise KosmoError("bad_request", "Only PNG and TGA files have previews.")
    if side == "checkpoint":
        store = _store(project, create=False)
        if store is None:
            raise KosmoError("blob_missing", "This project has no checkpoint history.")
        data = _get_blob(store, sha)
    else:
        path = contained(project.root, rel, what=rel)
        if not path.exists():
            raise KosmoError("stale_preview", "The current file no longer exists; compare again.")
        _lstat_regular(path, rel)
        if path.stat().st_size > MAX_PREVIEW_BYTES:
            raise KosmoError("too_large", "Image is too large to preview.")
        data = path.read_bytes()
        if sha256_bytes(data) != sha:
            raise KosmoError("stale_preview", "The current file changed since the comparison; compare again.")
    if len(data) > MAX_PREVIEW_BYTES:
        raise KosmoError("too_large", "Image is too large to preview.")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return data
    try:
        w, h, rgba = decode_tga(data)
    except ValueError as exc:
        raise KosmoError("preview_unavailable", f"TGA preview unavailable: {exc}") from exc
    return encode_png(w, h, rgba)


# ---------- restore ----------

def merge_metadata(current: bytes, historical: bytes) -> bytes:
    """Current metadata with the checkpoint's authored keys; reservations are the union (never freed)."""
    try:
        cur, old = json.loads(current.decode("utf-8")), json.loads(historical.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise KosmoError("bad_metadata", "Project metadata cannot be read for the restore.") from exc
    if not isinstance(cur, dict) or not isinstance(old, dict):
        raise KosmoError("bad_metadata", "Project metadata has an unexpected shape.")
    out = json.loads(json.dumps(cur))
    for key in RESTORED_META_KEYS:
        if key in old:
            out[key] = old[key]
    res = out.setdefault("reservations", {})
    if not isinstance(res, dict):
        raise KosmoError("bad_metadata", "Current reservations have an unexpected shape.")
    for kind, items in (old.get("reservations") or {}).items():
        have = {r.get("id") for r in res.get(kind, []) if isinstance(r, dict)}
        for r in items if isinstance(items, list) else []:
            if isinstance(r, dict) and r.get("id") not in have:
                res.setdefault(kind, []).append(r)
                have.add(r.get("id"))
    if out == cur:
        return current
    return _json_bytes(out).replace(b"\n", b"\r\n") if b"\r\n" in current else _json_bytes(out)


def _candidate_check(slug: str, target: dict[str, str], dm_bytes: bytes | None) -> dict[str, Any]:
    """Syntax and referenced-file check of the restored .dm against the restored file set (before applying)."""
    from .validate import Report, _check_statement
    if dm_bytes is None:
        return {"ok": False, "syntax_errors": [], "statement_errors": 0, "missing_assets": [],
                "message": "The checkpoint has no authoritative .dm; the restored project will not validate."}
    text = decode_dm(dm_bytes)[0]
    pr = parse(text)
    rep, refs, assets = Report(), [], []
    for st in pr.toplevel:
        _check_statement("top", st, rep, "candidate", refs, assets)
    for b in pr.blocks:
        if b.context != "unknown":
            for st in [b.opener, *b.statements]:
                _check_statement(b.context, st, rep, "candidate", refs, assets)
    missing = sorted({a.value for _st, t, a in assets if t == "img" and isinstance(a.value, str)
                      and f"mod/{slug}/{a.value}" not in target})
    errors = [i for i in pr.issues if i["severity"] == "error"]
    return {"ok": not errors and not missing and not rep.of("error"), "syntax_errors": errors[:50],
            "statement_errors": len(rep.of("error")), "missing_assets": missing[:100],
            "message": "Static pre-check of the restored .dm only; full validation runs after the restore."}


def _plan(project: Project, store: Path, m: dict[str, Any], cap: dict[str, Any]) -> dict[str, Any]:
    target = {rel: sha for rel, sha in m["shas"].items() if rel != META_FILE}
    blobs: dict[str, bytes] = {}
    missing = []
    for rel, sha in sorted(target.items()):
        if cap["shas"].get(rel) == sha:
            continue
        try:
            blobs[sha] = _get_blob(store, sha)
        except KosmoError as exc:
            missing.append({"path": rel, "sha256": sha, "code": exc.code})
    if missing:
        raise KosmoError("blob_missing", "Historical content needed for this restore is missing or damaged; nothing "
                                         "was changed.", missing=missing[:20])
    meta_note: dict[str, Any] = {"restored_keys": list(RESTORED_META_KEYS), "reservations": "union"}
    cur_meta = project.meta_path.read_bytes()
    if sha256_bytes(cur_meta) != cap["shas"].get(META_FILE):
        raise KosmoError("changed_during_capture", "Project metadata changed; preview again.")
    if META_FILE in m["shas"]:
        merged = merge_metadata(cur_meta, _get_blob(store, m["shas"][META_FILE]))
    else:
        merged = cur_meta
    meta_sha = sha256_bytes(merged)
    blobs[meta_sha] = merged
    target[META_FILE] = meta_sha
    ops = []
    for rel in sorted(target.keys() | cap["shas"].keys()):
        t, c = target.get(rel), cap["shas"].get(rel)
        if t == c:
            continue
        op = "add" if c is None else "delete" if t is None else "replace"
        ops.append({"op": op, "path": rel, "role": path_role(project.slug, rel), "before": c, "after": t,
                    "bytes_before": cap["files"][rel]["bytes"] if c else None,
                    "bytes_after": len(blobs[t]) if t else None})
    result = content_revision(target)
    body = {"checkpoint": m["id"], "target_revision": m["revision"], "current_revision": cap["revision"],
            "result_revision": result, "ops": [[o["op"], o["path"], o["before"], o["after"]] for o in ops]}
    dm_rel = f"mod/{project.slug}/{project.slug}.dm"
    dm_bytes = blobs.get(target[dm_rel]) if dm_rel in target else None
    if dm_bytes is None and dm_rel in target:  # unchanged by the restore: the current file is the candidate
        dm_bytes = contained(project.root, dm_rel, what=dm_rel).read_bytes()
        if sha256_bytes(dm_bytes) != target[dm_rel]:
            raise KosmoError("changed_during_capture", "The .dm changed; preview again.")
    return {"hash": sha256_bytes(_canon(body)), "ops": ops, "result_revision": result, "blobs": blobs,
            "metadata": meta_note, "candidate": _candidate_check(project.slug, target, dm_bytes)}


def _plan_view(project: Project, m: dict[str, Any], cap: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    counts = Counter(o["op"] for o in plan["ops"])
    return {"schema": PLAN_SCHEMA, "project": project.slug, "checkpoint": _summary(m, cap["revision"]),
            "current_revision": cap["revision"], "result_revision": plan["result_revision"],
            "plan_hash": plan["hash"], "ops": plan["ops"], "counts": {k: counts.get(k, 0) for k in ("add", "replace", "delete")},
            "noop": not plan["ops"], "metadata": plan["metadata"], "candidate_check": plan["candidate"],
            "recovery": "A complete pre-restore checkpoint of the current files is created before any change, and a "
                        "new checkpoint is recorded after it. Older history is kept.",
            "limitations": ["Not a filesystem-atomic transaction: files are replaced one at a time under the project "
                            "lock with a journal; on failure the touched files are restored from the pre-restore "
                            "checkpoint.",
                            "Project identity and configuration stay current; only name and dependencies come from "
                            "the checkpoint, and reservations are merged so no reserved ID is freed."]}


def preview_restore(workspace: Path, slug: str, body: dict[str, Any]) -> dict[str, Any]:
    project = open_project(workspace, slug)
    store = _store(project, create=False)
    m = _load_checkpoint(project, store, body.get("checkpoint"))
    cap = _capture(project)
    expected = body.get("expected_revision")
    if expected is not None and expected != cap["revision"]:
        raise KosmoError("stale_revision", "The project changed since you looked at it; reload first.",
                         expected=expected, actual=cap["revision"])
    view = _plan_view(project, m, cap, _plan(project, store, m, cap))  # type: ignore[arg-type]
    return {**view, "preview": True, "interrupted_restores": _interrupted(store)}


def _place(src: Path, dest: Path) -> None:
    """Move one staged file into place (separate so tests can inject a failure)."""
    os.replace(src, dest)


def _current_sha(path: Path, rel: str) -> str | None:
    if not path.exists() and not is_link(path):
        return None
    _lstat_regular(path, rel)
    return sha256_bytes(path.read_bytes())


def _ensure_parent(project: Project, rel: str) -> Path:
    dest = contained(project.root, rel, what=rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    return contained(project.root, rel, what=rel)


def _prune(project: Project, rel: str) -> None:
    """Remove folders a restore emptied, never above mod/<slug> or maps/."""
    stops = {project.root / "mod" / project.slug, project.root / "maps", project.root}
    cur = (project.root / rel).parent
    while cur not in stops and project.root in cur.parents:
        try:
            os.rmdir(cur)
        except OSError:
            return
        cur = cur.parent


def _revert(project: Project, store: Path, ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return every file an op touched to its before content; untouched or foreign edits are reported."""
    problems = []
    for op in reversed(ops):
        rel = op["path"]
        try:
            dest = contained(project.root, rel, what=rel)
            now = _current_sha(dest, rel)
            if now == op["before"]:
                continue
            if now != op["after"]:
                problems.append({"path": rel, "reason": "changed by someone else; left as is"})
                continue
            if op["before"] is None:
                os.unlink(dest)
                _prune(project, rel)
            else:
                atomic_write_bytes(_ensure_parent(project, rel), _get_blob(store, op["before"]))
        except (OSError, KosmoError) as exc:
            problems.append({"path": rel, "reason": getattr(exc, "message", None) or str(exc)})
    return problems


def apply_restore(workspace: Path, slug: str, body: dict[str, Any], via: str = "api",
                  catalog: Any = None) -> dict[str, Any]:
    project = open_project(workspace, slug)
    if body.get("confirm") is not True:
        raise KosmoError("confirm_required", "Applying a restore needs confirm: true after reviewing the preview.")
    expected, plan_hash = body.get("expected_revision"), body.get("plan_hash")
    if not (isinstance(expected, str) and SHA_RE.match(expected) and isinstance(plan_hash, str) and SHA_RE.match(plan_hash)):
        raise KosmoError("bad_request", "Apply needs expected_revision and plan_hash from the restore preview.")
    with project_lock(project):
        store = _store(project, create=True)
        pending = _interrupted(store)
        if pending:
            raise KosmoError("restore_interrupted", "An earlier restore did not finish; recover it first.",
                             journal=pending[0]["id"])
        m = _load_checkpoint(project, store, body.get("checkpoint"))
        cap = _capture(project, store)  # also stores the current content for the pre-restore checkpoint
        if cap["revision"] != expected:
            raise KosmoError("stale_revision", "The project changed after the preview; preview the restore again.",
                             expected=expected, actual=cap["revision"])
        plan = _plan(project, store, m, cap)
        if plan["hash"] != plan_hash:
            raise KosmoError("plan_changed", "The restore plan differs from the preview; preview again.",
                             expected=plan_hash, actual=plan["hash"])
        view = _plan_view(project, m, cap, plan)
        if not plan["ops"]:
            return {**view, "preview": False, "written": False, "note": "The current files already match."}
        pre = _write_checkpoint(project, store, cap, "pre-restore", via=via, label=f"Before restoring {m['id']}",
                                extra={"restore_target": m["id"]})
        now = _now()
        jid = _new_id("rs", now)
        folder = _sub(store, "journal", jid, create=True)
        staged = _sub(store, "journal", jid, "staged", create=True)
        ops = []
        try:  # stage every replacement before the first project file changes
            for n, op in enumerate(plan["ops"]):
                item = {k: op[k] for k in ("op", "path", "before", "after")}
                if op["after"] is not None:
                    data = plan["blobs"][op["after"]]
                    if sha256_bytes(data) != op["after"]:
                        raise KosmoError("blob_corrupt", f"Staged content for {op['path']} does not match.")
                    item["staged"] = f"{n:05d}"
                    with open(staged / item["staged"], "xb") as fh:
                        fh.write(data)
                        fh.flush()
                        os.fsync(fh.fileno())
                ops.append(item)
        except BaseException:
            shutil.rmtree(contained(store, folder, what="restore journal"), ignore_errors=True)
            raise
        # Additions and replacements first, deletions last; each destination is re-checked before it changes.
        ops.sort(key=lambda o: (o["op"] == "delete", o["path"]))
        journal = {"schema": JOURNAL_SCHEMA, "id": jid, "state": "applying", "checkpoint": m["id"],
                   "pre_restore": pre["id"], "plan_hash": plan["hash"], "current_revision": cap["revision"],
                   "result_revision": plan["result_revision"], "created_utc": _iso(now), "ops": ops}
        _write_journal(folder, journal)
        try:
            for op in ops:
                rel = op["path"]
                dest = contained(project.root, rel, what=rel)
                if _current_sha(dest, rel) != op["before"]:
                    raise KosmoError("changed_during_restore", f"{rel} changed during the restore.", path=rel)
                if op["op"] == "delete":
                    os.unlink(dest)
                    _prune(project, rel)
                else:
                    _place(staged / op["staged"], _ensure_parent(project, rel))
        except BaseException as exc:
            problems = _revert(project, store, ops)
            journal.update(state="rolled_back" if not problems else "rollback_failed",
                           error=getattr(exc, "message", None) or str(exc) or type(exc).__name__, problems=problems)
            _write_journal(folder, journal)
            if problems:
                raise KosmoError("restore_rollback_failed", "The restore failed and some files could not be put back; "
                                 f"recover from journal {jid} or pre-restore checkpoint {pre['id']}.",
                                 journal=jid, pre_restore=pre["id"], problems=problems[:20]) from exc
            if isinstance(exc, KosmoError):
                raise KosmoError(exc.code, f"{exc.message} Every touched file was put back from pre-restore "
                                           f"checkpoint {pre['id']}.", pre_restore=pre["id"], journal=jid) from exc
            raise KosmoError("restore_failed", "A file could not be written; every touched file was put back from "
                                               f"pre-restore checkpoint {pre['id']}.", pre_restore=pre["id"],
                             journal=jid, cause=type(exc).__name__) from exc
        final = _capture(project, store)
        post = _write_checkpoint(project, store, final, "restore", via=via, label=f"Restored {m['id']}",
                                 extra={"restored_from": m["id"], "pre_restore": pre["id"]})
        journal.update(state="complete", post_restore=post["id"], verified=final["revision"] == plan["result_revision"])
        _write_journal(folder, journal)
        shutil.rmtree(contained(store, staged, what="staged files"), ignore_errors=True)
    from .validate import validate_project
    try:
        v = validate_project(workspace, slug, catalog)
        validation = {"ok": v["ok"], "counts": v["counts"], "errors": v["errors"][:20]}
    except KosmoError as exc:
        validation = {"ok": False, "error": exc.to_dict()}
    return {**view, "preview": False, "written": True, "pre_restore": _summary(pre), "post_restore": _summary(post),
            "revision": final["revision"], "verified": final["revision"] == plan["result_revision"],
            "journal": jid, "validation_after": validation,
            "note": "Restored. The restored files may be an older, broken state; check validation_after."}


def recover_restore(workspace: Path, slug: str, body: dict[str, Any]) -> dict[str, Any]:
    """Put back files touched by an interrupted restore from its journal and pre-restore checkpoint."""
    project = open_project(workspace, slug)
    if body.get("confirm") is not True:
        raise KosmoError("confirm_required", "Recovery needs confirm: true.")
    jid = body.get("journal")
    if not isinstance(jid, str) or not JOURNAL_RE.match(jid):
        raise KosmoError("bad_request", "journal must be a restore journal id.")
    with project_lock(project):
        store = _store(project, create=False)
        found = [(p, j) for p, j in _journals(store) if p.name == jid]
        if not found:
            raise KosmoError("journal_missing", f"Restore journal {jid} does not exist.")
        folder, journal = found[0]
        if journal.get("state") in ("complete", "rolled_back", "recovered"):
            return {"journal": jid, "state": journal["state"], "written": False}
        ops = journal.get("ops")
        if not isinstance(ops, list):
            raise KosmoError("journal_corrupt", "The restore journal cannot be read; restore its pre-restore "
                                                "checkpoint instead.")
        for op in ops:
            path_role(slug, op.get("path"))
        problems = _revert(project, store, ops)  # type: ignore[arg-type]
        journal.update(state="recovered" if not problems else "rollback_failed", problems=problems)
        _write_journal(folder, journal)
    return {"journal": jid, "state": journal["state"], "problems": problems, "written": True,
            "pre_restore": journal.get("pre_restore")}


# ---------- one entry point for CLI, MCP and the browser ----------

ACTIONS: dict[str, set[str]] = {
    "checkpoint": {"label", "note", "actor", "expected_revision"},
    "review": {"reviewer_kind", "reviewer", "note", "label", "checkpoint", "expected_revision"},
    "restore": {"checkpoint", "preview", "expected_revision", "plan_hash", "confirm"},
    "recover": {"journal", "confirm"},
}


def save_revisions(workspace: Path, slug: str, body: Any, catalog: Any = None, via: str = "api") -> dict[str, Any]:
    """body.action: checkpoint | review | restore (preview true by default) | recover."""
    if not isinstance(body, dict) or body.get("action") not in ACTIONS:
        raise KosmoError("bad_request", f"action must be one of {sorted(ACTIONS)}.")
    action = body["action"]
    extra = set(body) - ACTIONS[action] - {"action"}
    if extra:
        raise KosmoError("bad_request", f"Unexpected fields for {action}: {sorted(extra)}.")
    if action == "checkpoint":
        return create_checkpoint(workspace, slug, body, via)
    if action == "review":
        return mark_review(workspace, slug, body, via)
    if action == "recover":
        return recover_restore(workspace, slug, body)
    if body.get("preview", True) is not False:
        return preview_restore(workspace, slug, body)
    return apply_restore(workspace, slug, body, via, catalog)


def revisions_state(workspace: Path, slug: str, kind: str) -> dict[str, Any]:
    """author_state kinds: revisions, revisions:baseline, revisions:<checkpoint id> (compare with current)."""
    if kind == "revisions":
        return revision_state(workspace, slug)
    return compare(workspace, slug, kind.split(":", 1)[1])
