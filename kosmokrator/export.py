"""Export an error-free project as <slug>/<slug>.dm plus referenced assets."""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import secrets
import shutil
import zipfile
from pathlib import Path
from typing import Any

from . import __version__
from .catalog import Catalog
from .errors import KosmoError
from .paths import contained, exact_case_lookup, is_link
from .project import Project, open_project, project_lock, read_dm, resolve_dm_target, sha256_bytes
from .validate import validate_project

MANIFEST_NAME = "kosmokrator-manifest.json"
# <slug>-<UTC stamp>[-<8 hex>]: names written by export_mod (CLI default) and export_revision (web).
EXPORT_TAIL = r"-\d{8}T\d{6}Z(?:-[0-9a-f]{8})?"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_LISTED_EXPORTS = 20


def _within(a: Path, b: Path) -> bool:
    try:
        a.relative_to(b)
        return True
    except ValueError:
        return False


def export_mod(workspace: Path, slug: str, dest: str | None = None, fmt: str = "zip",
               catalog: Catalog | None = None, dependencies: list[str] | None = None) -> dict[str, Any]:
    if fmt not in ("zip", "folder"):
        raise KosmoError("bad_format", "format must be 'zip' or 'folder'")
    project = open_project(workspace, slug)
    report = validate_project(workspace, slug, catalog=catalog, dependencies=dependencies)
    if not report["ok"]:
        raise KosmoError("validation_failed", "Export refused: validation reported errors",
                         counts=report["counts"], errors=report["errors"][:50])

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if dest:
        out = contained(workspace, dest, what="export destination")
    else:
        exports = project.root / "exports"
        exports.mkdir(exist_ok=True)
        out = exports / (f"{slug}-{stamp}.zip" if fmt == "zip" else f"{slug}-{stamp}")
        out = contained(workspace, out, what="export destination")
    resolved = out.resolve()
    for forbidden in (project.root / "mod", project.state_dir):
        if resolved == forbidden.resolve() or _within(resolved, forbidden.resolve()):
            raise KosmoError("self_export", "Export destination must not be inside the project's source or state "
                             "folders", dest=str(out))
    if out.exists():
        raise KosmoError("dest_exists", "Export destination already exists; refusing to overwrite", dest=str(out))
    if not out.parent.is_dir():
        raise KosmoError("dest_parent_missing", "Parent folder of the export destination does not exist",
                         dest=str(out))
    if fmt == "zip" and out.suffix.lower() != ".zip":
        raise KosmoError("bad_dest", "Zip export destination must end with .zip", dest=str(out))
    manifest_path = out.with_name(out.name + ".manifest.json") if fmt == "zip" else out / MANIFEST_NAME
    if fmt == "zip" and manifest_path.exists():
        raise KosmoError("dest_exists", "Manifest path already exists; refusing to overwrite", dest=str(manifest_path))

    # Collect payload from validated sources; re-check hashes and containment.
    dm_bytes = read_dm(resolve_dm_target(project, None))[0]
    if sha256_bytes(dm_bytes) != report["sha256"]:
        raise KosmoError("changed_during_export", ".dm changed after validation; retry")
    payload: list[tuple[str, bytes]] = [(f"{slug}/{slug}.dm", dm_bytes)]
    for ref in report["assets"]:
        found, why = exact_case_lookup(project.mod_dir, ref)
        if found is None:
            raise KosmoError("asset_changed", f"Asset {ref} is no longer valid ({why})")
        contained(project.mod_dir, found, what="asset")
        rel = "/".join(part for part in ref.split("/") if part not in ("", "."))
        payload.append((f"{slug}/{rel}", found.read_bytes()))

    files = [{"path": name, "sha256": sha256_bytes(data), "bytes": len(data)} for name, data in payload]
    created: list[Path] = []
    try:
        if fmt == "zip":
            with open(out, "xb") as fh:
                created.append(out)
                with zipfile.ZipFile(fh, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for name, data in payload:
                        zf.writestr(name, data)
            archive_sha = sha256_bytes(out.read_bytes())
        else:
            out.mkdir()
            created.append(out)
            for name, data in payload:
                target = out / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "xb") as fh:
                    fh.write(data)
            archive_sha = None
        manifest = {
            "tool": "kosmokrator", "tool_version": __version__, "created_utc": stamp,
            "project": slug, "format": fmt,
            "install_hint": f"Copy the '{slug}' folder (containing {slug}.dm) into the Dominions 6 user data "
                            "'mods' directory (Game Tools > Open User Data Directory).",
            "files": files, "archive_sha256": archive_sha,
            "validation": {"sha256": report["sha256"], "counts": report["counts"]},
            "target_game_version": report["target_game_version"],
            "manual_version": report["manual_version"],
            "catalog": report["catalog"],
            "disclaimer": "Static validation only; not proof that the mod loads, plays or balances in game.",
        }
        with open(manifest_path, "x", encoding="utf-8", newline="\n") as fh:
            created.append(manifest_path)
            json.dump(manifest, fh, indent=2)
            fh.write("\n")
    except BaseException:
        for p in reversed(created):  # remove only what this call created
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()
        raise
    return {"project": slug, "format": fmt, "destination": str(out), "manifest_path": str(manifest_path),
            "manifest": manifest, "validation": {"counts": report["counts"], "warnings": report["warnings"]}}


def _mod_snapshot(project: Project) -> dict[str, str]:
    """SHA-256 of every regular file under the mod folder, keyed by mod-relative path; links are refused."""
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(project.mod_dir, followlinks=False):
        d = Path(dirpath)
        for name in [*dirnames, *filenames]:
            if is_link(d / name):
                raise KosmoError("symlink_rejected", "The mod folder contains a symlink or junction",
                                 path=(d / name).relative_to(project.mod_dir).as_posix())
        for name in filenames:
            out[(d / name).relative_to(project.mod_dir).as_posix()] = sha256_bytes((d / name).read_bytes())
    return out


def _exports_dir(project: Project, create: bool) -> Path | None:
    path = contained(project.workspace, project.root / "exports", what="exports folder")
    if create:
        path.mkdir(exist_ok=True)
        path = contained(project.workspace, path, what="exports folder")  # refuse a link planted meanwhile
    if is_link(path) or not path.is_dir():
        return None
    return path


def export_revision(workspace: Path, slug: str, expected_sha256: Any, fmt: str = "zip",
                    catalog: Catalog | None = None) -> dict[str, Any]:
    """Export exactly the saved revision the caller saw, or nothing.

    Holds the project lock (editor saves and patches are refused meanwhile) while it checks the .dm hash,
    snapshots every mod file, runs the unchanged export_mod (which validates and refuses errors) into a new unique
    name under <project>/exports, then re-snapshots. Every packaged file must hash to the snapshot taken before
    validation and the mod folder must be unchanged afterwards; otherwise the new export is removed.
    """
    if not isinstance(expected_sha256, str) or not SHA_RE.match(expected_sha256.lower()):
        raise KosmoError("bad_request", "expected_sha256 (64 hex characters of the saved .dm) is required")
    if fmt not in ("zip", "folder"):
        raise KosmoError("bad_format", "format must be 'zip' or 'folder'")
    expected = expected_sha256.lower()
    project = open_project(workspace, slug)
    with project_lock(project):
        actual = sha256_bytes(read_dm(resolve_dm_target(project, None))[0])
        if actual != expected:
            raise KosmoError("sha_mismatch", "The saved .dm is not the revision shown; reload before exporting",
                             expected=expected, actual=actual)
        before = _mod_snapshot(project)
        exports = _exports_dir(project, create=True)
        if exports is None:
            raise KosmoError("symlink_rejected", "The project's exports folder is a link or not a folder")
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        export_id = f"{slug}-{stamp}-{secrets.token_hex(4)}"
        out = exports / (f"{export_id}.zip" if fmt == "zip" else export_id)
        res = export_mod(workspace, slug, str(out.relative_to(workspace)), fmt, catalog)
        manifest_path = Path(res["manifest_path"])
        manifest = res["manifest"]
        try:
            prefix = f"{slug}/"
            packaged = all(f["path"].startswith(prefix) and before.get(f["path"][len(prefix):]) == f["sha256"]
                           for f in manifest["files"])
            if not (packaged and manifest["validation"]["sha256"] == expected and _mod_snapshot(project) == before):
                raise KosmoError("changed_during_export", "Mod files changed while exporting; the new export was "
                                 "removed. Reload and try again.")
        except BaseException:
            for p in (manifest_path, out):  # only what this call created
                if p.is_dir() and not is_link(p):
                    shutil.rmtree(p, ignore_errors=True)
                elif p.exists():
                    p.unlink()
            raise
    return {"project": slug, "export_id": export_id, "format": fmt, "sha256": expected,
            "path": project.rel(out) + ("/" if fmt == "folder" else ""), "manifest_path": project.rel(manifest_path),
            "manifest": manifest, "validation": res["validation"]}


def _export_entry(exports: Path, slug: str, name: str) -> dict[str, Any] | None:
    m = re.fullmatch(re.escape(slug) + EXPORT_TAIL + r"(\.zip)?", name)
    path = exports / name
    if not m or is_link(path):
        return None
    if m.group(1):
        if not path.is_file():
            return None
        return {"export_id": name[:-4], "format": "zip", "path": path, "manifest_path": exports / f"{name}.manifest.json"}
    if not path.is_dir():
        return None
    return {"export_id": name, "format": "folder", "path": path, "manifest_path": path / MANIFEST_NAME}


def find_export(workspace: Path, slug: str, export_id: str) -> dict[str, Any]:
    """Locate one export by id: a fixed name pattern inside <project>/exports, never a client path."""
    project = open_project(workspace, slug)
    exports = _exports_dir(project, create=False)
    if exports is not None and re.fullmatch(re.escape(slug) + EXPORT_TAIL, export_id or ""):
        for name in (f"{export_id}.zip", export_id):
            entry = _export_entry(exports, slug, name)
            if entry:
                contained(project.workspace, entry["path"], what="export")
                return entry
    raise KosmoError("export_missing", "No such export in this project.")


def read_export_manifest(entry: dict[str, Any]) -> dict[str, Any]:
    p = entry["manifest_path"]
    try:
        if is_link(p) or not p.is_file() or p.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
    except (OSError, ValueError) as exc:
        raise KosmoError("export_missing", "The export manifest is missing or unreadable.") from exc
    return data


def list_exports(workspace: Path, slug: str) -> list[dict[str, Any]]:
    """Newest exports first (bounded), with the revision and hashes their manifests record."""
    project = open_project(workspace, slug)
    exports = _exports_dir(project, create=False)
    if exports is None:
        return []
    items: list[dict[str, Any]] = []
    for name in sorted(os.listdir(exports), reverse=True):
        entry = _export_entry(exports, slug, name)
        if not entry:
            continue
        item: dict[str, Any] = {"export_id": entry["export_id"], "format": entry["format"],
                                "path": project.rel(entry["path"]) + ("/" if entry["format"] == "folder" else "")}
        try:
            man = read_export_manifest(entry)
            val = man.get("validation") or {}
            item.update(created_utc=man.get("created_utc"), archive_sha256=man.get("archive_sha256"),
                        sha256=val.get("sha256"), counts=val.get("counts"), files=len(man.get("files") or []))
        except KosmoError as exc:
            item["error"] = exc.code
        if entry["format"] == "zip":
            item["bytes"] = entry["path"].stat().st_size
        items.append(item)
        if len(items) >= MAX_LISTED_EXPORTS:
            break
    return items
