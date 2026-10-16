"""argparse CLI. Exit codes: 0 ok, 1 validation found errors, 2 operation/usage error."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import DEFAULT_TARGET_GAME_VERSION, __version__
from .core import Kosmokrator, envelope


def _read_arg_file(path: str | None) -> str | None:
    if path is None:
        return None
    data = sys.stdin.buffer.read() if path == "-" else Path(path).read_bytes()
    return data.decode("utf-8")


def _common(p: argparse.ArgumentParser, sub: bool) -> None:
    # Subparser copies use SUPPRESS so they do not overwrite values given before the subcommand.
    d = (lambda v: argparse.SUPPRESS) if sub else (lambda v: v)
    p.add_argument("--workspace", "-w", default=d(None),
                   help="Explicit workspace root (required for project operations)")
    p.add_argument("--catalog", default=d(None), help="Path to a local dom6inspector checkout or its gamedata "
                                                      "folder (default: $KOSMOKRATOR_CATALOG)")
    p.add_argument("--target-version", default=d(DEFAULT_TARGET_GAME_VERSION),
                   help=f"Target Dominions version recorded in new projects (default {DEFAULT_TARGET_GAME_VERSION})")
    p.add_argument("--json", action="store_true", default=d(False), help="Print the full JSON result")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    _common(common, sub=True)
    ap = argparse.ArgumentParser(prog="kosmokrator", description="Static Dominions 6 mod project tooling "
                                 "(no game launch, no load/balance guarantee).")
    _common(ap, sub=False)
    ap.add_argument("--version", action="version", version=f"kosmokrator {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    p = sub.add_parser("create", parents=[common], help="Create a new project (refuses to overwrite)")
    p.add_argument("slug")
    p.add_argument("--name")
    p.add_argument("--description")

    p = sub.add_parser("inspect", parents=[common], help="Parse the project's .dm without changing it")
    p.add_argument("project")
    p.add_argument("--file", help="Other .dm inside the mod folder (default: the authoritative .dm)")

    p = sub.add_parser('view', parents=[common], help='Resolved project model, references and compatibility report')
    p.add_argument('project')

    p = sub.add_parser("patch", parents=[common], help="Guarded single replace/insert with SHA-256 check")
    p.add_argument("project")
    p.add_argument("--expected-sha256", required=True)
    p.add_argument("--old-file", help="File holding the exact text to replace ('-' for stdin)")
    p.add_argument("--new-file", help="File holding the replacement text")
    p.add_argument("--insert-line", type=int, help="Insert before this 1-based line (last+1 appends)")
    p.add_argument("--text-file", help="File holding the text to insert")
    p.add_argument("--file", help="Other .dm inside the mod folder")

    p = sub.add_parser("lookup", parents=[common], help="Look up a command in the curated manual subset")
    p.add_argument("command", nargs="?", help="Command name, e.g. #startsite; omit to list curated commands")
    p.add_argument("--context", choices=["top", "monster", "site", "nation", "weapon", "armor", "spell", "item", "merc", "event"])

    p = sub.add_parser("allocate", parents=[common], help="Reserve free ids in the documented modding range")
    p.add_argument("project")
    p.add_argument("kind", choices=["monster", "site", "nation", "weapon", "armor"])
    p.add_argument("count", type=int, nargs="?", default=1)
    p.add_argument("--label", action="append", default=[])
    p.add_argument("--dep", action="append", default=[], help="Dependency .dm inside the workspace")

    p = sub.add_parser("search", parents=[common], help="Search the local game-data catalog")
    p.add_argument("query")
    p.add_argument("--category", default="all",
                   choices=["all", "units", "nations", "weapons", "armors", "sites", "spells", "items"])
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--project", help="Search this project's reference snapshot when it has one")

    p = sub.add_parser("validate", parents=[common], help="Static validation (errors/warnings/unverified)")
    p.add_argument("project")
    p.add_argument("--dep", action="append", default=[])

    p = sub.add_parser("health", parents=[common], help="Prioritized project findings for one captured revision "
                                                        "(static; exit 1 when errors block export)")
    p.add_argument("project")
    p.add_argument("--expected-revision", help="Report whether a previously read health revision is stale")

    p = sub.add_parser("export", parents=[common], help="Export an error-free project to a new zip/folder")
    p.add_argument("project")
    p.add_argument("--dest", help="New path inside the workspace (default: <project>/exports/...)")
    p.add_argument("--format", choices=["zip", "folder"], default="zip")
    p.add_argument("--dep", action="append", default=[])

    p = sub.add_parser("demo", parents=[common], help="Build the Hebdomad demo project via the core operations")
    p.add_argument("--slug", default="hebdomad")
    p.add_argument("--export", choices=["zip", "folder"])
    p.add_argument("--export-dest")

    p = sub.add_parser("import-dm", parents=[common], help="Import an existing .dm and the assets it references "
                                                           "as a NEW project (the source is never changed)")
    p.add_argument("source", help="Path to the existing .dm; assets are read from its folder")
    p.add_argument("--slug", required=True, help="New project slug (refuses an existing one)")
    p.add_argument("--name")
    p.add_argument("--preview", action="store_true", help="Report what would be imported; write nothing")

    p = sub.add_parser("author", parents=[common], help="Show or preview/save sites, spells, weapons, armour, "
                                                        "nation heroes or playtest records")
    p.add_argument("project")
    p.add_argument("kind", help="sites | spells | weapons | armors | heroes:<nation id> | playtests | commands:<context> | dependencies | inheritance | compatibility | health | balance[:nation IDs] | map-builds | maps | maps:<id> | maps:import | reference-snapshot")
    p.add_argument("--body-file", help="JSON request (as for the web route; '-' for stdin). Omit to show state")

    p = sub.add_parser('import-map', parents=[common], help='Import a map bundle into an existing project')
    p.add_argument('project')
    p.add_argument('source', help='Main .map file; sibling planes, variants and referenced assets are copied')
    p.add_argument('--save', action='store_true', help='Import after validation; default is preview only')

    p = sub.add_parser('export-map', parents=[common], help='Export a saved map as a separate ZIP')
    p.add_argument('project')
    p.add_argument('map_id')
    p.add_argument('--expected-revision', required=True)

    p = sub.add_parser("reference", parents=[common], help="Search or show catalog spells, sites, weapons, armour")
    p.add_argument("category", choices=["spells", "sites", "weapons", "armors"])
    p.add_argument("query", nargs="?")
    p.add_argument("--id", type=int, help="Show one catalog row with labelled fields (spells: effect/summon)")
    p.add_argument("--project", help="Read this project's reference snapshot when it has one")

    sub.add_parser("mcp", parents=[common], help="Run the MCP stdio server (needs the 'mcp' extra)")

    p = sub.add_parser("serve", parents=[common], help="Run the local mod browser and authoring UI (loopback only)")
    p.add_argument("--open-browser", action="store_true", help="Open the local browser after binding successfully")
    p.add_argument("--port", type=int, default=8765, help="TCP port (default 8765; 0 picks a free port)")
    p.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost", "::1"],
                   help="Loopback address to bind (default 127.0.0.1)")
    p.add_argument("--docs", help="Optional folder of Markdown docs to show read-only (e.g. docs)")
    p = sub.add_parser("trait-icons", parents=[common], help="Extract confirmed trait icons from your local game")
    p.add_argument("--game", required=True, help="Dominions 6 installation folder (read-only source)")
    p = sub.add_parser("tools", parents=[common], help="Inspect, preview or run configured external mod tools")
    p.add_argument("action", choices=["status", "preview", "run", "history", "receipt"])
    p.add_argument("--tool", choices=["domerger", "spritegen"])
    p.add_argument("--body-file", help="JSON options file (projects for merger)")
    p.add_argument("--expected-preview-sha256")
    p.add_argument("--run-id")
    return ap


def _human(cmd: str, res: dict[str, Any]) -> str:
    r = res["result"]
    if cmd == "create":
        return f"Created project {r['project']} at {r['root']}\n.dm: {r['dm_path']}\nsha256: {r['sha256']}"
    if cmd == "inspect":
        lines = [f"{r['file']}  sha256={r['sha256']}  {r['bytes']} bytes  {r['encoding']}/{r['newlines']}",
                 f"{r['statement_count']} statements, {len(r['blocks'])} blocks, "
                 f"{len(r['unverified_commands'])} unverified commands, {len(r['syntax_issues'])} syntax issues"]
        for b in r["blocks"]:
            lines.append(f"  L{b['line']}-{b['end_line']}  {b['opener']} {b['id'] if b['id'] is not None else ''}")
        return "\n".join(lines)
    if cmd == "patch":
        return f"{r['mode']} applied to {r['file']}\nbefore {r['before_sha256']}\nafter  {r['after_sha256']}\n" \
               f"backup {r['backup']}\n{r['diff']}"
    if cmd == "lookup":
        if 'label' in r:
            return f"{r['label']} {r.get('signature', '')}\n{r['summary']}\n{r['source']['document']} {r['source']['version']}, p.{r['source'].get('page', '?')} ({r['schema_status']})"
        if "curated" in r:
            return "\n".join(f"{c['context']:8} {c['command']:20} p.{c['page']:<3} {c['summary']}" for c in r["curated"])
        out = [f"{r['command']}: {r['status']} - {r['note']}"]
        for s in r["specs"]:
            args = " ".join(f"<{a['name']}:{a['type']}{'?' if a['optional'] else ''}>" for a in s["args"])
            out.append(f"  [{s['context']}] {s['command']} {args}  -- {s['summary']} "
                       f"({s['source']['section']}, p.{s['source']['page']}, manual {s['source']['version']})")
            if s.get("notes"):
                out.append(f"      note: {s['notes']}")
        return "\n".join(out)
    if cmd == "allocate":
        return f"Reserved {r['kind']} ids {r['ids']} (range {r['range'][0]}-{r['range'][1]})\n" + \
            "\n".join(f"  caveat: {c}" for c in r["caveats"])
    if cmd == "search":
        out = [f"{r['returned']} of {r['total_matches']} matches (catalog rev {r['catalog'].get('revision')})"]
        out += [f"  {x['category']:8} {x['id']:>6}  {x['name']}" for x in r["results"]]
        return "\n".join(out)
    if cmd in ("validate", "demo"):
        v = r if cmd == "validate" else r["validation"]
        out = []
        if cmd == "demo":
            out.append(f"Demo project {r['project']} built at {r['root']}; ids {r['ids']}")
        c = v["counts"]
        out.append(f"{v['file']}: {'OK' if v['ok'] else 'ERRORS'}  errors={c['errors']} warnings={c['warnings']} "
                   f"unverified={c['unverified']}")
        for sev in ("errors", "warnings"):
            for i in v[sev]:
                out.append(f"  {sev[:-1]:7} L{i.get('line') or '-'}: [{i['code']}] {i['message']}")
        if c["unverified"]:
            out.append(f"  ({c['unverified']} unverified items; use --json to list)")
        if cmd == "demo" and r.get("export"):
            e = r["export"]
            out.append(f"Export: {e.get('destination') or e}")
        return "\n".join(out)
    if cmd == "health":
        c = r["counts"]
        out = [f"{r['project']}: {r['status'].upper()}  errors={c['error']} warnings={c['warning']} "
               f"unverified={c['unverified']} info={c['info']}",
               f"revision {r['revision']}" + ("  (STALE: differs from --expected-revision)" if r["stale"] else ""),
               f"catalog: {r['catalog']['state']}"]
        for f in r["findings"]:
            if f["severity"] == "info":
                continue
            loc = f["location"]
            where = loc["asset"] or (loc["object"] or {}).get("key") or ""
            out.append(f"  {f['severity']:10} L{loc['line'] or '-'}: [{f['code']}] {f['message']}"
                       + (f" ({f['count']}x)" if f["count"] > 1 else "") + (f"  {where}" if where else ""))
            out.append(f"             next: {f['next_action']}")
        if c["info"]:
            out.append(f"  ({c['info']} info items; use --json to list)")
        out.append("Not checked: " + ", ".join(x["check"] for x in r["scope"]["not_checked"]))
        return "\n".join(out)
    if cmd == "export":
        files = "\n".join(f"  {f['sha256']}  {f['path']}" for f in r["manifest"]["files"])
        return f"Exported to {r['destination']}\nmanifest {r['manifest_path']}\n{files}"
    return json.dumps(r, indent=2)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    if args.cmd == "mcp":
        from .mcp_server import serve
        return serve(args.workspace, args.catalog, args.target_version)
    if args.cmd == "serve":
        from .webserver import serve as serve_web
        return serve_web(args.workspace, args.catalog, args.docs, args.host, args.port, args.open_browser)
    k = Kosmokrator(args.workspace, args.catalog, args.target_version)
    c = args.cmd
    try:
        if c == "trait-icons":
            from .trait_icons import install_native_icons
            res = envelope(install_native_icons, args.workspace, args.game)
        elif c == "create":
            res = envelope(k.create_project, args.slug, args.name, args.description)
        elif c == "inspect":
            res = envelope(k.inspect_mod, args.project, args.file)
        elif c == "patch":
            res = envelope(k.apply_mod_patch, args.project, args.expected_sha256,
                           old=_read_arg_file(args.old_file), new=_read_arg_file(args.new_file),
                           insert_line=args.insert_line, text=_read_arg_file(args.text_file), file=args.file)
        elif c == "lookup":
            res = envelope(k.lookup_command, args.command, args.context)
        elif c == "allocate":
            res = envelope(k.allocate_ids, args.project, args.kind, args.count, args.label, args.dep)
        elif c == "search":
            res = envelope(k.search_game_data, args.query, args.category, args.limit, args.project)
        elif c == "validate":
            res = envelope(k.validate_mod, args.project, args.dep)
        elif c == "health":
            res = envelope(k.project_health, args.project, args.expected_revision)
        elif c == "export":
            res = envelope(k.export_mod, args.project, args.dest, args.format, args.dep)
        elif c == "import-dm":
            res = envelope(k.import_dm, args.source, args.slug, args.name, args.preview)
        elif c == 'import-map':
            res = envelope(k.import_map, args.project, args.source, not args.save)
        elif c == 'export-map':
            res = envelope(k.export_map, args.project, args.map_id, args.expected_revision)
        elif c == "author":
            if args.body_file:
                try:
                    body = json.loads(_read_arg_file(args.body_file) or "")
                except ValueError as exc:
                    raise OSError(f"--body-file is not valid JSON: {exc}") from exc
                res = envelope(k.author_save, args.project, args.kind, body)
            else:
                res = envelope(k.author_state, args.project, args.kind)
        elif c == 'view':
            res = envelope(k.project_view, args.project)
        elif c == "reference":
            res = envelope(k.reference, args.category, args.query, args.id, args.project)
        elif c == "tools":
            if args.action == "status":
                res = envelope(k.external_tools)
            elif args.action in ("history", "receipt"):
                if args.action == "receipt" and not args.run_id:
                    raise ValueError("receipt requires --run-id")
                res = envelope(k.external_tool_runs, args.run_id)
            else:
                if not args.tool:
                    raise ValueError("preview/run requires --tool")
                body = json.loads(_read_arg_file(args.body_file) or "{}")
                if args.action == "preview":
                    res = envelope(k.preview_external_tool, args.tool, body)
                else:
                    if not args.expected_preview_sha256:
                        raise ValueError("run requires --expected-preview-sha256")
                    res = envelope(k.run_external_tool, args.tool, body, args.expected_preview_sha256)
        else:
            res = envelope(k.build_demo, args.slug, args.export, args.export_dest)
    except (OSError, UnicodeDecodeError, ValueError) as exc:  # e.g. unreadable input or invalid request JSON
        res = {"ok": False, "error": {"code": "input_error", "message": str(exc)}}
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif res["ok"]:
        print(_human(c, res))
    else:
        e = res["error"]
        print(f"error [{e['code']}]: {e['message']}", file=sys.stderr)
        for key, val in (e.get("details") or {}).items():
            if key == "errors":
                for i in val:
                    print(f"  L{i.get('line') or '-'}: [{i['code']}] {i['message']}", file=sys.stderr)
            else:
                print(f"  {key}: {val}", file=sys.stderr)
    if not res["ok"]:
        return 2
    if c in ("validate", "health") and not res["result"]["ok"]:
        return 1
    if c == "demo" and not res["result"]["validation"]["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
