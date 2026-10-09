"""Extract verified native trait art into a local workspace cache, separate from mod exports."""

from __future__ import annotations

import hashlib
import json
import re
import struct
from pathlib import Path
from typing import Any

from .errors import KosmoError
from .paths import atomic_write_bytes, contained, is_link, resolve_workspace
from .tga import encode_png
from .trait_icon_data import ICON_SPECS, RES_SHA256

CACHE_NAME = ".kosmokrator-trait-icons"
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_ICON_BYTES = 64 * 1024


def decode_native_icon(data: bytes, index: int) -> tuple[int, int, bytes]:
    """Decode one TRS v4 RGB565 sparse image, refusing unsupported flags and malformed runs.

    Header: TCSF, big-endian sprite count/version, four format bytes. Each 12-byte table record
    stores width/height, flags, reserved metadata and absolute offset. A zero dimension means 256.
    Payload: big-endian run count, then (skip, length, RGB565 pixels). A 255 length prefix introduces
    a three-byte extended length. Skipped pixels are transparent; stored black pixels remain opaque.
    """
    if len(data) < 16 or data[:4] != b"TCSF":
        raise ValueError("Not a TRS graphics archive")
    count, version = struct.unpack_from(">HH", data, 4)
    table_end = 12 + count * 12
    if version != 4 or data[8:12] != b"\x03\x20\x00\x00" or table_end + 4 > len(data):
        raise ValueError("Unsupported TRS format")
    if not 0 <= index < count:
        raise ValueError("Sprite id outside the archive")
    w, h, flags, reserved, start = struct.unpack_from(">BBHII", data, 12 + index * 12)
    w, h = w or 256, h or 256
    end = struct.unpack_from(">I", data, 20 + (index + 1) * 12)[0] if index + 1 < count else len(data)
    if flags not in (0, 1) or reserved or not table_end + 4 <= start < end <= len(data):
        raise ValueError("Unsupported TRS sprite encoding or invalid offset")
    p = start
    runs = struct.unpack_from(">I", data, p)[0]
    p += 4
    if runs > w * h:
        raise ValueError("Too many sprite runs")
    rgba = bytearray(w * h * 4)
    pos = 0

    # TRS sparse runs use the same variable length for skips and pixel counts.
    def length() -> int:
        nonlocal p
        if p >= end:
            raise ValueError("Truncated sprite run")
        value = data[p]
        p += 1
        if value == 255:
            if p + 3 > end:
                raise ValueError("Truncated extended sprite run")
            value = int.from_bytes(data[p:p + 3], "big")
            p += 3
        return value

    for _ in range(runs):
        pos += length()
        size = length()
        if pos + size > w * h or p + size * 2 > end:
            raise ValueError("Sprite run exceeds its image")
        for _ in range(size):
            colour = struct.unpack_from(">H", data, p)[0]
            p += 2
            r, g, b = colour >> 11, (colour >> 5) & 63, colour & 31
            rgba[pos * 4:pos * 4 + 4] = bytes(((r << 3) | (r >> 2), (g << 2) | (g >> 4),
                                             (b << 3) | (b >> 2), 255))
            pos += 1
    if p != end:
        raise ValueError("Unexpected trailing sprite data")
    return w, h, bytes(rgba)


def install_native_icons(workspace: str | None, game: str) -> dict[str, Any]:
    """Read only the user's res.trs and atomically populate the workspace's private icon cache."""
    root = resolve_workspace(workspace)
    game_root = Path(game).expanduser().absolute()
    if is_link(game_root) or not game_root.is_dir():
        raise KosmoError("game_missing", "--game must be an existing Dominions 6 installation directory.")
    archive = contained(game_root.resolve(), "data/res.trs", what="native graphics")
    if not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise KosmoError("icons_missing", "Dominions 6 data/res.trs is missing or too large.")
    raw = archive.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    # Icon indices are version-sensitive; a changed archive must be reviewed before it is accepted.
    if sha != RES_SHA256:
        raise KosmoError("icons_version", "This graphics archive has not been verified against the native trait "
                         "mapping. Keep text labels until its icon indices are reviewed.", sha256=sha)
    decoded = {}
    try:
        for index in sorted({spec[0] for spec in ICON_SPECS.values()}):
            w, h, rgba = decode_native_icon(raw, index)
            decoded[index] = (w, h, encode_png(w, h, rgba))
    except (ValueError, struct.error) as exc:
        raise KosmoError("icons_decode", str(exc)) from exc
    cache = contained(root, CACHE_NAME, what="native icon cache")
    cache.mkdir(exist_ok=True)
    entries = {}
    for index, (w, h, png) in decoded.items():
        atomic_write_bytes(contained(cache, f"{index}.png", what="native icon"), png)
        entries[str(index)] = {"width": w, "height": h, "sha256": hashlib.sha256(png).hexdigest()}
    manifest = {"schema": 1, "archive_sha256": sha, "sprites": entries}
    atomic_write_bytes(contained(cache, "manifest.json", what="icon manifest"),
                       (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    from .traits import TRAITS
    return {"cache": str(cache), "mapped_traits": len(set(ICON_SPECS) & set(TRAITS)),
            "icon_keys": len(ICON_SPECS), "unique_icons": len(decoded), "archive_sha256": sha,
            "note": "Restart the browser server to load this cache. Mod files and exports were not changed."}


def load_icon_cache(workspace: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Load only verified, bounded PNGs; a missing or corrupt optional cache stays text-only."""
    icons: dict[str, Any] = {}
    images: dict[str, bytes] = {}
    try:
        cache = contained(workspace, CACHE_NAME, what="native icon cache")
        manifest_path = contained(cache, "manifest.json", what="icon manifest")
        if not manifest_path.is_file() or manifest_path.stat().st_size > 128 * 1024:
            return icons, images
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("schema") != 1 or manifest.get("archive_sha256") != RES_SHA256:
            return icons, images
        records = manifest.get("sprites")
        if not isinstance(records, dict):
            return icons, images
        decoded = {}
        for index in {spec[0] for spec in ICON_SPECS.values()}:
            record = records.get(str(index))
            if not isinstance(record, dict):
                continue
            path = contained(cache, f"{index}.png", what="native icon")
            if not path.is_file() or path.stat().st_size > MAX_ICON_BYTES:
                continue
            png = path.read_bytes()
            if len(png) < 33 or png[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR":
                continue
            w, h = struct.unpack_from(">II", png, 16)
            if not 0 < w <= 64 or not 0 < h <= 64 or record.get("width") != w or record.get("height") != h:
                continue
            if hashlib.sha256(png).hexdigest() != record.get("sha256"):
                continue
            decoded[index] = (w, h, png)
        for key, (index, label, _call) in ICON_SPECS.items():
            if index not in decoded or not re.fullmatch(r"[a-z0-9_]+", key):
                continue
            w, h, png = decoded[index]
            icons[key] = {"url": f"/api/trait-icons/{key}.png", "width": w, "height": h,
                          "label": label, "sprite": index}
            images[key] = png
    except (OSError, ValueError, UnicodeError, KosmoError):
        return {}, {}
    return icons, images
