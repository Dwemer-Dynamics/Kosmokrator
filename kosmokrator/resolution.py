"""Ordered dependency layers and conservative explicit-reference graph."""
import hashlib
import json
from pathlib import Path
from .catalog import Catalog, CATEGORIES
from .dmparse import parse, block_id, block_name
from .manual_commands import commands
from .project import dependency_texts

CATEGORIES_BY_CONTEXT = {'monster': 'units', 'nation': 'nations', 'site': 'sites', 'spell': 'spells',
                         'weapon': 'weapons', 'armor': 'armors', 'item': 'items'}
REF_CONTEXT = {'mon': 'monster', 'monid': 'monster', 'monneg': 'monster', 'site': 'site',
               'sitename': 'site', 'weapon': 'weapon', 'armor': 'armor', 'item': 'item',
               'spell': 'spell', 'nation': 'nation', 'nationref': 'nation'}


def layers(workspace, project, text):
    return dependency_texts(workspace, project.meta.get('dependencies')) + [('project', text)]


def relationships(workspace, project, text, catalog):
    """Resolve authored references against effective identities, retaining all contributing blocks."""
    order = layers(workspace, project, text)
    objects, edges, overlaps, warnings = [], [], [], []
    by_id, by_name, histories, blocks = {}, {}, {}, []
    ambiguous_names = set()
    for origin, source in order:
        for b in parse(source).blocks:
            ctx, ident, name = b.context, block_id(b), block_name(b)
            category = CATEGORIES_BY_CONTEXT.get(ctx)
            row = catalog.row(category, ident) if category and catalog and isinstance(ident, int) else None
            if isinstance(ident, str):
                selected = by_name.get((ctx, ident.lower()))
                if selected:
                    ident, name = selected['id'], name or selected['name']
            if not isinstance(ident, int) and ident is not None and category and catalog:
                hits = [r for r in catalog.table(category) if r.get('name', '').lower() == str(ident).lower()]
                if len(hits) == 1:
                    row, ident = hits[0], int(hits[0]['id'])
            key = f'{ctx}:line:{b.opener.line}' if origin == 'project' else f'{origin}:{ctx}:line:{b.opener.line}'
            previous = by_id.get((ctx, ident)) if ident is not None else by_name.get((ctx, (name or '').lower()))
            kind = 'new' if b.new else 'dependency_override' if previous and previous['origin'] != 'project' else 'extension' if previous else 'vanilla_override' if row else 'extension'
            obj = {'key': key, 'context': ctx, 'id': ident, 'name': name or (row or {}).get('name') or str(block_id(b) or ctx),
                   'line': b.opener.line, 'origin': origin, 'opener': b.opener.command,
                   'identity': {'kind': kind, 'origin': previous['origin'] if previous else 'catalog' if row else origin,
                                'note': 'Commands apply in activation order; selectors intentionally extend existing definitions.'}}
            objects.append(obj)
            blocks.append((b, obj))
            identity = (ctx, ident if ident is not None else (name or key).lower())
            history = histories.setdefault(identity, [])
            if history or b.new and row:
                overlap = {'context': ctx, 'id': ident, 'name': obj['name'],
                           'severity': 'error' if b.new else 'info',
                           'origins': [x['origin'] for x in history] + (['catalog'] if row and not history else []) + [origin],
                           'reason': 'New definition reuses an existing identity.' if b.new else 'Intentional selector override; later commands win where modelled.'}
                collision = b.new and isinstance(ident, int)
                conflicted = collision or any(x.get('classification') == 'hard_id_collision' and
                                             x['context'] == ctx and x['id'] == ident for x in overlaps)
                contributors = [{k: x[k] for k in ('key', 'origin', 'line', 'opener')} for x in history + [obj]]
                if row and not history:
                    contributors.insert(0, {'key': f'catalog:{ctx}:{ident}', 'origin': 'catalog', 'line': None, 'opener': None})
                # Report authored statement order, never assume a later block replaces the whole object.
                effects = {}
                for block, contributor in blocks:
                    if contributor['key'] not in {x['key'] for x in contributors}:
                        continue
                    for statement in block.statements:
                        effects.setdefault(statement.command, []).append({
                            'origin': contributor['origin'], 'line': statement.line,
                            'arguments': [a.value for a in statement.args]})
                overlap.update(
                    classification='hard_id_collision' if collision else 'ambiguous_named_definition' if b.new else 'intentional_selector_override',
                    contributors=contributors, last_contributor=contributors[-1],
                    winner=None if b.new or conflicted else contributors[-1], blocked_by_collision=conflicted,
                    effects=[{'command': command, 'contributors': statements,
                              'last_authored': statements[-1],
                              'interpretation': 'Authored order only; copies, clears, repeated/list commands and unsupported semantics can change the effective result.'}
                             for command, statements in effects.items()],
                    actions=[{'action': action, 'reason': reason, 'automatic': False} for action, reason in (
                        [('remap_ids', 'Reserve a free ID with all dependencies declared, then review every typed reference before a guarded edit. Reordering does not repair a duplicate new ID.'),
                         ('declare_dependency', 'Declare every intended input before allocating replacement IDs and validating again.')]
                        if b.new else
                        [('review_override', 'A selector explicitly addresses an existing identity; confirm the shared target and commands are intended.'),
                         ('change_order', 'Preview a dependency reorder to inspect which authored commands come last. This project remains last; actual game activation must match the declared order.')])])
                if not b.new:
                    overlap['reason'] = 'Selector explicitly targets a shared identity; intent and effective gameplay must be reviewed.'
                if conflicted and not collision:
                    overlap['actions'].append({'action': 'remap_ids', 'automatic': False,
                                               'reason': 'Earlier duplicate new definitions make this target unsafe; repair their ID collision before relying on selector order.'})
                overlaps.append(overlap)
            history.append(obj)
            if ident is not None:
                by_id[(ctx, ident)] = obj
            if obj['name']:
                old_named = by_name.get((ctx, obj['name'].lower()))
                if old_named and old_named['id'] != obj['id']:
                    ambiguous_names.add((ctx, obj['name'].lower()))
                    warnings.append(f"Ambiguous {ctx} name: {obj['name']}")
                by_name[(ctx, obj['name'].lower())] = obj
    incoming, outgoing, unresolved, order_uncertain = {}, {}, [], []
    block_positions = {obj['key']: i for i, (_, obj) in enumerate(blocks)}
    effective = overlay_catalog(catalog, order)
    spell_effects = {}
    if catalog:
        from .catalog import _read_table
        path = catalog.gamedata / 'effects_spells.csv'
        if path.is_file():
            spell_effects = {r['record_id']: r for r in _read_table(path)}
    event_codes = {}
    for b, obj in blocks:
        if b.context == 'event':
            for s in b.statements:
                if s.command in ('code', 'code2') and s.args:
                    event_codes.setdefault(s.args[0].value, []).append(obj)
    for b, obj in blocks:
        schemas = commands(b.context)
        summon_effect = False
        if b.context == 'spell' and effective:
            row = effective.row('spells', obj['id']) if isinstance(obj['id'], int) else next(
                (r for r in effective.table('spells') if r.get('name', '').lower() == obj['name'].lower()), None)
            raw = spell_effects.get((row or {}).get('effect_record_id'), {})
            code = (row or {}).get('effect') or raw.get('effect_number')
            if str(code).isdigit():
                code = int(code)
                if raw.get('ritual') == '1' and code < 10000 and not (row or {}).get('effect'):
                    code += 10000
                from .content import SUMMON_EFFECTS
                summon_effect = code in SUMMON_EFFECTS
        for s in b.statements:
            if b.context == 'event' and s.command.startswith('req_code') and s.args:
                targets = event_codes.get(s.args[0].value, [])
                for target in targets:
                    if target['key'] != obj['key']:
                        incoming.setdefault(target['key'], []).append({**obj, 'command': s.command, 'line': s.line, 'relation': 'event code requirement'})
                        outgoing.setdefault(obj['key'], []).append({**target, 'command': s.command, 'relation': 'event code requirement'})
                        edges.append({'from': obj['key'], 'to': target['key'], 'command': s.command, 'line': s.line,
                                      'argument': s.args[0].value, 'status': 'resolved', 'relation': 'event code requirement'})
            schema = schemas.get(s.command, {})
            specs = schema.get('args', [])
            for position, arg in enumerate(s.args):
                typ = specs[position]['type'] if position < len(specs) else None
                ctx = REF_CONTEXT.get(typ)
                if b.context == 'spell' and s.command == 'damage' and position == 0 and summon_effect:
                    ctx = 'monster'
                if not ctx:
                    continue
                target = by_id.get((ctx, arg.value)) if isinstance(arg.value, int) else by_name.get((ctx, str(arg.value).lower()))
                if not isinstance(arg.value, int) and (ctx, str(arg.value).lower()) in ambiguous_names:
                    target = None
                row = None
                category = CATEGORIES_BY_CONTEXT.get(ctx)
                if not target and catalog and category and (ctx, str(arg.value).lower()) not in ambiguous_names:
                    if isinstance(arg.value, int):
                        row = catalog.row(category, arg.value)
                    else:
                        hits = [r for r in catalog.table(category) if r.get('name', '').lower() == str(arg.value).lower()]
                        row = hits[0] if len(hits) == 1 else None
                    if row:
                        target = {'key': f'catalog:{ctx}:{row["id"]}', 'context': ctx, 'id': int(row['id']),
                                  'name': row.get('name'), 'origin': 'catalog', 'line': None}
                edge = {'from': obj['key'], 'to': target['key'] if target else None, 'command': s.command,
                        'line': s.line, 'argument': arg.value, 'status': 'resolved' if target else 'unresolved',
                        'relation': 'authored reference', 'target_context': ctx}
                if target and s.command in ('copystats', 'copyspr', 'copyweapon', 'copyarmor', 'copyspell', 'copyitem', 'copysite'):
                    prior = any(t['context'] == ctx and
                                (t['id'] == target['id'] if target['id'] is not None else t['name'] == target['name']) and
                                block_positions[t['key']] <= block_positions[obj['key']] for t in objects)
                    catalog_target = catalog and category and isinstance(target['id'], int) and catalog.row(category, target['id'])
                    if not prior and not catalog_target:
                        edge['order_status'] = 'target_only_in_later_block'
                        order_uncertain.append({'classification': 'order_sensitive_reference',
                                                'source': {k: obj[k] for k in ('key', 'origin', 'line')},
                                                'command': s.command, 'line': s.line, 'argument': arg.value,
                                                'actions': [{'action': 'change_order', 'automatic': False,
                                                             'reason': 'The copy target is only authored later in the declared order. Place its provider before this consumer and recheck; final graph resolution does not prove copy-time availability.'}]})
                edges.append(edge)
                if target:
                    outgoing.setdefault(obj['key'], []).append({**target, 'command': s.command, 'relation': edge['relation']})
                    # Every block contributing to an identity is protected from unsafe deletion.
                    targets = [x for x in objects if x['context'] == target['context'] and
                               (x['id'] == target['id'] if target['id'] is not None else x['name'] == target['name'])]
                    for t in targets or [target]:
                        if t['key'] != obj['key']:
                            incoming.setdefault(t['key'], []).append({**obj, 'command': s.command, 'line': s.line, 'relation': edge['relation']})
                else:
                    unresolved.append(edge)
    if effective:
        for b, obj in blocks:
            if b.context != 'monster':
                continue
            row = effective.row('units', obj['id']) if isinstance(obj['id'], int) else next(
                (r for r in effective.table('units') if r.get('name', '').lower() == obj['name'].lower()), None)
            if not row:
                continue
            for prefix, ctx, count in [('wpn', 'weapon', 7), ('armor', 'armor', 4)]:
                for i in range(1, count + 1):
                    value = row.get(prefix + str(i))
                    if not value or not str(value).isdigit() or int(value) == 0:
                        continue
                    target = by_id.get((ctx, int(value)))
                    if not target or any(e['from'] == obj['key'] and e['to'] == target['key'] for e in edges):
                        continue
                    relation = 'effective inherited equipment reference'
                    edge = {'from': obj['key'], 'to': target['key'], 'command': prefix,
                            'line': b.opener.line, 'argument': int(value), 'status': 'resolved', 'relation': relation}
                    edges.append(edge)
                    outgoing.setdefault(obj['key'], []).append({**target, 'command': prefix, 'relation': relation})
                    for t in objects:
                        if t['context'] == ctx and t['id'] == target['id'] and t['key'] != obj['key']:
                            incoming.setdefault(t['key'], []).append({**obj, 'command': prefix, 'relation': relation})
    return {'objects': objects, 'edges': edges, 'unresolved': unresolved, 'incoming': incoming, 'outgoing': outgoing}, {
        'activation_order': [{'label': origin, 'sha256': hashlib.sha256(
            (project.dm_path if origin == 'project' else workspace / origin).read_bytes()).hexdigest()} for origin, source in order],
        'overlaps': overlaps, 'warnings': warnings,
        'summary': {'hard_id_collisions': sum(x['classification'] == 'hard_id_collision' for x in overlaps),
                    'intentional_overrides': sum(x['classification'] == 'intentional_selector_override' for x in overlaps),
                    'ambiguous_named_definitions': sum(x['classification'] == 'ambiguous_named_definition' for x in overlaps),
                    'unresolved_references': len(unresolved), 'order_sensitive_references': len(order_uncertain)},
        'guidance': [{'classification': 'ambiguous_reference' if
                         (edge.get('target_context'), str(edge['argument']).lower()) in ambiguous_names
                     else 'missing_or_unverified_reference',
                     'source': next(({k: obj[k] for k in ('key', 'origin', 'line')} for obj in objects if obj['key'] == edge['from']), {}),
                     'command': edge['command'], 'line': edge['line'], 'argument': edge['argument'],
                     'actions': [{'action': 'declare_dependency', 'automatic': False,
                                  'reason': 'If another mod provides this identity, declare its workspace file and recheck. Unlisted enabled mods are unknown.'},
                                 {'action': 'verify_reference', 'automatic': False,
                                  'reason': 'Check the typed target, catalog version and duplicate names. Prefer a verified numeric ID where supported; do not invent or automatically remap targets.'}]}
                    for edge in unresolved] + order_uncertain,
        'order_basis': 'Declared dependency files in metadata order, then project; not detected game activation order.',
        'limitations': ['Activation order is the explicit dependency list followed by this project; unlisted enabled mods are unknown.',
                        'winner identifies the last authored selector contributor, not a whole-object replacement or proof of effective gameplay. Hard ID collisions have no safe winner.',
                        'References use documented typed arguments. Computed spell effects, event chains and runtime-generated references may remain unresolved.']}


def overlay_catalog(catalog, sources):
    """Copy supported catalog fields through dependency blocks without mutating the supplied catalog."""
    if catalog is None and not sources:
        return None
    digest = hashlib.sha256(json.dumps(sources, ensure_ascii=False).encode()).hexdigest()
    tables = {category: [dict(r) for r in catalog.table(category)] if catalog else [] for category in CATEGORIES}
    result = Catalog(catalog.root if catalog else Path('.'),
                     (catalog.gamedata if catalog else Path('.')) / ('overlay-' + digest),
                     dict(catalog.meta) if catalog else {'source': 'authored project/dependency fields only'}, tables)
    for origin, source in sources:
        for b in parse(source).blocks:
            category = CATEGORIES_BY_CONTEXT.get(b.context)
            if not category:
                continue
            ident = block_id(b)
            rows = tables[category]
            existing = next((r for r in rows if str(r.get('id')) == str(ident) or
                             isinstance(ident, str) and r.get('name', '').lower() == ident.lower()), None)
            if ident is None:
                # Auto-numbered definitions can be referenced by name; synthetic IDs stay internal.
                ident = -1000000 - len(rows)
            row = dict(existing) if existing and not b.new else {'id': str(ident)}
            if existing:
                rows.remove(existing)
            for s in b.statements:
                values = [a.value for a in s.args]
                if s.command == 'copystats' and values and b.context == 'monster':
                    donor = next((r for r in rows if str(r.get('id')) == str(values[0]) or r.get('name', '').lower() == str(values[0]).lower()), None)
                    if donor:
                        retained = {k: row[k] for k in ('id', 'name', 'descr', 'spr1', 'spr2') if k in row}
                        row = {**donor, **retained}
                elif s.command in ('clearweapons', 'cleararmor'):
                    prefix, count = ('wpn', 7) if s.command == 'clearweapons' else ('armor', 4)
                    for i in range(1, count + 1):
                        row[prefix + str(i)] = '0'
                elif s.command in ('weapon', 'armor') and b.context == 'monster' and values:
                    prefix, count = ('wpn', 7) if s.command == 'weapon' else ('armor', 4)
                    i = next((i for i in range(1, count + 1) if row.get(prefix + str(i), '0') in ('', '0')), None)
                    if i:
                        row[prefix + str(i)] = str(values[0])
                elif s.command in ('copyweapon', 'copyarmor', 'copyspell', 'copyitem', 'copysite') and values:
                    donor = next((r for r in rows if str(r.get('id')) == str(values[0]) or r.get('name', '').lower() == str(values[0]).lower()), None)
                    if donor:
                        row.update(donor)
                elif s.command == 'clear':
                    row = {'id': str(ident)}
                elif s.command == 'clearmagic':
                    for path in ('F', 'A', 'W', 'E', 'S', 'D', 'N', 'G', 'B', 'H'):
                        row[path] = '0'
                elif s.command == 'clearspec' and b.context == 'monster':
                    from .traits import TRAITS
                    for name, trait in TRAITS.items():
                        if 'clearspec' in trait.bounds:
                            row[name] = '0'
                    for name in ('startdom', 'pathcost'):
                        row[name] = '0'
                elif s.command == 'magicskill' and len(values) == 2 and isinstance(values[0], int) and 0 <= values[0] <= 9:
                    row[('F', 'A', 'W', 'E', 'S', 'D', 'N', 'G', 'B', 'H')[values[0]]] = str(values[1])
                elif len(values) == 1:
                    key = {'gcost': 'basecost'}.get(s.command, s.command)
                    row[key] = str(values[0])
                elif not values and s.command not in ('clear', 'clearspec', 'clearmagic'):
                    row[s.command] = '1'
            row['id'] = str(existing['id'] if existing and not b.new else ident)
            row['_origin'] = origin
            rows.append(row)
    return result
