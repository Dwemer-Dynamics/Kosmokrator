"""Bounded authoring for the local web browser: create or duplicate monsters and pretenders, create nations, and
attach uploaded PNG sprite frames to a project monster.

Every write follows one transaction under the project lock: the expected SHA-256 of the .dm is checked, ids come
from project.free_ids_locked (catalog, .dm, dependencies and reservations) and are reserved in the metadata, the
candidate text is a set of pure insertions (or, for artwork, small spans inside one block) that is re-parsed and
re-checked, and only then is the .dm backed up and replaced. If the .dm write fails the reservation is rolled back;
if that also fails the error says which ids stay reserved. Uploaded frames are new, uniquely named files; on any
failure only the files this request created are removed. Existing art files are never overwritten or deleted.

Nothing here edits arbitrary text, writes outside the project mod folder or installs into the game.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import difflib
import os
import re
import secrets
import struct
import zlib
from pathlib import Path
from typing import Any, Callable

from .browse import build_project_model
from .catalog import Catalog, search
from .dmparse import Block, block_id, newline_style, parse
from .errors import KosmoError
from .paths import contained, is_link
from .project import (_save_meta, free_ids_locked, open_project, project_lock, read_dm,
                      record_reservations_locked, reload_meta, resolve_dm_target, sha256_bytes, write_dm_locked)
from .validate import Report, _check_statement

SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")
TEXT_LIMITS = {"name": 60, "epithet": 60, "descr": 1999}
ROLES = ("troop", "commander", "god")
PATHS = ["F", "A", "W", "E", "S", "D", "N", "G", "B", "H"]
MAX_START_SITES = 4
MAX_ROSTER = 40
# PNG frame contract (Kosmokrator rules for unit sprites, docs/ASSET-RULESET.md).
PNG_SIG = b"\x89PNG\r\n\x1a\n"
MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_FRAME_SIDE = 256
RECOMMENDED_SIDE = 64
FRAME_CMDS = {"idle": "spr1", "attack": "spr2"}


# ---------- shared helpers ----------
def _text(body: dict[str, Any], key: str, required: bool, field: str | None = None) -> str | None:
    v = body.get(key)
    lim = TEXT_LIMITS.get(field or key, 200)
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise KosmoError("bad_value", f"{key} is required.", field=key)
        return None
    if not isinstance(v, str):
        raise KosmoError("bad_value", f"{key} must be text.", field=key)
    v = v.strip()
    if '"' in v or any(c in v for c in "\r\n\t\x00#") or len(v) > lim:
        raise KosmoError("bad_value", f"{key} must be at most {lim} characters without double quotes, '#', tabs "
                                      "or line breaks.", field=key)
    return v


def _int(body: dict[str, Any], key: str, lo: int, hi: int, required: bool = True) -> int | None:
    v = body.get(key)
    if v is None and not required:
        return None
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise KosmoError("bad_value", f"{key} must be a whole number {lo}-{hi}.", field=key)
    return v


def _sha(body: dict[str, Any]) -> str:
    sha = body.get("expected_sha256")
    if not isinstance(sha, str) or not SHA_RE.match(sha):
        raise KosmoError("bad_request", "expected_sha256 must be the 64-hex SHA-256 the page shows.")
    return sha.lower()


def _preview_flag(body: dict[str, Any]) -> bool:
    p = body.get("preview", False)
    if not isinstance(p, bool):
        raise KosmoError("bad_request", "preview must be true or false.")
    return p


def _nl(text: str) -> str:
    return "\r\n" if newline_style(text) == "crlf" else "\n"


def _unique_block(pr: Any, context: str, openers: tuple[str, ...], ident: int, text: str) -> Block:
    hits = [b for b in pr.blocks if b.context == context and b.opener.command in openers and block_id(b) == ident]
    if len(hits) != 1:
        raise KosmoError("object_missing" if not hits else "ambiguous_block",
                         f"Expected exactly one {'/'.join('#' + o for o in openers)} {ident} block, found {len(hits)}.",
                         lines=[b.opener.line for b in hits])
    b = hits[0]
    if b.end is None or text[text.rfind("\n", 0, b.end.start) + 1:b.end.start].strip():
        raise KosmoError("not_editable", f"Block {ident} is not closed by #end on its own line.", lines=[b.opener.line])
    return b


def _end_pos(text: str, b: Block) -> int:
    return text.rfind("\n", 0, b.end.start) + 1  # type: ignore[union-attr]


def _apply(text: str, inserts: list[tuple[int, str]]) -> str:
    out = text
    for pos, ins in sorted(inserts, key=lambda x: x[0], reverse=True):
        out = out[:pos] + ins + out[pos:]
    return out


def _check_new(cand: str, old_issues: int, new_lines: set[int], dm_rel: str) -> None:
    """The candidate gains no syntax problems and its new lines pass the curated argument checks."""
    pr = parse(cand)
    if len(pr.issues) != old_issues:
        raise KosmoError("preflight_failed", "The new text would add syntax problems; nothing was written.")
    rep = Report()
    for b in pr.blocks:
        for st in [b.opener, *b.statements]:
            if st.line in new_lines:
                _check_statement(b.context, st, rep, dm_rel, [], [])
    errs = rep.of("error")
    if errs:
        raise KosmoError("preflight_failed", "Generated commands fail the curated argument checks.",
                         problems=[i["message"] for i in errs][:10])


def _line_numbers(text: str, inserts: list[tuple[int, str]]) -> set[int]:
    """1-based line numbers, in the candidate, of the lines added by `inserts`."""
    lines: set[int] = set()
    shift = 0
    for pos, ins in sorted(inserts, key=lambda x: x[0]):
        first = text.count("\n", 0, pos) + 1 + shift
        n = ins.count("\n")
        lines.update(range(first, first + max(n, 1)))
        shift += n
    return lines


def _diff(old: str, new: str, rel: str) -> str:
    d = list(difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile=f"a/{rel}", tofile=f"b/{rel}",
                                  lineterm="", n=1))
    return "\n".join(d[:400])


def _model(workspace: Path, slug: str, catalog: Catalog | None, sha: str) -> dict[str, Any]:
    m = build_project_model(workspace, slug, catalog)
    if m["provenance"]["sha256"].lower() != sha:
        raise KosmoError("sha_mismatch", "The .dm changed since this page loaded. Reload; your form values are kept.",
                         expected=sha, actual=m["provenance"]["sha256"])
    return m


def _transaction(workspace: Path, slug: str, sha: str, preview: bool, kinds: dict[str, int],
                 labels: dict[str, list[str | None]], catalog: Catalog | None,
                 build: Callable[[str, dict[str, list[int]]], tuple[list[tuple[int, str]], dict[str, Any]]]
                 ) -> dict[str, Any]:
    """Reserve ids and insert generated text under one project lock (no nested locks)."""
    project = open_project(workspace, slug)
    with project_lock(project) if not preview else contextlib.nullcontext():
        reload_meta(project)
        path = resolve_dm_target(project, None)
        data, text, enc = read_dm(path)
        if sha256_bytes(data).lower() != sha:
            raise KosmoError("sha_mismatch", "The .dm changed since this page loaded. Reload; your form values are "
                                             "kept.", expected=sha, actual=sha256_bytes(data))
        ids = {k: free_ids_locked(project, k, n, None, catalog)[0] for k, n in kinds.items()}
        inserts, info = build(text, ids)
        assets = info.pop("_assets", {})
        cand = _apply(text, inserts)
        rel = project.rel(path)
        _check_new(cand, len(parse(text).issues), _line_numbers(text, inserts), rel)
        try:
            new_data = cand.encode(enc)
        except UnicodeEncodeError as exc:
            raise KosmoError("encoding", f"The new text cannot be written in the file's {enc} encoding.") from exc
        out = {"project": slug, "preview": preview, "ids": ids, "diff": _diff(text, cand, rel),
               "before_sha256": sha256_bytes(data), "assets": list(assets), **info}
        if preview:
            return {**out, "written": False,
                    "note": "Preview only: ids are re-checked and reserved when you create; they can change if "
                            "another reservation is made first."}
        before_meta = {k: list(v) for k, v in (project.meta.get("reservations") or {}).items()}
        for k, v in ids.items():
            record_reservations_locked(project, k, v, labels.get(k))
        written_assets = []
        try:
            for asset_rel, asset_data in assets.items():
                target = contained(project.mod_dir, asset_rel, what="generated asset")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as fh:
                    written_assets.append(target)
                    fh.write(asset_data)
            backup = write_dm_locked(project, path, data, new_data)
        except BaseException as exc:
            for target in written_assets:
                target.unlink(missing_ok=True)
            try:
                project.meta["reservations"] = before_meta
                _save_meta(project)
            except OSError:
                raise KosmoError("write_failed_reservation_kept", "The .dm was not changed, and rolling back the "
                                                                  "id reservation also failed; these ids stay "
                                                                  "reserved in kosmokrator.json.",
                                 counts={k: v for k, v in ids.items()}) from exc
            if isinstance(exc, OSError):
                raise KosmoError("write_failed", "The .dm could not be written; nothing changed and the id "
                                                 "reservation was rolled back.") from exc
            raise
    return {**out, "written": True, "after_sha256": sha256_bytes(new_data), "backup": backup}


def _project_monsters(m: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {x["id"]: x for x in m["monsters"] if x.get("new") and isinstance(x.get("id"), int)}


def _nation_block_id(m: dict[str, Any], nid: Any) -> dict[str, Any]:
    if isinstance(nid, bool) or not isinstance(nid, int):
        raise KosmoError("bad_value", "Choose a nation from this project.", field="nation")
    n = next((x for x in m["nations"] if x.get("id") == nid), None)
    if n is None:
        raise KosmoError("bad_value", f"Nation {nid} is not defined by a #selectnation block in this project.",
                         field="nation")
    return n


# ---------- donor lookup ----------
def donor_search(catalog: Catalog | None, query: str, limit: int = 25) -> dict[str, Any]:
    """Bounded catalog unit search for the create form (id or name substring)."""
    if catalog is None:
        raise KosmoError("catalog_missing", "No game-data catalog: vanilla donors cannot be searched.")
    q = (query or "").strip()
    if not q or len(q) > 60:
        raise KosmoError("bad_query", "Type 1-60 characters of a unit name or an id.")
    res = search(catalog, q, "units", max(1, min(limit, 40)))
    return {"query": q, "results": [{"id": r["id"], "name": r["name"]} for r in res["results"]],
            "total_matches": res["total_matches"], "truncated": res["truncated"]}


# ---------- monsters and pretenders ----------
def _role_inserts(text: str, pr: Any, m: dict[str, Any], body: dict[str, Any], mid: int, role: str) -> tuple[list[tuple[int, str]], list[str]]:
    """Nation or start-site lines that make the new monster a troop, commander or god of one nation."""
    nl = _nl(text)
    if role == "none":
        return [], ["Not recruited by any nation yet; add it to a nation later."]
    n = _nation_block_id(m, body.get("nation"))
    nb = _unique_block(pr, "nation", ("selectnation",), n["id"], text)
    if role == "god":
        return [(_end_pos(text, nb), f"#addgod {mid}{nl}")], [f"#addgod {mid} in {n.get('name') or n['id']}"]
    where = body.get("recruit")
    if where == "fort":
        cmd = "addrecunit" if role == "troop" else "addreccom"
        return [(_end_pos(text, nb), f"#{cmd} {mid}{nl}")], [f"#{cmd} {mid} in {n.get('name') or n['id']} (forts)"]
    site_id = body.get("site")
    if where != "site" or isinstance(site_id, bool) or not isinstance(site_id, int):
        raise KosmoError("bad_value", "Choose where it is recruited: forts of the nation, or one of its start "
                                      "sites (capital only).", field="recruit")
    site = next((s for s in m["sites"] if s.get("id") == site_id), None)
    if site is None or n["uid"] not in (site.get("start_site_of") or []):
        raise KosmoError("bad_value", f"Site {site_id} is not a project start site of this nation.", field="site")
    sb = _unique_block(pr, "site", ("newsite", "selectsite"), site_id, text)
    cmd = "homemon" if role == "troop" else "homecom"
    return [(_end_pos(text, sb), f"#{cmd} {mid}{nl}")], [f"#{cmd} {mid} at {site.get('name') or site_id} (capital only)"]


def _god_lines(body: dict[str, Any]) -> list[str]:
    g = body.get("god")
    if not isinstance(g, dict) or set(g) - {"startdom", "pathcost", "gcost", "magic"}:
        raise KosmoError("bad_value", "A new god needs startdom and pathcost (gcost and magic optional).", field="god")
    sd = _int(g, "startdom", 1, 10)
    pc = _int(g, "pathcost", 1, 200)
    gc = _int(g, "gcost", 0, 19999, required=False)
    lines = ["#homerealm 0", f"#startdom {sd}", f"#pathcost {pc}"]
    if gc is not None:
        lines.append(f"#gcost {gc}")
    magic = g.get("magic") or {}
    if not isinstance(magic, dict) or len(magic) > 10:
        raise KosmoError("bad_value", "magic must map path letters to levels.", field="magic")
    for p in PATHS:
        if p in magic:
            lv = _int(magic, p, 1, 10)
            lines.append(f"#magicskill {PATHS.index(p)} {lv}")
    if set(magic) - set(PATHS):
        raise KosmoError("bad_value", "Unknown magic path.", field="magic")
    return lines


def create_monster(workspace: Path, slug: str, catalog: Catalog | None, body: Any) -> dict[str, Any]:
    """New unit/god from a donor, or an exact duplicate of a project #newmonster block with a new id."""
    allowed = {"expected_sha256", "preview", "mode", "role", "donor", "source_id", "name", "descr", "nation",
               "recruit", "site", "god"}
    if not isinstance(body, dict) or set(body) - allowed:
        raise KosmoError("bad_request", "Unexpected fields in the create request.")
    sha, preview = _sha(body), _preview_flag(body)
    mode, role = body.get("mode"), body.get("role")
    if mode not in ("new", "duplicate"):
        raise KosmoError("bad_request", "mode must be 'new' or 'duplicate'.")
    if role not in ROLES + ("none",):
        raise KosmoError("bad_value", "Choose troop, commander, god or not recruited.", field="role")
    name = _text(body, "name", True)
    descr = _text(body, "descr", False)
    m = _model(workspace, slug, catalog, sha)
    pm = _project_monsters(m)
    warnings: list[str] = []
    if role == "god" and mode == "new":
        god_lines = _god_lines(body)
        if any(x.startswith("#magicskill 9 ") for x in god_lines):
            warnings.append("Holy (H) magic also needs #holy on the monster; add it with Edit values after creating.")
    elif body.get("god") is not None:
        raise KosmoError("bad_value", "God settings apply only to a new god.", field="god")
    if mode == "new":
        donor = body.get("donor")
        if not isinstance(donor, dict) or set(donor) - {"source", "id"} or donor.get("source") not in ("catalog", "project") \
                or isinstance(donor.get("id"), bool) or not isinstance(donor.get("id"), int):
            raise KosmoError("bad_value", "Choose a donor unit (catalog search or a project unit).", field="donor")
        did = donor["id"]
        if donor["source"] == "catalog":
            if catalog is None or catalog.row("units", did) is None:
                raise KosmoError("bad_value", f"Unit {did} is not in the catalog.", field="donor")
            donor_name = catalog.row("units", did).get("name")
        else:
            if did not in pm:
                raise KosmoError("bad_value", f"{did} is not a #newmonster defined in this project.", field="donor")
            donor_name = pm[did].get("name")
            warnings.append("Project donor: #copystats/#copyspr copy the donor as the game has read it so far; the new "
                            "block is appended after it.")
    else:
        sid = body.get("source_id")
        if isinstance(sid, bool) or not isinstance(sid, int) or sid not in pm:
            raise KosmoError("bad_value", "Choose a project #newmonster to duplicate.", field="source_id")
        if role == "god":
            g = pm[sid]["resolved"]["god"]
            if g["startdom"]["value"] is None or g["pathcost"]["value"] is None:
                raise KosmoError("bad_value", "The source has no #startdom/#pathcost, so it cannot be added as a god. "
                                              "Duplicate it as a unit, then set those with Edit values.", field="role")

    def build(text: str, ids: dict[str, list[int]]) -> tuple[list[tuple[int, str]], dict[str, Any]]:
        nl = _nl(text)
        mid = ids["monster"][0]
        pr = parse(text)
        if mode == "new":
            lines = [f"#newmonster {mid}", f"#copystats {did}", f"#copyspr {did}", f'#name "{name}"']
            if descr:
                lines.append(f'#descr "{descr}"')
            if role == "god":
                lines += god_lines
            lines.append("#end")
            block = nl.join(lines) + nl
            explain = [f"Copies stats, equipment, magic and abilities of {donor_name or did} (#{did}) with #copystats, "
                       "and its sprite with #copyspr. Change values afterwards with Edit values; upload art to "
                       "replace the borrowed sprite."]
        else:
            src = _unique_block(pr, "monster", ("newmonster",), sid, text)
            raw = text[src.opener.start:src.end.end]  # type: ignore[union-attr]
            block = _duplicate_text(raw, mid, name, descr, nl) + nl
            explain = [f"Exact copy of #newmonster {sid}: every command, comment, unknown command and sprite path is "
                       "kept; only the id, #name" + (" and #descr" if descr else "") + " change. Sprite files are "
                       "shared until you upload new art for the copy (the originals are never modified)."]
        pre = nl if text and not text.endswith("\n") else ""
        tail = [(len(text), f"{pre}{nl}-- Created in the Kosmokrator browser{nl}{block}")]
        role_ins, role_text = _role_inserts(text, pr, m, body, mid, role)
        return tail + role_ins, {"id": mid, "uid": f"monster:{mid}", "role": role, "assignments": role_text,
                                 "explanation": explain, "warnings": warnings,
                                 "route": "pretenders" if role == "god" else "units"}

    return _transaction(workspace, slug, sha, preview, {"monster": 1}, {"monster": [name]}, catalog, build)


def _duplicate_text(raw: str, mid: int, name: str, descr: str | None, nl: str) -> str:
    """Rewrite the opener id and the live #name/#descr of a copied block; everything else is byte-identical."""
    pr = parse(raw)
    b = pr.blocks[0]
    resets = [s for s in b.statements if s.command in ("copystats", "clear")]
    last_reset = resets[-1] if resets else None
    spans: list[tuple[int, int, str]] = [(b.opener.start, b.opener.end, f"#newmonster {mid}")]
    for cmd, value in (("name", name), ("descr", descr)):
        if value is None:
            continue
        live = [s for s in b.statements if s.command == cmd and s.args and s.args[0].kind == "str"
                and (last_reset is None or s.start > last_reset.start)]
        if live:
            st = live[-1]
            a = st.start + st.raw.find(st.args[0].raw)
            spans.append((a, a + len(st.args[0].raw), f'"{value}"'))
        else:
            anchor = last_reset or b.opener
            eol = raw.find("\n", anchor.end)
            eol = len(raw) if eol == -1 else eol + 1
            spans.append((eol, eol, f'#{cmd} "{value}"{nl}'))
    out = raw
    for a, z, rep in sorted(spans, key=lambda s: (s[0], s[1]), reverse=True):
        out = out[:a] + rep + out[z:]
    return out


# ---------- nations ----------
def create_nation(workspace: Path, slug: str, catalog: Catalog | None, body: Any) -> dict[str, Any]:
    allowed = {"expected_sha256", "preview", "name", "epithet", "era", "descr", "sites", "realms", "troops",
               "commanders", "gods", "startcom", "startscout", "startunits"}
    if not isinstance(body, dict) or set(body) - allowed:
        raise KosmoError("bad_request", "Unexpected fields in the nation request.")
    sha, preview = _sha(body), _preview_flag(body)
    name = _text(body, "name", True)
    epithet = _text(body, "epithet", True)
    descr = _text(body, "descr", False)
    era = body.get("era")
    if isinstance(era, bool) or not isinstance(era, int) or era not in (1, 2, 3):
        raise KosmoError("bad_value", "Era must be 1 (early), 2 (middle) or 3 (late).", field="era")
    m = _model(workspace, slug, catalog, sha)
    pm = _project_monsters(m)

    def ids_of(key: str, limit: int, what: str, ok: Callable[[dict[str, Any]], bool] = lambda _x: True) -> list[int]:
        v = body.get(key) or []
        if not isinstance(v, list) or len(v) > limit or len(set(map(repr, v))) != len(v):
            raise KosmoError("bad_value", f"{key}: at most {limit} different entries.", field=key)
        for i in v:
            if isinstance(i, bool) or not isinstance(i, int) or i not in pm or not ok(pm[i]):
                raise KosmoError("bad_value", f"{key}: {i!r} is not a project {what}.", field=key)
        return v

    troops = ids_of("troops", MAX_ROSTER, "#newmonster")
    commanders = ids_of("commanders", MAX_ROSTER, "#newmonster")
    gods = ids_of("gods", MAX_ROSTER, "custom god (needs #startdom and #pathcost)",
                  lambda x: x["resolved"]["god"]["startdom"]["value"] is not None
                  and x["resolved"]["god"]["pathcost"]["value"] is not None)
    one = lambda k: (ids_of(k, 1, "#newmonster") or [None])[0]  # noqa: E731
    startcom, startscout = one("startcom"), one("startscout")
    su = body.get("startunits") or []
    if not isinstance(su, list) or len(su) > 2:
        raise KosmoError("bad_value", "At most two starting squads.", field="startunits")
    squads = []
    for sq in su:
        if not isinstance(sq, dict) or set(sq) != {"id", "count"} \
                or isinstance(sq["id"], bool) or not isinstance(sq["id"], int) or sq["id"] not in pm \
                or isinstance(sq["count"], bool) or not isinstance(sq["count"], int) or not 1 <= sq["count"] <= 60:
            raise KosmoError("bad_value", "Each starting squad needs a project unit and a count 1-60.", field="startunits")
        squads.append((sq["id"], sq["count"]))
    sites_in = body.get("sites") or []
    if not isinstance(sites_in, list) or len(sites_in) > MAX_START_SITES or len(set(map(repr, sites_in))) != len(sites_in):
        raise KosmoError("bad_value", f"At most {MAX_START_SITES} different start sites.", field="sites")
    site_names = []
    for sid in sites_in:
        s = next((x for x in m["sites"] if x.get("id") == sid and x.get("new")), None)
        if s is None or not s.get("name") or '"' in s["name"]:
            raise KosmoError("bad_value", f"Site {sid!r} is not a named #newsite in this project.", field="sites")
        site_names.append(s["name"])
    realms = body.get("realms") or []
    if not isinstance(realms, list) or any(isinstance(r, bool) or not isinstance(r, int) or not 1 <= r <= 10
                                           for r in realms) or len(set(realms)) != len(realms):
        raise KosmoError("bad_value", "Home realms must be distinct numbers 1-10.", field="realms")
    warnings = []
    if startcom is None:
        warnings.append("No starting commander chosen (#startcom). What the game does for a new nation without one "
                        "is not verified; pick one before testing.")
    if not troops and not commanders:
        warnings.append("No recruitable troops or commanders yet.")
    if not gods and not realms:
        warnings.append("No pretenders: choose custom gods or home realms, or the nation may have none to pick.")
    if not site_names:
        warnings.append("No start sites.")

    def build(text: str, ids: dict[str, list[int]]) -> tuple[list[tuple[int, str]], dict[str, Any]]:
        nl = _nl(text)
        nid = ids["nation"][0]
        lines = [f"#selectnation {nid}", f'#name "{name}"', f'#epithet "{epithet}"', f"#era {era}"]
        if descr:
            lines.append(f'#descr "{descr}"')
        lines.append("#clearnation")
        flag_rel = f"art/nations/{nid}-flag.tga"
        lines.append(f'#flag "{flag_rel}"')
        from .tga import nation_flag
        lines += [f'#startsite "{s}"' for s in site_names]
        lines += [f"#homerealm {r}" for r in sorted(realms)]
        lines += [f"#addgod {g}" for g in gods]
        lines += [f"#addrecunit {t}" for t in troops] + [f"#addreccom {c}" for c in commanders]
        if startcom is not None:
            lines.append(f"#startcom {startcom}")
        if startscout is not None:
            lines.append(f"#startscout {startscout}")
        for i, (uid, cnt) in enumerate(squads, 1):
            lines += [f"#startunittype{i} {uid}", f"#startunitnbrs{i} {cnt}"]
        lines.append("#end")
        pre = nl if text and not text.endswith("\n") else ""
        return [(len(text), f"{pre}{nl}-- Nation created in the Kosmokrator browser{nl}" + nl.join(lines) + nl)], {
            "id": nid, "uid": f"nation:{nid}", "warnings": warnings,
            "_assets": {flag_rel: nation_flag(f"{nid}:{name}")},
            "explanation": ["#name, #epithet and #era come first, then #clearnation and the explicit choices. "
                            "A shaded hanging standard is generated automatically. Realm 10 (Default) is added only "
                            "when ticked. Customize the flag and colours through source/assets; "
                            "test in Dominions 6."]}

    return _transaction(workspace, slug, sha, preview, {"nation": 1}, {"nation": [name]}, catalog, build)


# ---------- PNG frames ----------
def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def decode_png_rgba(data: bytes) -> tuple[int, int, bytes]:
    """Strict stdlib decode of an 8-bit RGBA, non-interlaced PNG: chunk CRCs, IHDR, IDAT, filters, IEND.

    Returns (width, height, RGBA bytes). Raises ValueError with a readable reason for anything else.
    """
    if len(data) > MAX_FRAME_BYTES:
        raise ValueError(f"file is larger than {MAX_FRAME_BYTES // 1024} KB")
    if not data.startswith(PNG_SIG):
        raise ValueError("not a PNG file (bad signature)")
    pos, idat, ihdr, ended, seen_idat_end = 8, bytearray(), None, False, False
    while pos < len(data):
        if pos + 12 > len(data):
            raise ValueError("truncated chunk")
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        if ln > len(data) or pos + 12 + ln > len(data):
            raise ValueError("chunk length runs past the end of the file")
        body = data[pos + 8:pos + 8 + ln]
        crc = struct.unpack(">I", data[pos + 8 + ln:pos + 12 + ln])[0]
        if zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            raise ValueError(f"CRC mismatch in {kind!r} chunk")
        pos += 12 + ln
        if ihdr is None and kind != b"IHDR":
            raise ValueError("IHDR must be the first chunk")
        if kind == b"IHDR":
            if ihdr is not None or ln != 13:
                raise ValueError("bad IHDR")
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            if seen_idat_end:
                raise ValueError("IDAT chunks are not consecutive")
            idat += body
        elif kind == b"IEND":
            if ln != 0:
                raise ValueError("IEND must be empty")
            ended = True
            break
        else:
            if idat:
                seen_idat_end = True
            if not kind[0] & 0x20:
                raise ValueError(f"unsupported critical chunk {kind.decode('latin-1')!r}")
    if not ended or pos != len(data):
        raise ValueError("missing IEND or data after IEND")
    w, h, depth, ctype, comp, filt, inter = ihdr  # type: ignore[misc]
    if depth != 8 or ctype != 6:
        raise ValueError(f"must be 8-bit RGBA (truecolour with alpha); got bit depth {depth}, colour type {ctype}")
    if comp or filt or inter:
        raise ValueError("interlaced or non-standard compression/filter method")
    if not (1 <= w <= MAX_FRAME_SIDE and 1 <= h <= MAX_FRAME_SIDE):
        raise ValueError(f"size {w}x{h} is outside 1-{MAX_FRAME_SIDE} px")
    stride = w * 4
    need = h * (stride + 1)
    dec = zlib.decompressobj()
    try:
        raw = dec.decompress(bytes(idat), need + 1)
    except zlib.error as exc:
        raise ValueError(f"image data does not decompress: {exc}") from exc
    if len(raw) != need or not dec.eof or dec.unconsumed_tail or dec.unused_data:
        raise ValueError("image data size does not match the header")
    out = bytearray(h * stride)
    prev = bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if f > 4:
            raise ValueError(f"bad filter type {f} on row {y}")
        for x in range(stride):
            a = line[x - 4] if x >= 4 else 0
            b = prev[x]
            c = prev[x - 4] if x >= 4 else 0
            if f == 1:
                line[x] = (line[x] + a) & 0xFF
            elif f == 2:
                line[x] = (line[x] + b) & 0xFF
            elif f == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 0xFF
            elif f == 4:
                line[x] = (line[x] + _paeth(a, b, c)) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, bytes(out)


def check_frame(data: bytes) -> dict[str, Any]:
    """Decode and apply the sprite contract: binary alpha, not empty. Returns facts plus warnings."""
    w, h, px = decode_png_rgba(data)
    alpha = px[3::4]
    partial = sum(1 for a in alpha if a not in (0, 255))
    if partial:
        raise ValueError(f"{partial} pixel(s) have partial transparency; alpha must be 0 or 255 only")
    rows = [y for y in range(h) if any(alpha[y * w:(y + 1) * w])]
    if not rows:
        raise ValueError("the image is fully transparent")
    cols = [x for x in range(w) if any(alpha[x::w])]
    warnings = []
    if (w, h) != (RECOMMENDED_SIDE, RECOMMENDED_SIDE):
        warnings.append(f"{w}x{h} px; most unit sprites are {RECOMMENDED_SIDE}x{RECOMMENDED_SIDE}.")
    if h - 1 - rows[-1] > 2:
        warnings.append(f"The lowest opaque row is {h - 1 - rows[-1]} px above the bottom edge; check that the feet "
                        "stand on the bottom like vanilla sprites.")
    return {"width": w, "height": h, "bytes": len(data), "sha256": sha256_bytes(data),
            "bbox": [cols[0], rows[0], cols[-1], rows[-1]], "warnings": warnings}


def upload_art(workspace: Path, slug: str, mid: int, catalog: Catalog | None, body: Any) -> dict[str, Any]:
    """Write new PNG frame files and point #spr1/#spr2 of one project #newmonster block at them."""
    if not isinstance(body, dict) or set(body) - {"expected_sha256", "preview", "frames"}:
        raise KosmoError("bad_request", "Body must be {expected_sha256, preview, frames}.")
    sha, preview = _sha(body), _preview_flag(body)
    frames_in = body.get("frames")
    if not isinstance(frames_in, dict) or not frames_in or set(frames_in) - set(FRAME_CMDS):
        raise KosmoError("bad_request", "frames must contain idle and/or attack.")
    frames: dict[str, bytes] = {}
    facts: dict[str, Any] = {}
    for k, v in frames_in.items():
        if not isinstance(v, str) or len(v) > (MAX_FRAME_BYTES * 4) // 3 + 8:
            raise KosmoError("bad_png", f"{k}: base64 PNG of at most {MAX_FRAME_BYTES // 1024} KB expected.", field=k)
        try:
            frames[k] = base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise KosmoError("bad_png", f"{k}: not valid base64.", field=k) from exc
        try:
            facts[k] = check_frame(frames[k])
        except ValueError as exc:
            raise KosmoError("bad_png", f"{k} frame rejected: {exc}.", field=k) from exc
    if len(facts) == 2 and (facts["idle"]["width"], facts["idle"]["height"]) != (facts["attack"]["width"],
                                                                                  facts["attack"]["height"]):
        facts["attack"]["warnings"].append("Idle and attack frames have different sizes; the sprite may jump.")
    m = _model(workspace, slug, catalog, sha)
    mon = _project_monsters(m).get(mid)
    if mon is None:
        raise KosmoError("object_missing", f"No project #newmonster {mid}; art can be attached only to monsters "
                                           "defined in this project.")
    gf = mon["resolved"]["god"]
    is_god = mon.get("role") == "pretender" or (gf["startdom"]["value"] is not None and gf["pathcost"]["value"] is not None)
    folder = "pretenders" if is_god else "units"
    project = open_project(workspace, slug)
    written: list[Path] = []
    with project_lock(project) if not preview else contextlib.nullcontext():
        path = resolve_dm_target(project, None)
        data, text, enc = read_dm(path)
        if sha256_bytes(data).lower() != sha:
            raise KosmoError("sha_mismatch", "The .dm changed since this page loaded. Reload; your chosen files are kept.",
                             expected=sha, actual=sha256_bytes(data))
        pr = parse(text)
        b = _unique_block(pr, "monster", ("newmonster",), mid, text)
        token = secrets.token_hex(4)
        refs = {k: f"art/{folder}/{mid}-{token}-{k}.png" for k in frames}
        cand, plan = _sprite_patch(text, b, refs)
        rel = project.rel(path)
        new_lines = {i + 1 for i, ln in enumerate(cand.splitlines()) if any(r in ln for r in refs.values())}
        _check_new(cand, len(pr.issues), new_lines, rel)
        new_data = cand.encode(enc)
        out = {"project": slug, "id": mid, "preview": preview, "frames": facts, "files": list(refs.values()),
               "plan": plan, "diff": _diff(text, cand, rel), "before_sha256": sha256_bytes(data)}
        if preview:
            return {**out, "written": False}
        try:
            art_dir = contained(project.mod_dir, f"art/{folder}", what="art folder")
            for part in (project.mod_dir / "art", art_dir):
                contained(project.mod_dir, part, what="art folder")
                if is_link(part):
                    raise KosmoError("symlink_rejected", "The art folder is a link or junction.")
                part.mkdir(exist_ok=True)
                if is_link(part) or not part.is_dir():
                    raise KosmoError("symlink_rejected", "The art folder is a link, junction or not a folder.")
            for k, ref in refs.items():
                target = contained(project.mod_dir, ref, what="art file")
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
                written.append(target)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(frames[k])
                    fh.flush()
                    os.fsync(fh.fileno())
            backup = write_dm_locked(project, path, data, new_data)
        except BaseException as exc:
            for p in written:
                with contextlib.suppress(OSError):
                    os.unlink(p)
            if isinstance(exc, KosmoError):
                raise
            if isinstance(exc, OSError):
                raise KosmoError("write_failed", "Writing the art or the .dm failed; files created by this request "
                                                 "were removed and the .dm is unchanged.") from exc
            raise
    return {**out, "written": True, "after_sha256": sha256_bytes(new_data), "backup": backup}


def _sprite_patch(text: str, b: Block, refs: dict[str, str]) -> tuple[str, list[dict[str, Any]]]:
    """Replace or add #spr1/#spr2 in the block and drop its #copyspr lines (so no donor sprite is aliased)."""
    nl = _nl(text)
    spans: list[tuple[int, int, str]] = []
    plan: list[dict[str, Any]] = []
    existing = {k: [s for s in b.statements if s.command == c] for k, c in FRAME_CMDS.items()}
    copyspr = [s for s in b.statements if s.command == "copyspr"]
    for k, sts in existing.items():
        if len(sts) > 1:
            raise KosmoError("edit_blocked", f"#{FRAME_CMDS[k]} appears {len(sts)} times in this block; fix the source "
                                             "first.", lines=[s.line for s in sts])
    if copyspr:
        missing = [k for k in FRAME_CMDS if k not in refs and not existing[k]]
        if missing:
            raise KosmoError("edit_blocked", "This monster borrows its sprite with #copyspr. Upload both frames so "
                                             "that #copyspr can be removed without losing the "
                                             f"{' and '.join(missing)} frame.", lines=[s.line for s in copyspr])
    end_ls = _end_pos(text, b)
    for k, ref in refs.items():
        sts = existing[k]
        if sts:
            st = sts[0]
            a = st.start + (st.raw.find(st.args[0].raw) if st.args else len(st.raw))
            z = a + (len(st.args[0].raw) if st.args else 0)
            spans.append((a, z, f'{" " if not st.args else ""}"{ref}"'))
            plan.append({"frame": k, "action": "replace", "line": st.line, "before": st.raw.strip(),
                         "after": f'#{FRAME_CMDS[k]} "{ref}"'})
        else:
            spans.append((end_ls, end_ls, f'#{FRAME_CMDS[k]} "{ref}"{nl}'))
            plan.append({"frame": k, "action": "append", "after": f'#{FRAME_CMDS[k]} "{ref}"'})
    for st in copyspr:
        ls = text.rfind("\n", 0, st.start) + 1
        le = text.find("\n", st.end)
        le = len(text) if le == -1 else le + 1
        if text[ls:st.start].strip() or text[st.end:le].strip():
            spans.append((st.start, st.end, ""))
        else:
            spans.append((ls, le, ""))
        plan.append({"frame": "copyspr", "action": "remove", "line": st.line, "before": st.raw.strip(),
                     "explanation": "Removed so the donor's sprite no longer applies to this monster."})
    out = text
    for a, z, rep in sorted(spans, key=lambda s: (s[0], s[1]), reverse=True):
        out = out[:a] + rep + out[z:]
    return out, plan
