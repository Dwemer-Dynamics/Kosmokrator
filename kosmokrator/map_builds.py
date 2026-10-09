"""Agent map briefs and revision-checked review of locally staged map bundles."""
from __future__ import annotations

import base64
import json
import re
import secrets
import tempfile
from pathlib import Path

from .errors import KosmoError
from .maps import NAME, MAX_BYTES, _files, _state, _revision, import_map
from .paths import contained
from .project import open_project, project_lock, sha256_bytes, state_subdir, atomic_write_bytes
from .tga import decode_tga

DEFAULTS = dict(map_id='NewRealms', title='New Realms', theme='', width=1600, height=1000,
                players=4, land_provinces=48, sea_provinces=12, cave_provinces=0,
                wraparound=False, all_layers=True)


def _brief(value):
    """Validate a bounded design request before producing an agent handoff."""
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise KosmoError('bad_request', 'Brief contains unsupported fields.')
    b = {**DEFAULTS, **value}
    if not isinstance(b['map_id'], str) or not NAME.fullmatch(b['map_id']) or len(b['map_id']) > 48:
        raise KosmoError('bad_map_id', 'Use a map ID starting with a letter, then letters, digits or underscores.')
    for name, limit in [('title', 120), ('theme', 4000)]:
        if not isinstance(b[name], str) or len(b[name]) > limit or '\0' in b[name]:
            raise KosmoError('bad_request', f'{name} must be text of at most {limit} characters.')
    for name, lo, hi in [('width',256,4096),('height',256,4096),('players',1,64),
                         ('land_provinces',1,2000),('sea_provinces',0,2000),('cave_provinces',0,2000)]:
        if type(b[name]) is not int or not lo <= b[name] <= hi:
            raise KosmoError('bad_request', f'{name} must be a whole number from {lo} to {hi}.')
    if b['width'] * b['height'] > 16000000 or sum(b[n] for n in ('land_provinces','sea_provinces','cave_provinces')) > 2000:
        raise KosmoError('too_large', 'Use at most 16 megapixels and 2000 provinces across planes.')
    for name in ('wraparound','all_layers'):
        if type(b[name]) is not bool: raise KosmoError('bad_request', f'{name} must be true or false.')
    minimum_bytes = (b['width']*b['height'] + (256*256 if b['cave_provinces'] else 0))*3*(18 if b['all_layers'] else 1)
    if minimum_bytes > MAX_BYTES:
        raise KosmoError('too_large','The requested TGA layers exceed the 128 MiB bundle limit; reduce dimensions or layer count.')
    return b


def _root(project):
    return contained(project.root, project.state_dir / 'map-jobs', what='map jobs')


def _jobs(project):
    root = _root(project); jobs = []
    if root.exists():
        for folder in sorted(root.iterdir()):
            if not re.fullmatch(r'[0-9a-f]{12}', folder.name):
                raise KosmoError('bad_map_job', 'Unexpected entry in map jobs directory.')
            path = contained(project.root, folder/'request.json', what='map job request')
            if not path.is_file() or path.stat().st_size > 16384:
                raise KosmoError('bad_map_job', 'Missing or oversized map job request.')
            data = path.read_bytes()
            try: job = json.loads(data)
            except (ValueError,UnicodeDecodeError): raise KosmoError('bad_map_job', 'Invalid map job JSON.')
            if not isinstance(job,dict): raise KosmoError('bad_map_job','Map job request must be an object.')
            if job.get('id') != folder.name: raise KosmoError('bad_map_job', 'Map job ID differs from folder.')
            job['brief'] = _brief(job.get('brief'))
            output = contained(project.root, folder/'output', what='map job output')
            job['output_path'] = output.relative_to(project.root).as_posix()
            job['status'] = 'staged' if output.is_dir() and any(output.iterdir()) else 'awaiting_agent'
            receipt = contained(project.root,folder/'accepted.json',what='map acceptance receipt')
            receipt_data = b''
            if receipt.exists():
                if receipt.stat().st_size > 4096: raise KosmoError('bad_map_job','Oversized acceptance receipt.')
                receipt_data = receipt.read_bytes()
                try: job['acceptance'] = json.loads(receipt_data)
                except (ValueError,UnicodeDecodeError): raise KosmoError('bad_map_job','Invalid acceptance receipt.')
                if not isinstance(job['acceptance'],dict): raise KosmoError('bad_map_job','Acceptance receipt must be an object.')
                job['status'] = 'accepted'
            job['request_sha256'] = sha256_bytes(data)
            job['receipt_sha256'] = sha256_bytes(receipt_data)
            jobs.append(job)
    return jobs


def map_build_state(workspace: Path, slug: str):
    project = open_project(workspace, slug); jobs = _jobs(project)
    revision = sha256_bytes(json.dumps([(j['id'],j['request_sha256'],j['receipt_sha256']) for j in jobs]).encode())
    return {'revision':revision, 'jobs':jobs, 'defaults':DEFAULTS,
            'limits':{'max_bundle_bytes':MAX_BYTES,'max_provinces':2000,'max_jobs':64},
            'note':'Codex or Claude builds artwork and geography in the job output folder. Review before importing a new map; existing maps are never overwritten.'}


def _handoff(b, output):
    return (f"Build original Dominions 6 map {b['map_id']} ({b['title']}). Theme: {b['theme'] or 'choose coherent natural geography'}.\n"
            f"Surface {b['width']}x{b['height']}; {b['land_provinces']} land and {b['sea_provinces']} sea provinces; "
            f"{b['cave_provinces']} cave provinces on plane 2; {b['players']} intended players; wraparound={b['wraparound']}.\n"
            "Output paths below are relative to the project root, not the tool repository. Read docs/MAP-DESIGN.md, docs/MAP-LAYERS.md and docs/AGENT-MAPS.md first. "
            "Create continuous coasts, rivers and mountain chains; natural province shapes, no grid. "
            "Keep a single ownership mask; derive #pb spans, borders and adjacency from it. "
            "Place exactly one pure-white centre per province; no other white pixels. "
            "Use original agent-created artwork and retain provenance outside output. "
            "All seasonal/terrain images must share dimensions, markers and ownership. "
            + ("Generate base, winter and all eight normal/winter terrain looks for each plane. " if b['all_layers'] else "Generate at least base artwork for each plane. ")
            + f"Write only flat game bundle files into {output}, with {b['map_id']}.map as the main file. "
            "Do not edit live maps. Use author_state map-builds, author_save action review, then preview/accept with the reviewed output revision. "
            "Report visual review and untested game behavior separately; no automatic game launch or publication.")


def _review(project, job, catalog):
    root = contained(project.root, _root(project)/job['id']/'output', what='map output')
    files = _files(root)
    # Validate the same immutable bytes that the review hash and eventual import cover.
    with tempfile.TemporaryDirectory(prefix='kosmo-map-review-') as temp:
        staging = Path(temp)
        for name,data in files.items(): (staging/name).write_bytes(data)
        state = _state(project, job['brief']['map_id'], staging, catalog)
    b = job['brief']; checks = []
    def check(name, passed, detail): checks.append({'check':name,'passed':bool(passed),'detail':detail})
    surface = state['planes'][0]
    check('surface_dimensions', (surface['width'],surface['height']) == (b['width'],b['height']), 'Surface dimensions match the design brief.')
    check('surface_count', len(surface['provinces']) == b['land_provinces']+b['sea_provinces'], 'Surface province count matches land plus sea request.')
    # Terrain bit 2 denotes sea; deep-sea provinces must also carry that flag.
    sea = sum(bool(int(p.get('terrain',0)) & 4) for p in surface['provinces'])
    check('sea_count', sea == b['sea_provinces'], f"Requested {b['sea_provinces']}; found {sea} sea provinces.")
    caves = sum(len(p['provinces']) for p in state['planes'][1:])
    check('cave_count', caves == b['cave_provinces'], f"Requested {b['cave_provinces']}; found {caves} lower-plane provinces.")
    check('plane_count', len(state['planes']) == (2 if b['cave_provinces'] else 1), 'One surface and optional cave plane.')
    check('eligible_starts', sum(not p['nostart'] for plane in state['planes'] for p in plane['provinces']) >= b['players'], 'Enough non-excluded provinces for the requested player count; fairness is not established.')
    if b['cave_provinces']:
        check('cave_terrain', all(p['terrain'] & 4096 for plane in state['planes'][1:] for p in plane['provinces']), 'Lower-plane provinces carry the cave terrain flag.')
    wrap = {s['command'] for s in surface['statements']} & {'wraparound','hwraparound','vwraparound'}
    check('wraparound', ('wraparound' in wrap) if b['wraparound'] else not wrap, 'Wrapping matches the brief; true requests full wrapping.')
    for p in state['planes']:
        check(f"plane{p['number']}_ownership", bool(p['image'].get('area_count')), 'Province ownership spans are required for agent-generated maps.')
        baseline = None; geometry_ok = True
        for variant in p['image'].get('variants',[]):
            if not variant['available']: continue
            try: w,h,rgba = decode_tga(files[variant['file']],max_pixels=16000000)
            except ValueError as exc:
                geometry_ok = False
                check(f"plane{p['number']}_image_decode",False,f"{variant['file']}: {exc}")
                continue
            markers = set(); position = rgba.find(b'\xff\xff\xff\xff')
            while position >= 0:
                if position % 4 == 0: markers.add(position//4)
                position = rgba.find(b'\xff\xff\xff\xff',position+1)
            geometry = (w,h,markers)
            if baseline is None: baseline = geometry
            else: geometry_ok &= geometry == baseline
        check(f"plane{p['number']}_variant_centres",geometry_ok and baseline is not None,'Every supplied TGA variant has the same dimensions and exact white province centres.')
        if b['all_layers']:
            variants = p['image'].get('variants',[])
            check(f"plane{p['number']}_layers", all(v['available'] for v in variants) and len(variants) == 18, 'Base, winter and all eight terrain looks in both seasons are required.')
    checks.append({'check':'visual_and_game_review','passed':None,'detail':'Natural boundaries, player start fairness, geography/art consistency and in-game behavior require separate review.'})
    revision = sha256_bytes((job['request_sha256']+_revision(files)).encode())
    return {'job_id':job['id'],'output_revision':revision,'validation':state['validation'],'compliance':checks,
            'files':[{'name':n,'bytes':len(data),'sha256':sha256_bytes(data)} for n,data in files.items()],
            'ready':not state['validation']['errors'] and all(c['passed'] is not False for c in checks),
            'planes':state['planes'],'in_game_tested':False},files


def save_map_build(workspace: Path, slug: str, body: dict, catalog=None):
    """Create immutable agent briefs, or review/import a hash-bound staged bundle."""
    if not isinstance(body,dict) or set(body)-{'action','preview','expected_revision','brief','job_id','expected_output_revision'}:
        raise KosmoError('bad_request','Use action, preview, expected_revision and the action fields.')
    if type(body.get('preview',True)) is not bool: raise KosmoError('bad_request','preview must be true or false.')
    project = open_project(workspace, slug); current = map_build_state(workspace,slug)
    if body.get('expected_revision') != current['revision']:
        raise KosmoError('revision_mismatch','Map jobs changed; reload before continuing.')
    action = body.get('action'); preview = body.get('preview',True)
    if action == 'create':
        b = _brief(body.get('brief')); steps = ['Create geography and ownership mask','Generate original artwork and seasonal/terrain variants','Package flat game files','Review static checks and brief compliance','Preview and accept as a new map']
        if preview: return {'preview':True,'brief':b,'steps':steps}
        with project_lock(project):
            if map_build_state(workspace,slug)['revision'] != current['revision']:
                raise KosmoError('revision_mismatch','Map jobs changed; reload.')
            if len(current['jobs']) >= 64: raise KosmoError('too_many_jobs','At most 64 map jobs per project.')
            folder = state_subdir(project,'map-jobs')/secrets.token_hex(6); folder.mkdir()
            output = folder/'output';output.mkdir()
            (folder/'work').mkdir()
            rel = output.relative_to(project.root).as_posix()
            job = {'id':folder.name,'brief':b,'steps':steps,'output_path':rel,'handoff':_handoff(b,rel),'prompt':_handoff(b,rel)}
            (folder/'request.json').write_text(json.dumps(job,indent=2),encoding='utf-8')
        return {'preview':False,'job':job,'state':map_build_state(workspace,slug)}
    job = next((j for j in current['jobs'] if j['id'] == body.get('job_id')),None)
    if not job: raise KosmoError('map_job_missing','Choose an existing map job.')
    if action not in ('review','accept'): raise KosmoError('bad_request','Action must be create, review or accept.')
    report, files = _review(project,job,catalog)
    if action == 'review': return report
    if body.get('expected_output_revision') != report['output_revision']:
        raise KosmoError('revision_mismatch','Agent output changed; review it again before acceptance.')
    if not report['ready']: raise KosmoError('validation_failed','Output fails static checks or the brief.',review=report)
    b = job['brief']
    imported = import_map(workspace,slug,{'id':b['map_id'],'main':b['map_id']+'.map','preview':preview,
                          'files':[{'name':n,'data':base64.b64encode(data).decode()} for n,data in files.items()]},catalog)
    if not preview:
        with project_lock(project):
            receipt = contained(project.root,_root(project)/job['id']/'accepted.json',what='map acceptance receipt')
            atomic_write_bytes(receipt,json.dumps({'map_id':b['map_id'],'output_revision':report['output_revision'],'map_revision':imported['revision'],'in_game_tested':False}).encode())
    return {**report,'preview':preview,'import':imported,'note':'Accepted files are a static map bundle, not proof of visuals, fairness or in-game behavior.'}
