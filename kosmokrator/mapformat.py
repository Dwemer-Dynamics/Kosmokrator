"""Dominions 6 map syntax and bounded geography readers, separate from mod schemas."""
from __future__ import annotations

import bisect
import struct
from pathlib import Path
from typing import Any

from .dmparse import parse
from .tga import decode_tga

MAP_MANUAL = "https://www.illwinter.com/dom6/dom6mapman.pdf"
FORMAT_MANUAL = "https://www.illwinter.com/dom6/dom6fileformats.pdf"
MAX_PIXELS = 16 * 1024 * 1024
MAX_PROVINCES = 10000
TERRAIN_FLAGS = [{"value": 1 << power, "label": label} for power, label in (
    (0, "Small province"), (1, "Large province"), (2, "Sea"), (3, "Freshwater"),
    (4, "Highlands"), (5, "Swamp"), (6, "Waste"), (7, "Forest / kelp"), (8, "Farm"),
    (9, "No random start"), (10, "Many sites"), (11, "Deep sea"), (12, "Cave"),
    (13, "Fire sites"), (14, "Air sites"), (15, "Water sites"), (16, "Earth sites"),
    (17, "Astral sites"), (18, "Death sites"), (19, "Nature sites"), (20, "Glamour sites"),
    (21, "Blood sites"), (22, "Holy sites"), (23, "Mountains"), (25, "Good throne location"),
    (26, "Good start location"), (27, "Bad throne location"), (30, "Warmer"),
    (31, "Colder"), (36, "Cave wall"))]
BORDER_TYPES = [{"value": n, "label": label} for n, label in
                ((0, "Standard"), (1, "Mountain pass"), (2, "River"), (4, "Impassable"), (8, "Road"))]


def _arg(name: str, kind: str = "int", lo: int | None = None, hi: int | None = None) -> dict:
    return {"name": name, "type": kind, "min": lo, "max": hi}


# Only reviewed forms are editable. Unknown/new-version commands remain verbatim.
COMMANDS: dict[str, dict[str, Any]] = {}
def _schema(names: str, args: list[dict], scope: str = "global") -> None:
    for name in names.split():
        COMMANDS[name] = {"command": name, "args": args, "scope": scope}

P = _arg("province", lo=1, hi=MAX_PROVINCES)
N = _arg("nation", lo=0, hi=499)
_schema("dom2title description planename", [_arg("text", "str")])
_schema("imagefile winterimagefile", [_arg("filename", "str")])
_schema("mapsize", [_arg("width", lo=256, hi=65535), _arg("height", lo=256, hi=65535)])
_schema("domversion", [_arg("version", lo=1)])
_schema("nodeepcaves nodeepchoice mapnohide nohomelandnames nonamefilter wraparound hwraparound vwraparound", [])
_schema("neighbour", [P, _arg("neighbor", lo=1, hi=MAX_PROVINCES)])
_schema("neighbourspec", [P, _arg("neighbor", lo=1, hi=MAX_PROVINCES), _arg("border", lo=0, hi=15)])
_schema("landname", [P, _arg("name", "str")])
_schema("terrain", [P, _arg("terrain mask", lo=0, hi=2**53-1)])
_schema("gate", [P, _arg("gate", lo=0)])
_schema("start nostart", [P])
_schema("specstart", [N, P])
_schema("teamstart", [P, _arg("team", lo=0)])
_schema("allowedplayer cannotwin", [N])
_schema("computerplayer", [N, _arg("difficulty", lo=1, hi=5)])
_schema("victorycondition", [_arg("condition", lo=0), _arg("attribute", lo=0)])
_schema("features", [_arg("frequency", lo=0, hi=100)])
_schema("saildist", [_arg("distance", lo=1, hi=10)])
_schema("maptextcol", [_arg(c, "float", 0, 1) for c in ("red", "green", "blue", "alpha")])
_schema("mapdomcol", [_arg(c, lo=0, hi=255) for c in ("red", "green", "blue", "alpha")])
_schema("setland land", [P])
_schema("poptype", [_arg("population type", lo=0)], "province")
_schema("owner", [N], "province")
_schema("killfeatures temple lab", [], "province")
_schema("feature knownfeature", [_arg("site", "ref")], "province")
_schema("fort", [_arg("fort", lo=1)], "province")
_schema("unrest", [_arg("unrest", lo=0, hi=500)], "province")
_schema("population", [_arg("population", lo=0, hi=50000)], "province")
_schema("defence", [_arg("defence", lo=0, hi=125)], "province")
_schema("skybox batmap", [_arg("filename", "str")], "province")
_schema("groundcol rockcol fogcol", [_arg(c, lo=0, hi=255) for c in ("red", "green", "blue")], "province")
_schema("commander", [_arg("monster", "ref")], "province")
_schema("comname additem", [_arg("name", "str")], "commander")
_schema("bodyguards units", [_arg("count", lo=1), _arg("monster", "ref")], "commander")
_schema("xp", [_arg("experience", lo=0, hi=900)], "commander")
_schema("randomequip", [_arg("wealth", lo=0, hi=4)], "commander")
_schema("clearmagic", [], "commander")
_schema("mag_fire mag_air mag_water mag_earth mag_astral mag_death mag_nature mag_glamour mag_blood mag_priest",
        [_arg("level", lo=0)], "commander")
_schema("god", [N, _arg("monster", "ref")])
_schema("dominionstr", [N, _arg("strength", lo=1, hi=10)])
_schema("scale", [_arg("scale", "str"), N, _arg("value", lo=-5, hi=5)])


def statements(text: str):
    """Reuse the lossless lexer, without applying .dm block semantics to maps."""
    return parse(text).statements


def read_d6m(data: bytes) -> dict[str, Any]:
    """Read v3 geometry only; the game owns rendering of the recipe's terrain art."""
    if len(data) < 34:
        raise ValueError("Truncated d6m header")
    magic, version, w, h, spec = struct.unpack_from("<iiiiq", data)
    if magic != 898933:
        raise ValueError("Invalid d6m magic number")
    if version != 3:
        raise ValueError("Only documented d6m version 3 is supported")
    if w < 1 or h < 1 or w*h > MAX_PIXELS:
        raise ValueError("d6m dimensions exceed the preview limit")
    count = struct.unpack_from("<i", data, 30)[0]
    if not 1 <= count <= MAX_PROVINCES:
        raise ValueError("Invalid d6m province count")
    end = 34 + count*12 + w*h*4
    if len(data) != end+4 or struct.unpack_from("<i", data, end)[0] != 1155:
        raise ValueError("d6m length or final marker does not match its header")
    coords = []
    for i in range(count):
        x, y, flags = struct.unpack_from("<HHq", data, 34+i*12)
        if not 0 <= x < w or not 0 <= y < h:
            raise ValueError("d6m province coordinate is outside its image")
        coords.append({"id": i+1, "x": x, "y": h-1-y, "spec": flags})
    return {"width": w, "height": h, "positions": coords, "count": count,
            "note": "Schematic d6m coordinates; this is not the game's rendered terrain artwork."}


def geography(path: Path, rows) -> dict[str, Any]:
    """Resolve centres from d6m or TGA markers; #pb ownership gives authoritative TGA IDs."""
    data = path.read_bytes()
    if path.suffix.lower() == ".d6m":
        return {"kind": "d6m", **read_d6m(data)}
    if path.suffix.lower() != ".tga":
        return {"kind": "unavailable", "positions": [], "note": "RGB image preview is not supported; source is preserved."}
    w, h, rgba = decode_tga(data, max_pixels=MAX_PIXELS)
    white = []
    for y in range(h-1, -1, -1):
        line = rgba[y*w*4:(y+1)*w*4]
        pos = line.find(b"\xff\xff\xff")
        while pos >= 0:
            if pos % 4 == 0 and line[pos:pos+3] == b"\xff\xff\xff":
                white.append((pos//4, y))
            pos = line.find(b"\xff\xff\xff", pos+1)
        if len(white) > MAX_PROVINCES:
            raise ValueError("Too many white province markers (limit 10000)")
    spans: dict[int, list] = {}
    sums: dict[int, list] = {}
    for st in rows:
        if st.command != "pb" or len(st.args) != 4 or any(a.kind != "int" for a in st.args):
            continue
        x, y, length, pid = [a.value for a in st.args]
        if 0 <= x < w and 0 <= y < h and 0 < length <= w-x and 1 <= pid <= MAX_PROVINCES:
            spans.setdefault(h-1-y, []).append((x, x+length, pid))
            acc = sums.setdefault(pid, [0, 0, 0])
            acc[0] += (x+(length-1)/2)*length
            acc[1] += (h-1-y)*length
            acc[2] += length
    for line in spans.values():
        line.sort()
    positions = {}
    unowned = []
    for x, y in white:
        line = spans.get(y, [])
        idx = bisect.bisect_right(line, (x, w+1, MAX_PROVINCES+1))-1
        if idx >= 0 and line[idx][0] <= x < line[idx][1]:
            pid = line[idx][2]
            if pid in positions:
                raise ValueError("Multiple white centres belong to the same #pb province")
            positions[pid] = {"id": pid, "x": x, "y": y}
        else:
            unowned.append((x, y))
    for pid, (sx, sy, n) in sums.items():
        positions.setdefault(pid, {"id": pid, "x": sx/n, "y": sy/n})
    if not spans:
        positions = {i+1: {"id": i+1, "x": x, "y": y} for i, (x, y) in enumerate(white)}
    return {"kind": "tga", "width": w, "height": h, "positions": list(positions.values()),
            "count": len(white), "marker_count": len(white), "area_count": len(sums),
            "note": "Province positions use #pb ownership." if spans else
                    "Province IDs inferred from white pixels, bottom-to-top then left-to-right; verify numbering in the map editor.",
            "unowned_markers": len(unowned) if spans else 0}
