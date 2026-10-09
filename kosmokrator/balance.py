"""Read-only, provenance-labelled nation comparison tables; never a power score."""

from copy import deepcopy

from .catalog import _read_table
from .errors import KosmoError

PATHS = 'FAWESDNGBH'


def _int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _table(catalog, filename, warnings):
    path = catalog.gamedata / filename
    if not path.is_file():
        warnings.append(f'Missing catalog table: {filename}; related comparisons are incomplete.')
        return []
    return _read_table(path)


def _unit(unit, recruitment=None):
    """Reuse resolved fields and estimates while keeping raw economy inputs separate."""
    resolved = unit.get('resolved', {})
    magic = resolved.get('magic', {})
    randoms = deepcopy(magic.get('random', []))
    for pick in randoms:
        paths = pick.get('paths', [])
        chance = _int(pick.get('chance'))
        # Only a single authored one-level pick has an unambiguous local probability.
        simple = (pick.get('source') == 'authored' and pick.get('levels') == 1
                  and pick.get('count') is None and chance is not None and 0 <= chance <= 100 and paths)
        pick['per_path_probability'] = {p: chance / 100 / len(paths) for p in paths} if simple else None
        pick['probability_note'] = ('Assumes equal path selection for this one independent pick; not a combined distribution.'
                                    if simple else 'Raw random metadata; linked/count/encoded probabilities not expanded.')
    equipped = resolved.get('equipped', {})
    return {'id': unit.get('id'), 'uid': unit.get('uid'), 'name': unit.get('name'),
            'role': unit.get('role'), 'origin': unit.get('source', 'project'),
            'recruitment': deepcopy(recruitment if recruitment is not None else unit.get('recruitment', [])),
            'stats': deepcopy(resolved.get('stats', {})),
            'raw_costs': deepcopy(resolved.get('costs', {})),
            'cost_estimates': deepcopy(equipped.get('costs', {})),
            'equipment': deepcopy(resolved.get('equipment', {})),
            'protection': deepcopy(equipped.get('protection', {})),
            'equipped': deepcopy(equipped),
            'fixed_paths': {p: f.get('value') for p, f in magic.get('paths', {}).items()},
            'random_magic': randoms,
            'specials': deepcopy(resolved.get('specials', {})),
            'creature_traits': deepcopy(resolved.get('creature_traits', {})),
            'source': deepcopy(unit.get('provenance') or unit.get('source'))}


def _magic_access(units):
    """Show access per recruit rather than combining incompatible mage random outcomes."""
    mages = [u for u in units if u['fixed_paths'] or u['random_magic']]
    return {'recruitable_mages': [{'id': u['id'], 'name': u['name'], 'recruitment': u['recruitment'],
                                  'fixed_paths': u['fixed_paths'], 'random_magic': u['random_magic']} for u in mages],
            'fixed_maxima': {p: max((u['fixed_paths'].get(p) or 0 for u in mages), default=0) for p in PATHS},
            'note': 'Maxima are per-path and may belong to different recruits. Random access, capital availability and recruitment time remain separate.'}


def _summons(model, catalog, warnings):
    """Resolve simple copied/authored ritual summons in command order, with conservative counts."""
    from .content import SUMMON_EFFECTS
    effects = {r['record_id']: r for r in _table(catalog, 'effects_spells.csv', warnings)} if catalog else {}
    units = {u['id']: u for u in model.get('monsters', [])}
    out = []
    for spell in model.get('other_definitions', []):
        if spell.get('kind') != 'spell':
            continue
        state, restrictions, blocked = {}, [], []
        for command in spell.get('authored', []):
            cmd = command['command'].lstrip('#')
            args = command.get('args', [])
            numbers = [_int(v) for v in args]
            value = numbers[0] if numbers else None
            if cmd in ('clear', 'copyspell', 'selectspell'):
                state, restrictions, blocked = {}, [], []
                row = catalog.row('spells', value) if catalog and cmd != 'clear' and value is not None else None
                if row:
                    effect = effects.get(row.get('effect_record_id'), {})
                    code = _int(effect.get('effect_number'))
                    if code is not None and code < 10000 and effect.get('ritual') == '1':
                        code += 10000
                    state = {k: _int(row.get(k)) for k in ('school', 'researchlevel', 'path1', 'path2', 'pathlevel1', 'pathlevel2', 'fatiguecost')}
                    state.update(effect=code, damage=_int(effect.get('raw_argument')),
                                 nreff=_int(effect.get('area_base')),
                                 scaling=_int(effect.get('area_per_level')) or 0,
                                 template_id=value, next_spell=_int(row.get('next_spell')))
                elif cmd != 'clear':
                    blocked.append('Spell template is unresolved.')
            elif cmd in ('path', 'pathlevel') and len(numbers) == 2 and numbers[0] in (0, 1):
                state[f'{cmd}{numbers[0] + 1}'] = numbers[1]
            elif cmd == 'restricted':
                restrictions.append(value if value is not None else (args[0].strip('"') if args else None))
            elif cmd in ('effect', 'damage', 'school', 'researchlevel', 'fatiguecost', 'nreff', 'nextspell'):
                state['next_spell' if cmd == 'nextspell' else cmd] = value
                if cmd == 'nreff':
                    state['scaling'] = 0
            elif cmd in ('nextspelleffect', 'effectcopy', 'copyspells'):
                blocked.append(f'Unsupported spell composition: #{cmd}.')
        code = state.get('effect')
        if code not in SUMMON_EFFECTS:
            continue
        target = state.get('damage')
        target_unit = units.get(target) or (catalog.row('units', target) if catalog and target is not None else None)
        count, fatigue = state.get('nreff'), state.get('fatiguecost')
        ritual = code >= 10000
        # Only plain troop/commander rituals have a straightforward per-unit denominator here.
        simple = (code in (10001, 10021) and target_unit is not None and count is not None
                  and 0 < count < 500 and not state.get('scaling') and not state.get('next_spell')
                  and fatigue is not None and fatigue >= 0 and fatigue % 100 == 0 and not blocked)
        requirements = []
        for slot in (1, 2):
            path, level = state.get(f'path{slot}'), state.get(f'pathlevel{slot}')
            if path is not None and 0 <= path < len(PATHS) and level is not None and level > 0:
                requirements.append({'path': PATHS[path], 'level': level})
        gems = fatigue // 100 if ritual and fatigue is not None and fatigue >= 0 and fatigue % 100 == 0 else None
        out.append({'uid': spell.get('uid'), 'name': spell.get('name'), 'source': deepcopy(spell.get('source')),
                    'restrictions': restrictions, 'effect': code, 'effect_label': SUMMON_EFFECTS[code],
                    'school': state.get('school'), 'researchlevel': state.get('researchlevel'),
                    'requirements': requirements, 'target': {'id': target, 'name': target_unit.get('name') if target_unit else None,
                                                             'status': 'known' if target_unit else 'unresolved'},
                    'raw_count': count, 'count': count if simple else None,
                    'raw_fatiguecost': fatigue, 'gem_cost': gems, 'gem_path': requirements[0]['path'] if requirements else None,
                    'gems_per_unit': gems / count if simple else None,
                    'status': 'static_simple_ritual' if simple else 'unresolved_per_unit',
                    'notes': blocked + ['Gem cost uses fatigue / 100 for rituals. Counts with scaling, encoded nreff, chained effects or unknown targets have no per-unit estimate. Discounts, extra gems, boosters and caster availability are not simulated.']})
    return out


def balance_report(model, catalog, reference_nations=None):
    """Build same-era nation comparisons from an existing browser model without writing files."""
    from .browse import catalog_unit_view
    from .dmparse import parse
    from .equipped import equipped_sheet

    if reference_nations is not None and (not isinstance(reference_nations, (list, tuple))
                                         or any(type(n) is not int for n in reference_nations)):
        raise KosmoError('bad_value', 'reference_nations must be a list of catalog nation IDs.')
    if reference_nations is not None and len(reference_nations) > 12:
        raise KosmoError('bad_value', 'Choose at most 12 reference nations.')
    warnings, projects, references = [], [], []
    nations = model.get('nations', [])
    eras = {n.get('era') for n in nations if n.get('era') in (1, 2, 3)}
    summons = _summons(model, catalog, warnings)
    for nation in nations:
        nid, uid = nation.get('id'), nation.get('uid')
        rows = []
        for unit in model.get('monsters', []):
            recruitment = [r for r in unit.get('recruitment', []) if r.get('nation') == uid
                           or any(x.get('nation') == uid and x.get('site') == r.get('site') for x in unit.get('nations', []) if r.get('site'))]
            if recruitment:
                rows.append(_unit(unit, recruitment))
        projects.append({'id': nid, 'uid': uid, 'name': nation.get('name'), 'era': nation.get('era'),
                         'units': rows, 'magic_access': _magic_access(rows),
                         'gem_sites': deepcopy(nation.get('gem_sites', [])),
                         'summons': [s for s in summons if not s['restrictions'] or nid in s['restrictions'] or nation.get('name') in s['restrictions']],
                         'note': 'Resolved project recruitment only; inherited vanilla nation rosters are not reconstructed.'})
    available = []
    if catalog:
        available = [{'id': _int(n.get('id')), 'name': n.get('name'), 'epithet': n.get('epithet'), 'era': _int(n.get('era'))}
                     for n in catalog.table('nations') if _int(n.get('era')) in eras]
        available.sort(key=lambda n: (n['era'], n['id']))
        requested = list(dict.fromkeys(reference_nations)) if reference_nations is not None else [n['id'] for era in sorted(eras) for n in [a for a in available if a['era'] == era][:3]]
        by_id = {n['id']: n for n in available}
        if any(n not in by_id for n in requested):
            raise KosmoError('bad_value', 'Reference nations must exist in the catalog and match a project nation era.', available_ids=list(by_id))
        roster_tables = [(f'{where}_{kind}_types_by_nation.csv', role, where)
                         for where in ('fort', 'nonfort', 'coast') for kind, role in (('troop', 'troop'), ('leader', 'commander'))]
        memberships = {name: _table(catalog, name, warnings) for name, _, _ in roster_tables}
        attrs = _table(catalog, 'attributes_by_nation.csv', warnings)
        sites = {int(s['id']): s for s in catalog.table('sites') if _int(s.get('id')) is not None}
        cache = {}
        for nid in requested:
            membership = {}
            for filename, role, where in roster_tables:
                for row in memberships[filename]:
                    mid = _int(row.get('monster_number'))
                    if _int(row.get('nation_number')) == nid and mid is not None:
                        membership.setdefault(mid, []).append({'nation_id': nid, 'role': role, 'where': where, 'table': filename})
            for attr in attrs:
                if _int(attr.get('nation_number')) != nid or _int(attr.get('attribute')) != 52:
                    continue
                sid = _int(attr.get('raw_value'))
                site = sites.get(sid, {})
                for prefix, role in (('hmon', 'troop'), ('hcom', 'commander')):
                    for index in range(1, 6):
                        mid = _int(site.get(f'{prefix}{index}'))
                        if mid:
                            membership.setdefault(mid, []).append({'nation_id': nid, 'role': role, 'where': 'capital start site',
                                                                  'site_id': sid, 'site': site.get('name'), 'table': 'MagicSites.csv'})
            rows = []
            for mid, recruitment in sorted(membership.items()):
                if catalog.row('units', mid) is None:
                    warnings.append(f'Catalog nation {nid} recruits missing unit {mid}.')
                    continue
                if mid not in cache:
                    unit = catalog_unit_view(catalog, model.get('project', {}).get('slug', 'comparison'), mid)
                    unit['resolved']['equipped'] = equipped_sheet(unit, parse(f'#selectmonster {mid}\n#end\n').blocks[0], catalog)
                    cache[mid] = _unit(unit)
                unit = deepcopy(cache[mid])
                unit['recruitment'] = recruitment
                unit['role'] = 'commander' if any(r['role'] == 'commander' for r in recruitment) else 'troop'
                rows.append(unit)
            references.append({**by_id[nid], 'units': rows, 'magic_access': _magic_access(rows),
                               'note': 'Catalog fort/nonfort/coast tables plus capital start-site hmon/hcom. Conditional nation mechanics and other special recruitment are not reconstructed.'})
    else:
        requested = list(reference_nations or [])
        warnings.append('No catalog: vanilla reference nations, copied spell templates and vanilla equipment cannot be verified.')
    return {'schema': 'kosmokrator.balance/1', 'provenance': {'project': deepcopy(model.get('provenance', {})),
                                                            'catalog': deepcopy(catalog.meta) if catalog else None},
            'project_nations': projects, 'reference_nations': references,
            'selection': {'requested': requested, 'mode': 'explicit' if reference_nations is not None else 'first_three_per_era',
                          'available_nations': available, 'note': 'Default selection is a reproducible convenience, not an endorsement of benchmark relevance.'},
            'warnings': list(dict.fromkeys(warnings)),
            'limitations': ['Static comparison tables, not a power score or game-balance verdict.',
                            'Raw gold/autocalculation encodings are not final prices. Equipment estimates omit conditional mechanics and mounted totals.',
                            'Magic maxima do not establish crosspath combinations, mass access, boosters, research efficiency or affordability.',
                            'Summon ratios are limited to simple known-target rituals. No combat, upkeep, expansion or game execution is simulated.',
                            'Catalog data and resolver inheritance can differ from the installed game; review source provenance and unresolved fields.']}
