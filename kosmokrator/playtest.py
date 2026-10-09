"""Playtest records: human observations tied to the exact .dm SHA-256 they were made with.

Stored in <project>/playtests/records.json (outside the mod folder, so exports never include them). Records are
appended under the project lock; existing records are never rewritten. Kosmokrator stores what the tester wrote and
the evidence references they give; it draws no balance conclusions and does not open or verify evidence files.
"""

from __future__ import annotations

import contextlib
import json
import re
import secrets
from pathlib import Path
from typing import Any

from .author import _preview_flag, _sha
from .errors import KosmoError
from .paths import atomic_write_bytes, contained, is_link
from .project import _now, open_project, project_lock, read_dm, resolve_dm_target, sha256_bytes

EVIDENCE_KINDS = ("screenshot", "save", "log", "note", "map")
TEXT = {"game_version": 40, "nation": 80, "opponents": 300, "map": 160, "result_summary": 300,
        "observations": 4000, "tester": 60}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_RECORDS = 2000
NOTE = ("Records are observations by the tester, tied to the .dm SHA-256 they name. Kosmokrator makes no balance "
        "claim from them and does not open or verify evidence files.")
FIELDS = [
    {"key": "game_version", "label": "Game version", "type": "text", "max": 40, "help": "As shown in game."},
    {"key": "tester", "label": "Tester", "type": "text", "max": 60},
    {"key": "nation", "label": "Nation played", "type": "text", "max": 80},
    {"key": "opponents", "label": "Opponents / AI settings", "type": "text", "max": 300},
    {"key": "map", "label": "Map (name, seed or hash)", "type": "text", "max": 160},
    {"key": "turns", "label": "Turns played", "type": "int", "min": 0, "max": 500},
    {"key": "result_summary", "label": "Result summary", "type": "text", "max": 300},
    {"key": "observations", "label": "Observations", "type": "textarea", "max": 4000},
    {"key": "evidence", "label": "Evidence", "type": "evidence", "kinds": list(EVIDENCE_KINDS), "max_items": 20},
]


def _path(project: Any) -> Path:
    folder = contained(project.root, "playtests", what="playtests folder")
    if is_link(folder):
        raise KosmoError("symlink_rejected", "The playtests folder is a link.")
    return contained(project.root, "playtests/records.json", what="playtest records")


def _read(path: Path) -> list[dict[str, Any]]:
    if is_link(path):
        raise KosmoError("symlink_rejected", "The playtest file is a link.")
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise KosmoError("bad_playtests", "playtests/records.json cannot be read; fix or move it.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise KosmoError("bad_playtests", "playtests/records.json has an unexpected shape.")
    return data["records"]


def list_playtests(workspace: Path, slug: str) -> dict[str, Any]:
    project = open_project(workspace, slug)
    data, _t, _e = read_dm(resolve_dm_target(project, None))
    cur = sha256_bytes(data)
    recs = _read(_path(project))
    return {"current_sha256": cur, "records": [{**r, "matches_current": r.get("dm_sha256") == cur}
                                               for r in reversed(recs)],
            "fields": FIELDS, "file": "playtests/records.json", "note": NOTE}


def add_playtest(workspace: Path, slug: str, body: Any) -> dict[str, Any]:
    if not isinstance(body, dict) or set(body) - {"expected_sha256", "preview", "record"}:
        raise KosmoError("bad_request", "Body must be {expected_sha256, preview, record}.")
    sha, preview = _sha(body), _preview_flag(body)
    rec_in = body.get("record")
    if not isinstance(rec_in, dict) or set(rec_in) - (set(TEXT) | {"turns", "evidence"}):
        raise KosmoError("bad_request", "Unexpected fields in the record.")
    rec: dict[str, Any] = {}
    for k, lim in TEXT.items():
        v = rec_in.get(k)
        if v is None or v == "":
            continue
        if not isinstance(v, str) or len(v) > lim or "\x00" in v:
            raise KosmoError("bad_value", f"{k}: text of at most {lim} characters.", field=k)
        rec[k] = v.strip()
    t = rec_in.get("turns")
    if t is not None:
        if isinstance(t, bool) or not isinstance(t, int) or not 0 <= t <= 500:
            raise KosmoError("bad_value", "turns: whole number 0-500.", field="turns")
        rec["turns"] = t
    ev = rec_in.get("evidence") or []
    if not isinstance(ev, list) or len(ev) > 20:
        raise KosmoError("bad_value", "evidence: at most 20 entries.", field="evidence")
    evidence = []
    for e in ev:
        if not isinstance(e, dict) or set(e) - {"kind", "reference", "sha256"} or e.get("kind") not in EVIDENCE_KINDS \
                or not isinstance(e.get("reference"), str) or not 1 <= len(e["reference"].strip()) <= 300:
            raise KosmoError("bad_value", f"Each evidence entry needs a kind ({', '.join(EVIDENCE_KINDS)}) and a "
                                          "reference of 1-300 characters.", field="evidence")
        h = e.get("sha256")
        if h not in (None, "") and (not isinstance(h, str) or not SHA_RE.match(h.lower())):
            raise KosmoError("bad_value", "Evidence SHA-256 must be 64 hex characters.", field="evidence")
        evidence.append({"kind": e["kind"], "reference": e["reference"].strip(),
                         **({"sha256": h.lower()} if h else {})})
    rec["evidence"] = evidence
    if not rec.get("observations") and not rec.get("result_summary"):
        raise KosmoError("bad_value", "Write at least a result summary or observations.", field="observations")
    project = open_project(workspace, slug)
    with project_lock(project) if not preview else contextlib.nullcontext():
        data, _t, _e = read_dm(resolve_dm_target(project, None))
        cur = sha256_bytes(data)
        if cur != sha:
            raise KosmoError("sha_mismatch", "The .dm changed since this page loaded; a record must name the "
                                             "revision you tested. Reload; your form is kept.", expected=sha,
                             actual=cur)
        record = {"id": f"pt-{_now().replace(':', '').replace('-', '')}-{secrets.token_hex(3)}",
                  "created_utc": _now(), "dm_sha256": cur, **rec,
                  "claims": "none: observation only"}
        if preview:
            return {"preview": True, "written": False, "record": record, "note": NOTE}
        path = _path(project)
        recs = _read(path)
        if len(recs) >= MAX_RECORDS:
            raise KosmoError("too_many", f"At most {MAX_RECORDS} records per project.")
        folder = path.parent
        folder.mkdir(exist_ok=True)
        if is_link(folder):
            raise KosmoError("symlink_rejected", "The playtests folder is a link.")
        payload = {"schema": "kosmokrator.playtests/1", "records": recs + [record]}
        atomic_write_bytes(path, (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return {"preview": False, "written": True, "record": record, "note": NOTE}
