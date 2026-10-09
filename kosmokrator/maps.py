"""Project map bundles: lossless edits, static checks, guarded import and separate export."""
from __future__ import annotations

import base64
import collections
import difflib
import json
import math
import os
import re
import secrets
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .dmparse import decode_dm
from .errors import KosmoError
from .mapformat import (BORDER_TYPES, COMMANDS, FORMAT_MANUAL, MAP_MANUAL, MAX_PIXELS,
                        MAX_PROVINCES, TERRAIN_FLAGS, geography, statements)
from .paths import contained, exact_case_lookup, is_link
from .project import open_project, project_lock, read_dm, sha256_bytes, write_dm_locked
from .tga import decode_tga, encode_png

NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
FILE = re.compile(r"^[A-Za-z0-9_]+\.(?:map|tga|d6m|rgb|d3m|png|txt)$", re.I)
MAX_BYTES = 128 * 1024 * 1024
MAX_MAP_BYTES = 16 * 1024 * 1024
MAX_FILES = 160
READ_ONLY = {"imagefile", "winterimagefile", "mapsize", "land", "setland"}
# Map Making Manual 6.26 p.10 "Terrain Graphics": <map>.tga, <map>_winter.tga and these looks, each with an
# optional "w" winter suffix; numbered planes put "_planeN" first. The default look is used when one is missing.
TERRAIN_LOOKS = ("plain", "forest", "waste", "farm", "swamp", "highland", "kelp", "water")


def _bundle(project, ident: str) -> Path:
    if not isinstance(ident, str) or not NAME.fullmatch(ident) or len(ident) > 48:
        raise KosmoError("bad_map_id", "Map ID must start with a letter and use letters, digits or underscores (max 48).")
    return contained(project.root, project.root / "maps" / ident, what="map bundle")


def _files(root: Path) -> dict[str, bytes]:
    """Read only flat, bounded map bundles; reject links and nested content rather than silently omitting it."""
    if not root.is_dir():
        raise KosmoError("map_missing", "Map bundle does not exist.")
    out = {}
    total = 0
    for p in sorted(root.iterdir()):
        contained(root, p, what="map file")
        if not p.is_file() or not FILE.fullmatch(p.name):
            raise KosmoError("bad_map_file", f"Unsupported map bundle entry: {p.name}")
        size = p.stat().st_size
        total += size
        if total > MAX_BYTES or len(out) >= MAX_FILES or (p.suffix.lower() == '.map' and size > MAX_MAP_BYTES):
            raise KosmoError("too_large", "Map bundle exceeds file, source or total size limits.")
        out[p.name] = p.read_bytes()
    return out


def _revision(files: dict[str, bytes]) -> str:
    return sha256_bytes(json.dumps({n: sha256_bytes(b) for n, b in sorted(files.items())},
                                  sort_keys=True).encode())


def _main(files: dict[str, bytes], ident: str) -> str:
    wanted = f"{ident}.map"
    if wanted not in files:
        raise KosmoError("map_missing", f"Expected main file {wanted} in the map bundle.")
    return wanted


def _render(command: str, args: Any) -> str:
    """Render only typed reviewed commands, rejecting code injection and invented command forms."""
    spec = COMMANDS.get(command)
    if not spec or not isinstance(args, list) or len(args) != len(spec['args']):
        raise KosmoError("bad_map_command", f"Wrong or unsupported arguments for #{command}.")
    parts = []
    for a, v in zip(spec['args'], args):
        kind = a['type']
        if kind in ('int', 'float'):
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or (kind == 'int' and not isinstance(v, int)):
                raise KosmoError("bad_map_command", f"{a['name']} must be a {kind}.")
            if a['min'] is not None and v < a['min'] or a['max'] is not None and v > a['max']:
                raise KosmoError("bad_map_command", f"{a['name']} is outside its supported range.")
            parts.append(str(v))
        elif kind == 'ref' and isinstance(v, int) and not isinstance(v, bool) and v >= 0:
            parts.append(str(v))
        else:
            if not isinstance(v, str) or not v.strip() or len(v) > 16000 or any(c in v for c in ('"', '\0', '\r')):
                raise KosmoError("bad_map_command", f"{a['name']} must be nonempty text without quotes or NUL.")
            if '\n' in v and command != 'description':
                raise KosmoError("bad_map_command", "Only descriptions may contain newlines.")
            if command == 'scale':
                if v not in ('chaos', 'lazy', 'cold', 'death', 'unluck', 'unmagic'):
                    raise KosmoError("bad_map_command", "Unknown scale name.")
                parts.append(v)
            else:
                parts.append('"'+v+'"')
    return '#'+command+(' '+' '.join(parts) if parts else '')


def _reference_names(project, catalog) -> dict[str, dict]:
    """Build explicit mod/dependency name indexes for map-only reference rules."""
    from .resolution import relationships
    rel, _layers = relationships(project.workspace, project, read_dm(project.dm_path)[1], catalog)
    result = {k: {} for k in ('monster', 'site', 'nation', 'item', 'custom_monsters')}
    for obj in rel['objects']:
        if obj.get('context') in result and obj.get('name'):
            result[obj['context']].setdefault(str(obj.get('id')), obj['name'])
            result[obj['context']][obj['name'].casefold()] = obj['name']
            if obj['context'] == 'monster' and obj['identity']['kind'] == 'new':
                result['custom_monsters'][str(obj['id'])] = obj['name']
    return result


def _plane(root: Path, file: str, number: int, multiple: bool, names: dict, catalog=None) -> dict:
    data = contained(root, root/file, what="map source").read_bytes()
    text, enc = decode_dm(data)
    rows = statements(text)
    issues = []
    def issue(severity, message, line=None):
        issues.append({"severity": severity, "message": message, **({"line": line} if line else {})})
    if not rows or rows[0].command != 'dom2title':
        issue('error', '#dom2title must be the first command.')
    image_ref, width, height, title = None, 0, 0, file
    for st in rows:
        if st.errors:
            for e in st.errors:
                issue('error', e, st.line)
        if st.command == 'dom2title':
            title = ' '.join(str(a.value) for a in st.args)
        elif st.command == 'imagefile' and st.args:
            image_ref = str(st.args[0].value)
        elif st.command == 'mapsize' and len(st.args) == 2 and all(a.kind == 'int' for a in st.args):
            width, height = [a.value for a in st.args]
    if width < 256 or height < 256 or width*height > MAX_PIXELS:
        issue('error', '#mapsize must be at least 256×256 and within the 16 megapixel limit.')
    image = {"kind": "unavailable", "preview_url": None, "note": "No readable map image.", "positions": []}
    if not image_ref or not FILE.fullmatch(image_ref) or Path(image_ref).suffix.lower() not in ('.tga', '.d6m', '.rgb'):
        issue('error', '#imagefile must name a supported file in this map bundle.')
    else:
        path, reason = exact_case_lookup(root, image_ref)
        if path is None:
            issue('error', f'Missing map image {image_ref}: {reason}')
        else:
            try:
                image = {"preview_url": None, **geography(path, rows)}
                if image.get('width') and (width, height) != (image['width'], image['height']):
                    issue('error', '#mapsize does not match the image dimensions.')
                if image['kind'] == 'tga':
                    if not image.get('marker_count'):
                        issue('error', 'TGA image has no pure-white province centres.')
                    if image.get('area_count') and image['area_count'] != image['marker_count']:
                        issue('error', 'White province centre count differs from #pb province ownership count.')
                    if not image.get('area_count'):
                        issue('warning', 'No #pb province ownership spans; verify province numbering and dominion areas in the game map editor.')
                    if image.get('unowned_markers'):
                        issue('error', 'Some white province markers have no #pb ownership.')
                elif image['kind'] == 'unavailable':
                    issue('warning', image['note'])
            except (ValueError, OSError) as exc:
                if path.suffix.lower() == '.d6m' and 'version 3' in str(exc):
                    image = {'kind': 'd6m', 'preview_url': None, 'positions': [],
                             'note': 'Undocumented d6m version preserved; province coordinates are unavailable.'}
                    issue('warning', image['note'])
                else:
                    issue('error', f'Cannot read geography: {exc}')
    provinces = {}
    def province(pid):
        if isinstance(pid, bool) or not isinstance(pid, int) or not 1 <= pid <= MAX_PROVINCES:
            return None
        return provinces.setdefault(pid, {"id": pid, "name": f"Province {pid}", "terrain": 0,
               "terrain_labels": [], "position": None, "start": False, "nostart": False,
               "specstarts": [], "gates": [], "commands": [], "neighbors": []})
    positions = image.pop('positions', [])
    physical = {p['id'] for p in positions}
    for p in positions:
        province(p['id'])['position'] = {"x": p['x'], "y": p['y']}
    connections = {}
    specials = {}
    active, commander = None, False
    serialized = []
    starts = {}
    for st in rows:
        cmd, args = st.command, [a.value for a in st.args]
        serialized.append({"line": st.line, "command": cmd, "args": args, "raw": st.raw,
                           "editable": cmd in COMMANDS and cmd not in READ_ONLY})
        spec = COMMANDS.get(cmd)
        # Titles written as several unquoted words occur in shipped maps.
        if spec and cmd != 'dom2title':
            try:
                _render(cmd, args)
            except KosmoError as exc:
                issue('error', exc.message, st.line)
                continue
        elif not spec and cmd != 'pb':
            issue('warning', f'#{cmd} is preserved but not interpreted.', st.line)
        if cmd == 'pb':
            if len(args) != 4 or any(not isinstance(a, int) for a in args):
                issue('error', 'Invalid #pb ownership span.', st.line)
            elif not (0 <= args[0] < width and 0 <= args[1] < height and 0 < args[2] <= width-args[0] and 1 <= args[3] <= MAX_PROVINCES):
                issue('error', '#pb ownership span is outside the map.', st.line)
            continue
        if cmd in ('land', 'setland') and args:
            active, commander = province(args[0]), False
        if cmd == 'god':
            commander = True
        if spec and spec['scope'] in ('province', 'commander'):
            if not active and not (spec['scope'] == 'commander' and commander):
                issue('error', f'#{cmd} needs an active province.', st.line)
            if spec['scope'] == 'commander' and not commander:
                issue('error', f'#{cmd} needs an active commander.', st.line)
            if active:
                active['commands'].append(serialized[-1])
            if cmd == 'commander':
                commander = True
        elif cmd in ('land', 'setland') and active:
            active['commands'].append(serialized[-1])
        if cmd in ('landname', 'terrain', 'start', 'nostart', 'gate', 'teamstart') and args:
            p = province(args[0])
            if p:
                if cmd == 'landname': p['name'] = args[1]
                elif cmd == 'terrain': p['terrain'] = args[1]
                elif cmd == 'start': p['start'] = True
                elif cmd == 'nostart': p['nostart'] = True
                elif cmd == 'gate': p['gates'].append(args[1])
        if cmd == 'specstart' and len(args) == 2:
            nation, pid = args
            if nation in starts:
                issue('warning', f'Nation {nation} has repeated special starts.', st.line)
            starts[nation] = pid
            if pid in physical or not multiple:
                p = province(pid)
                if p: p['specstarts'].append(nation)
            else:
                issue('warning', f'Special start {pid} may address another plane; cross-plane numbering is preserved, not inferred.', st.line)
        if cmd in ('neighbour', 'neighbourspec') and len(args) >= 2:
            a, b = args[:2]
            if a == b:
                issue('error', 'A province cannot neighbor itself.', st.line)
            key = tuple(sorted((a, b)))
            if cmd == 'neighbour': connections[key] = {"a": key[0], "b": key[1], "kind": 0}
            else: specials[key] = args[2]
        if cmd in ('commander', 'units', 'bodyguards', 'god') and args:
            v = args[-1]
            if isinstance(v, int) and str(v) in names['custom_monsters']:
                issue('error', f'Custom monster {v} must be referenced by name: "{names["custom_monsters"][str(v)]}".', st.line)
        ref_type = 'monster' if cmd in ('commander', 'units', 'bodyguards', 'god') else 'site' if cmd in ('feature', 'knownfeature') else 'item' if cmd == 'additem' else None
        if ref_type and args:
            v = args[-1]
            category = {'monster': 'units', 'site': 'sites', 'item': 'items'}[ref_type]
            known = str(v) in names[ref_type] or str(v).casefold() in names[ref_type]
            if not known and catalog:
                known = any(str(r.get('id')) == str(v) or str(r.get('name', '')).casefold() == str(v).casefold()
                            for r in catalog.table(category))
            if not known:
                issue('warning', f'Unresolved {ref_type} reference: {v}. Enable the defining mod or check its name.', st.line)
    for key, kind in specials.items():
        if key not in connections:
            issue('warning', f'Special border {key[0]}–{key[1]} has no #neighbour connection.')
        else:
            connections[key]['kind'] = kind
    for edge in connections.values():
        for a, b in ((edge['a'], edge['b']), (edge['b'], edge['a'])):
            p = province(a)
            if p: p['neighbors'].append({"id": b, "kind": edge['kind']})
    for p in provinces.values():
        p['terrain_labels'] = [f['label'] for f in TERRAIN_FLAGS if p['terrain'] & f['value']]
        p['nostart'] |= bool(p['terrain'] & 512)
        if p['start'] and p['nostart']:
            issue('warning', f'Province {p["id"]}: no-start overrides its recommended start.')
        if p['terrain'] & 2048 and not p['terrain'] & 4:
            issue('warning', f'Province {p["id"]}: deep sea lacks the sea terrain flag.')
        if p['specstarts'] and p['nostart']:
            issue('warning', f'Province {p["id"]}: special start and no-start settings need scenario review.')
        if physical and p['id'] not in physical:
            issue('error', f'Province {p["id"]} is referenced but has no geography.')
        if p['specstarts'] and any(r['command'] == 'land' for r in p['commands']):
            issue('warning', f'Province {p["id"]}: #land clears starting troops and can kill its pretender. Use #setland for capital customization.')
    remaining = set(provinces)
    components = []
    while remaining:
        todo = [remaining.pop()]; group = []
        while todo:
            pid = todo.pop(); group.append(pid)
            for e in provinces[pid]['neighbors']:
                if not e['kind'] & 4 and e['id'] in remaining:
                    remaining.remove(e['id']); todo.append(e['id'])
        components.append(sorted(group))
    if len(components) > 1:
        issue('warning', f'{len(components)} disconnected movement components (gates, sailing and spells are not simulated).')
    for pid in set(starts.values()):
        if pid in provinces and any(e['id'] in starts.values() and not e['kind'] & 4 for e in provinces[pid]['neighbors']):
            issue('warning', f'Special start {pid} is directly adjacent to another special start.')
    return {"number": number, "file": file, "title": title, "width": width, "height": height,
            "image": {**image, "file": image_ref}, "provinces": sorted(provinces.values(), key=lambda p: p['id']),
            "connections": list(connections.values()), "statements": serialized,
            "components": components, "validation": _validation(issues), "encoding": enc}


def _variant_name(plane_file: str, look: str, winter: bool) -> str:
    stem = Path(plane_file).stem
    if look == 'default':
        return f'{stem}_winter.tga' if winter else ''
    return f'{stem}_{look}{"w" if winter else ""}.tga'


def _tga_size(data: bytes) -> tuple[int, int] | None:
    """Header-only check of the 24/32-bit true-colour TGA the manual requires; full decoding happens on request."""
    if len(data) < 18 or data[1] != 0 or data[2] not in (2, 10) or data[16] not in (24, 32):
        return None
    return int.from_bytes(data[12:14], 'little'), int.from_bytes(data[14:16], 'little')


def _variants(plane: dict, files: dict[str, bytes], base: str) -> list[dict]:
    """Inventory the documented terrain-look images of one plane; nothing here infers when the game shows them."""
    out = []
    size = (plane['image'].get('width'), plane['image'].get('height'))
    for look in ('default',) + TERRAIN_LOOKS:
        for winter in (False, True):
            name = _variant_name(plane['file'], look, winter) or plane['image'].get('file')
            entry = {'look': look, 'winter': winter, 'file': name, 'available': False, 'url': None, 'note': None}
            dims = _tga_size(files[name]) if name in files else None
            if name not in files:
                entry['note'] = 'Not in this bundle; the default look is used.'
            elif dims is None:
                entry['note'] = 'Not a 24/32-bit true-colour TGA.'
            elif dims != size:
                entry['note'] = f'Size {dims[0]}x{dims[1]} differs from the map image.'
            else:
                entry['available'] = True
                query = '' if look == 'default' and not winter else f'&look={look}&winter={int(winter)}'
                entry['url'] = f'{base}/image?plane={plane["number"]}{query}'
            out.append(entry)
    return out


def _validation(issues):
    return {"errors": sum(i['severity'] == 'error' for i in issues),
            "warnings": sum(i['severity'] == 'warning' for i in issues), "issues": issues}


def _state(project, ident: str, root: Path, catalog=None) -> dict:
    files = _files(root)
    main = _main(files, ident)
    plane_files = [(1, main)] + [(n, f'{ident}_plane{n}.map') for n in range(2, 9) if f'{ident}_plane{n}.map' in files]
    names = _reference_names(project, catalog)
    planes = [_plane(root, f, n, len(plane_files) > 1, names, catalog) for n, f in plane_files]
    issues = [{**i, 'plane': p['number']} for p in planes for i in p['validation']['issues']]
    for n, f in plane_files:
        if n > 1 and f'{ident}_plane{n-1}.map' not in files and n != 2:
            issues.append({'severity': 'warning', 'message': f'Plane {n-1} is missing before plane {n}.'})
    assigned = {f for _, f in plane_files}
    for f in files:
        if f.endswith('.map') and f not in assigned:
            issues.append({'severity': 'warning', 'message': f'{f} is bundled but is not a recognized plane.'})
    base = f'/api/projects/{project.slug}/maps/{ident}'
    for p in planes:
        if p['image']['kind'] == 'tga':
            p['image']['preview_url'] = f'{base}/image?plane={p["number"]}'
            p['image']['variants'] = _variants(p, files, base)
    return {'id': ident, 'title': planes[0]['title'], 'revision': _revision(files), 'planes': planes,
            'files': [{'name': n, 'bytes': len(b), 'sha256': sha256_bytes(b)} for n, b in files.items()],
            'validation': _validation(issues), 'terrain_flags': TERRAIN_FLAGS, 'border_types': BORDER_TYPES,
            'commands': [v for k, v in COMMANDS.items() if k not in READ_ONLY],
            'source_url': base+'/source', 'export_url': base+'/export',
            'provenance': {'map_manual': MAP_MANUAL, 'map_manual_version': '6.26', 'format_manual': FORMAT_MANUAL},
            'limitations': ['Static checks do not establish game loading or balance.',
                            'Imported geography and #pb areas are preserved; painting and generation are not implemented.',
                            'd6m previews show coordinates, not the game terrain renderer.',
                            'Terrain-look previews show bundled images clipped to #pb areas; they do not simulate when the game switches looks.',
                            'Cross-plane special-start numbering and gateway travel are not simulated.']}


def map_state(workspace: Path, slug: str, ident: str, catalog=None) -> dict:
    project = open_project(workspace, slug)
    return _state(project, ident, _bundle(project, ident), catalog)


def list_maps(workspace: Path, slug: str, catalog=None) -> dict:
    project = open_project(workspace, slug)
    root = contained(project.root, project.root/'maps', what='maps directory')
    result = []
    if root.is_dir():
        for p in sorted(root.iterdir()):
            if not p.is_dir() or not NAME.fullmatch(p.name):
                continue
            try:
                state = _state(project, p.name, _bundle(project, p.name), catalog)
                result.append({'id': p.name, 'title': state['title'], 'planes': len(state['planes']),
                               'provinces': sum(len(p['provinces']) for p in state['planes']),
                               'revision': state['revision'], 'validation': state['validation']})
            except (KosmoError, OSError, ValueError) as exc:
                result.append({'id': p.name, 'title': p.name, 'planes': 0, 'provinces': 0,
                               'validation': _validation([{'severity': 'error', 'message': str(exc)}])})
    return {'maps': result}


def _import_files(body: dict) -> tuple[str, dict[str, bytes]]:
    if not isinstance(body, dict) or not isinstance(body.get('files'), list) or not 1 <= len(body['files']) <= MAX_FILES:
        raise KosmoError('bad_request', 'Import needs an ID and a bounded list of map files.')
    ident = body.get('id')
    if not isinstance(ident, str) or not NAME.fullmatch(ident) or len(ident) > 48:
        raise KosmoError('bad_map_id', 'Use a map ID of letters, digits and underscores, starting with a letter.')
    if body.get('main') != f'{ident}.map':
        raise KosmoError('bad_map_file', 'Main map filename must match the map ID (names are preserved).')
    files = {}
    total = 0
    for item in body['files']:
        if not isinstance(item, dict) or not FILE.fullmatch(str(item.get('name', ''))):
            raise KosmoError('bad_map_file', 'Use flat map asset filenames without spaces or path separators.')
        name = item['name']
        if name.casefold() in {n.casefold() for n in files}:
            raise KosmoError('bad_map_file', 'Duplicate or case-colliding filename.')
        try:
            raw = base64.b64decode(item['data'], validate=True)
        except (KeyError, ValueError, TypeError) as exc:
            raise KosmoError('bad_map_file', 'File data must be base64.') from exc
        total += len(raw)
        if total > MAX_BYTES or (name.lower().endswith('.map') and len(raw) > MAX_MAP_BYTES):
            raise KosmoError('too_large', 'Map bundle exceeds size limits.')
        files[name] = raw
    _main(files, ident)
    return ident, files


def import_map(workspace: Path, slug: str, body: dict, catalog=None) -> dict:
    """Stage and inspect uploads before atomically adding a new bundle; never overwrite a map."""
    project = open_project(workspace, slug)
    ident, files = _import_files(body)
    dest = _bundle(project, ident)
    with tempfile.TemporaryDirectory(prefix='kosmo-map-') as temporary:
        staging = Path(temporary)
        for name, raw in files.items():
            (staging/name).write_bytes(raw)
        state = _state(project, ident, staging, catalog)
        result = {'id': ident, 'revision': state['revision'], 'validation': state['validation'],
                  'files': list(files), 'preview': body.get('preview', True) is not False}
        if result['preview']:
            return result
        if state['validation']['errors']:
            raise KosmoError('validation_failed', 'Map import has static errors; correct them before importing.', validation=state['validation'])
        with project_lock(project):
            if dest.exists() or is_link(dest):
                raise KosmoError('dest_exists', 'Map already exists; import never overwrites.')
            dest.parent.mkdir(parents=True, exist_ok=True)
            contained(project.root, dest.parent, what='maps directory')
            local = contained(project.root, dest.parent/f'_staging_{secrets.token_hex(6)}', what='map staging')
            try:
                local.mkdir()
                for name, raw in files.items():
                    with open(local/name, 'xb') as fh: fh.write(raw)
                os.rename(local, dest)
            finally:
                if local.exists(): shutil.rmtree(local)
        return result


def import_map_path(workspace: Path, slug: str, source: str, preview: bool = True, catalog=None) -> dict:
    """CLI-only import of a user's explicit map file and its flat sibling bundle."""
    path = Path(source).absolute()
    if is_link(path) or not path.is_file() or path.suffix != '.map':
        raise KosmoError('bad_map_file', 'Source must be a regular .map file.')
    root = path.parent.resolve()
    selected = {path.name}
    for p in root.iterdir():
        if FILE.fullmatch(p.name) and p.name.startswith(path.stem+'_'):
            selected.add(p.name)
    for name in list(selected):
        if not name.endswith('.map'): continue
        p = contained(root, root/name, what='source map')
        if p.stat().st_size > MAX_MAP_BYTES: raise KosmoError('too_large', 'Map source exceeds size limit.')
        for st in statements(decode_dm(p.read_bytes())[0]):
            if st.command in ('imagefile', 'winterimagefile', 'skybox', 'batmap') and st.args:
                ref = str(st.args[0].value)
                if ref == 'empty': continue
                if not FILE.fullmatch(ref): raise KosmoError('bad_map_file', 'Referenced asset must have a flat safe filename.')
                selected.add(ref)
    files = {}
    total = 0
    for name in sorted(selected):
        p = contained(root, root/name, what='source map asset')
        if not p.is_file(): raise KosmoError('bad_map_file', f'Missing map asset {name}.')
        total += p.stat().st_size
        if total > MAX_BYTES or len(files) >= MAX_FILES: raise KosmoError('too_large', 'Map bundle exceeds size limits.')
        files[name] = p.read_bytes()
    body = {'id': path.stem, 'main': path.name, 'preview': preview,
            'files': [{'name': n, 'data': base64.b64encode(b).decode()} for n, b in files.items()]}
    return import_map(workspace, slug, body, catalog)


def save_map(workspace: Path, slug: str, ident: str, body: dict, catalog=None) -> dict:
    """Apply bounded source-offset operations with whole-bundle revision checking and backup."""
    project = open_project(workspace, slug)
    if not isinstance(body, dict) or not isinstance(body.get('changes'), list) or not 1 <= len(body['changes']) <= 128:
        raise KosmoError('bad_request', 'Map edit needs 1–128 changes.')
    with project_lock(project):
        root = _bundle(project, ident)
        before = _state(project, ident, root, catalog)
        if body.get('expected_revision') != before['revision']:
            raise KosmoError('sha_mismatch', 'Map bundle changed. Reload its revision and review your draft again.')
        plane = next((p for p in before['planes'] if p['number'] == body.get('plane', 1)), None)
        if not plane: raise KosmoError('bad_request', 'Unknown map plane.')
        path = contained(root, root/plane['file'], what='map source')
        data = path.read_bytes(); text, enc = decode_dm(data)
        rows = statements(text); by_line = {st.line: st for st in rows}
        patches = {}; additions = []
        added_commander_province = None
        nl = '\r\n' if '\r\n' in text else '\n'
        province_ids = {p['id'] for p in plane['provinces']}
        def patch(st, rendered):
            if st.start in patches:
                raise KosmoError('bad_request', 'The same source statement was changed twice.')
            patches[st.start] = (st.end, rendered)
        def upsert(cmd, args, match, enabled=True):
            hits = [s for s in rows if s.command == cmd and match([a.value for a in s.args])]
            rendered = _render(cmd, args) if enabled else ''
            for s in hits[:-1] if enabled else hits: patch(s, '')
            if enabled:
                if hits: patch(hits[-1], rendered)
                else: additions.append(rendered)
        for change in body['changes']:
            if not isinstance(change, dict): raise KosmoError('bad_request', 'Each change must be an object.')
            op = change.get('op')
            if op == 'province':
                pid = change.get('province')
                if pid not in province_ids or isinstance(pid, bool): raise KosmoError('bad_request', 'Unknown province.')
                for key, cmd in (('name', 'landname'), ('terrain', 'terrain'), ('start', 'start'), ('nostart', 'nostart')):
                    if key not in change: continue
                    value = change[key]
                    if key == 'terrain' and change.get('nostart') is False and isinstance(value, int):
                        value &= ~512
                    if key in ('start', 'nostart') and not isinstance(value, bool): raise KosmoError('bad_request', 'Start values must be booleans.')
                    args = [pid] if key in ('start', 'nostart') else [pid, value]
                    upsert(cmd, args, lambda a: bool(a) and a[0] == pid, value if key in ('start', 'nostart') else True)
                # Nostart can also live in the terrain mask; disabling it must clear both representations.
                if change.get('nostart') is False and 'terrain' not in change:
                    old = next(p['terrain'] for p in plane['provinces'] if p['id'] == pid)
                    if old & 512: upsert('terrain', [pid, old & ~512], lambda a: bool(a) and a[0] == pid)
            elif op == 'connection':
                a, b, kind = change.get('a'), change.get('b'), change.get('kind')
                if isinstance(a, bool) or isinstance(b, bool) or a not in province_ids or b not in province_ids or a == b:
                    raise KosmoError('bad_request', 'Connection needs two different existing provinces.')
                if kind is not None and (isinstance(kind, bool) or kind not in (0, 1, 2, 4, 8)):
                    raise KosmoError('bad_request', 'Unsupported connection type.')
                pair = tuple(sorted((a, b)))
                match = lambda v: len(v) >= 2 and tuple(sorted(v[:2])) == pair
                upsert('neighbour', [a, b], match, kind is not None)
                upsert('neighbourspec', [a, b, kind or 0], match, kind not in (None, 0))
            elif op in ('add', 'replace', 'remove'):
                cmd = change.get('command', '')
                if op != 'remove' and (cmd in READ_ONLY or cmd not in COMMANDS):
                    raise KosmoError('bad_map_command', 'Geometry, #land and #setland cannot be changed through generic operations.')
                rendered = _render(cmd, change.get('args')) if op != 'remove' else ''
                if op == 'add':
                    scope = COMMANDS[cmd]['scope']
                    pid = change.get('province')
                    if cmd == 'god':
                        added_commander_province = None
                    if scope in ('province', 'commander'):
                        if pid not in province_ids or isinstance(pid, bool):
                            raise KosmoError('bad_request', 'Province-scoped additions need an existing province.')
                        if scope == 'province':
                            additions.append(_render('setland', [pid]))
                            added_commander_province = pid if cmd == 'commander' else None
                        elif added_commander_province != pid:
                            raise KosmoError('bad_request', 'Commander modifiers must follow a commander addition in the same province and batch.')
                    additions.append(rendered)
                else:
                    st = by_line.get(change.get('line'))
                    if not st or st.command not in COMMANDS or st.command in READ_ONLY:
                        raise KosmoError('bad_request', 'Source line is missing or read-only.')
                    if op == 'replace' and cmd != st.command:
                        raise KosmoError('bad_request', 'Replace preserves the command; use add/remove to change its type.')
                    patch(st, rendered)
            else: raise KosmoError('bad_request', 'Unknown map change operation.')
        for start, (end, rendered) in sorted(patches.items(), reverse=True): text = text[:start]+rendered+text[end:]
        if additions: text += ('' if text.endswith(('\n', '\r')) else nl)+nl.join(additions)+nl
        try: new_data = text.encode(enc)
        except UnicodeEncodeError as exc: raise KosmoError('bad_text', 'Text cannot be represented in this map encoding.') from exc
        files = _files(root); files[plane['file']] = new_data
        with tempfile.TemporaryDirectory(prefix='kosmo-map-edit-') as temporary:
            staging = Path(temporary)
            for name, raw in files.items(): (staging/name).write_bytes(raw)
            after = _state(project, ident, staging, catalog)
        old_errors = collections.Counter(i['message'] for i in before['validation']['issues'] if i['severity'] == 'error')
        new_errors = collections.Counter(i['message'] for i in after['validation']['issues'] if i['severity'] == 'error') - old_errors
        result = {'id': ident, 'before_revision': before['revision'], 'revision': after['revision'],
                  'preview': body.get('preview', True) is not False, 'validation': after['validation'],
                  'diff': ''.join(difflib.unified_diff(decode_dm(data)[0].splitlines(True), text.splitlines(True),
                                                     fromfile=plane['file'], tofile=plane['file']))}
        if new_errors: raise KosmoError('validation_failed', 'Edit introduces map errors.', validation=after['validation'])
        if not result['preview']:
            if _revision(_files(root)) != before['revision']: raise KosmoError('sha_mismatch', 'Map changed during validation.')
            result['backup'] = write_dm_locked(project, path, data, new_data)
        return result


def map_source(workspace: Path, slug: str, ident: str, plane: int = 1) -> bytes:
    project = open_project(workspace, slug)
    root = _bundle(project, ident)
    if not 1 <= plane <= 8: raise KosmoError('bad_request', 'Plane must be 1–8.')
    name = f'{ident}.map' if plane == 1 else f'{ident}_plane{plane}.map'
    path = contained(root, root/name, what='map source')
    if not path.is_file(): raise KosmoError('map_missing', 'Map plane does not exist.')
    return path.read_bytes()


def map_image(workspace: Path, slug: str, ident: str, plane: int = 1, look: str = 'default', winter: bool = False) -> bytes:
    return map_variant_image(workspace, slug, ident, plane, look, winter)[0]


def map_variant_image(workspace: Path, slug: str, ident: str, plane: int = 1, look: str = 'default',
                      winter: bool = False) -> tuple[bytes, str, bool]:
    """PNG of a plane's default or documented terrain-look image: (png, served file, fell back to default).

    The filename is built only from the fixed look list, never from request text. A missing or unusable
    variant falls back to the #imagefile, as the manual describes for missing looks.
    """
    if look != 'default' and look not in TERRAIN_LOOKS:
        raise KosmoError('bad_request', 'Unknown terrain look.')
    project = open_project(workspace, slug)
    root = _bundle(project, ident)
    rows = statements(decode_dm(map_source(workspace, slug, ident, plane))[0])
    ref = next((str(s.args[0].value) for s in reversed(rows) if s.command == 'imagefile' and s.args), '')
    if not FILE.fullmatch(ref) or not ref.lower().endswith('.tga'): raise KosmoError('image_missing', 'No TGA preview for this plane.')
    path, _reason = exact_case_lookup(root, ref)
    if path is None: raise KosmoError('image_missing', 'Map image is missing.')
    fallback = look != 'default' or winter
    if fallback:
        vpath, _reason = exact_case_lookup(root, _variant_name(f'{ident}.map' if plane == 1 else f'{ident}_plane{plane}.map', look, winter))
        if vpath is not None:
            with path.open('rb') as fh:
                size = _tga_size(fh.read(18))
            try:
                vw, vh, vrgba = decode_tga(vpath.read_bytes(), max_pixels=MAX_PIXELS)
                if (vw, vh) == size:
                    return encode_png(vw, vh, vrgba), vpath.name, False
            except ValueError:
                pass
    try: w, h, rgba = decode_tga(path.read_bytes(), max_pixels=MAX_PIXELS)
    except ValueError as exc: raise KosmoError('bad_map_image', str(exc)) from exc
    return encode_png(w, h, rgba), path.name, fallback


def export_map(workspace: Path, slug: str, ident: str, body: dict, catalog=None) -> dict:
    """Package saved maps separately from .dm mods; original art and all plane files remain byte-identical."""
    project = open_project(workspace, slug)
    if not isinstance(body, dict): raise KosmoError('bad_request', 'Export needs a revision.')
    with project_lock(project):
        root = _bundle(project, ident); state = _state(project, ident, root, catalog)
        if body.get('expected_revision') != state['revision']: raise KosmoError('sha_mismatch', 'Reload the map before exporting.')
        if state['validation']['errors']: raise KosmoError('validation_failed', 'Map has static errors.', validation=state['validation'])
        files = _files(root)
        name = f'map_{ident}_{state["revision"][:12]}_{secrets.token_hex(3)}.zip'
        exports = contained(project.root, project.root/'exports', what='exports directory')
        exports.mkdir(parents=True, exist_ok=True)
        path = contained(project.root, exports/name, what='map export')
        dependencies = project.meta.get('dependencies', [])
        readme = (f'{state["title"]}\n\nCopy the {ident} folder into your Dominions6/maps directory.\n'
                  f'Enable the {slug} mod and its required dependencies when using custom content.\n'
                  f'Explicit project dependencies: {json.dumps(dependencies)}\n'
                  'Static checks only; game loading and balance have not been tested.\n')
        try:
            with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
                for filename, data in files.items(): archive.writestr(f'{ident}/{filename}', data)
                archive.writestr('INSTALL.txt', readme)
                archive.writestr('kosmokrator-map-manifest.json', json.dumps({
                    'project': slug, 'map': ident, 'revision': state['revision'],
                    'files': state['files'], 'dependencies': dependencies,
                    'validation': state['validation'], 'limitations': state['limitations']}, indent=2))
            if _revision(_files(root)) != state['revision']:
                raise KosmoError('sha_mismatch', 'Map changed during export.')
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return {'id': name, 'url': f'/api/projects/{slug}/maps/{ident}/exports/{name}',
                'files': list(files), 'revision': state['revision'], 'path': str(path)}


def map_export_path(workspace: Path, slug: str, ident: str, filename: str) -> Path:
    project = open_project(workspace, slug)
    _bundle(project, ident)
    if not re.fullmatch(r'map_'+re.escape(ident)+r'_[a-f0-9]{12}_[a-f0-9]{6}\.zip', filename):
        raise KosmoError('bad_request', 'Unknown map export filename.')
    path = contained(project.root, project.root/'exports'/filename, what='map export')
    if not path.is_file(): raise KosmoError('map_missing', 'Map export does not exist.')
    return path
