"""Project-local reference snapshot: the catalog data and local reference art one project needs, kept inside it.

A snapshot lets a project be browsed and edited without the external dom6inspector checkout. It is a local
authoring reference, separate from the distributable mod: exports and Workshop folders are built only from the
project's mod folder, so nothing here is ever packaged.

Layout under <project>/.kosmokrator/reference/ (copied with the project folder; ignored by the project .gitignore):
  current.json             pointer {"schema": 1, "snapshot": "<id>"}, replaced atomically after a snapshot is complete
  <id>/manifest.json       source, version, provenance, scope, per-file SHA-256 and the missing-dependency report
  <id>/NOTICE.txt          attribution and the local-only notice
  <id>/catalog/            dom6inspector layout: LICENSE, gamedata/*.csv (every top-level table, unmodified) and
                           images/{magicicons,abilityicons,items,sprites}/ (sprites: referenced units or all)
  <id>/trait-icons/        verified native UI icons copied from the workspace cache, when that cache is present

A project with a snapshot reads only that snapshot (never the live catalog as well), so versions are not mixed.
Status compares it with the live catalog when one is configured. Paths in the manifest are project-relative.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import secrets
import shutil
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from . import __version__
from .catalog import Catalog
from .errors import KosmoError
from .paths import atomic_write_bytes, contained, is_link
from .project import Project, open_project, project_lock, read_dm, resolve_dm_target, sha256_bytes

REF_DIR = "reference"
POINTER = "current.json"
MANIFEST = "manifest.json"
SCHEMA = "kosmokrator.reference/1"
SNAP_RE = re.compile(r"^snap-\d{8}T\d{6}Z-[0-9a-f]{8}$")
STAGING_RE = re.compile(r"^\.staging-snap-\d{8}T\d{6}Z-[0-9a-f]{8}$")
TABLE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*\.csv$")
SPRITE_RE = re.compile(r"^(\d{4,6})_([12])\.png$")
ITEM_RE = re.compile(r"^item([1-9]\d{0,4})\.png$")
# Fixed allow-list of native icon files the browser serves (gem, path and the sacred badge).
MAGIC_ICONS = tuple([f"Gem_{p}.png" for p in "FAWESDNGBH"] + [f"Path_{p}.png" for p in "FAWESDNGBHU"])
ABILITY_ICONS = ("holy.png",)
SPRITE_SCOPES = ("referenced", "all")
PART_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")
PNG_SIG = b"\x89PNG\r\n\x1a\n"
# Bounds for one snapshot. The full dom6inspector sprite folder is about 15 MB of data in about 8,800 small
# files (more on disk, because of file system block size).
MAX_FILES = 12000
MAX_BYTES = 192 * 1024 * 1024
MAX_TABLES = 200
MAX_TABLE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_BYTES = 1024 * 1024
MAX_LICENSE_BYTES = 256 * 1024
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_POINTER_BYTES = 4096
LOCAL_NOTICE = ("Local authoring reference only. This snapshot contains game imagery extracted from a locally owned "
                "copy of Dominions 6 (catalog sprites, item and magic icons, and native UI icons when present). It is "
                "separate from the distributable mod: exports and Workshop folders never include it. Do not "
                "redistribute it.")
TABLES_NOTE = ("Every top-level gamedata table of the source catalog, copied byte for byte, so lookups, inheritance and "
               "search read the same rows as the live catalog. The per-object description text folders "
               "(gamedata/unitdescr, spelldescr, itemdescr) are not copied; Kosmokrator does not read them.")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- reading ----------

def _ref_root(project: Project) -> Path:
    contained(project.root, project.state_dir, what="state directory")
    return contained(project.root, project.state_dir / REF_DIR, what="reference directory")


def _pointer(project: Project) -> str | None:
    """The current snapshot id, None when there is none; a malformed pointer is an error, never ignored."""
    root = _ref_root(project)
    if not root.exists():
        return None
    if is_link(root) or not root.is_dir():
        raise KosmoError("reference_invalid", "The reference folder is a link or not a folder.")
    ptr = contained(root, POINTER, what="reference pointer")
    if not ptr.exists():
        return None
    if is_link(ptr) or not ptr.is_file() or ptr.stat().st_size > MAX_POINTER_BYTES:
        raise KosmoError("reference_invalid", "The reference pointer is not a small regular file.")
    try:
        data = json.loads(ptr.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise KosmoError("reference_invalid", "The reference pointer cannot be read.") from exc
    sid = data.get("snapshot") if isinstance(data, dict) and data.get("schema") == 1 else None
    if not isinstance(sid, str) or not SNAP_RE.match(sid):
        raise KosmoError("reference_invalid", "The reference pointer does not name a snapshot.")
    return sid


def _walk_files(base: Path) -> dict[str, Path]:
    """Regular files under base keyed by posix relative path; any link or junction is refused."""
    out: dict[str, Path] = {}
    if is_link(base):
        raise KosmoError("reference_invalid", "A snapshot folder is a link or junction.")
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        d = Path(dirpath)
        for name in [*dirnames, *filenames]:
            if is_link(d / name):
                raise KosmoError("reference_invalid", "The snapshot contains a link or junction.",
                                 path=(d / name).relative_to(base).as_posix())
        for name in filenames:
            out[(d / name).relative_to(base).as_posix()] = d / name
        if len(out) > MAX_FILES + 8:
            raise KosmoError("reference_invalid", "The snapshot holds more files than allowed.")
    return out


_LOAD_LOCK = threading.Lock()
_LOADED: dict[tuple, tuple[Catalog, dict[str, Any]]] = {}
# Recorded SHA-256 of every snapshot file, keyed by the snapshot catalog root, for verified image reads.
_FILE_SHA: dict[str, dict[str, str]] = {}


def _load_snapshot(project: Project, sid: str) -> tuple[Catalog, dict[str, Any]]:
    """Verify one snapshot (exact file set, sizes and SHA-256) and return a Catalog reading only from it."""
    snap = contained(_ref_root(project), sid, what="reference snapshot")
    man_path = contained(snap, MANIFEST, what="reference manifest")
    if is_link(snap) or not snap.is_dir() or is_link(man_path) or not man_path.is_file():
        raise KosmoError("reference_invalid", f"Snapshot {sid} is missing or not a regular folder.")
    st = man_path.stat()
    # Tables are re-verified whenever one changes on disk; images are verified on every read (read_verified).
    gamedata_dir = snap / "catalog" / "gamedata"
    # Folder mtimes change when an entry (such as a planted link) is added, so the full check runs again.
    folders = [snap, snap / "catalog", gamedata_dir, snap / "catalog" / "images", snap / "trait-icons",
               *(snap / "catalog" / "images" / f for f in ("magicicons", "abilityicons", "items", "sprites"))]
    try:
        table_stats = tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(gamedata_dir.iterdir()))
        folder_stats = tuple((os.lstat(f).st_mtime_ns, is_link(f)) if os.path.lexists(f) else None for f in folders)
    except OSError:
        table_stats, folder_stats = (), ()
    key = (str(snap), st.st_mtime_ns, st.st_size, table_stats, folder_stats)
    with _LOAD_LOCK:
        if key in _LOADED:
            return _LOADED[key]
    if st.st_size > MAX_MANIFEST_BYTES:
        raise KosmoError("reference_invalid", "The snapshot manifest is too large.")
    try:
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise KosmoError("reference_invalid", "The snapshot manifest cannot be read.") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA or manifest.get("snapshot") != sid \
            or not isinstance(manifest.get("files"), list):
        raise KosmoError("reference_invalid", "The snapshot manifest has an unexpected format.")
    listed = {f.get("path"): f for f in manifest["files"] if isinstance(f, dict)}
    found = _walk_files(snap)
    found.pop(MANIFEST, None)
    if set(found) != set(listed):
        extra, missing = sorted(set(found) - set(listed)), sorted(set(listed) - set(found))
        raise KosmoError("reference_invalid", "Snapshot files do not match the manifest.",
                         problems=[*(f"unlisted: {p}" for p in extra[:10]), *(f"missing: {p}" for p in missing[:10])])
    for rel, path in found.items():
        rec = listed[rel]
        if rel.startswith("catalog/images/"):
            # Catalog images: size here, SHA-256 on every read (read_verified), so large sets load quickly.
            ok = path.stat().st_size == rec.get("bytes")
        else:
            data = path.read_bytes()
            ok = len(data) == rec.get("bytes") and sha256_bytes(data) == rec.get("sha256")
        if not ok:
            raise KosmoError("reference_invalid", "A snapshot file does not match its recorded SHA-256.",
                             problems=[rel])
    gamedata = snap / "catalog" / "gamedata"
    if not (gamedata / "BaseU.csv").is_file():
        raise KosmoError("reference_invalid", "The snapshot holds no catalog tables.")
    src = manifest.get("source") or {}
    meta = {
        "catalog_path": f".kosmokrator/{REF_DIR}/{sid}/catalog",
        "source": src.get("source"), "source_url": src.get("source_url"), "revision": src.get("revision"),
        "dataset_version": src.get("dataset_version"),
        "dataset_version_source": f"project reference snapshot {sid} (captured from {src.get('dataset_version_source')})",
        "disclaimer": src.get("disclaimer"),
        "reference_snapshot": {"project": project.slug, "snapshot": sid, "created_utc": manifest.get("created_utc"),
                               "tables": "complete", "sprites": (manifest.get("scope") or {}).get("sprites"),
                               "local_only": True},
    }
    result = (Catalog(snap / "catalog", gamedata, meta), manifest)
    with _LOAD_LOCK:
        if len(_LOADED) >= 16:
            _LOADED.clear()
            _FILE_SHA.clear()
        _LOADED[key] = result
        _FILE_SHA[str(snap / "catalog")] = {rel: rec.get("sha256") for rel, rec in listed.items()}
    return result


def project_reference(workspace: Path, slug: str) -> tuple[Catalog | None, dict[str, Any] | None, str | None]:
    """(snapshot catalog, manifest, snapshot id) for a project; (None, None, None) without a snapshot.

    A snapshot that exists but fails verification raises reference_invalid instead of falling back."""
    project = open_project(workspace, slug)
    sid = _pointer(project)
    if sid is None:
        return None, None, None
    cat, manifest = _load_snapshot(project, sid)
    return cat, manifest, sid


def resolve_catalog(workspace: Path, slug: str, live: Catalog | None, live_error: dict[str, Any] | None
                    ) -> tuple[Catalog | None, dict[str, Any] | None]:
    """The catalog a project reads: its own snapshot if it has one, otherwise the live catalog (unchanged)."""
    try:
        cat, _manifest, sid = project_reference(workspace, slug)
    except KosmoError as exc:
        if exc.code == "reference_invalid":
            return None, {"code": exc.code, "message": f"{exc.message} The project's reference snapshot is not used "
                          "and the live catalog is not substituted. Recreate the snapshot from a live catalog."}
        raise
    if sid is None:
        return live, live_error
    return cat, None


def read_verified(catalog: Catalog | None, path: Path) -> bytes | None:
    """Bytes of one catalog file. For a snapshot catalog they must match the manifest SHA-256 (else None)."""
    if catalog is None or not (catalog.meta or {}).get("reference_snapshot"):
        return path.read_bytes()
    with _LOAD_LOCK:
        records = _FILE_SHA.get(str(catalog.root))
    try:
        rel = "catalog/" + path.relative_to(catalog.root).as_posix()
    except ValueError:
        return None
    if records is None or rel not in records or is_link(path) or not path.is_file():
        return None
    data = path.read_bytes()
    return data if sha256_bytes(data) == records[rel] else None


def snapshot_trait_icon_dir(workspace: Path, slug: str) -> tuple[str, Path] | None:
    """(snapshot id, verified trait-icons folder) when the project's snapshot carries native UI icons."""
    cat, _manifest, sid = project_reference(workspace, slug)
    if cat is None or sid is None:
        return None
    path = cat.root.parent / "trait-icons"
    return (sid, path) if (path / "manifest.json").is_file() else None


# ---------- comparing ----------

_FP_LOCK = threading.Lock()
_FP: dict[tuple, str] = {}


def _tables_of(gamedata: Path) -> list[Path]:
    return sorted((p for p in gamedata.iterdir() if TABLE_RE.match(p.name) and p.is_file() and not is_link(p)),
                  key=lambda p: p.name)


def _live_fingerprint(live: Catalog) -> str:
    """SHA-256 over (table name, table SHA-256) of the live catalog, cached by name/size/mtime."""
    tables = _tables_of(live.gamedata)
    key = (str(live.gamedata), *((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in tables))
    with _FP_LOCK:
        if key in _FP:
            return _FP[key]
    h = hashlib.sha256()
    for p in tables:
        h.update(f"{p.name}:{sha256_bytes(p.read_bytes())};".encode())
    out = h.hexdigest()
    with _FP_LOCK:
        if len(_FP) > 8:
            _FP.clear()
        _FP[key] = out
    return out


def _version(meta: dict[str, Any] | None) -> dict[str, Any]:
    meta = meta or {}
    return {"dataset_version": meta.get("dataset_version"), "revision": meta.get("revision")}


# ---------- referenced data ----------

def _int(v: Any) -> int | None:
    s = str(v).strip() if v is not None else ""
    return int(s) if s.lstrip("-").isdigit() else None


def referenced(model: dict[str, Any]) -> dict[str, set[int]]:
    """Catalog unit and item ids a built project model refers to.

    Units: catalog monster references of every object, #copystats donors, #copyspr, #selectmonster targets,
    catalog pretender candidates and the default balance reference rosters. Items: catalog item references,
    #selectitem targets and item #copyspr."""
    units: set[int] = set()
    items: set[int] = set()
    for group in ("nations", "monsters", "sites", "other_definitions"):
        for obj in model.get(group) or []:
            for use in obj.get("uses") or []:
                if use.get("origin") == "catalog" and isinstance(use.get("id"), int):
                    if use.get("context") == "monster":
                        units.add(use["id"])
                    elif use.get("context") == "item":
                        items.add(use["id"])
    project_ids = {u.get("id") for u in model.get("monsters") or [] if u.get("new")}
    for u in model.get("monsters") or []:
        donor = u.get("donor") or {}
        if isinstance(donor.get("id"), int):
            units.add(donor["id"])
        if not u.get("new") and isinstance(u.get("id"), int):
            units.add(u["id"])
        for s in u.get("authored") or []:
            if s.get("command") == "#copyspr" and s.get("args"):
                v = _int(s["args"][0])
                if v is not None:
                    units.add(v)
    for g in (model.get("pretenders") or {}).get("gods") or []:
        if g.get("source") == "catalog" and isinstance(g.get("id"), int):
            units.add(g["id"])
    for n in (model.get("balance") or {}).get("reference_nations") or []:
        for u in n.get("units") or []:
            if u.get("origin") == "catalog" and isinstance(u.get("id"), int):
                units.add(u["id"])
    for d in model.get("other_definitions") or []:
        opener = str(d.get("opener") or "").lower()
        if opener == "#selectitem" and isinstance(d.get("id"), int):
            items.add(d["id"])
        if opener in ("#newitem", "#selectitem"):
            for s in d.get("authored") or []:
                if str(s.get("command") or "").lower() == "#copyspr" and s.get("args"):
                    v = _int(s["args"][0])
                    if v is not None:
                        items.add(v)
    return {"units": {i for i in units if i >= 0 and i not in project_ids}, "items": {i for i in items if i > 0}}


# ---------- status ----------

def reference_status(workspace: Path, slug: str, live: Catalog | None, model: dict[str, Any] | None = None
                     ) -> dict[str, Any]:
    """Snapshot state for one project: none, offline (in use, no live catalog), current, stale or invalid."""
    out: dict[str, Any] = {"schema": SCHEMA, "project": slug, "notice": LOCAL_NOTICE,
                           "live": {"available": live is not None, **_version(live.meta if live else None)}}
    try:
        cat, manifest, sid = project_reference(workspace, slug)
    except KosmoError as exc:
        if exc.code != "reference_invalid":
            raise
        return {**out, "state": "invalid", "active": False, "snapshot": None,
                "error": {"code": exc.code, "message": exc.message,
                          "problems": exc.details.get("problems") if isinstance(exc.details, dict) else None},
                "summary": "The reference snapshot failed verification and is not used. No catalog data is "
                           "substituted for this project until it is recreated from a live catalog."}
    if sid is None:
        return {**out, "state": "none", "active": False, "snapshot": None,
                "summary": "No reference snapshot. This project reads the live catalog the server was started with."
                           if live else "No reference snapshot and no live catalog: vanilla references are unresolved."}
    assert cat is not None and manifest is not None
    snap_version = _version(cat.meta)
    if live is None:
        state, summary = "offline", ("Using this project's reference snapshot. No live catalog is configured, so it "
                                     "cannot be compared or refreshed.")
        same = None
    else:
        same = snap_version == _version(live.meta) and \
            (manifest.get("tables") or {}).get("fingerprint") == _live_fingerprint(live)
        state = "current" if same else "stale"
        summary = ("Using this project's reference snapshot; it matches the live catalog." if same else
                   "Using this project's reference snapshot, which differs from the live catalog. The snapshot stays "
                   "in use (versions are never mixed) until you refresh it.")
    coverage = manifest.get("scope") or {}
    have = set(coverage.get("sprite_units") or [])
    now_missing: list[int] = []
    project_changed = None
    if model is not None:
        refs = referenced(model)
        units_table = {_int(r.get("id")) for r in cat.table("units")}
        now_missing = sorted(i for i in refs["units"] if i in units_table and i not in have)
        project_changed = ((model.get("provenance") or {}).get("sha256") != manifest.get("project_sha256"))
        if coverage.get("sprites") == "all":
            now_missing = []
    return {**out, "state": state, "active": True, "snapshot": sid, "summary": summary,
            "matches_live": same, "created_utc": manifest.get("created_utc"),
            "tool_version": manifest.get("tool_version"), "source": manifest.get("source"),
            "version": snap_version, "scope": {k: v for k, v in coverage.items() if k != "sprite_units"},
            "totals": manifest.get("totals"), "groups": manifest.get("groups"),
            "missing": manifest.get("missing"), "trait_icons": manifest.get("trait_icons"),
            "project_sha256_at_snapshot": manifest.get("project_sha256"), "project_changed": project_changed,
            "sprites_missing_now": now_missing[:200], "sprites_missing_now_count": len(now_missing)}


def workspace_reference_summary(workspace: Path, live: Catalog | None) -> dict[str, Any]:
    """Which projects in the workspace read a reference snapshot (for server metadata)."""
    from .project import META_FILE
    from .paths import SLUG_RE
    items = []
    for entry in sorted(workspace.iterdir(), key=lambda p: p.name):
        if is_link(entry) or not entry.is_dir() or not SLUG_RE.match(entry.name) or not (entry / META_FILE).is_file():
            continue
        try:
            st = reference_status(workspace, entry.name, live)
        except (KosmoError, OSError, ValueError):
            continue
        if st["state"] != "none":
            items.append({"slug": entry.name, "state": st["state"], "snapshot": st.get("snapshot"),
                          **(st.get("version") or {})})
    return {"projects_with_snapshot": len(items), "projects": items,
            "note": "Projects listed here read their own reference snapshot instead of the live catalog."}


# ---------- creating ----------

def _portable_url(url: Any) -> str | None:
    """Origin URL without credentials; local paths are omitted from the portable manifest."""
    if not isinstance(url, str) or not url:
        return None
    if url.startswith("git@") and ":" in url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https", "ssh", "git") or not parts.hostname:
        return None
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _source_file(base: Path, name: str, limit: int) -> bytes | None:
    """A regular, bounded file directly inside base (no links); None when absent."""
    path = base / name
    if is_link(base) or is_link(path) or not path.is_file():
        return None
    if path.stat().st_size > limit:
        raise KosmoError("reference_too_large", f"Catalog file {name} is larger than allowed.")
    return path.read_bytes()


def _source_stat(base: Path, name: str, limit: int) -> tuple[Path, int] | None:
    """(path, size) of a regular, bounded image directly inside base (no links); None when absent or too large."""
    path = base / name
    try:
        if is_link(base) or is_link(path) or not path.is_file():
            return None
        size = path.stat().st_size
    except OSError:
        return None
    return (path, size) if 8 <= size <= limit else None


def _plan(project: Project, live: Catalog, model: dict[str, Any], sprites: str) -> dict[str, Any]:
    """Every file to copy plus the missing-dependency report; nothing is written.

    Tables and the licence are read here (their hashes form the fingerprint). Images are planned from their sizes
    and read once, when the snapshot is written."""
    gamedata = live.gamedata
    repo = gamedata.parent
    images = repo / "images"
    for part in (gamedata, repo, images):
        if is_link(part):
            raise KosmoError("symlink_rejected", "The live catalog path contains a link or junction.")
    files: dict[str, bytes | Path] = {}
    groups: dict[str, dict[str, Any]] = {}
    missing: list[dict[str, Any]] = []
    total = 0

    def add(group: str, rel: str, data: bytes | tuple[Path, int]) -> None:
        nonlocal total
        size = len(data) if isinstance(data, bytes) else data[1]
        files[rel] = data if isinstance(data, bytes) else data[0]
        total += size
        g = groups.setdefault(group, {"files": 0, "bytes": 0})
        g["files"] += 1
        g["bytes"] += size
        if len(files) > MAX_FILES or total > MAX_BYTES:
            raise KosmoError("reference_too_large", f"The snapshot would exceed {MAX_FILES} files or "
                             f"{MAX_BYTES // (1024 * 1024)} MB; nothing was written.")

    tables = _tables_of(gamedata)
    if len(tables) > MAX_TABLES or not any(p.name == "BaseU.csv" for p in tables):
        raise KosmoError("catalog_incomplete", "The live catalog's gamedata folder is not a usable dom6inspector table set.")
    fp = hashlib.sha256()
    for p in tables:
        data = _source_file(gamedata, p.name, MAX_TABLE_BYTES)
        if data is None:
            continue
        add("tables", f"catalog/gamedata/{p.name}", data)
        fp.update(f"{p.name}:{sha256_bytes(data)};".encode())
    lic = _source_file(repo, "LICENSE", MAX_LICENSE_BYTES)
    if lic is not None:
        add("license", "catalog/LICENSE", lic)
    else:
        missing.append({"kind": "license", "name": "LICENSE", "reason": "the source catalog has no LICENSE file"})
    for folder, names, group in (("magicicons", MAGIC_ICONS, "magic_icons"), ("abilityicons", ABILITY_ICONS, "ability_icons")):
        for name in names:
            data = _source_stat(images / folder, name, MAX_IMAGE_BYTES)
            if data is None:
                missing.append({"kind": group[:-1], "name": name, "reason": "not in the source catalog"})
            else:
                add(group, f"catalog/images/{folder}/{name}", data)
    # Every catalog item icon (about 1.5 MB): item references are cheap to keep complete.
    item_dir = images / "items"
    item_ids: set[int] = set()
    if item_dir.is_dir() and not is_link(item_dir):
        for p in sorted(item_dir.iterdir(), key=lambda x: x.name):
            mi = ITEM_RE.match(p.name)
            if mi:
                data = _source_stat(item_dir, p.name, MAX_IMAGE_BYTES)
                if data is not None:
                    add("item_icons", f"catalog/images/items/{p.name}", data)
                    item_ids.add(int(mi.group(1)))
    refs = referenced(model)
    for i in sorted(refs["items"] - item_ids):
        missing.append({"kind": "item_icon", "id": i, "reason": "referenced item has no icon in the source catalog"})
    units_table = {_int(r.get("id")) for r in live.table("units")}
    sprite_dir = images / "sprites"
    if is_link(sprite_dir):
        raise KosmoError("symlink_rejected", "The catalog sprite folder is a link or junction.")
    wanted: list[int]
    if sprites == "all":
        wanted = sorted({int(m.group(1)) for m in (SPRITE_RE.match(n) for n in (os.listdir(sprite_dir) if sprite_dir.is_dir() else [])) if m})
    else:
        wanted = sorted(refs["units"])
    sprite_units = []
    for uid in wanted:
        if uid not in units_table and sprites != "all":
            missing.append({"kind": "unit", "id": uid, "reason": "referenced unit is not in the catalog table"})
            continue
        got = 0
        for frame in ("1", "2"):
            name = f"{uid:04d}_{frame}.png"
            data = _source_stat(sprite_dir, name, MAX_IMAGE_BYTES)
            if data is not None:
                add("sprites", f"catalog/images/sprites/{name}", data)
                got += 1
            elif sprites != "all":
                missing.append({"kind": "sprite", "id": uid, "frame": "idle" if frame == "1" else "attack",
                                "reason": "no sprite file in the source catalog"})
        if got:
            sprite_units.append(uid)
    return {"files": files, "groups": groups, "missing": missing, "total": total, "fingerprint": fp.hexdigest(),
            "tables": [p.name for p in tables], "sprite_units": sprite_units, "refs": refs}


def _trait_icon_files(workspace: Path) -> tuple[dict[str, bytes], dict[str, Any] | None]:
    """Verified native trait/stat icons from the workspace cache, re-hashed against its manifest."""
    from .trait_icons import CACHE_NAME, MAX_ICON_BYTES, MISC_SHA256
    from .trait_icon_data import RES_SHA256
    try:
        cache = contained(workspace, CACHE_NAME, what="native icon cache")
        man_path = contained(cache, "manifest.json", what="icon manifest")
        if is_link(cache) or not man_path.is_file() or man_path.stat().st_size > 128 * 1024:
            return {}, None
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, KosmoError):
        return {}, None
    if not isinstance(manifest, dict) or manifest.get("schema") != 1 or manifest.get("archive_sha256") != RES_SHA256:
        return {}, None
    out: dict[str, bytes] = {}
    kept: dict[str, Any] = {"schema": 1, "archive_sha256": RES_SHA256, "sprites": {}}

    def take(records: Any, prefix: str, target: dict[str, Any]) -> None:
        for idx, rec in (records or {}).items() if isinstance(records, dict) else []:
            if not str(idx).isdigit() or not isinstance(rec, dict):
                continue
            name = f"{prefix}{int(idx)}.png"
            data = _source_file(cache, name, MAX_ICON_BYTES)
            if data is not None and sha256_bytes(data) == rec.get("sha256"):
                out[name] = data
                target[str(int(idx))] = {k: rec.get(k) for k in ("width", "height", "sha256")}

    take(manifest.get("sprites"), "", kept["sprites"])
    if manifest.get("misc_archive_sha256") == MISC_SHA256:
        kept.update(misc_archive_sha256=MISC_SHA256, misc_sprites={})
        take(manifest.get("misc_sprites"), "misc-", kept["misc_sprites"])
    if not out:
        return {}, None
    return out, kept


def _rmtree_contained(root: Path, path: Path) -> bool:
    """Remove a snapshot or staging folder this module owns; links are never followed."""
    try:
        contained(root, path, what="reference folder")
        if is_link(path) or not path.is_dir():
            return False
        _walk_files(path)  # refuses links/junctions anywhere inside
        shutil.rmtree(path)
        return True
    except (OSError, KosmoError):
        return False


def create_snapshot(workspace: Path, slug: str, live: Catalog | None, body: Any) -> dict[str, Any]:
    """Preview or write a reference snapshot of exactly the saved revision the caller saw.

    Body: expected_sha256 (saved .dm), expected_snapshot (current snapshot id, or null when there is none),
    sprites ("referenced" or "all") and preview (bool). Under the project lock the new snapshot is written to a
    staging folder, renamed into place and only then made current; the previous snapshot is removed afterwards."""
    from .browse import build_project_model
    if not isinstance(body, dict) or set(body) - {"expected_sha256", "expected_snapshot", "sprites", "preview"}:
        raise KosmoError("bad_request", "Body needs expected_sha256, expected_snapshot, optional sprites and preview.")
    expected = body.get("expected_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise KosmoError("bad_request", "expected_sha256 (64 hex characters of the saved .dm) is required.")
    if "expected_snapshot" not in body or not (body["expected_snapshot"] is None or (
            isinstance(body["expected_snapshot"], str) and SNAP_RE.match(body["expected_snapshot"]))):
        raise KosmoError("bad_request", "expected_snapshot must be the current snapshot id, or null when there is none.")
    sprites = body.get("sprites", "referenced")
    if sprites not in SPRITE_SCOPES:
        raise KosmoError("bad_request", "sprites must be 'referenced' or 'all'.", field="sprites")
    preview = body.get("preview", False) is True
    if live is None:
        raise KosmoError("catalog_missing", "A live catalog (--catalog or KOSMOKRATOR_CATALOG) is needed to create "
                         "or refresh a reference snapshot. Any existing snapshot stays in use.")
    project = open_project(workspace, slug)
    with project_lock(project):
        dm = sha256_bytes(read_dm(resolve_dm_target(project, None))[0])
        if dm != expected.lower():
            raise KosmoError("sha_mismatch", "The saved .dm is not the revision shown; reload first.",
                             expected=expected.lower(), actual=dm)
        try:
            current = _pointer(project)
        except KosmoError:
            current = "invalid"
        if current != body["expected_snapshot"] and not (current == "invalid" and body["expected_snapshot"] is None):
            raise KosmoError("reference_changed", "The project's reference snapshot changed since this page loaded; "
                             "reload first.", expected=body["expected_snapshot"], actual=current)
        model = build_project_model(workspace, slug, live)
        plan = _plan(project, live, model, sprites)
        icons, icon_manifest = _trait_icon_files(workspace)
        for name, data in icons.items():
            plan["files"][f"trait-icons/{name}"] = data
            plan["groups"].setdefault("trait_icons", {"files": 0, "bytes": 0})
            plan["groups"]["trait_icons"]["files"] += 1
            plan["groups"]["trait_icons"]["bytes"] += len(data)
            plan["total"] += len(data)
        if icon_manifest:
            imdata = (json.dumps(icon_manifest, indent=2) + "\n").encode("utf-8")
            plan["files"]["trait-icons/manifest.json"] = imdata
            plan["total"] += len(imdata)
        else:
            plan["missing"].append({"kind": "trait_icons", "reason": "no verified native UI icon cache in the "
                                    "workspace (kosmokrator trait-icons --game ...); trait labels stay text-only"})
        if len(plan["files"]) > MAX_FILES or plan["total"] > MAX_BYTES:
            raise KosmoError("reference_too_large", "The snapshot would exceed the size limits; nothing was written.")
        meta = live.meta
        ver = meta.get("dataset_version")
        source = {"name": "dom6inspector", "source": meta.get("source"),
                  "source_url": _portable_url(meta.get("source_url")), "revision": meta.get("revision"),
                  "dataset_version": ver,
                  "dataset_version_source": f"index.html ('[ver {ver}]')" if ver else "unknown (no version marker)",
                  "license": "GPL-3.0 (catalog/LICENSE, copied from the source checkout)",
                  "attribution": "Game-data tables and images from dom6inspector by larzm42 "
                                 "(https://github.com/larzm42/dom6inspector). Dominions 6 and its artwork belong to "
                                 "Illwinter Game Design.",
                  "disclaimer": meta.get("disclaimer")}
        summary = {
            "sprites": sprites, "tables": "complete", "tables_note": TABLES_NOTE, "table_count": len(plan["tables"]),
            "item_icons": "complete" if plan["groups"].get("item_icons") else "none in source",
            "magic_icons": "fixed set (gem and path icons)", "ability_icons": "fixed set (sacred badge)",
            "sprite_units_count": len(plan["sprite_units"]),
            "sprites_note": ("Every unit sprite in the source catalog." if sprites == "all" else
                             "Only sprites of catalog units this project referenced when the snapshot was made. Other "
                             "catalog units (for example new comparison picks) show no sprite until the snapshot is "
                             "refreshed with all sprites."),
            "trait_icons": bool(icon_manifest),
            "excluded": ["gamedata/unitdescr, spelldescr, itemdescr (description text, not read by Kosmokrator)",
                         "images/sites and other catalog images not used by Kosmokrator", ".git, scripts, mods, manuals",
                         "game archives and any other user files"],
        }
        totals = {"files": len(plan["files"]), "bytes": plan["total"]}
        result = {"project": slug, "preview": preview, "sprites": sprites, "replaces": current,
                  "source": source, "scope": summary, "totals": totals, "groups": plan["groups"],
                  "missing": plan["missing"][:500], "missing_count": len(plan["missing"]), "notice": LOCAL_NOTICE}
        if preview:
            return result
        root = _ref_root(project)
        contained(project.root, project.state_dir, what="state directory")
        project.state_dir.mkdir(exist_ok=True)
        root.mkdir(exist_ok=True)
        root = _ref_root(project)
        if is_link(root):
            raise KosmoError("symlink_rejected", "The reference folder is a link or junction.")
        # Leftover staging folders from an interrupted run are ours to clear.
        for entry in list(root.iterdir()):
            if STAGING_RE.match(entry.name):
                _rmtree_contained(root, entry)
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        sid = f"snap-{stamp}-{secrets.token_hex(4)}"
        staging = contained(root, f".staging-{sid}", what="reference staging")
        os.mkdir(staging)
        try:
            notice = (f"Kosmokrator reference snapshot {sid} for project '{slug}'\n\n{LOCAL_NOTICE}\n\n"
                      f"{source['attribution']}\nCatalog revision: {source['revision'] or 'unknown'}; "
                      f"dataset version: {ver or 'unknown'}. Catalog licence: catalog/LICENSE (GPL-3.0).\n"
                      "Native UI icons in trait-icons/ were decoded locally from the user's own game files.\n")
            plan["files"]["NOTICE.txt"] = notice.encode("utf-8")
            records = []
            rels = sorted(plan["files"])
            if any(not all(PART_RE.match(part) for part in rel.split("/")) for rel in rels):
                raise KosmoError("bad_path", "Unexpected snapshot file name; nothing was written.")
            # Folders are created and checked once; file names were rebuilt from fixed patterns above.
            for folder in sorted({rel.rsplit("/", 1)[0] for rel in rels if "/" in rel}):
                d = contained(staging, folder, what="reference folder")
                d.mkdir(parents=True, exist_ok=True)
                contained(staging, d, what="reference folder")
            written = 0
            for rel in rels:
                src = plan["files"][rel]
                if isinstance(src, Path):
                    data = _source_file(src.parent, src.name, MAX_IMAGE_BYTES)
                    if data is None or data[:8] != PNG_SIG:
                        raise KosmoError("catalog_changed", f"Catalog image {src.name} changed or is not a PNG; "
                                         "nothing was written.")
                else:
                    data = src
                written += len(data)
                if written > MAX_BYTES:
                    raise KosmoError("reference_too_large", "The snapshot grew past the size limit; nothing was written.")
                with open(staging.joinpath(*rel.split("/")), "xb") as fh:
                    fh.write(data)
                records.append({"path": rel, "sha256": sha256_bytes(data), "bytes": len(data)})
            totals = {"files": len(records), "bytes": sum(r["bytes"] for r in records)}
            manifest = {
                "schema": SCHEMA, "snapshot": sid, "project": slug, "created_utc": _now(),
                "tool": "kosmokrator", "tool_version": __version__, "project_sha256": dm,
                "local_only": True, "notice": LOCAL_NOTICE, "source": source,
                "tables": {"files": plan["tables"], "fingerprint": plan["fingerprint"], "complete": True},
                "scope": {**summary, "sprite_units": plan["sprite_units"]},
                "trait_icons": ({"archive_sha256": icon_manifest.get("archive_sha256"),
                                 "misc_archive_sha256": icon_manifest.get("misc_archive_sha256"),
                                 "icons": len(icons)} if icon_manifest else None),
                "groups": plan["groups"], "totals": totals,
                "missing": plan["missing"], "files": records,
            }
            with open(staging / MANIFEST, "x", encoding="utf-8", newline="\n") as fh:
                json.dump(manifest, fh, indent=1)
                fh.write("\n")
            final = contained(root, sid, what="reference snapshot")
            os.rename(staging, final)
        except BaseException:
            _rmtree_contained(root, staging)
            raise
        ptr = contained(root, POINTER, what="reference pointer")
        if is_link(ptr):
            _rmtree_contained(root, final)
            raise KosmoError("symlink_rejected", "The reference pointer is a link or junction.")
        try:
            _load_snapshot(project, sid)  # verify what was written before switching to it
            atomic_write_bytes(ptr, (json.dumps({"schema": 1, "snapshot": sid}) + "\n").encode("utf-8"))
        except BaseException:
            _rmtree_contained(root, final)
            raise
        removed = []
        for entry in list(root.iterdir()):
            if SNAP_RE.match(entry.name) and entry.name != sid and _rmtree_contained(root, entry):
                removed.append(entry.name)
    return {**result, "snapshot": sid, "totals": totals, "removed": removed,
            "path": f".kosmokrator/{REF_DIR}/{sid}"}
