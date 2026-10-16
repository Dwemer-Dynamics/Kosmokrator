"""Local web browser and bounded editor: a stdlib HTTP server bound to loopback only.

Serves the bundled static UI from kosmokrator/web/ and JSON views built by browse.py. Every path is checked
with the same containment helpers as the CLI (no '..', no links, exact case inside the mod folder). GET and
HEAD are read-only. There are three bounded edit/export writes: POST /api/projects/<slug>/monsters/<id>/edit, which
changes curated commands inside one project monster block through edit.py (project lock, expected SHA-256, backup),
POST /api/projects/<slug>/nations/<id>/edit, which does the same for one #selectnation block through nation_edit.py,
and
POST /api/projects/<slug>/export, which packages exactly the saved revision the page shows into a new, uniquely
named file under <project>/exports through export.py (project lock, expected SHA-256, no overwrite). All need
an exact same-origin request, application/json, a small body and the per-server CSRF token that is embedded in
the served index.html. Exports are read back only by fixed export id. The catalog and the docs folder are
never written, and nothing is installed into the game.

Authoring routes (author.py) use the same request checks: POST .../create/monster, .../create/nation and
.../monsters/<id>/art (the only route allowing a larger body, for two PNG frames). They write under the project
lock against the expected SHA-256, with id reservation and a backup.

Bounded content authoring (content.py, playtest.py, importdm.py) uses the same checks: POST .../content/<kind>
(sites, spells, weapons, armors), .../nations/<id>/heroes, .../playtests, and POST /api/import, which creates a NEW
project from an uploaded .dm and assets (never overwrites). GET /api/tools only reports administrator-configured
external tool status; nothing is executed from the browser.

Project reference snapshots (reference.py): POST .../reference-snapshot previews or writes a self-contained copy of
the catalog tables and local reference art one project needs under <project>/.kosmokrator/reference (project lock,
expected SHA-256 and expected snapshot id). A project with a snapshot reads only that snapshot in every project route,
including the project-scoped icon routes .../gem-icons, path-icons, ability-icons, item-icons and trait-icons.
Exports and Workshop folders never include it.

Vanilla inspector (inspector.py): GET .../inspector, .../inspector/<category> (q, repeatable c=field:op[:value],
sort, order, page, per_page, age, nation, role; the original field/op/value filter still works), .../inspector/<category>/filters and
.../inspector/<category>/<id> browse the catalog that project reads, read-only; images use the existing id-based sprite
and icon routes. Mercenary
companies (mercs.py): GET .../mercs lists the project's #newmerc blocks and POST .../mercs previews or appends one
structured company through the guarded advanced-editor writer.

Workshop preparation (workshop.py): POST .../workshop/prepare turns one existing export of the shown revision into
<project>/exports/workshop/<id>/<slug>/ (exported files plus dom6ws.txt and banner.png) with a ZIP and a manifest
beside it, and POST .../workshop/<id>/install copies that folder into the Dominions 6 mods folder fixed by the server
(KOSMOKRATOR_DOMINIONS_MODS or %APPDATA%/Dominions6/mods), refusing any existing folder it did not install. Nothing
is uploaded or published; the game's own Mods menu uploads to Steam. GET .../preflight?target=<export or Workshop id>
(preflight.py) compares that verified bundle with the installed mods, read-only and only when asked; install requires
its current fingerprint (and an acknowledgement when it has review warnings).

Reviewed ID remapping (remap.py): GET .../remap lists project-owned numbered definitions, who else uses each ID and
suggested free IDs; POST .../remap previews a mapping (writes nothing) or, with preview false, applies exactly the
previewed plan (expected revision, occupancy fingerprint, plan hash, confirm) after a pre-remap checkpoint.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from .browse import SCHEMA, ModelCache, asset_path, catalog_unit_view, list_projects, project_doc_path
from .catalog import load_catalog
from .author import create_monster, create_nation, donor_search, upload_art
from .content import (KINDS as CONTENT_KINDS, REF_CATS, content_state, heroes_state, reference_detail,
                      reference_search, save_content, save_heroes)
from .command_edit import command_state, save_commands
from .inspector import CATS as INSPECTOR_CATS, MAX_CONDITIONS as INSPECTOR_MAX_CONDITIONS, detail as inspector_detail, \
    filter_meta as inspector_filters, list_rows as inspector_list, summary as inspector_summary
from .mercs import merc_state, save_merc
from .dependencies import dependency_state, save_dependencies
from .maps import (list_maps, map_state, import_map, save_map, map_variant_image, map_source,
                   export_map, map_export_path)
from .importdm import import_from_body
from .playtest import add_playtest, list_playtests
from .edit import apply_edit, editor_state
from .nation_edit import apply_nation_edit, editor_state as nation_editor_state
from .export import export_revision, find_export, list_exports, read_export_manifest
from .workshop import (MODS_ENV, install_workshop, mods_dir_config, prepare_workshop, workshop_archive,
                       workshop_banner, workshop_manifest, workshop_state)
from .pretenders import SPRITE_FRAMES, catalog_sprite_path
from .errors import KosmoError
from .paths import SLUG_RE, contained, is_link, resolve_workspace
from .project import open_project, read_dm, resolve_dm_target
from .tga import decode_tga, encode_png
from .integrations import tool_status, preview_tool, run_tool, list_tool_runs, tool_receipt, tool_archive
from .loadout import equipment_state, save_equipment
from .trait_icons import load_icon_cache
from .reference import (create_snapshot, read_verified, reference_status, resolve_catalog, snapshot_trait_icon_dir,
                        workspace_reference_summary)

WEB_DIR = Path(__file__).resolve().parent / "web"
# Fixed allow-list: the static route never maps request text onto the filesystem.
STATIC = {"index.html": "text/html; charset=utf-8", "app.css": "text/css; charset=utf-8",
          "app.js": "text/javascript; charset=utf-8", "favicon.svg": "image/svg+xml"}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
DOC_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*\.md$")
MAX_DOC_BYTES = 2 * 1024 * 1024
SECTIONS = ("nations", "monsters", "sites", "other_definitions", "assets", "validation", "pretenders", "readiness", "inheritance", "compatibility")
# /pretenders/<god>: "project-5011", "catalog-3416" or the full uid "god:catalog:3416".
GOD_REF_RE = re.compile(r"^(?:god:)?(project|catalog)[-:](\d{1,6})$")
MONSTER_ID_RE = re.compile(r"^\d{1,6}$")
# Native magic-path gem icons from the configured catalog: the file name is rebuilt from this fixed set only.
GEM_ICON_PATHS = frozenset("FAWESDNGBH")
# Catalog magic-path skill icons (images/magicicons/Path_<P>.png). The catalog's own formatter uses them for unit
# paths and requirements, and Path_U for random paths; Path_R (its research total) is not served.
PATH_ICON_PATHS = frozenset("FAWESDNGBHU")
# Catalog ability icons used by its formatter; only the sacred badge exists there.
ABILITY_ICON_NAMES = frozenset({"holy"})
# Catalog item icons are images/items/item<id>.png for a vanilla item id (or its #copyspr id).
ITEM_ICON_RE = re.compile(r"^([1-9]\d{0,3})\.png$")
MAX_CATALOG_ICON_BYTES = 64 * 1024
EDIT_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/monsters/(\d{1,6})/edit")
NATION_EDIT_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/nations/(\d{1,3})/edit")
EXPORT_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/export")
WORKSHOP_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/workshop/(?:(prepare)|"
                               r"([a-z][a-z0-9_]{1,47}-ws-\d{8}T\d{6}Z-[0-9a-f]{8})/(install))")
CREATE_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/create/(monster|nation)")
ART_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/monsters/(\d{1,6})/art")
CONTENT_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/content/(sites|spells|weapons|armors)")
HEROES_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/nations/(\d{1,3})/heroes")
PLAYTEST_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/playtests")
IMPORT_ROUTE = "/api/import"
MAX_EDIT_BYTES = 64 * 1024
TOOLS_ROUTE_RE = re.compile(r"/api/tools/(domerger|nationgen|spritegen|mapnuke)/(preview|run)")
REFERENCE_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/reference-snapshot")
MERC_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/mercs")
REVISIONS_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/revisions")
REMAP_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/remap")
EQUIPMENT_ROUTE_RE = re.compile(r"/api/projects/([a-z][a-z0-9_]{1,47})/monsters/(\d{1,6})/equipment")
# Import uploads one .dm plus its assets as base64; bounded like the art route.
MAX_IMPORT_BODY_BYTES = 6 * 1024 * 1024
# Only the purpose-built art route accepts a larger body: two base64 PNG frames of at most 2 MB each.
MAX_ART_BODY_BYTES = 6 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
CSRF_META = '<meta name="kosmo-csrf" content="">'
# Error codes from the editor and the core patcher, mapped to HTTP statuses.
EDIT_STATUS = {"sha_mismatch": HTTPStatus.CONFLICT, "project_locked": HTTPStatus.CONFLICT,
               "write_failed": HTTPStatus.INTERNAL_SERVER_ERROR,
               "write_failed_reservation_kept": HTTPStatus.INTERNAL_SERVER_ERROR,
               "changed_during_export": HTTPStatus.CONFLICT, "dest_exists": HTTPStatus.CONFLICT,
               "stale_export": HTTPStatus.CONFLICT, "install_conflict": HTTPStatus.CONFLICT,
               "export_changed": HTTPStatus.CONFLICT, "workshop_changed": HTTPStatus.CONFLICT,
               "export_missing": HTTPStatus.NOT_FOUND, "workshop_missing": HTTPStatus.NOT_FOUND,
               "install_unavailable": HTTPStatus.CONFLICT,
               "project_exists": HTTPStatus.CONFLICT,
               "validation_failed": HTTPStatus.UNPROCESSABLE_ENTITY,
               "object_missing": HTTPStatus.NOT_FOUND, "project_missing": HTTPStatus.NOT_FOUND,
               "reference_changed": HTTPStatus.CONFLICT, "reference_too_large": HTTPStatus.REQUEST_ENTITY_TOO_LARGE}
EDIT_STATUS.update(object_in_use=HTTPStatus.CONFLICT, id_conflict=HTTPStatus.CONFLICT)
EDIT_STATUS.update(preflight_required=HTTPStatus.BAD_REQUEST, preflight_stale=HTTPStatus.CONFLICT,
                   preflight_blocked=HTTPStatus.CONFLICT, preflight_review=HTTPStatus.CONFLICT)
# Local checkpoints and restore (revisions.py).
EDIT_STATUS.update(stale_revision=HTTPStatus.CONFLICT, plan_changed=HTTPStatus.CONFLICT,
                   restore_interrupted=HTTPStatus.CONFLICT, changed_during_capture=HTTPStatus.CONFLICT,
                   changed_during_restore=HTTPStatus.CONFLICT, checkpoint_missing=HTTPStatus.NOT_FOUND,
                   baseline_missing=HTTPStatus.NOT_FOUND, journal_missing=HTTPStatus.NOT_FOUND,
                   blob_missing=HTTPStatus.UNPROCESSABLE_ENTITY, blob_corrupt=HTTPStatus.UNPROCESSABLE_ENTITY,
                   manifest_corrupt=HTTPStatus.UNPROCESSABLE_ENTITY,
                   restore_failed=HTTPStatus.INTERNAL_SERVER_ERROR,
                   restore_rollback_failed=HTTPStatus.INTERNAL_SERVER_ERROR)
# Reviewed ID remapping (remap.py).
EDIT_STATUS.update(occupancy_changed=HTTPStatus.CONFLICT, remap_blocked=HTTPStatus.CONFLICT,
                   changed_during_remap=HTTPStatus.CONFLICT, remap_failed=HTTPStatus.INTERNAL_SERVER_ERROR,
                   remap_rollback_failed=HTTPStatus.INTERNAL_SERVER_ERROR)
# Only these error details are echoed to the browser (no absolute, lock or temp paths).
SAFE_DETAILS = {"lines", "field", "blocked", "problems", "expected", "actual", "counts", "errors", "validation",
                "missing", "paths", "path", "journal", "pre_restore", "pre_remap", "findings"}
MAX_DONOR_QUERY = 60


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class BrowserState:
    """Server-wide configuration plus the bounded model cache."""

    def __init__(self, workspace: str, catalog: str | None, docs: str | None) -> None:
        self.workspace = resolve_workspace(workspace)
        self.catalog_arg = catalog
        self.docs = None
        if docs:
            d = Path(docs).expanduser()
            d = (d if d.is_absolute() else Path.cwd() / d)
            if not d.is_dir() or is_link(d):
                raise KosmoError("docs_missing", f"--docs must be an existing directory (not a link): {d}")
            self.docs = d.resolve()
        self.cache = ModelCache()
        self.trait_icons, self.trait_icon_images = load_icon_cache(self.workspace)
        self._snapshot_icons: dict[tuple[str, str], tuple[dict[str, Any], dict[str, bytes]]] = {}
        self.csrf = secrets.token_urlsafe(32)  # per server process; only ever sent inside index.html
        # The Workshop install destination is fixed when the server starts; requests can never name a path.
        self.mods_env = {k: v for k, v in os.environ.items() if k in (MODS_ENV, "APPDATA")}

    def mods_config(self) -> dict[str, Any]:
        return mods_dir_config(self.mods_env)

    def catalog(self) -> tuple[Any, dict[str, Any] | None]:
        """(catalog or None, status) - a missing or broken catalog is reported, never fatal."""
        try:
            return load_catalog(self.catalog_arg, required=True), None
        except KosmoError as exc:
            return None, exc.to_dict()

    def catalog_for(self, slug: str) -> tuple[Any, dict[str, Any] | None]:
        """The catalog one project reads: its verified reference snapshot if it has one, else the live catalog."""
        live, err = self.catalog()
        return resolve_catalog(self.workspace, slug, live, err)

    def trait_icons_for(self, slug: str) -> tuple[dict[str, Any], dict[str, bytes]]:
        """Native UI icons for one project: its snapshot copy when present, else the verified workspace cache."""
        found = snapshot_trait_icon_dir(self.workspace, slug)
        if found is None:
            icons = {k: {**v, "url": f"/api/projects/{slug}/trait-icons/{k}.png"} for k, v in self.trait_icons.items()}
            return icons, self.trait_icon_images
        sid, path = found
        key = (slug, sid)  # a copied project folder keeps its snapshot id
        if key not in self._snapshot_icons:
            if len(self._snapshot_icons) > 16:
                self._snapshot_icons.clear()
            self._snapshot_icons[key] = load_icon_cache(self.workspace, path, f"/api/projects/{slug}/trait-icons")
        return self._snapshot_icons[key]

    def global_docs(self) -> list[dict[str, Any]]:
        if not self.docs:
            return []
        return [{"name": p.name, "bytes": p.stat().st_size} for p in sorted(self.docs.iterdir())
                if p.suffix.lower() == ".md" and p.is_file() and not is_link(p) and DOC_NAME_RE.match(p.name)]


class Handler(BaseHTTPRequestHandler):
    server_version = f"Kosmokrator/{__version__}"
    state: BrowserState  # set on the subclass by make_server

    # ----- plumbing -----
    def log_message(self, fmt: str, *args: Any) -> None:  # quieter, to stderr
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _headers(self, status: int, ctype: str, length: int, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _send(self, status: int, body: bytes, ctype: str, extra: dict[str, str] | None = None) -> None:
        self._headers(status, ctype, len(body), extra)
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj: Any, status: int = 200, download: str | None = None) -> None:
        body = json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8")
        extra = {"Content-Disposition": f'attachment; filename="{download}"'} if download else None
        self._send(status, body, "application/json; charset=utf-8", extra)

    def _error(self, status: int, code: str, message: str, **details: Any) -> None:
        err: dict[str, Any] = {"code": code, "message": message}
        if details:
            err["details"] = details
        self._json({"ok": False, "error": err}, status)

    def _reject_write(self) -> None:
        # Any body is ignored and never read into the workspace.
        self.close_connection = True
        body = json.dumps({"ok": False, "error": {"code": "read_only", "message": "Only GET and HEAD are "
                                                  "accepted here. Use the documented editor, creation, artwork "
                                                  "or export POST routes for writes."}}).encode("utf-8")
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, body, "application/json; charset=utf-8", {"Allow": "GET, HEAD"})

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_TRACE = do_CONNECT = _reject_write

    def do_POST(self) -> None:
        """Bounded authoring and export writes; request checks run before the body is read."""
        self.close_connection = True
        try:
            if not self._host_ok():
                return self._error(HTTPStatus.FORBIDDEN, "bad_host", "Only loopback Host headers are accepted.")
            m = EDIT_ROUTE_RE.fullmatch(self.path)
            mx = EXPORT_ROUTE_RE.fullmatch(self.path)
            mc = CREATE_ROUTE_RE.fullmatch(self.path)
            ma = ART_ROUTE_RE.fullmatch(self.path)
            mn = NATION_EDIT_ROUTE_RE.fullmatch(self.path)
            mco = CONTENT_ROUTE_RE.fullmatch(self.path)
            mh = HEROES_ROUTE_RE.fullmatch(self.path)
            mp = PLAYTEST_ROUTE_RE.fullmatch(self.path)
            mi = self.path == IMPORT_ROUTE
            mt = TOOLS_ROUTE_RE.fullmatch(self.path)
            me = EQUIPMENT_ROUTE_RE.fullmatch(self.path)
            mw = WORKSHOP_ROUTE_RE.fullmatch(self.path)
            mg = re.fullmatch(r'/api/projects/([a-z][a-z0-9_]{1,47})/commands', self.path)
            md = re.fullmatch(r'/api/projects/([a-z][a-z0-9_]{1,47})/dependencies', self.path)
            mb = re.fullmatch(r'/api/projects/([a-z][a-z0-9_]{1,47})/map-builds', self.path)
            mm = re.fullmatch(r'/api/projects/([a-z][a-z0-9_]{1,47})/maps/(import|[A-Za-z][A-Za-z0-9_]{0,47}/(?:edit|export))', self.path)
            mr = REFERENCE_ROUTE_RE.fullmatch(self.path)
            mmerc = MERC_ROUTE_RE.fullmatch(self.path)
            mrev = REVISIONS_ROUTE_RE.fullmatch(self.path)
            mremap = REMAP_ROUTE_RE.fullmatch(self.path)
            if not (m or mx or mc or ma or mn or mco or mh or mp or mi or mt or me or mg or md or mm or mb or mw or mr or mmerc
                    or mrev or mremap):
                return self._reject_write()
            limit = 180 * 1024 * 1024 if mm and mm.group(2) == 'import' else MAX_ART_BODY_BYTES if ma else MAX_IMPORT_BODY_BYTES if mi else MAX_EDIT_BYTES
            host = (self.headers.get("Host") or "").strip()
            if self.headers.get("Origin") != f"http://{host}" or \
                    self.headers.get("Sec-Fetch-Site", "same-origin") != "same-origin":
                return self._error(HTTPStatus.FORBIDDEN, "bad_origin", "Edits are accepted only from this page "
                                                                       "(exact same origin).")
            token = self.headers.get("X-Kosmo-CSRF") or ""
            if not hmac.compare_digest(token.encode(), self.state.csrf.encode()):
                return self._error(HTTPStatus.FORBIDDEN, "bad_csrf", "Missing or wrong editor token. Reload the "
                                                                     "page (the token changes when the server "
                                                                     "restarts).")
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "bad_content_type",
                                   "Content-Type must be application/json.")
            length = self.headers.get("Content-Length") or ""
            if not length.isdigit() or not 0 < int(length) <= limit:
                return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE if length.isdigit() and int(length) else
                                   HTTPStatus.LENGTH_REQUIRED, "bad_length",
                                   f"Body must be 1-{limit} bytes with a Content-Length.")
            try:
                body = json.loads(self.rfile.read(int(length)).decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                return self._error(HTTPStatus.BAD_REQUEST, "bad_json", "Body is not valid UTF-8 JSON.")
            if mw:
                slug = mw.group(1)
                if mw.group(2):
                    res = prepare_workshop(self.state.workspace, slug, body)
                else:
                    res = install_workshop(self.state.workspace, slug, mw.group(3), body, self.state.mods_config())
                return self._json({"ok": True, "result": res})
            if mr:
                live, _err = self.state.catalog()
                return self._json({"ok": True, "result": create_snapshot(self.state.workspace, mr.group(1), live, body)})
            # Project routes read the project's own reference snapshot when it has one.
            scoped = next((x for x in (m, mx, mc, ma, mn, mco, mh, mp, me, mg, md, mm, mb, mmerc, mrev, mremap) if x), None)
            cat, _err = self.state.catalog_for(scoped.group(1)) if scoped else self.state.catalog()
            if mb:
                from .map_builds import save_map_build
                return self._json({'ok':True,'result':save_map_build(self.state.workspace,mb.group(1),body,cat)})
            if mm:
                slug, action = mm.groups()
                if action == 'import':
                    result = import_map(self.state.workspace, slug, body, cat)
                else:
                    ident, operation = action.split('/')
                    result = (save_map if operation == 'edit' else export_map)(self.state.workspace, slug, ident, body, cat)
                return self._json({'ok': True, 'result': result})
            if mmerc:
                return self._json({"ok": True, "result": save_merc(self.state.workspace, mmerc.group(1), cat, body)})
            if mrev:
                from .revisions import save_revisions
                return self._json({"ok": True, "result": save_revisions(self.state.workspace, mrev.group(1), body,
                                                                        cat, via="browser")})
            if mremap:
                from .remap import save_remap
                return self._json({"ok": True, "result": save_remap(self.state.workspace, mremap.group(1), body, cat,
                                                                    self.state.mods_config(), via="browser")})
            if mg:
                return self._json({'ok': True, 'result': save_commands(self.state.workspace, mg.group(1), cat, body)})
            if md:
                return self._json({'ok': True, 'result': save_dependencies(self.state.workspace, md.group(1), body)})
            if me:
                return self._json({"ok": True, "result": save_equipment(self.state.workspace, me.group(1), int(me.group(2)), cat, body)})
            if mt:
                if not isinstance(body, dict) or set(body) - {"request", "expected_preview_sha256"}:
                    return self._error(HTTPStatus.BAD_REQUEST, "bad_request", "Body needs request and optional expected_preview_sha256.")
                if mt.group(2) == "preview":
                    result = preview_tool(self.state.workspace, mt.group(1), body.get("request", {}))
                else:
                    result = run_tool(self.state.workspace, mt.group(1), body.get("request", {}),
                                      body.get("expected_preview_sha256"))
                return self._json({"ok": True, "result": result})
            if mco:
                return self._json({"ok": True, "result": save_content(self.state.workspace, mco.group(1),
                                                                      mco.group(2), cat, body)})
            if mh:
                return self._json({"ok": True, "result": save_heroes(self.state.workspace, mh.group(1),
                                                                     int(mh.group(2)), cat, body)})
            if mp:
                return self._json({"ok": True, "result": add_playtest(self.state.workspace, mp.group(1), body)})
            if mi:
                return self._json({"ok": True, "result": import_from_body(self.state.workspace, body)})
            if mc or ma:
                slug = (mc or ma).group(1)
                if mc and mc.group(2) == "monster":
                    res = create_monster(self.state.workspace, slug, cat, body)
                elif mc:
                    res = create_nation(self.state.workspace, slug, cat, body)
                else:
                    res = upload_art(self.state.workspace, slug, int(ma.group(2)), cat, body)
                return self._json({"ok": True, "result": res})
            if mn:
                res = apply_nation_edit(self.state.workspace, mn.group(1), int(mn.group(2)), cat, body)
                return self._json({"ok": True, "result": res})
            if mx:
                if not isinstance(body, dict):
                    return self._error(HTTPStatus.BAD_REQUEST, "bad_request", "Body must be a JSON object.")
                res = export_revision(self.state.workspace, mx.group(1), body.get("expected_sha256"),
                                      body.get("format", "zip"), cat)
                return self._json({"ok": True, "result": res})
            res = apply_edit(self.state.workspace, m.group(1), int(m.group(2)), cat, body)
            return self._json({"ok": True, "result": res})
        except KosmoError as exc:
            status = EDIT_STATUS.get(exc.code, HTTPStatus.FORBIDDEN if exc.code in (
                "path_escape", "symlink_rejected") else HTTPStatus.BAD_REQUEST)
            self._error(status, exc.code, exc.message, **{k: v for k, v in exc.details.items() if k in SAFE_DETAILS})
        except OSError:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "write_error", "The file could not be read or written; "
                                                                         "nothing was changed by this request.")

    def do_HEAD(self) -> None:
        self.do_GET()

    def _host_ok(self) -> bool:
        # DNS-rebinding guard: only loopback names are accepted in the Host header.
        host = (self.headers.get("Host") or "").strip()
        m = re.fullmatch(r"\[([0-9a-fA-F:]+)\](?::\d+)?|([^:]+)(?::\d+)?", host)
        if not m:
            return False
        return _is_loopback(m.group(1) or m.group(2))

    # ----- routing -----
    def do_GET(self) -> None:
        try:
            if not self._host_ok():
                return self._error(HTTPStatus.FORBIDDEN, "bad_host", "Only loopback Host headers are accepted.")
            parts = urlsplit(self.path)
            raw_path = parts.path
            if "\\" in raw_path or "%00" in raw_path.lower() or "%5c" in raw_path.lower() or "%2f" in raw_path.lower():
                return self._error(HTTPStatus.BAD_REQUEST, "bad_path", "Encoded separators, backslashes and NUL "
                                                                       "are not accepted.")
            segs = [unquote(s) for s in raw_path.split("/")[1:]]
            if any(s in (".", "..") or "\x00" in s for s in segs):
                return self._error(HTTPStatus.BAD_REQUEST, "path_escape", "Path traversal is not allowed.")
            multi = parse_qs(parts.query)
            self._query_lists = multi  # repeatable parameters (the inspector's c=) read the full list
            query = {k: v[-1] for k, v in multi.items()}
            self._route(segs, query)
        except KosmoError as exc:
            status = HTTPStatus.NOT_FOUND if exc.code.endswith(("missing", "not_a_file")) else HTTPStatus.BAD_REQUEST
            if exc.code in ("stale_preview", "changed_during_capture"):
                status = HTTPStatus.CONFLICT
            if exc.code in ("path_escape", "symlink_rejected", "asset_symlink"):
                status = HTTPStatus.FORBIDDEN
            self._error(status, exc.code, exc.message, **exc.details)
        except (OSError, ValueError, UnicodeError) as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "read_error", str(exc))

    def _route(self, segs: list[str], q: dict[str, str]) -> None:
        st = self.state
        if segs in ([""], []) or segs == ["index.html"]:
            return self._static("index.html")
        if len(segs) == 2 and segs[0] == "static":
            return self._static(segs[1])
        if segs and segs[-1] == "":
            segs = segs[:-1]
        if not segs or segs[0] != "api":
            return self._error(HTTPStatus.NOT_FOUND, "not_found", "Unknown route.")
        api = segs[1:]
        dl = q.get("download") in ("1", "true")
        if api == ["meta"]:
            cat, cat_err = st.catalog()
            return self._json({"ok": True, "schema": SCHEMA, "tool_version": __version__, "read_only": False,
                               "editing": "project monster blocks only (POST /api/projects/<slug>/monsters/<id>/edit)",
                               "exporting": "saved revision into <project>/exports (POST /api/projects/<slug>/export)",
                                 "workspace": str(st.workspace),
                                 "runtime": {"python_executable": sys.executable, "platform": sys.platform},
                                 "catalog": cat.meta if cat else None,
                               "catalog_error": cat_err, "docs": st.global_docs(),
                               "project_references": workspace_reference_summary(st.workspace, cat)})
        if api == ["projects"]:
            cat, cat_err = st.catalog()
            res = list_projects(st.workspace, st.cache, cat, catalog_for=lambda s: st.catalog_for(s)[0])
            return self._json({"ok": True, **res, "catalog_error": cat_err},
                              download="projects.json" if dl else None)
        if api == ["tools"]:
            return self._json({"ok": True, "result": tool_status(st.workspace)})
        if api == ["trait-icons"]:
            return self._json({"ok": True, "icons": st.trait_icons})
        if len(api) == 2 and api[0] in ("trait-icons", "gem-icons", "path-icons", "ability-icons", "item-icons"):
            return self._icon(api[0], api[1], None)
        if api == ["tools", "runs"]:
            return self._json({"ok": True, "result": list_tool_runs(st.workspace)})
        if len(api) in (3, 4) and api[:2] == ["tools", "runs"]:
            if len(api) == 4 and api[3] == "archive.zip":
                raw = tool_archive(st.workspace, api[2])
                return self._send(200, raw, "application/zip", {
                    "Content-Disposition": f'attachment; filename="{api[2]}.zip"'})
            if len(api) == 3:
                return self._json({"ok": True, "result": tool_receipt(st.workspace, api[2])})
        if len(api) == 2 and api[0] == "docs":
            return self._global_doc(api[1], dl)
        if len(api) >= 2 and api[0] == "projects":
            slug = api[1]
            if not SLUG_RE.match(slug):
                return self._error(HTTPStatus.BAD_REQUEST, "bad_slug", "Invalid project slug.")
            return self._project(slug, api[2:], q, dl)
        return self._error(HTTPStatus.NOT_FOUND, "not_found", "Unknown API route.")

    def _static(self, name: str) -> None:
        if name not in STATIC:
            return self._error(HTTPStatus.NOT_FOUND, "not_found", "Unknown static file.")
        path = contained(WEB_DIR, name, what="static file")
        if is_link(path) or not path.is_file():
            return self._error(HTTPStatus.NOT_FOUND, "not_found", "Static file missing from the package.")
        data = path.read_bytes()
        if name == "index.html":
            data = data.replace(CSRF_META.encode(), f'<meta name="kosmo-csrf" content="{self.state.csrf}">'.encode())
        self._send(200, data, STATIC[name])

    def _model(self, slug: str) -> dict[str, Any]:
        cat, cat_err = self.state.catalog_for(slug)
        model = self.state.cache.get(self.state.workspace, slug, cat)
        live, _live_err = self.state.catalog()
        return {**model, "catalog_error": cat_err,
                "reference": reference_status(self.state.workspace, slug, live, model)}

    def _latest_export(self, slug: str) -> dict[str, Any]:
        """The newest export, read fresh on every request (exports are outside the model cache's fingerprint)."""
        try:
            items = list_exports(self.state.workspace, slug)
        except KosmoError as exc:
            return {"available": False, "error": exc.code}
        return {"available": True, "export": items[0] if items else None}

    def _project(self, slug: str, rest: list[str], q: dict[str, str], dl: bool) -> None:
        if len(rest) == 3 and rest[0] == "monsters" and rest[1].isdigit() and rest[2] == "equipment":
            cat, _ = self.state.catalog_for(slug)
            return self._json({"ok": True, "result": equipment_state(self.state.workspace, slug, int(rest[1]), cat)})
        ws = self.state.workspace
        if not rest:
            return self._json({"ok": True, **self._model(slug), "latest_export": self._latest_export(slug)},
                              download=f"{slug}.json" if dl else None)
        head = rest[0]
        if head == 'health' and len(rest) == 1:
            from .health import build_health
            live, live_err = self.state.catalog()
            expected = q.get('expected_revision') or None
            # Rebuilt for every report: the browser cache is keyed by stat fingerprints, not the captured identity.
            return self._json({'ok': True, 'result': build_health(ws, slug, live, live_err, expected)},
                              download=f"{slug}-health.json" if dl else None)
        if head == 'preflight' and len(rest) == 1:
            from .preflight import preflight
            return self._json({'ok': True, 'result': preflight(ws, slug, q.get('target'), self.state.mods_config())},
                              download=f"{slug}-preflight.json" if dl else None)
        if head == 'revisions':
            from .revisions import compare, preview_image, revision_state
            if len(rest) == 1:
                return self._json({'ok': True, 'result': revision_state(ws, slug)})
            if len(rest) == 2 and rest[1] == 'compare':
                return self._json({'ok': True, 'result': compare(ws, slug, q.get('target') or 'baseline')},
                                  download=f"{slug}-changes.json" if dl else None)
            if len(rest) == 2 and rest[1] == 'preview':
                png = preview_image(ws, slug, q.get('side', ''), q.get('path', ''), q.get('sha', ''))
                return self._send(200, png, 'image/png')
        if head == 'remap' and len(rest) == 1:
            from .remap import remap_state
            cat, _err = self.state.catalog_for(slug)
            return self._json({'ok': True, 'result': remap_state(ws, slug, cat, self.state.mods_config())},
                              download=f"{slug}-remap.json" if dl else None)
        if head == 'map-builds' and len(rest) == 1:
            from .map_builds import map_build_state
            return self._json({'ok':True,'result':map_build_state(ws,slug)})
        if head == 'balance' and len(rest) == 1:
            from .balance import balance_report
            refs = q.get('references')
            if refs is not None and (not re.fullmatch(r'\d+(?:,\d+){0,11}',refs)):
                raise KosmoError('bad_request','references must contain up to 12 comma-separated nation IDs.')
            cat, _err = self.state.catalog_for(slug)
            return self._json({'ok':True,'result':balance_report(self._model(slug),cat,[int(x) for x in refs.split(',')] if refs else None)})
        if head == 'maps':
            cat, _err = self.state.catalog_for(slug)
            if len(rest) == 1:
                return self._json({'ok': True, 'result': list_maps(ws, slug, cat)})
            ident = rest[1]
            if len(rest) == 2:
                return self._json({'ok': True, 'result': map_state(ws, slug, ident, cat)})
            if len(rest) == 3 and rest[2] in ('image', 'source'):
                number = q.get('plane', '1')
                if not number.isdigit() or not 1 <= int(number) <= 8:
                    raise KosmoError('bad_request', 'Plane must be 1–8.')
                if rest[2] == 'image':
                    # Optional documented terrain look (Map Making Manual p.10); plain ?plane= requests are unchanged.
                    look, winter = q.get('look', 'default'), q.get('winter', '0')
                    if winter not in ('0', '1'):
                        raise KosmoError('bad_request', 'Winter must be 0 or 1.')
                    png, served, fallback = map_variant_image(ws, slug, ident, int(number), look, winter == '1')
                    return self._send(200, png, 'image/png', {'X-Kosmo-Map-Image': served,
                                                              'X-Kosmo-Map-Fallback': '1' if fallback else '0'})
                raw = map_source(ws, slug, ident, int(number))
                return self._send(200, raw, 'text/plain; charset='+('utf-8' if raw.decode('utf-8', errors='replace').encode('utf-8') == raw else 'iso-8859-1'))
            if len(rest) == 4 and rest[2] == 'exports':
                path = map_export_path(ws, slug, ident, rest[3])
                return self._send(200, path.read_bytes(), 'application/zip',
                                  {'Content-Disposition': f'attachment; filename="{path.name}"'})
            return self._error(HTTPStatus.NOT_FOUND, 'not_found', 'Unknown map route.')
        if head == 'commands' and len(rest) == 1:
            cat, _err = self.state.catalog_for(slug)
            return self._json({'ok': True, 'result': command_state(ws, slug, q.get('context', 'monster'), cat)})
        if head == 'dependencies' and len(rest) == 1:
            return self._json({'ok': True, 'result': dependency_state(ws, slug)})
        if head == "source" and len(rest) == 1:
            project = open_project(ws, slug)
            data, _text, enc = read_dm(resolve_dm_target(project, None))
            extra = {"Content-Disposition": f'attachment; filename="{slug}.dm"'} if dl else None
            ctype = "text/plain; charset=" + ("utf-8" if enc == "utf-8" else "iso-8859-1")
            return self._send(200, data, ctype, extra)
        if head == "assets" and len(rest) >= 2:
            return self._asset(slug, "/".join(rest[1:]), q, dl)
        if head == "exports":
            return self._export(slug, rest[1:])
        if head == "workshop":
            if len(rest) == 1:
                return self._json({"ok": True, "result": workshop_state(ws, slug, self.state.mods_config())})
            if len(rest) == 3 and rest[2] == "manifest":
                return self._json({"ok": True, "manifest": workshop_manifest(ws, slug, rest[1])})
            if len(rest) == 3 and rest[2] == "banner.png":
                return self._send(200, workshop_banner(ws, slug, rest[1]), "image/png")
            if len(rest) == 3 and rest[2] == "archive":
                name, raw = workshop_archive(ws, slug, rest[1])
                return self._send(200, raw, "application/zip", {"Content-Disposition": f'attachment; filename="{name}"'})
            return self._error(HTTPStatus.NOT_FOUND, "not_found", "Unknown Workshop route.")
        if head == "donors" and len(rest) == 1:
            open_project(ws, slug)
            cat, _err = self.state.catalog_for(slug)
            return self._json({"ok": True, "result": donor_search(cat, q.get("q", "")[:MAX_DONOR_QUERY + 1])})
        if head == "content" and len(rest) == 2 and rest[1] in CONTENT_KINDS:
            cat, _err = self.state.catalog_for(slug)
            return self._json({"ok": True, "result": content_state(ws, slug, rest[1], cat)})
        if head == "reference" and len(rest) == 1:
            open_project(ws, slug)
            cat, _err = self.state.catalog_for(slug)
            return self._json({"ok": True, "result": reference_search(cat, q.get("cat", ""),
                                                                      q.get("q", "")[:MAX_DONOR_QUERY + 1])})
        if head == "reference" and len(rest) == 3 and rest[1] in REF_CATS and re.fullmatch(r"\d{1,5}", rest[2]):
            open_project(ws, slug)
            cat, _err = self.state.catalog_for(slug)
            return self._json({"ok": True, "result": reference_detail(cat, rest[1], int(rest[2]))})
        if head == "inspector" and 1 <= len(rest) <= 3:
            open_project(ws, slug)
            cat, _err = self.state.catalog_for(slug)
            if len(rest) == 1:
                return self._json({"ok": True, "result": inspector_summary(cat)})
            if rest[1] not in INSPECTOR_CATS:
                return self._error(HTTPStatus.NOT_FOUND, "not_found", "Unknown inspector category.")
            if len(rest) == 2:
                conds = getattr(self, "_query_lists", {}).get("c", [])
                if len(conds) > INSPECTOR_MAX_CONDITIONS:
                    return self._error(HTTPStatus.BAD_REQUEST, "bad_query",
                                       f"At most {INSPECTOR_MAX_CONDITIONS} conditions.", field="c")
                return self._json({"ok": True, "result": inspector_list(
                    cat, rest[1], q.get("q", ""), q.get("field", ""), q.get("op", ""), q.get("value", ""),
                    q.get("page", "1"), q.get("per_page", ""), conditions=conds, sort=q.get("sort", ""),
                    order=q.get("order", ""), age=q.get("age", ""), nation=q.get("nation", ""),
                    role=q.get("role", ""))})
            if rest[2] == "filters":
                return self._json({"ok": True, "result": inspector_filters(cat, rest[1])})
            if not re.fullmatch(r"\d{1,6}", rest[2]):
                return self._error(HTTPStatus.NOT_FOUND, "not_found", "Inspector ids are whole numbers.")
            return self._json({"ok": True, "result": inspector_detail(cat, slug, rest[1], int(rest[2]))})
        if head == "mercs" and len(rest) == 1:
            cat, _err = self.state.catalog_for(slug)
            return self._json({"ok": True, "result": merc_state(ws, slug, cat)})
        if head == "playtests" and len(rest) == 1:
            return self._json({"ok": True, "result": list_playtests(ws, slug)})
        if head == "nations" and len(rest) == 3 and rest[2] == "heroes" and re.fullmatch(r"\d{1,3}", rest[1]):
            cat, _err = self.state.catalog_for(slug)
            return self._json({"ok": True, "result": heroes_state(ws, slug, int(rest[1]), cat)})
        if head == "reference-snapshot" and len(rest) == 1:
            return self._json({"ok": True, "result": self._model(slug)["reference"]})
        if head == "trait-icons" and len(rest) == 1:
            open_project(ws, slug)
            return self._json({"ok": True, "icons": self.state.trait_icons_for(slug)[0]})
        if len(rest) == 2 and head in ("trait-icons", "gem-icons", "path-icons", "ability-icons", "item-icons"):
            open_project(ws, slug)
            return self._icon(head, rest[1], slug)
        if head == "catalog-units" and len(rest) in (2, 4) and MONSTER_ID_RE.match(rest[1]):
            return self._catalog_unit(slug, int(rest[1]), rest[2:])
        if head == "docs" and len(rest) >= 2:
            name = "/".join(rest[1:])
            path = project_doc_path(ws, slug, name)
            return self._send_doc(path, dl)
        m = self._model(slug)
        prov = {"schema": m["schema"], "provenance": m["provenance"]}
        if head in SECTIONS and len(rest) == 1:
            return self._json({"ok": True, **prov, head: m[head]}, download=f"{slug}-{head}.json" if dl else None)
        if head == "pretenders" and len(rest) in (2, 4):
            return self._pretender(slug, m, prov, rest, dl)
        if head == "monsters" and len(rest) == 3 and rest[2] == "edit" and MONSTER_ID_RE.match(rest[1]):
            cat, _err = self.state.catalog_for(slug)
            return self._json({"ok": True, "result": editor_state(ws, slug, int(rest[1]), cat)})
        if head == "nations" and len(rest) == 3 and rest[2] == "edit" and re.fullmatch(r"\d{1,3}", rest[1]):
            cat, _err = self.state.catalog_for(slug)
            return self._json({"ok": True, "result": nation_editor_state(ws, slug, int(rest[1]), cat)})
        if head in ("monsters", "sites", "nations", "other_definitions") and len(rest) == 2:
            uid_tail = rest[1]
            for obj in m[head]:
                if str(obj.get("id")) == uid_tail or obj["uid"] == uid_tail or obj["uid"].split(":", 1)[1] == uid_tail:
                    return self._json({"ok": True, **prov, "object": obj},
                                      download=f"{slug}-{obj['uid'].replace(':', '-')}.json" if dl else None)
            return self._error(HTTPStatus.NOT_FOUND, "object_missing", f"No {head[:-1]} {uid_tail!r} in {slug}.")
        return self._error(HTTPStatus.NOT_FOUND, "not_found", "Unknown project route.")

    def _pretender(self, slug: str, m: dict[str, Any], prov: dict[str, Any], rest: list[str], dl: bool) -> None:
        match = GOD_REF_RE.match(rest[1])
        god = None
        if match:
            uid = f"god:{match.group(1)}:{int(match.group(2))}"
            god = next((g for g in m["pretenders"]["gods"] if g["uid"] == uid), None)
        if god is None:
            return self._error(HTTPStatus.NOT_FOUND, "object_missing", f"No pretender {rest[1]!r} in {slug}.")
        if len(rest) == 2:
            return self._json({"ok": True, **prov, "object": god},
                              download=f"{slug}-{god['uid'].replace(':', '-')}.json" if dl else None)
        # Vanilla god sprites only: the god must be a catalog candidate in this project's model, and the file
        # path is rebuilt from its integer id and a fixed frame name. There is no general catalog file route.
        if rest[2] != "sprite" or rest[3] not in SPRITE_FRAMES or god["source"] != "catalog":
            return self._error(HTTPStatus.NOT_FOUND, "not_found", "Unknown pretender route.")
        cat, _err = self.state.catalog_for(slug)
        path = catalog_sprite_path(cat, god["id"], rest[3])
        if path is None:
            return self._error(HTTPStatus.NOT_FOUND, "sprite_missing", "No catalog sprite for this pretender.")
        data = read_verified(cat, path)
        if data is None:
            return self._error(HTTPStatus.NOT_FOUND, "sprite_missing", "The snapshot sprite does not match its manifest.")
        self._send(200, data, "image/png")

    def _gem_icon(self, name: str) -> None:
        """One catalog gem icon (images/magicicons/Gem_<P>.png) for a path letter from GEM_ICON_PATHS only."""
        self._icon("gem-icons", name, None)

    def _icon(self, kind: str, name: str, slug: str | None) -> None:
        """One native icon by fixed key. With a slug it comes from that project's catalog (its snapshot if any)."""
        key = name[:-4] if name.endswith(".png") else ""
        if kind == "trait-icons":
            png = (self.state.trait_icons_for(slug)[1] if slug else self.state.trait_icon_images).get(key)
            if png is None:
                return self._error(HTTPStatus.NOT_FOUND, "icon_missing", "No confirmed native icon for this trait.")
            return self._send(200, png, "image/png")
        if kind == "gem-icons":
            return self._catalog_icon("magicicons", f"Gem_{key}.png" if key in GEM_ICON_PATHS else None, slug)
        if kind == "path-icons":
            return self._catalog_icon("magicicons", f"Path_{key}.png" if key in PATH_ICON_PATHS else None, slug)
        if kind == "ability-icons":
            return self._catalog_icon("abilityicons", f"{key}.png" if key in ABILITY_ICON_NAMES else None, slug)
        mi = ITEM_ICON_RE.match(name)
        return self._catalog_icon("items", f"item{int(mi.group(1))}.png" if mi else None, slug)

    def _catalog_icon(self, folder: str, fname: str | None, slug: str | None = None) -> None:
        """One small PNG from the catalog's images/<folder>; callers rebuild fname from a fixed allow-list or an id."""
        cat, _err = self.state.catalog_for(slug) if slug else self.state.catalog()
        if fname is None or cat is None:
            return self._error(HTTPStatus.NOT_FOUND, "icon_missing", "No native catalog icon for this key.")
        base = cat.gamedata.parent / "images" / folder
        path = base / fname
        if any(is_link(part) for part in (base.parent, base, path)) or not path.is_file() \
                or path.stat().st_size > MAX_CATALOG_ICON_BYTES:
            return self._error(HTTPStatus.NOT_FOUND, "icon_missing", "No native catalog icon for this key.")
        data = read_verified(cat, path) or b""
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return self._error(HTTPStatus.NOT_FOUND, "icon_missing", "No native catalog icon for this key.")
        self._send(200, data, "image/png")

    def _catalog_unit(self, slug: str, mid: int, rest: list[str]) -> None:
        """Read-only comparison data for one catalog unit, or its sprite rebuilt from the integer id."""
        open_project(self.state.workspace, slug)
        cat, _err = self.state.catalog_for(slug)
        if not rest:
            return self._json({"ok": True, "result": catalog_unit_view(cat, slug, mid)})
        if rest[0] != "sprite" or rest[1] not in SPRITE_FRAMES:
            return self._error(HTTPStatus.NOT_FOUND, "not_found", "Unknown catalog unit route.")
        path = catalog_sprite_path(cat, mid, rest[1])
        if path is None:
            return self._error(HTTPStatus.NOT_FOUND, "sprite_missing", "No catalog sprite for this unit.")
        data = read_verified(cat, path)
        if data is None:
            return self._error(HTTPStatus.NOT_FOUND, "sprite_missing", "The snapshot sprite does not match its manifest.")
        self._send(200, data, "image/png")

    def _export(self, slug: str, rest: list[str]) -> None:
        """Read back exports by fixed id only: the list, one manifest, or one zip archive."""
        ws = self.state.workspace
        if not rest:
            return self._json({"ok": True, "exports": list_exports(ws, slug)})
        if len(rest) != 2 or rest[1] not in ("manifest", "archive"):
            return self._error(HTTPStatus.NOT_FOUND, "not_found", "Unknown export route.")
        entry = find_export(ws, slug, rest[0])
        if rest[1] == "manifest":
            return self._json({"ok": True, "export_id": entry["export_id"], "format": entry["format"],
                               "manifest": read_export_manifest(entry)})
        path = entry["path"]
        if entry["format"] != "zip" or is_link(path) or not path.is_file():
            return self._error(HTTPStatus.NOT_FOUND, "export_missing", "Folder exports have no archive to download.")
        if path.stat().st_size > MAX_ARCHIVE_BYTES:
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "export_too_large", "Archive is too large to serve.")
        self._send(200, path.read_bytes(), "application/zip",
                   {"Content-Disposition": f'attachment; filename="{entry["export_id"]}.zip"'})

    def _asset(self, slug: str, ref: str, q: dict[str, str], dl: bool) -> None:
        path = asset_path(self.state.workspace, slug, ref)
        data = path.read_bytes()
        if q.get("format") == "png" and path.suffix.lower() == ".tga":
            try:
                w, h, rgba = decode_tga(data)
            except ValueError as exc:
                return self._error(HTTPStatus.UNPROCESSABLE_ENTITY, "preview_unavailable",
                                   f"TGA preview unavailable: {exc}", path=ref)
            return self._send(200, encode_png(w, h, rgba), "image/png")
        ctype = {".png": "image/png", ".tga": "image/x-tga"}.get(path.suffix.lower()) or \
            mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not ctype.startswith("image/png"):
            dl = True  # never let the browser render anything but PNG inline
        extra = {"Content-Disposition": f'attachment; filename="{path.name}"'} if dl else None
        self._send(200, data, ctype, extra)

    def _global_doc(self, name: str, dl: bool) -> None:
        if not self.state.docs or not DOC_NAME_RE.match(name):
            return self._error(HTTPStatus.NOT_FOUND, "doc_missing", "No such document.")
        if name not in {d["name"] for d in self.state.global_docs()}:
            return self._error(HTTPStatus.NOT_FOUND, "doc_missing", "No such document.")
        self._send_doc(contained(self.state.docs, name, what="document"), dl)

    def _send_doc(self, path: Path, dl: bool) -> None:
        if is_link(path) or not path.is_file():
            raise KosmoError("doc_missing", "No such document.")
        if path.stat().st_size > MAX_DOC_BYTES:
            raise KosmoError("doc_too_large", "Document is too large to display.")
        extra = {"Content-Disposition": f'attachment; filename="{path.name}"'} if dl else None
        self._send(200, path.read_bytes(), "text/plain; charset=utf-8", extra)


def make_server(workspace: str, catalog: str | None, docs: str | None, host: str = "127.0.0.1",
                port: int = 8765) -> ThreadingHTTPServer:
    if not _is_loopback(host):
        raise KosmoError("host_not_loopback", "The browser only binds to loopback addresses (127.0.0.1, ::1, "
                                              "localhost).", host=host)
    state = BrowserState(workspace, catalog, docs)
    handler = type("BoundHandler", (Handler,), {"state": state})
    server_cls = ThreadingHTTPServer
    if ":" in host:
        import socket

        server_cls = type("V6Server", (ThreadingHTTPServer,), {"address_family": socket.AF_INET6})
    server = server_cls((host, port), handler)
    server.daemon_threads = True
    return server


def serve(workspace: str | None, catalog: str | None, docs: str | None, host: str, port: int,
          open_browser: bool = False) -> int:
    """CLI entry: run until Ctrl+C. Returns a process exit code."""
    try:
        server = make_server(workspace or "", catalog, docs, host, port)
    except KosmoError as exc:
        print(f"error [{exc.code}]: {exc.message}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error [bind_failed]: {exc}", file=sys.stderr)
        return 2
    h, p = server.server_address[:2]
    shown = f"[{h}]" if ":" in str(h) else h
    print(f"Kosmokrator local mod browser and editors on http://{shown}:{p}/  (workspace "
          f"{server.RequestHandlerClass.state.workspace})\nLoopback only. Saving edits changes project .dm files "
          "(with backups); creation and artwork saves also update project files. Exports add new files under "
          "<project>/exports.\nPress Ctrl+C to stop.", flush=True)
    try:
        if open_browser:
            import webbrowser
            try:
                if not webbrowser.open(f"http://{shown}:{p}/"):
                    print("Browser could not be opened; use the address above.", file=sys.stderr)
            except OSError:
                print("Browser could not be opened; use the address above.", file=sys.stderr)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
