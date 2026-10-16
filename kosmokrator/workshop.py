"""Prepare a validated export for the Dominions 6 Steam Workshop uploader, and optionally install it locally.

Kosmokrator never uploads or publishes. Dominions 6 itself uploads a local mod: Mods menu, right-click the 'local'
entry, "Upload to Steam Workshop" (Sombre's creator guide, steamcommunity.com/sharedfiles/filedetails/?id=3141394816).
The guide states that everything inside the mod folder is uploaded, that the folder needs a dom6ws.txt containing
only `Visibility = "Public"`, and that the preview must be banner.png at 256x256. The game writes dom6ws_pfid after
the first upload; deleting it makes the next upload a new Workshop item, so it is never written, moved or removed.

prepare_workshop builds a Workshop content folder from one existing export (the same revision the page shows):
the exported <slug>/<slug>.dm and assets, byte for byte, plus dom6ws.txt and banner.png. The banner is the export's
own #icon image (or another packaged image the caller names by its exact manifest path), placed unscaled and
centred on a transparent 256x256 canvas, or nearest-neighbour downscaled when a side exceeds 256. Nothing else is
added: the manifest, logs, art sources and project state stay outside the content folder.

install_workshop copies one prepared folder into <mods>/<slug>. <mods> comes from the server's trusted configuration
(KOSMOKRATOR_DOMINIONS_MODS, else %APPDATA%/Dominions6/mods when it exists), never from a request. A folder that is
already there is only touched when it is identical, or when every file in it is one this project installed before
(recorded under the project's .kosmokrator/workshop). Anything else is refused and left exactly as it is.
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import os
import re
import secrets
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from . import __version__
from .errors import KosmoError
from .export import SHA_RE, find_export, read_export_manifest
from .paths import atomic_write_bytes, contained, is_link
from .project import Project, open_project, project_lock, read_dm, resolve_dm_target, sha256_bytes, state_subdir
from .tga import decode_tga, encode_png

STEAM_APP_ID = 2511500
STEAM_RUN_URL = f"steam://run/{STEAM_APP_ID}"
GUIDE_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id=3141394816"
# dom6ws.txt values documented by the guide. It names only "Public"; private, friends-only and unlisted are
# changed on the Workshop item page after upload, so no other token is written into the file.
VISIBILITY_VALUES = ("Public",)
WS_FILE = "dom6ws.txt"
BANNER_FILE = "banner.png"
BANNER_SIDE = 256
# Written by the game after an upload; identifies the published item and must survive every update.
PFID_NAMES = frozenset({"dom6ws_pfid", "dom6ws_pfid.txt"})
WS_ID_TAIL = r"-ws-\d{8}T\d{6}Z-[0-9a-f]{8}"
MAX_LISTED = 10
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_REPORTED = 20
MODS_ENV = "KOSMOKRATOR_DOMINIONS_MODS"
INSTALL_RECORD = "installs.json"
ICON_RE = re.compile(rb'^[ \t]*#icon[ \t]+"([^"\r\n]+)"', re.MULTILINE)

UPLOAD_STEPS = [
    "Start Dominions 6 from Steam (the Steam client must be running and signed in).",
    "Open the Mods menu and find this mod's 'local' entry (a Workshop entry of the same mod may also be listed).",
    "Right-click the local entry and choose \"Upload to Steam Workshop\".",
    "On the new Workshop page, set the title, description and visibility (private, friends only, unlisted or "
    "public). Every later update resets the description to \"Dominions 6 mod\", so re-enter it after updating.",
    "Keep the dom6ws_pfid file the game writes into the mod folder. Deleting it makes the next upload a new item.",
]


# ---------- trusted install destination ----------
def mods_dir_config(env: dict[str, str] | None = None) -> dict[str, Any]:
    """The Dominions 6 mods folder chosen by the server process (never by a request).

    KOSMOKRATOR_DOMINIONS_MODS wins (an empty value or 'off' disables installing); otherwise the documented
    Windows user data folder %APPDATA%/Dominions6/mods is used when it already exists.
    """
    env = os.environ if env is None else env
    raw = env.get(MODS_ENV)
    if raw is not None:
        if raw.strip().lower() in ("", "off", "none", "0"):
            return {"path": None, "source": "disabled", "available": False,
                    "reason": f"Local install is turned off ({MODS_ENV} is empty or 'off')."}
        path, source = Path(raw).expanduser(), "environment"
    elif env.get("APPDATA"):
        path, source = Path(env["APPDATA"]) / "Dominions6" / "mods", "appdata"
    else:
        return {"path": None, "source": "none", "available": False,
                "reason": f"No Dominions 6 mods folder found. Set {MODS_ENV} before starting the server."}
    if not path.is_absolute():
        return {"path": str(path), "source": source, "available": False,
                "reason": f"{MODS_ENV} must be an absolute path."}
    if is_link(path) or (path.exists() and not path.is_dir()):
        return {"path": str(path), "source": source, "available": False,
                "reason": "The mods folder is a link or not a folder; refusing to install there."}
    if not path.is_dir():
        return {"path": str(path), "source": source, "available": False,
                "reason": "The mods folder does not exist. Start Dominions 6 once, or create it yourself."}
    return {"path": str(path.resolve()), "source": source, "available": True, "reason": None}


def _mods_root(config: dict[str, Any]) -> Path:
    if not config.get("available"):
        raise KosmoError("install_unavailable", config.get("reason") or "Local install is not configured.")
    root = Path(config["path"])
    if is_link(root) or not root.is_dir():
        raise KosmoError("install_unavailable", "The configured mods folder is missing, a link or not a folder.")
    return root.resolve()


# ---------- banner ----------
def _decode_image(name: str, data: bytes) -> tuple[int, int, bytes]:
    low = name.lower()
    try:
        if low.endswith(".tga"):
            return decode_tga(data)
        if low.endswith(".png"):
            from .author import decode_png_rgba  # strict 8-bit RGBA, sides up to 256
            return decode_png_rgba(data)
    except ValueError as exc:
        raise KosmoError("banner_unsupported", f"The banner source {name} cannot be read: {exc}. Use an 8-bit "
                         "RGBA PNG (up to 256x256) or a 24/32-bit TGA.") from exc
    raise KosmoError("banner_unsupported", f"The banner source {name} must be a .tga or .png image.")


def fit_banner(width: int, height: int, rgba: bytes, side: int = BANNER_SIDE) -> tuple[bytes, dict[str, Any]]:
    """Centre the image on a transparent side x side canvas without changing its pixels or aspect ratio.

    Images larger than the canvas are reduced by nearest-neighbour sampling with one scale for both axes, which is
    deterministic and adds no new colours. Returns (PNG bytes, description of what was done).
    """
    scale = min(1.0, side / width, side / height)
    nw, nh = max(1, int(width * scale)), max(1, int(height * scale))
    ox, oy = (side - nw) // 2, (side - nh) // 2
    canvas = bytearray(side * side * 4)  # all transparent
    for y in range(nh):
        sy = min(height - 1, y * height // nh)
        for x in range(nw):
            sx = min(width - 1, x * width // nw)
            s, d = (sy * width + sx) * 4, ((oy + y) * side + ox + x) * 4
            canvas[d:d + 4] = rgba[s:s + 4]
    method = "centred unscaled on a transparent canvas" if scale == 1.0 else \
        f"nearest-neighbour downscale to {nw}x{nh}, centred on a transparent canvas"
    return encode_png(side, side, bytes(canvas)), {"source_size": [width, height], "placed_size": [nw, nh],
                                                   "offset": [ox, oy], "method": method}


def _is_banner_ready(name: str, data: bytes) -> bool:
    if not name.lower().endswith(".png") or data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
        return False
    return int.from_bytes(data[16:20], "big") == BANNER_SIDE and int.from_bytes(data[20:24], "big") == BANNER_SIDE


# ---------- reading an export ----------
def _safe_rel(path: str, slug: str) -> str:
    """Manifest path '<slug>/<rel>' -> '<rel>' after refusing anything that could leave the content folder."""
    if not isinstance(path, str) or "\\" in path or "\x00" in path or not path.startswith(f"{slug}/"):
        raise KosmoError("export_invalid", "The export manifest lists a file outside the mod folder.")
    rel = path[len(slug) + 1:]
    parts = PurePosixPath(rel).parts
    if not rel or rel.startswith("/") or re.match(r"^[A-Za-z]:", rel) or any(p in ("", ".", "..") for p in parts):
        raise KosmoError("export_invalid", "The export manifest lists an unsafe file path.")
    return "/".join(parts)


def _export_payload(workspace: Path, slug: str, export_id: Any) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Every file of one export, re-hashed against its manifest. Extra, missing or changed files are refused."""
    if not isinstance(export_id, str) or len(export_id) > 120:
        raise KosmoError("bad_request", "export_id (from the export list) is required.")
    entry = find_export(workspace, slug, export_id)
    man = read_export_manifest(entry)
    files = man.get("files")
    if not isinstance(files, list) or not files:
        raise KosmoError("export_invalid", "The export manifest lists no files.")
    want: dict[str, str] = {}
    for f in files:
        if not isinstance(f, dict) or not isinstance(f.get("sha256"), str):
            raise KosmoError("export_invalid", "The export manifest has a malformed file entry.")
        want[_safe_rel(f.get("path"), slug)] = f["sha256"]
    out: dict[str, bytes] = {}
    if entry["format"] == "zip":
        path = entry["path"]
        if path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise KosmoError("export_too_large", "The export archive is too large to prepare.")
        raw = path.read_bytes()
        if sha256_bytes(raw) != man.get("archive_sha256"):
            raise KosmoError("export_changed", "The export archive no longer matches its manifest hash.")
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [i.filename for i in zf.infolist() if not i.is_dir()]
            if sorted(names) != sorted(f"{slug}/{r}" for r in want):
                raise KosmoError("export_changed", "The export archive does not hold exactly the manifest's files.")
            for rel in want:
                out[rel] = zf.read(f"{slug}/{rel}")
    else:
        base = contained(entry["path"], slug, what="export folder")
        for rel in want:
            p = contained(base, rel, what="exported file")
            if is_link(p) or not p.is_file():
                raise KosmoError("export_changed", f"Exported file {rel} is missing or a link.")
            out[rel] = p.read_bytes()
        found = _walk(base)
        if set(found) != set(want):
            raise KosmoError("export_changed", "The export folder does not hold exactly the manifest's files.")
    for rel, data in out.items():
        if sha256_bytes(data) != want[rel]:
            raise KosmoError("export_changed", f"Exported file {rel} no longer matches its manifest hash.")
    return {**entry, "manifest": man}, out


def _walk(base: Path) -> dict[str, Path]:
    """Regular files under base keyed by relative POSIX path; any link or junction is refused."""
    found: dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        d = Path(dirpath)
        for name in [*dirnames, *filenames]:
            if is_link(d / name):
                raise KosmoError("symlink_rejected", "A folder to be read or replaced contains a symlink or junction.",
                                 path=(d / name).relative_to(base).as_posix())
        for name in filenames:
            found[(d / name).relative_to(base).as_posix()] = d / name
    return found


def _current_sha(project: Project) -> str:
    return sha256_bytes(read_dm(resolve_dm_target(project, None))[0])


def _check_revision(project: Project, expected: Any, recorded: Any) -> str:
    if not isinstance(expected, str) or not SHA_RE.match(expected.lower()):
        raise KosmoError("bad_request", "expected_sha256 (64 hex characters of the saved .dm) is required")
    expected = expected.lower()
    actual = _current_sha(project)
    if actual != expected:
        raise KosmoError("sha_mismatch", "The saved .dm is not the revision shown; reload first.",
                         expected=expected, actual=actual)
    if recorded != expected:
        raise KosmoError("stale_export", "This export was built from an older .dm revision. Export the current "
                         "revision, then prepare it.", expected=expected, actual=recorded)
    return expected


# ---------- prepared bundles ----------
def _workshop_dir(project: Project, create: bool) -> Path | None:
    exports = contained(project.workspace, project.root / "exports", what="exports folder")
    path = contained(project.workspace, exports / "workshop", what="workshop folder")
    if create:
        exports.mkdir(exist_ok=True)
        path.mkdir(exist_ok=True)
        path = contained(project.workspace, path, what="workshop folder")
    if is_link(exports) or is_link(path) or not path.is_dir():
        return None
    return path


def _entry(project: Project, wid: Any) -> dict[str, Path]:
    if not isinstance(wid, str) or not re.fullmatch(re.escape(project.slug) + WS_ID_TAIL, wid):
        raise KosmoError("workshop_missing", "No such prepared Workshop folder in this project.")
    base = _workshop_dir(project, create=False)
    if base is None:
        raise KosmoError("workshop_missing", "No such prepared Workshop folder in this project.")
    folder, archive, manifest = base / wid, base / f"{wid}.zip", base / f"{wid}.manifest.json"
    if is_link(folder) or not folder.is_dir() or is_link(manifest) or not manifest.is_file():
        raise KosmoError("workshop_missing", "No such prepared Workshop folder in this project.")
    return {"folder": folder, "content": folder / project.slug, "archive": archive, "manifest": manifest}


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        if is_link(path) or path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
    except (OSError, ValueError) as exc:
        raise KosmoError("workshop_missing", "The prepared folder's manifest is missing or unreadable.") from exc
    return data


def _choose_banner(slug: str, payload: dict[str, bytes], banner_asset: Any) -> tuple[bytes, dict[str, Any]]:
    """banner.png bytes from a packaged image only: an exported banner.png, the named asset, or the #icon file."""
    if BANNER_FILE in payload:
        if banner_asset not in (None, BANNER_FILE):
            raise KosmoError("banner_conflict", "The mod already ships a banner.png; it is used as is.")
        if not _is_banner_ready(BANNER_FILE, payload[BANNER_FILE]):
            raise KosmoError("banner_conflict", "The mod's own banner.png is not 256x256. Replace or rename it in "
                             "the mod folder, then export again.")
        return payload[BANNER_FILE], {"source": BANNER_FILE, "method": "the mod's own 256x256 banner.png, unchanged"}
    if banner_asset is None:
        m = ICON_RE.search(payload[f"{slug}.dm"])
        if not m:
            raise KosmoError("banner_missing", "The .dm has no #icon banner to reuse. Add a #icon image (or a 256x256 "
                             "banner.png) to the mod, export again, then prepare.")
        banner_asset = m.group(1).decode("latin-1")
    if not isinstance(banner_asset, str) or len(banner_asset) > 200:
        raise KosmoError("bad_request", "banner_asset must be the path of an image in this export.")
    rel = "/".join(p for p in banner_asset.split("/") if p not in ("", "."))
    if rel not in payload or not rel.lower().endswith((".tga", ".png")):
        raise KosmoError("banner_missing", f"{banner_asset} is not an image packaged in this export.")
    w, h, rgba = _decode_image(rel, payload[rel])
    png, how = fit_banner(w, h, rgba)
    return png, {"source": rel, **how}


def prepare_workshop(workspace: Path, slug: str, body: Any) -> dict[str, Any]:
    """Build <project>/exports/workshop/<id>/<slug>/ plus <id>.zip and <id>.manifest.json from one export."""
    if not isinstance(body, dict) or set(body) - {"expected_sha256", "export_id", "visibility", "banner_asset"}:
        raise KosmoError("bad_request", "Body needs expected_sha256, export_id, visibility and optional banner_asset.")
    visibility = body.get("visibility")
    if visibility not in VISIBILITY_VALUES:
        raise KosmoError("bad_visibility", "Choose a documented dom6ws.txt visibility. Only \"Public\" is documented; "
                         "set private, friends-only or unlisted on the Workshop page after uploading.",
                         field="visibility")
    project = open_project(workspace, slug)
    with project_lock(project):
        source, payload = _export_payload(workspace, slug, body.get("export_id"))
        sha = _check_revision(project, body.get("expected_sha256"), (source["manifest"].get("validation") or {}).get("sha256"))
        if f"{slug}.dm" not in payload:
            raise KosmoError("export_invalid", f"The export has no {slug}/{slug}.dm.")
        bad = sorted(r for r in payload if r in PFID_NAMES or r == WS_FILE)
        ws_text = f'Visibility = "{visibility}"'.encode("ascii")
        if bad and not (bad == [WS_FILE] and payload[WS_FILE] == ws_text):
            raise KosmoError("export_conflict", "The export already contains Workshop control files ("
                             + ", ".join(bad) + "). Create a clean source export without Workshop control files; "
                             "preserve dom6ws_pfid in any installed or published mod folder.")
        banner, banner_info = _choose_banner(slug, payload, body.get("banner_asset"))
        content = dict(payload)
        content[WS_FILE] = ws_text
        content[BANNER_FILE] = banner

        base = _workshop_dir(project, create=True)
        if base is None:
            raise KosmoError("symlink_rejected", "The project's exports/workshop folder is a link or not a folder.")
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        wid = f"{slug}-ws-{stamp}-{secrets.token_hex(4)}"
        folder, archive, man_path = base / wid, base / f"{wid}.zip", base / f"{wid}.manifest.json"
        names = sorted(content)
        created: list[Path] = []
        try:
            folder.mkdir()
            created.append(folder)
            for rel in names:
                target = folder / slug / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                contained(folder, target, what="prepared file")
                with open(target, "xb") as fh:
                    fh.write(content[rel])
            with open(archive, "xb") as fh:
                created.append(archive)
                with zipfile.ZipFile(fh, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for rel in names:
                        zf.writestr(f"{slug}/{rel}", content[rel])
            files = [{"path": f"{slug}/{r}", "sha256": sha256_bytes(content[r]), "bytes": len(content[r])} for r in names]
            manifest = {
                "tool": "kosmokrator", "tool_version": __version__, "kind": "workshop_content", "created_utc": stamp,
                "workshop_id": wid, "project": slug, "content_folder": slug, "sha256": sha,
                "source_export": {"export_id": source["export_id"], "format": source["format"],
                                  "archive_sha256": source["manifest"].get("archive_sha256")},
                "validation": source["manifest"].get("validation"),
                "visibility": visibility, "dom6ws_txt": ws_text.decode("ascii"), "banner": banner_info,
                "files": files, "archive_sha256": sha256_bytes(archive.read_bytes()),
                "steam_app_id": STEAM_APP_ID, "upload_steps": UPLOAD_STEPS, "guide": GUIDE_URL,
                "notes": ["This manifest stays outside the content folder; only the content folder is uploaded.",
                          "Kosmokrator did not upload or publish anything. The game's own uploader does that.",
                          "Static validation only; not proof that the mod loads, plays or balances in game."],
            }
            with open(man_path, "x", encoding="utf-8", newline="\n") as fh:
                created.append(man_path)
                json.dump(manifest, fh, indent=2)
                fh.write("\n")
        except BaseException:
            for p in reversed(created):  # only what this call created
                if p.is_dir() and not is_link(p):
                    shutil.rmtree(p, ignore_errors=True)
                elif p.exists():
                    p.unlink()
            raise
    return _summary(project, wid, manifest, folder)


def _summary(project: Project, wid: str, manifest: dict[str, Any], folder: Path) -> dict[str, Any]:
    return {"workshop_id": wid, "project": project.slug, "sha256": manifest.get("sha256"),
            "created_utc": manifest.get("created_utc"), "visibility": manifest.get("visibility"),
            "banner": manifest.get("banner"), "files": manifest.get("files"),
            "archive_sha256": manifest.get("archive_sha256"), "source_export": manifest.get("source_export"),
            "validation": manifest.get("validation"),
            "path": project.rel(folder / project.slug) + "/", "folder_abs": str(folder / project.slug),
            "archive_path": project.rel(folder.parent / f"{wid}.zip"),
            "manifest_path": project.rel(folder.parent / f"{wid}.manifest.json")}


def workshop_archive(workspace: Path, slug: str, wid: str) -> tuple[str, bytes]:
    project = open_project(workspace, slug)
    e = _entry(project, wid)
    if is_link(e["archive"]) or not e["archive"].is_file():
        raise KosmoError("workshop_missing", "The prepared ZIP is missing.")
    if e["archive"].stat().st_size > MAX_ARCHIVE_BYTES:
        raise KosmoError("export_too_large", "Archive is too large to serve.")
    return f"{wid}.zip", e["archive"].read_bytes()


def workshop_banner(workspace: Path, slug: str, wid: str) -> bytes:
    """The prepared banner.png, served only when it still matches the manifest hash."""
    project = open_project(workspace, slug)
    e = _entry(project, wid)
    want = next((f.get("sha256") for f in _read_manifest(e["manifest"]).get("files") or []
                 if isinstance(f, dict) and f.get("path") == f"{slug}/{BANNER_FILE}"), None)
    path = e["content"] / BANNER_FILE
    if is_link(e["content"]) or is_link(path) or not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise KosmoError("workshop_missing", "The prepared banner.png is missing.")
    data = path.read_bytes()
    if sha256_bytes(data) != want:
        raise KosmoError("workshop_changed", "The prepared banner.png no longer matches its manifest.")
    return data


def workshop_manifest(workspace: Path, slug: str, wid: str) -> dict[str, Any]:
    project = open_project(workspace, slug)
    return _read_manifest(_entry(project, wid)["manifest"])


# ---------- local install ----------
def _verified_content(project: Project, e: dict[str, Path], man: dict[str, Any]) -> dict[str, bytes]:
    """The prepared content folder's files, which must be exactly the manifest's files with matching hashes."""
    if is_link(e["content"]) or not e["content"].is_dir():
        raise KosmoError("workshop_changed", "The prepared content folder is missing or a link.")
    want = {_safe_rel(f.get("path"), project.slug): f.get("sha256") for f in man.get("files") or []
            if isinstance(f, dict)}
    if set(os.listdir(e["folder"])) != {project.slug}:
        raise KosmoError("workshop_changed", "The prepared folder holds files besides the content folder.")
    found = _walk(e["content"])
    if not want or set(found) != set(want):
        raise KosmoError("workshop_changed", "The prepared content folder does not match its manifest. Prepare again.")
    out = {rel: p.read_bytes() for rel, p in found.items()}
    for rel, data in out.items():
        if sha256_bytes(data) != want[rel]:
            raise KosmoError("workshop_changed", f"Prepared file {rel} no longer matches its manifest. Prepare again.")
    if set(out) & PFID_NAMES:
        raise KosmoError("workshop_changed", "A prepared folder must not contain dom6ws_pfid.")
    return out


def _records(project: Project, create: bool = False) -> tuple[Path, dict[str, Any]]:
    """The install record; the state folder is only created when about to write (reads stay write-free)."""
    folder = state_subdir(project, "workshop") if create else         contained(project.root, project.state_dir / "workshop", what="state workshop directory")
    path = folder / INSTALL_RECORD
    if not path.exists():
        return path, {}
    if is_link(path):
        raise KosmoError("symlink_rejected", "The install record is a link.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return path, data if isinstance(data, dict) else {}


def destination_status(project: Project, config: dict[str, Any], new: dict[str, str] | None = None) -> dict[str, Any]:
    """What <mods>/<slug> holds relative to this project's last install and an optional new file set (rel -> sha)."""
    out: dict[str, Any] = {"mods_dir": config.get("path"), "available": bool(config.get("available")),
                           "reason": config.get("reason"), "destination": None, "state": "unavailable"}
    if not config.get("available"):
        return out
    root = _mods_root(config)
    dest = contained(root, project.slug, what="install destination")
    out["destination"] = str(dest)
    if not dest.exists() and not is_link(dest):
        out["state"] = "absent"
        return out
    if is_link(dest) or not dest.is_dir():
        out.update(state="conflict", conflict="The destination is a link or not a folder.")
        return out
    try:
        found = _walk(dest)
    except KosmoError as exc:
        out.update(state="conflict", conflict=exc.message)
        return out
    pfid = sorted(r for r in found if r in PFID_NAMES)
    have = {r: sha256_bytes(p.read_bytes()) for r, p in found.items() if r not in PFID_NAMES}
    _rp, records = _records(project)
    rec = (records.get(str(dest)) or {}).get("files") or {}
    out["pfid_present"] = bool(pfid)
    out["managed"] = bool(rec)
    if new is not None and have == new:
        out["state"] = "identical"
    elif rec and all(rec.get(r) == h or (new or {}).get(r) == h for r, h in have.items()):
        # Every file is one this project installed (or the new content, after an interrupted update).
        out["state"] = "managed"
    else:
        changed = sorted(r for r, h in have.items() if rec.get(r) != h and (new or {}).get(r) != h)
        out.update(state="conflict", unmanaged=changed[:MAX_REPORTED], unmanaged_count=len(changed),
                   conflict="The folder was not installed by this project, or files in it changed since.")
    return out


def install_workshop(workspace: Path, slug: str, wid: str, body: Any, config: dict[str, Any]) -> dict[str, Any]:
    """Copy a prepared content folder into <mods>/<slug>: new, identical, or a managed update; never a conflict.

    The body must carry the fingerprint of a current installation preflight (expected_preflight) and, when that
    check has review warnings, the same fingerprint as acknowledge_review. The preflight is recomputed from the
    verified content under the project lock immediately before the first write.
    """
    from .preflight import build_report, require_current
    if not isinstance(body, dict) or set(body) - {"expected_sha256", "expected_preflight", "acknowledge_review"}:
        raise KosmoError("bad_request", "Body needs expected_sha256, expected_preflight and optional "
                         "acknowledge_review; the destination is fixed by the server.")
    project = open_project(workspace, slug)
    root = _mods_root(config)
    with project_lock(project):
        e = _entry(project, wid)
        man = _read_manifest(e["manifest"])
        _check_revision(project, body.get("expected_sha256"), man.get("sha256"))
        content = _verified_content(project, e, man)
        new = {r: sha256_bytes(d) for r, d in content.items()}
        report = build_report(project, {"type": "workshop", "id": wid, "manifest": man, "payload": content,
                                        "sha256": man.get("sha256")}, config)
        require_current(report, body)
        status = destination_status(project, config, new)
        dest = Path(status["destination"])
        if status["state"] == "conflict":
            raise KosmoError("install_conflict", f"{dest} already exists and is not a Kosmokrator install of this "
                             "project (or was changed since). Nothing was changed. Back it up and copy the prepared "
                             "folder yourself, or move the existing folder away first; keep its dom6ws_pfid if the "
                             "mod is already published.",
                             problems=[status.get("conflict")] + list(status.get("unmanaged") or []))
        written: list[str] = []
        removed: list[str] = []
        if status["state"] == "absent":
            dest.mkdir()
            try:
                for rel in sorted(content):
                    target = contained(root, dest / rel, what="install target")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with open(target, "xb") as fh:
                        fh.write(content[rel])
                    written.append(rel)
            except BaseException:
                shutil.rmtree(dest, ignore_errors=True)  # the folder did not exist before this call
                raise
        elif status["state"] == "managed":
            have = _walk(dest)
            for rel in sorted(content):
                target = contained(root, dest / rel, what="install target")
                if rel in have and sha256_bytes(have[rel].read_bytes()) == new[rel]:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                contained(root, target, what="install target")
                atomic_write_bytes(target, content[rel])
                written.append(rel)
            for rel, p in sorted(have.items()):  # earlier managed files this revision no longer ships
                if rel not in content and rel not in PFID_NAMES:
                    contained(root, p, what="install target").unlink()
                    removed.append(rel)
        rec_path, records = _records(project, create=True)
        records[str(dest)] = {"workshop_id": wid, "sha256": man.get("sha256"), "files": new,
                              "installed_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")}
        atomic_write_bytes(rec_path, (json.dumps(records, indent=2) + "\n").encode("utf-8"))
        after = destination_status(project, config, new)
    return {"workshop_id": wid, "destination": str(dest), "result": {"absent": "installed", "identical": "unchanged",
            "managed": "updated"}[status["state"]], "written": written, "removed": removed,
            "pfid_preserved": bool(after.get("pfid_present")), "status": after,
            "preflight": {"fingerprint": report["fingerprint"], "status": report["status"], "counts": report["counts"]}}


# ---------- status ----------
def workshop_state(workspace: Path, slug: str, config: dict[str, Any]) -> dict[str, Any]:
    project = open_project(workspace, slug)
    items: list[dict[str, Any]] = []
    base = _workshop_dir(project, create=False)
    if base is not None:
        for name in sorted(os.listdir(base), reverse=True):
            if not re.fullmatch(re.escape(slug) + WS_ID_TAIL, name) or not (base / name).is_dir():
                continue
            try:
                e = _entry(project, name)
                items.append(_summary(project, name, _read_manifest(e["manifest"]), e["folder"]))
            except KosmoError as exc:
                items.append({"workshop_id": name, "error": exc.code})
            if len(items) >= MAX_LISTED:
                break
    try:
        dest = destination_status(project, config)
    except KosmoError as exc:
        dest = {"available": False, "state": "unavailable", "reason": exc.message, "mods_dir": config.get("path")}
    return {"project": slug, "sha256": _current_sha(project), "visibility_values": list(VISIBILITY_VALUES),
            "steam_run_url": STEAM_RUN_URL, "steam_app_id": STEAM_APP_ID, "guide": GUIDE_URL,
            "upload_steps": UPLOAD_STEPS, "install": {**dest, "source": config.get("source"),
                                                       "env": MODS_ENV},
            "prepared": items}
