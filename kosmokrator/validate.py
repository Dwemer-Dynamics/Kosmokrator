"""Static validation of a project's .dm and assets.

Severity model:
  error      - known invalid per the manual/catalog; export is refused.
  warning    - legal but risky or contrary to manual guidance.
  unverified - outside the curated subset or not checkable offline; kept verbatim.
No result here guarantees that the mod loads, behaves or is balanced in game.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import MANUAL_VERSION
from . import commands as cmdreg
from .catalog import Catalog
from .dmparse import Arg, Block, ParseResult, Statement, definitions, parse
from .errors import KosmoError
from .images import image_info
from .paths import SAFE_NAME_RE, exact_case_lookup, is_link, mod_relpath_problems
from .project import (ID_KINDS, Project, dependency_texts, open_project, read_dm, resolve_dm_target,
                      sha256_bytes)

PATH_BITS = [128 << i for i in range(10)]  # Fire 128 ... Priest 65536 (Magic Paths, p.33)
LOC_BITS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 16384]  # Magic site locmasks (p.37)
IMAGE_EXT = {".tga", ".png"}
# Commands whose first argument is a file, wherever they appear (Visuals p.13, Mounts p.30, Mod Info p.5,
# Nation p.42, Items p.55, Sound p.5). Used so uncurated contexts still export their assets.
GENERIC_ASSETS = {"spr": "img", "spr1": "img", "spr2": "img", "xspr1": "img", "xspr2": "img",
                  "unmountedspr1": "img", "unmountedspr2": "img", "flag": "img", "indepflag": "img",
                  "icon": "img", "sample": "file"}
REF_CATEGORY = {"mon": "units", "monid": "units", "site": "sites", "sitename": "sites", "weapon": "weapons",
                "armor": "armors", "item": "items", "nation": "nations", "nationref": "nations", "spell": "spells"}
REF_KIND = {"mon": "monster", "monid": "monster", "site": "site", "sitename": "site", "weapon": "weapon", "armor": "armor",
            "item": "item", "nation": "nation", "nationref": "nation", "spell": "spell"}

LIMITATIONS = [
    "Static checks only: no result guarantees that Dominions loads the mod, or that it plays or balances well.",
    f"Command grammar combines reviewed schemas and the manual command index {MANUAL_VERSION}; unsupported signatures are "
    "reported as unverified and kept verbatim. Structural checking does not simulate command effects.",
    "Vanilla references are checked against the supplied third-party catalog, which may differ from the "
    "installed game version.",
    "Asset paths are resolved relative to the mod folder (the folder containing the .dm), per the manual's "
    "Files and File Formats section; confirm in game.",
    "Conflicts with mods that were not supplied as dependencies are not detected.",
]


class Report:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, severity: str, code: str, message: str, file: str | None = None, line: int | None = None,
            command: str | None = None, **extra: Any) -> None:
        item = {"severity": severity, "code": code, "message": message, "file": file, "line": line}
        if command:
            item["command"] = command
        item.update(extra)
        self.items.append(item)

    def of(self, severity: str) -> list[dict[str, Any]]:
        return [i for i in self.items if i["severity"] == severity]


class Index:
    """Known objects by id and lower-case name, from catalog, project and dependencies."""

    def __init__(self, catalog: Catalog | None) -> None:
        self.catalog = catalog
        self.ids: dict[str, dict[int, str]] = {}
        self.names: dict[str, dict[str, list[str]]] = {}
        self.name_identities: dict[tuple[str, str], set[Any]] = {}

    def add(self, kind: str, ident: int | None, name: str | None, origin: str) -> None:
        if ident is not None:
            self.ids.setdefault(kind, {}).setdefault(ident, origin)
        if name:
            self.names.setdefault(kind, {}).setdefault(name.lower(), []).append(origin)
            self.name_identities.setdefault((kind, name.lower()), set()).add(ident if ident is not None else ('named', origin))

    def resolve(self, typ: str, arg: Arg) -> tuple[str, str]:
        """Return (status, detail): status in ok / ambiguous / missing / unverified."""
        kind, cat = REF_KIND[typ], REF_CATEGORY[typ]
        if arg.kind == "int":
            if arg.value == -1 and typ == "nationref":
                return "unverified", "last manipulated nation reference depends on source order"
            if arg.value < 0 and kind == "monster":
                return "unverified", "negative monster numbers are montags/special references"
            if arg.value in self.ids.get(kind, {}):
                return "ok", self.ids[kind][arg.value]
            if self.catalog is not None and arg.value in self.catalog.ids(cat):
                return "ok", "catalog"
            return ("missing", "not defined in project, dependencies or catalog") if self.catalog else \
                ("unverified", "no catalog supplied")
        name = str(arg.value).lower()
        local = self.names.get(kind, {}).get(name, [])
        cat_ids = self.catalog.names(cat).get(name, []) if self.catalog else []
        hits = len(self.name_identities.get((kind, name), set()) | set(cat_ids))
        if hits == 1:
            return "ok", local[0] if local else "catalog"
        if hits > 1:
            return "ambiguous", f"name matches {hits} objects (catalog ids {cat_ids[:6]}, local {local[:3]})"
        return ("missing", "name not found in project, dependencies or catalog") if self.catalog else \
            ("unverified", "no catalog supplied")


def _check_args(st: Statement, spec: cmdreg.CommandSpec, rep: Report, file: str,
                refs: list[tuple[Statement, str, Arg]], assets: list[tuple[Statement, str, Arg]]) -> None:
    cmd = f"#{st.command}"
    required = sum(1 for a in spec.args if not a.optional)
    if len(st.args) < required:
        rep.add("error", "missing_argument", f"{cmd} needs {required} argument(s), got {len(st.args)}",
                file, st.line, cmd)
        return
    if len(st.args) > len(spec.args):
        rep.add("error", "extra_argument", f"{cmd} takes at most {len(spec.args)} argument(s), got {len(st.args)}",
                file, st.line, cmd)
    for a, s in zip(st.args, spec.args):
        t = s.type
        bad = None
        if t == "int" and a.kind != "int":
            bad = "an integer"
        elif t == "float" and a.kind not in ("int", "float"):
            bad = "a number"
        elif t in ("str", "img", "file", "sitename") and a.kind != "str":
            bad = "a double-quoted string"
            if t == "sitename" and a.kind == "int":
                bad += " (site assignment by number is not possible for this command)"
        elif t in ("mon", "monneg", "site", "weapon", "armor", "item", "spell", "nationref") and a.kind not in ("int", "str"):
            bad = "a quoted name or a number"
        elif t in ("nation", "monid") and a.kind != "int":
            bad = "a number"
        elif t in ("pathmask", "locmask") and a.kind != "int":
            bad = "an integer bitmask"
        if bad:
            rep.add("error", "bad_argument", f"{cmd} argument '{s.name}' must be {bad}, got {a.raw!r}",
                    file, st.line, cmd)
            continue
        if a.kind in ("int", "float"):
            v = a.value
            if s.lo is not None and v < s.lo or s.hi is not None and v > s.hi:
                rep.add("error", "out_of_range",
                        f"{cmd} argument '{s.name}'={a.raw} outside documented range "
                        f"{s.lo:g}..{'' if s.hi is None else f'{s.hi:g}'}", file, st.line, cmd)
            if s.choices is not None and v not in s.choices:
                rep.add("error", "out_of_range", f"{cmd} argument '{s.name}'={a.raw} not in documented values",
                        file, st.line, cmd, allowed=list(s.choices))
            if t == "pathmask":
                if v <= 0 or v & ~sum(PATH_BITS):
                    rep.add("error", "bad_mask", f"{cmd} mask {v} is not a sum of path masks 128..65536",
                            file, st.line, cmd)
                elif v == 65536:
                    rep.add("error", "priest_only_mask",
                            "#custommagic with only the priest mask crashes the mod (manual, Magic Paths p.33)",
                            file, st.line, cmd)
            if t == "locmask" and v & ~sum(LOC_BITS):
                rep.add("error", "bad_mask", f"{cmd} {v} is not a sum of documented locmask values",
                        file, st.line, cmd, allowed=LOC_BITS)
        if a.kind == "str" and st.command in ("descr", "description") and len(a.value) > 1999:
            rep.add("error", "description_too_long", f"{cmd} is {len(a.value)} characters; max 1999 (p.64)",
                    file, st.line, cmd)
        if t in cmdreg.REF_TYPES:
            refs.append((st, t, a))
        if t in cmdreg.ASSET_TYPES:
            assets.append((st, t, a))


def _check_statement(ctx: str, st: Statement, rep: Report, file: str, refs: list, assets: list) -> None:
    cmd = f"#{st.command}"
    spec = cmdreg.get(ctx, st.command)
    if spec is None:
        from .manual_commands import CONTEXTS, commands
        entry = commands(ctx).get(st.command) if ctx in CONTEXTS else None
        if entry and entry['editable']:
            args = tuple(cmdreg.ArgSpec(a['name'], a['type'], a.get('min'), a.get('max'),
                                        tuple(a['choices']) if a.get('choices') is not None else None,
                                        a.get('optional', False)) for a in entry['args'])
            spec = cmdreg.CommandSpec(st.command, ctx, args, 'Manual command index', entry['source']['page'], entry['summary'])
    if spec:
        _check_args(st, spec, rep, file, refs, assets)
        return
    if st.command in GENERIC_ASSETS and st.args and st.args[0].kind == "str":
        assets.append((st, GENERIC_ASSETS[st.command], st.args[0]))
    if ctx not in cmdreg.CORE_CONTEXTS:
        rep.add("unverified", "uncurated_context", f"{cmd} inside a {ctx} block is not checked", file, st.line,
                cmd, raw=st.raw)
        return
    if st.command in cmdreg.DOCUMENTED[ctx]:
        rep.add("unverified", "documented_uncurated", f"{cmd} is documented for {ctx} but its arguments are "
                "not checked", file, st.line, cmd, raw=st.raw)
        return
    curated_elsewhere = sorted({c for (c, n) in cmdreg.REGISTRY if n == st.command} - {ctx})
    documented_elsewhere = [c for c in cmdreg.documented_contexts(st.command) if c != ctx]
    if ctx == "top" and (curated_elsewhere or documented_elsewhere):
        rep.add("error", "needs_block", f"{cmd} must be inside a {'/'.join(curated_elsewhere or documented_elsewhere)}"
                " block (nothing is selected at top level)", file, st.line, cmd)
    elif curated_elsewhere:
        rep.add("error", "wrong_context", f"{cmd} is documented for {'/'.join(curated_elsewhere)} blocks, not {ctx}",
                file, st.line, cmd)
    elif documented_elsewhere:
        rep.add("warning", "wrong_context", f"{cmd} is documented for {'/'.join(documented_elsewhere)}, not {ctx}",
                file, st.line, cmd)
    else:
        rep.add("unverified", "unknown_command", f"{cmd} is not in the curated subset; kept verbatim", file,
                st.line, cmd, raw=st.raw)


def _block_rules(b: Block, rep: Report, file: str, catalog: Catalog | None) -> None:
    sts = b.statements
    names = [s.command for s in sts]
    first = lambda c: names.index(c) if c in names else None  # noqa: E731
    if b.context == "monster" and b.new:
        if "name" not in names:
            rep.add("warning", "unnamed_monster", "New monster has no #name", file, b.opener.line)
        cs = first("copystats")
        if cs is not None:
            if cs != 0:
                rep.add("warning", "copystats_order", "#copystats overwrites earlier commands; use it first after "
                        "#newmonster (p.13)", file, sts[cs].line, "#copystats")
            if "name" in names[:cs]:
                rep.add("warning", "name_overwritten", "#name before #copystats is overwritten; put #name after it",
                        file, sts[first("name")].line, "#name")
            for add, clear in (("weapon", "clearweapons"), ("armor", "cleararmor")):
                ai = first(add)
                if ai is not None and ai > cs and clear not in names[cs:ai]:
                    rep.add("warning", f"no_{clear}", f"#{add} after #copystats without #{clear} adds to the "
                            "inherited equipment (p.17)", file, sts[ai].line, f"#{add}")
            base = sts[cs].args[0].value if sts[cs].args and sts[cs].args[0].kind == "int" else None
            row = catalog.row("units", base) if (catalog and base is not None) else None
            if row is not None:
                has_magic = any((row.get(k) or "").strip() not in ("", "0") for k in
                                ("F", "A", "W", "E", "S", "D", "N", "G", "B", "H", "mask1"))
                if has_magic and ("magicskill" in names or "custommagic" in names) and "clearmagic" not in names:
                    rep.add("warning", "inherited_magic", f"Base {base} has magic; add #clearmagic before setting "
                            "paths or the inherited paths/randoms remain", file, sts[cs].line, "#copystats")
        holy_magic = any(s.command == "magicskill" and len(s.args) == 2 and s.args[0].value == 9 for s in sts) or \
            any(s.command == "custommagic" and s.args and s.args[0].kind == "int" and s.args[0].value & 65536
                for s in sts)
        if holy_magic and "holy" not in names:
            inherited = False
            if cs is not None and catalog and sts[cs].args and sts[cs].args[0].kind == "int":
                row = catalog.row("units", sts[cs].args[0].value)
                inherited = bool(row and (row.get("holy") or "").strip() not in ("", "0") and "clearspec" not in names)
            if not inherited:
                rep.add("warning", "holy_required", "Units with Holy magic must also have #holy (p.33)",
                        file, b.opener.line)
    if b.context == "site" and b.new and "name" not in names:
        rep.add("warning", "unnamed_site", "New site has no #name", file, b.opener.line)
    if b.context == "nation":
        ni = first("name")
        if ni is not None and ni != 0:
            rep.add("error", "nation_name_order", "#name must be the first command when modifying a nation (p.41)",
                    file, sts[ni].line, "#name")
        ei = first("era")
        if ei is not None:
            allowed = {"name", "epithet"}
            if any(c not in allowed for c in names[:ei]):
                rep.add("warning", "era_order", "#era should come right after #name/#epithet; texts may not work "
                        "otherwise (p.42)", file, sts[ei].line, "#era")
        starts = [s for s in sts if s.command == "startsite"]
        if len(starts) > 4:
            rep.add("error", "too_many_startsites", "#startsite can be used at most 4 times (p.43)",
                    file, starts[4].line, "#startsite")
        sc = first("startcom")
        for c in ("startunittype1", "startunittype2", "startunitnbrs1", "startunitnbrs2", "startscout"):
            ci = first(c)
            if ci is not None and sc is not None and ci < sc:
                rep.add("warning", "startcom_order", f"#{c} before #startcom is cleared by it (p.45)",
                        file, sts[ci].line, f"#{c}")
        dc = first("defcom1")
        if dc is not None:
            for i, c in enumerate(names[:dc]):
                if c.startswith(("defunit", "defmult", "defcom2")):
                    rep.add("warning", "defcom1_order", f"#{c} before #defcom1 is cleared by it (p.45)",
                            file, sts[i].line, f"#{c}")


def _check_asset(project: Project, st: Statement, t: str, a: Arg, rep: Report, file: str,
                 used: dict[str, Path]) -> None:
    cmd = f"#{st.command}"
    ref = str(a.value)
    problems = mod_relpath_problems(ref)
    if problems:
        for p in problems:
            rep.add("error", "bad_asset_path", f"{cmd} {ref!r}: {p}", file, st.line, cmd, asset=ref)
        return
    if t == "img" and Path(ref).suffix.lower() not in IMAGE_EXT:
        rep.add("error", "bad_image_type", f"{cmd} {ref!r}: images must be .tga or .png (p.3)", file, st.line, cmd,
                asset=ref)
    found, why = exact_case_lookup(project.mod_dir, ref)
    if found is None:
        msg = {"missing": "file not found in the mod folder",
               "case_mismatch": "file exists with different letter case; filenames are case sensitive (p.3)",
               "symlink": "path traverses a symlink/junction",
               "not_a_file": "not a regular file"}[why or "missing"]
        rep.add("error", f"asset_{why}", f"{cmd} {ref!r}: {msg}", file, st.line, cmd, asset=ref)
        return
    used[ref] = found
    if t != "img":
        return
    info = image_info(found)
    for p in info["problems"]:
        rep.add("error", "bad_image", f"{cmd} {ref!r}: {p}", file, st.line, cmd, asset=ref)
    w, h = info.get("width"), info.get("height")
    if w and h and not info["problems"]:
        if st.command in ("flag", "indepflag") and (w, h) != (128, 128):
            rep.add("error", "flag_size", f"{cmd} image is {w}x{h}; it must be 128x128 (p.43)", file, st.line, cmd,
                    asset=ref)
        elif st.command == "icon" and (w, h) not in ((128, 32), (256, 64)):
            rep.add("warning", "icon_size", f"#icon is {w}x{h}; manual suggests 128x32 or 256x64", file, st.line, cmd,
                    asset=ref)
        elif st.command.startswith(("spr", "xspr", "unmountedspr")) and (w not in (8, 16, 32, 64, 128) or
                                                                         h not in (8, 16, 32, 64, 128)):
            rep.add("warning", "sprite_size", f"{cmd} is {w}x{h}; manual suggests 8/16/32/64/128 px", file,
                    st.line, cmd, asset=ref)


def _scan_mod_dir(project: Project, rep: Report) -> list[str]:
    """Check filesystem names in the mod folder; returns relative file list."""
    files = []
    for dirpath, dirnames, filenames in os.walk(project.mod_dir, followlinks=False):
        d = Path(dirpath)
        for name in list(dirnames) + filenames:
            p = d / name
            rel = p.relative_to(project.mod_dir).as_posix()
            if is_link(p):
                rep.add("error", "symlink_in_mod", f"{rel} is a symlink/junction; not allowed", project.rel(p))
                if name in dirnames:
                    dirnames.remove(name)
                continue
            if not SAFE_NAME_RE.match(name):
                rep.add("error", "unsafe_filename", f"{rel}: spaces or special characters in filenames break "
                        "network lobby use (p.3)", project.rel(p))
            if name in filenames:
                files.append(rel)
    return files


def validate_project(workspace: Path, slug: str, catalog: Catalog | None = None,
                     dependencies: list[str] | None = None) -> dict[str, Any]:
    project = open_project(workspace, slug)
    rep = Report()
    dm_rel = project.rel(project.dm_path)
    if not project.dm_path.is_file():
        raise KosmoError("dm_missing", f"Authoritative .dm missing at {dm_rel}")
    if project.dm_path.name != f"{slug}.dm" or project.dm_path.parent.name != slug:
        rep.add("error", "dm_placement", "The .dm must be <slug>/<slug>.dm inside the mod folder (p.3)", dm_rel)
    files = _scan_mod_dir(project, rep)
    for f in files:
        if f.endswith(".dm") and f != f"{slug}.dm":
            rep.add("warning", "extra_dm", f"Extra .dm file {f} is not part of this mod's export", dm_rel)

    data, text, enc = read_dm(resolve_dm_target(project, None))
    pr: ParseResult = parse(text)
    for issue in pr.issues:
        rep.add(issue["severity"], "syntax", issue["message"], dm_rel, issue["line"])
    for s in pr.stray:
        rep.add("warning", "stray_text", f"Text outside commands/comments is ignored: {s['text'][:60]!r}",
                dm_rel, s["line"])

    refs: list[tuple[Statement, str, Arg]] = []
    assets: list[tuple[Statement, str, Arg]] = []
    for st in pr.toplevel:
        _check_statement("top", st, rep, dm_rel, refs, assets)
    for b in pr.blocks:
        if b.context == "unknown":
            rep.add("unverified", "unknown_block", f"#{b.opener.command} block is not curated; contents kept "
                    "verbatim", dm_rel, b.opener.line, f"#{b.opener.command}", raw=b.opener.raw)
            for st in b.statements:
                if st.command in GENERIC_ASSETS and st.args and st.args[0].kind == "str":
                    assets.append((st, GENERIC_ASSETS[st.command], st.args[0]))
            continue
        for st in [b.opener, *b.statements]:
            _check_statement(b.context, st, rep, dm_rel, refs, assets)
        _block_rules(b, rep, dm_rel, catalog)

    # Definitions, duplicates and id ranges.
    index = Index(catalog)
    own = definitions(pr)
    dep_defs: list[tuple[str, dict[str, Any]]] = []
    deps = list(project.meta.get("dependencies") or []) + list(dependencies or [])
    for label, dep_text in dependency_texts(workspace, deps):
        for d in definitions(parse(dep_text)):
            dep_defs.append((label, d))
            index.add(d["kind"], d["id"], d["name"], label)
    reserved = {k: {int(r["id"]) for r in v} for k, v in project.meta.get("reservations", {}).items()}
    seen: dict[tuple[str, int], int] = {}
    new_names: dict[tuple[str, str], int] = {}
    for d in own:
        kind, ident, line = d["kind"], d["id"], d["line"]
        index.add(kind, ident, d["name"], "project")
        if d["new"] and ident is None and kind in ("monster", "site", "nation"):
            rep.add("unverified", "auto_id", f"Unnumbered #new{kind}: the game assigns the id; references must "
                    "use the name and may shift if the mod changes (p.4)", dm_rel, line)
        if ident is None:
            continue
        key = (kind, ident)
        if key in seen and (d["new"] or kind == "nation"):
            sev = "error" if d["new"] else "warning"
            rep.add(sev, "duplicate_definition", f"{kind} {ident} also defined/selected at line {seen[key]}",
                    dm_rel, line, object_kind=kind, object_id=ident)
        seen.setdefault(key, line)
        dep_hit = [lbl for lbl, dd in dep_defs if dd["kind"] == kind and dd["id"] == ident]
        if dep_hit:
            rep.add("error" if d["new"] else "warning", "dependency_conflict",
                    f"{kind} {ident} is also defined/selected in {dep_hit[0]}", dm_rel, line,
                    object_kind=kind, object_id=ident)
        cat_name = ID_KINDS.get(kind, {}).get("catalog")
        in_catalog = bool(catalog and cat_name and ident in catalog.ids(cat_name))
        if d["new"] and in_catalog:
            rep.add("error", "id_in_use", f"New {kind} {ident} collides with an existing catalog object", dm_rel, line,
                    object_kind=kind, object_id=ident)
        if kind == "monster" and d["new"] and 9000 <= ident <= 19999:
            rep.add("warning", "id_range", f"Monster {ident} is outside 5000-8999 given in #newmonster (p.13), "
                    "though inside the 0-19999 limit table (p.64)", dm_rel, line)
        if kind == "nation":
            if in_catalog:
                rep.add("warning", "modifies_existing_nation", f"#selectnation {ident} modifies an existing "
                        "nation from the catalog", dm_rel, line)
            elif ident < 150:
                rep.add("warning", "id_range", f"Nation {ident} is below the 150+ range for new nations (p.41)",
                        dm_rel, line)
        if kind in ID_KINDS and (d["new"] or (kind == "nation" and not in_catalog))                 and ident not in reserved.get(kind, set()):
            rep.add("warning", "unreserved_id", f"{kind} {ident} was not reserved with allocate_ids", dm_rel, line)
    for d in own:
        if d["new"] and d["name"]:
            k = (d["kind"], d["name"].lower())
            if k in new_names:
                rep.add("warning", "duplicate_name", f"New {d['kind']} name {d['name']!r} also used at line "
                        f"{new_names[k]}; name references become ambiguous", dm_rel, d["line"])
            new_names.setdefault(k, d["line"])
            cat_name = ID_KINDS.get(d["kind"], {}).get("catalog") or {"item": "items", "spell": "spells"}.get(d["kind"])
            if catalog and cat_name and d["name"].lower() in catalog.names(cat_name):
                rep.add("warning", "name_shadows_catalog", f"New {d['kind']} name {d['name']!r} also exists in the "
                        "catalog; name references become ambiguous", dm_rel, d["line"])

    # References.
    for st, t, a in refs:
        status, detail = index.resolve(t, a)
        cmd = f"#{st.command}"
        if status == "missing":
            rep.add("error", "unresolved_reference", f"{cmd} {a.raw}: {detail}", dm_rel, st.line, cmd, argument=a.value)
        elif status == "ambiguous":
            rep.add("warning", "ambiguous_reference", f"{cmd} {a.raw}: {detail}; prefer a number", dm_rel, st.line, cmd,
                    argument=a.value)
        elif status == "unverified":
            rep.add("unverified", "unverified_reference", f"{cmd} {a.raw}: {detail}", dm_rel, st.line, cmd,
                    argument=a.value)

    # Assets.
    used_assets: dict[str, Path] = {}
    for st, t, a in assets:
        _check_asset(project, st, t, a, rep, dm_rel, used_assets)
    for f in files:
        if f != f"{slug}.dm" and f not in used_assets and not f.endswith(".dm"):
            rep.add("warning", "unreferenced_file", f"{f} is not referenced by the .dm and will not be exported",
                    dm_rel, asset=f)

    errors, warnings, unverified = rep.of("error"), rep.of("warning"), rep.of("unverified")
    return {
        "project": slug, "file": dm_rel, "sha256": sha256_bytes(data), "encoding": enc,
        "ok": not errors,
        "counts": {"errors": len(errors), "warnings": len(warnings), "unverified": len(unverified)},
        "errors": errors, "warnings": warnings, "unverified": unverified,
        "assets": {k: project.rel(v) for k, v in sorted(used_assets.items())},
        "target_game_version": project.meta.get("target_game_version"),
        "manual_version": MANUAL_VERSION,
        "catalog": catalog.meta if catalog else None,
        "dependencies": deps,
        "limitations": LIMITATIONS,
    }
