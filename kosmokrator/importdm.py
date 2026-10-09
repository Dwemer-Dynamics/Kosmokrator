"""Import an existing .dm (plus its assets) as a NEW Kosmokrator project.

The source is never modified: the CLI reads it, the browser uploads its bytes. The new project is created with the
same exclusive rules as `create` (refuses an existing slug), the .dm bytes are written unchanged (encoding, line
endings, comments and unknown commands kept), and assets are written as new files inside the new mod folder only.
If anything fails after the project folder was created by this call, the files and folders this call created are
removed again (nothing that existed before is touched).
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import os
import re
import shutil
from pathlib import Path
from typing import Any

from .dmparse import decode_dm, newline_style, parse
from .errors import KosmoError
from .paths import atomic_write_bytes, contained, is_link
from .project import _check_slug, create_project, open_project, sha256_bytes

ASSET_EXT = (".tga", ".png", ".rgb", ".sw", ".al", ".d6m", ".map")
ASSET_RE = re.compile(r"^[A-Za-z0-9_\-. ]+(?:/[A-Za-z0-9_\-. ]+){0,6}$")
MAX_DM_BYTES = 4 * 1024 * 1024
MAX_ASSETS = 400
MAX_TOTAL_BYTES = 64 * 1024 * 1024


def _clean_rel(p: str) -> str:
    if not isinstance(p, str):
        raise KosmoError("bad_asset_path", "Asset paths must be text.")
    q = p.replace("\\", "/")
    while q.startswith("./"):
        q = q[2:]
    if not q or len(q) > 200 or not ASSET_RE.match(q) or any(s in ("", ".", "..") for s in q.split("/")) \
            or not q.lower().endswith(ASSET_EXT):
        raise KosmoError("bad_asset_path", f"Asset path {p!r} must be relative, without '..', and end in "
                                           f"{', '.join(ASSET_EXT)}.", field="assets")
    return q


def referenced_assets(text: str) -> list[str]:
    """String arguments of the .dm that look like asset files (relative to the mod folder)."""
    out: list[str] = []
    for st in parse(text).statements:
        for a in st.args:
            if a.kind == "str" and isinstance(a.value, str) and a.value.lower().endswith(ASSET_EXT):
                v = a.value.replace("\\", "/")
                while v.startswith("./"):
                    v = v[2:]
                if v not in out:
                    out.append(v)
    return out


def import_project(workspace: Path, slug: str, name: str | None, dm_bytes: bytes, assets: dict[str, bytes],
                   preview: bool, source_label: str) -> dict[str, Any]:
    """Shared by CLI and web. `assets` maps a relative path inside the mod folder to its bytes."""
    _check_slug(slug)
    if not dm_bytes or len(dm_bytes) > MAX_DM_BYTES:
        raise KosmoError("bad_dm", f"The .dm must be 1 byte to {MAX_DM_BYTES // 1024 // 1024} MB.", field="dm")
    try:
        text, enc = decode_dm(dm_bytes)
    except (UnicodeDecodeError, ValueError) as exc:
        raise KosmoError("bad_dm", f"The .dm cannot be decoded: {exc}", field="dm") from exc
    pr = parse(text)
    if not any(st.command == "modname" for st in pr.toplevel):
        raise KosmoError("bad_dm", "No #modname found: this does not look like a Dominions mod file.", field="dm")
    if len(assets) > MAX_ASSETS or sum(len(b) for b in assets.values()) > MAX_TOTAL_BYTES:
        raise KosmoError("too_large", f"At most {MAX_ASSETS} assets and {MAX_TOTAL_BYTES // 1024 // 1024} MB.",
                         field="assets")
    clean: dict[str, bytes] = {}
    for rel, data in assets.items():
        c = _clean_rel(rel)
        if c.lower() in {k.lower() for k in clean}:
            raise KosmoError("bad_asset_path", f"Asset {c} is listed twice.", field="assets")
        clean[c] = data
    root = contained(workspace, slug, what="project directory")
    if root.exists() or is_link(root):
        raise KosmoError("project_exists", f"A project or folder named {slug!r} already exists; choose a new slug. "
                                           "Import never overwrites.", field="slug")
    refs = referenced_assets(text)
    ref_l = {r.lower(): r for r in refs}
    listed = [{"path": k, "bytes": len(v), "sha256": sha256_bytes(v), "referenced": k.lower() in ref_l,
               "case_mismatch": k.lower() in ref_l and ref_l[k.lower()] != k} for k, v in clean.items()]
    missing = [r for r in refs if r.lower() not in {k.lower() for k in clean}]
    warnings = []
    if missing:
        warnings.append(f"{len(missing)} file(s) the .dm references were not supplied; validation will report them.")
    if any(a["case_mismatch"] for a in listed):
        warnings.append("Some asset names differ in letter case from the .dm reference; the game may not find them "
                        "on case-sensitive systems.")
    unref = [a["path"] for a in listed if not a["referenced"]]
    if unref:
        warnings.append(f"{len(unref)} supplied file(s) are not referenced by the .dm; they are copied anyway.")
    out = {"preview": preview, "project": slug, "source": source_label, "dm_path": f"mod/{slug}/{slug}.dm",
           "sha256": sha256_bytes(dm_bytes), "bytes": len(dm_bytes), "encoding": enc, "newlines": newline_style(text),
           "syntax_issues": len(pr.issues), "assets": listed, "missing_assets": missing, "warnings": warnings,
           "note": "The source is never changed. The new project's .dm is a byte-identical copy; run validation "
                   "next. Nothing is installed into the game."}
    if preview:
        return {**out, "written": False}
    modname = next((st.args[0].value for st in pr.toplevel if st.command == "modname" and st.args
                    and st.args[0].kind == "str"), None)
    display = name or (modname if isinstance(modname, str) and '"' not in modname and "\n" not in modname else None)
    create_project(workspace, slug, display)
    try:
        project = open_project(workspace, slug)
        # create_project supplies a placeholder banner; the incoming source owns this asset on import.
        # Only remove that known placeholder inside the project this call just created exclusively.
        if any(rel.lower() == "mod_banner.tga" for rel in clean):
            placeholder = contained(project.mod_dir, "mod_banner.tga", what="generated banner")
            if is_link(placeholder):
                raise KosmoError("symlink_rejected", "The generated banner is a link.")
            placeholder.unlink()
        atomic_write_bytes(project.dm_path, dm_bytes)
        for rel, data in clean.items():
            target = contained(project.mod_dir, rel, what="asset")
            parent = target.parent
            parts = []
            p = parent
            while p != project.mod_dir:
                parts.append(p)
                p = p.parent
            for d in reversed(parts):
                contained(project.mod_dir, d, what="asset folder")
                if is_link(d):
                    raise KosmoError("symlink_rejected", "An asset folder is a link.")
                d.mkdir(exist_ok=True)
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
        if sha256_bytes(project.dm_path.read_bytes()) != out["sha256"]:
            raise KosmoError("internal", "The copied .dm does not match the source hash.")
    except BaseException:
        with contextlib.suppress(OSError):
            if not is_link(root):
                shutil.rmtree(root)  # only the folder this call just created exclusively
        raise
    return {**out, "written": True}


def import_from_path(workspace: Path, slug: str, name: str | None, source: str, preview: bool) -> dict[str, Any]:
    """CLI entry: read SOURCE.dm and the files it references inside its own folder (no links, no '..')."""
    src = Path(source).expanduser().resolve()
    if src.suffix.lower() != ".dm" or not src.is_file() or is_link(Path(source)):
        raise KosmoError("bad_source", "Source must be an existing .dm file (not a link).")
    with contextlib.suppress(ValueError):
        src.relative_to(workspace.resolve() / slug)
        raise KosmoError("bad_source", "The source is inside the target project folder.")
    data = src.read_bytes()
    text, _enc = decode_dm(data)
    assets: dict[str, bytes] = {}
    for ref in referenced_assets(text):
        try:
            rel = _clean_rel(ref)
            p = contained(src.parent, rel, what="asset")
        except KosmoError:
            continue
        if p.is_file() and not is_link(p):
            assets[rel] = p.read_bytes()
    return import_project(workspace, slug, name, data, assets, preview, src.name)


def import_from_body(workspace: Path, body: Any) -> dict[str, Any]:
    """Web entry: {preview, slug, name?, dm: {filename, base64}, assets: [{path, base64}]}."""
    if not isinstance(body, dict) or set(body) - {"preview", "slug", "name", "dm", "assets"}:
        raise KosmoError("bad_request", "Body must be {preview, slug, name?, dm, assets?}.")
    preview = body.get("preview", False)
    if not isinstance(preview, bool):
        raise KosmoError("bad_request", "preview must be true or false.")
    slug = body.get("slug")
    if not isinstance(slug, str):
        raise KosmoError("bad_slug", "Choose a new project slug.", field="slug")
    name = body.get("name")
    if name is not None and (not isinstance(name, str) or '"' in name or "\n" in name or len(name) > 60):
        raise KosmoError("bad_value", "Name: at most 60 characters, no double quotes or line breaks.", field="name")
    dm = body.get("dm")
    if not isinstance(dm, dict) or not isinstance(dm.get("base64"), str):
        raise KosmoError("bad_dm", "Choose a .dm file.", field="dm")
    fname = dm.get("filename") or "upload.dm"
    if not isinstance(fname, str) or not fname.lower().endswith(".dm") or "/" in fname or "\\" in fname:
        raise KosmoError("bad_dm", "The mod file must be a .dm.", field="dm")
    try:
        dm_bytes = base64.b64decode(dm["base64"], validate=True)
        assets: dict[str, bytes] = {}
        items = body.get("assets") or []
        if not isinstance(items, list) or len(items) > MAX_ASSETS:
            raise KosmoError("bad_request", f"assets: at most {MAX_ASSETS} files.", field="assets")
        for a in items:
            if not isinstance(a, dict) or set(a) != {"path", "base64"} or not isinstance(a["base64"], str):
                raise KosmoError("bad_request", "Each asset needs path and base64.", field="assets")
            assets[a["path"]] = base64.b64decode(a["base64"], validate=True)
    except (binascii.Error, ValueError) as exc:
        if isinstance(exc, KosmoError):
            raise
        raise KosmoError("bad_base64", "A file is not valid base64.", field="assets") from exc
    return import_project(workspace, slug, name, dm_bytes, assets, preview, fname)
