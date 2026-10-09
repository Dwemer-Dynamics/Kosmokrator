"""Minimal PNG/TGA header checks (stdlib only).

PNG: only the signature, the IHDR fields and the presence of a trailing IEND are checked. Chunk CRCs,
IDAT/zlib data, palettes and ancillary chunks are NOT decoded, so a PNG with a valid header can still
be corrupt; Dominions itself is the final authority.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

PNG_SIG = b"\x89PNG\r\n\x1a\n"
# PNG spec, IHDR: allowed bit depths per colour type.
PNG_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}


def image_info(path: Path) -> dict[str, Any]:
    """Return {format, width, height, depth, alpha, problems} from the file header."""
    data = path.read_bytes()
    ext = path.suffix.lower()
    info: dict[str, Any] = {"format": None, "width": None, "height": None, "depth": None, "problems": []}
    if data.startswith(PNG_SIG):
        info["format"] = "png"
        if len(data) < 33 or data[12:16] != b"IHDR" or struct.unpack(">I", data[8:12])[0] != 13:
            info["problems"].append("PNG is truncated or lacks a valid IHDR chunk")
            return info
        w, h, bit_depth, color_type, compression, filt, interlace = struct.unpack(">IIBBBBB", data[16:29])
        info.update(width=w, height=h, depth=bit_depth, alpha=color_type in (4, 6))
        if w == 0 or h == 0 or w > 0x7FFFFFFF or h > 0x7FFFFFFF:
            info["problems"].append(f"PNG has invalid dimensions {w}x{h}")
        if color_type not in PNG_DEPTHS:
            info["problems"].append(f"PNG colour type {color_type} is not defined")
        elif bit_depth not in PNG_DEPTHS[color_type]:
            info["problems"].append(f"PNG bit depth {bit_depth} is not allowed for colour type {color_type}")
        if compression != 0 or filt != 0 or interlace not in (0, 1):
            info["problems"].append(f"PNG IHDR has unsupported compression/filter/interlace "
                                    f"({compression}/{filt}/{interlace})")
        if b"IEND" not in data[-16:]:
            info["problems"].append("PNG has no IEND chunk at the end (truncated?)")
        if ext != ".png":
            info["problems"].append("PNG data in a file without .png extension")
        return info
    if ext == ".tga":
        info["format"] = "tga"
        if len(data) < 18:
            info["problems"].append("TGA header is truncated")
            return info
        id_len, cmap_type, img_type = data[0], data[1], data[2]
        w, h = struct.unpack("<HH", data[12:16])
        depth = data[16]
        info.update(width=w, height=h, depth=depth, alpha=depth == 32)
        # Manual (Files and File Formats, p.3): 24/32-bit colour, uncompressed or RLE.
        if cmap_type != 0 or img_type not in (2, 10):
            info["problems"].append(f"TGA type {img_type} (colour map {cmap_type}); must be true-colour "
                                    "uncompressed (2) or RLE (10)")
        if depth not in (24, 32):
            info["problems"].append(f"TGA depth {depth}; must be 24 or 32 bit")
        if w == 0 or h == 0:
            info["problems"].append("TGA has zero width or height")
        if img_type == 2 and depth in (24, 32) and len(data) < 18 + id_len + w * h * depth // 8:
            info["problems"].append("TGA pixel data is shorter than its header declares")
        return info
    info["problems"].append("not a PNG or TGA image")
    return info
