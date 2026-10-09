"""Tiny stdlib TGA writer used for the demo's original flag."""

from __future__ import annotations

import struct

RGBA = tuple[int, int, int, int]


def encode_tga(width: int, height: int, pixels: list[list[RGBA]]) -> bytes:
    """Uncompressed 32-bit true-colour TGA; pixels[y][x] with y=0 at the top."""
    # Image type 2, 32 bpp, descriptor 0x08 = 8 alpha bits, classic bottom-left origin (rows stored bottom-up).
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 0x08)
    body = bytearray()
    for row in reversed(pixels):
        for r, g, b, a in row:
            body += bytes((b, g, r, a))
    return header + bytes(body)


def nation_flag(seed: str = "Hebdomad", colour: tuple[int, int, int] | None = None,
                finial: str | None = None) -> bytes:
    """Original Dom6-style standard: plain folded cloth and a distinct metal finial above its crossbar."""
    import hashlib
    import math

    key = hashlib.sha256(seed.encode("utf-8")).digest()
    base = colour or ((142, 48, 31), (54, 89, 119), (68, 103, 59), (113, 63, 111))[key[0] % 4]
    shape = finial or ("sun", "spear", "anvil", "flame")[key[1] % 4]
    if shape not in ("sun", "spear", "anvil", "flame", "seal"):
        raise ValueError("Unknown flag finial")
    px = [[(0, 0, 0, 0) for _ in range(128)] for _ in range(128)]
    staff = ((62, 43, 27), (117, 85, 48), (171, 133, 77), (113, 79, 43), (52, 36, 25))
    for y in range(49, 128):
        for x in range(61, 66):
            px[y][x] = staff[x-61] + (255,)
    for y in range(55, 59):
        for x in range(30, 99):
            px[y][x] = ((186, 148, 84) if y == 55 else (94, 65, 34)) + (255,)
    for x in range(36, 93):
        bottom = 117 - int(15 * (1 - abs(x-64)/28))
        for y in range(59, bottom):
            fold = .78 + .17 * math.cos((x-36)*.27) + .05 * math.sin(y*.18+x*.07)
            edge = x < 38 or x > 90 or y < 61 or y >= bottom-2
            c = (157, 119, 57) if edge else tuple(max(1, min(255, int(v*fold))) for v in base)
            px[y][x] = c + (255,)
    # Keep the silhouette separate from the cloth; left highlights and right shadows suggest solid metal.
    for y in range(28, 54):
        for x in range(47, 82):
            dx, dy = x-64, y-40
            r = math.hypot(dx, dy)
            on = False
            if shape in ("sun", "seal"):
                on = (7 <= r <= 10) if shape == "seal" else r <= 8
                if r <= 13:
                    for i in range(7):
                        angle = -math.pi/2+i*2*math.pi/7
                        if math.hypot(dx-11*math.cos(angle), dy-11*math.sin(angle)) <= 2:
                            on = True
                if shape == "seal" and abs(dx) <= 3 and 35 <= y <= 45:
                    on = abs(dx) <= max(0, (y-35)//2) and y <= 43 or abs(dx) <= 2 and y > 43
            elif shape == "spear":
                on = abs(dx) <= max(0, (y-28)//3) and y <= 42 or abs(dx) <= 2 and y >= 40
            elif shape == "anvil":
                on = (34 <= y <= 39 and -15 <= dx <= 13-(y-34)) or (39 <= y <= 45 and abs(dx) <= 4) or (46 <= y <= 49 and abs(dx) <= 9)
            elif shape == "flame":
                on = 30 <= y <= 44 and abs(dx+int(2*math.sin(y*.5))) <= max(0,(y-30)//3) or 45 <= y <= 49 and abs(dx) <= 9-(y-45)
            if on:
                c = (220, 180, 100) if dx < -2 else (170, 124, 57) if dx < 3 else (106, 72, 31)
                if shape == "seal" and abs(dx) <= 3 and 35 <= y <= 45:
                    c = (227, 121, 35) if dx < 1 else (143, 61, 21)
                px[y][x] = c + (255,)
    return encode_tga(128, 128, px)


def hebdomad_flag() -> bytes:
    """Fire/earth standard with a seven-rayed bronze seal enclosing a small flame."""
    return nation_flag("Hebdomad", (142, 48, 31), "seal")


def default_mod_banner() -> bytes:
    """Original 256x64 bronze header for new projects, replacing the game's unknown-mod graphic."""
    import math

    px = [[(36, 29, 25, 255) for _ in range(256)] for _ in range(64)]
    for y in range(64):
        for x in range(256):
            edge = min(x, 255-x, y, 63-y)
            if edge < 2:
                px[y][x] = (141, 107, 57, 255)
            elif edge == 2:
                px[y][x] = (65, 47, 30, 255)
            else:
                px[y][x] = (43 + (x+y)%3, 32 + (x+y)%3, 28, 255)
            r = math.hypot(x-128, y-32)
            if 19 <= r < 21 or abs(x-128)+abs(y-32) < 8:
                px[y][x] = (196, 156, 78, 255)
    return encode_tga(256, 64, px)


def decode_tga(data: bytes, max_pixels: int = 1024 * 1024) -> tuple[int, int, bytes]:
    """Decode true-colour 24/32-bit TGA (type 2 raw or 10 RLE) to (width, height, top-down RGBA bytes).

    Only the formats the manual allows for mod images are supported; anything else raises ValueError.
    """
    if len(data) < 18:
        raise ValueError("TGA header is truncated")
    id_len, cmap_type, img_type = data[0], data[1], data[2]
    w, h = struct.unpack("<HH", data[12:16])
    depth, desc = data[16], data[17]
    if cmap_type != 0 or img_type not in (2, 10) or depth not in (24, 32):
        raise ValueError(f"unsupported TGA (type {img_type}, colour map {cmap_type}, {depth} bit)")
    if not w or not h or w * h > max_pixels:
        raise ValueError(f"TGA size {w}x{h} is empty or too large to preview")
    bpp = depth // 8
    pos = 18 + id_len
    need = w * h * bpp
    if img_type == 2:
        raw = data[pos:pos + need]
    else:
        out = bytearray()
        while len(out) < need:
            if pos >= len(data):
                break
            hdr = data[pos]
            pos += 1
            n = (hdr & 0x7F) + 1
            if hdr & 0x80:
                out += data[pos:pos + bpp] * n
                pos += bpp
            else:
                out += data[pos:pos + n * bpp]
                pos += n * bpp
        raw = bytes(out[:need])
    if len(raw) < need:
        raise ValueError("TGA pixel data is shorter than its header declares")
    rows = []
    for y in range(h):
        row = bytearray()
        line = raw[y * w * bpp:(y + 1) * w * bpp]
        for x in range(0, len(line), bpp):
            b, g, r = line[x], line[x + 1], line[x + 2]
            row += bytes((r, g, b, line[x + 3] if bpp == 4 else 255))
        rows.append(bytes(row))
    if not desc & 0x20:  # bit 5 clear = bottom-left origin, rows stored bottom-up
        rows.reverse()
    if desc & 0x10:  # bit 4 set = right-to-left columns
        rows = [b"".join(r[i:i + 4] for i in range(len(r) - 4, -4, -4)) for r in rows]
    return w, h, b"".join(rows)


def encode_png(width: int, height: int, rgba: bytes) -> bytes:
    """Minimal RGBA PNG (filter 0 rows, zlib) used to preview TGA files in a browser."""
    import zlib

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    stride = width * 4
    raw = b"".join(b"\x00" + rgba[y * stride:(y + 1) * stride] for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
