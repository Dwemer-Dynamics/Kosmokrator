"""Conservative equipment estimates; conditional game calculations remain explicit."""
import csv
import math


def _number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def equipped_sheet(unit, block, catalog):
    """Combine supported equipment and base fields without turning missing data into zero."""
    resolved = unit['resolved']
    stats, eq = resolved['stats'], resolved['equipment']
    base = lambda key: stats.get(key, {}).get('value')
    field = lambda value, note, status='estimated': {'value': value, 'status': status if value is not None else 'unresolved', 'note': note}
    equipment = {}
    missing = []
    for group, category in [('weapons', 'weapons'), ('armor', 'armors')]:
        rows = []
        for item in eq[group]:
            row = catalog.row(category, item.get('id')) if catalog and item.get('id') is not None else None
            if row:
                rows.append(dict(row))
            else:
                missing.append(item.get('name') or str(item.get('ref')))
        equipment[group] = rows
    protections = {}
    effects = {}
    if catalog:
        data_root = catalog.root / 'gamedata' if (catalog.root / 'gamedata').is_dir() else catalog.root
        path = data_root / 'protections_by_armor.csv'
        if path.is_file():
            with path.open(encoding='utf-8', newline='') as stream:
                for row in csv.DictReader(stream, delimiter='\t'):
                    protections.setdefault(row['armor_number'], {})[_number(row['zone_number'])] = _number(row['protection'])
        path = data_root / 'effects_weapons.csv'
        if path.is_file():
            with path.open(encoding='utf-8', newline='') as stream:
                effects = {row['record_id']: row for row in csv.DictReader(stream, delimiter='\t')}
    p_body, p_head, p_general = 0, 0, 0
    armor_def, armor_enc, weapon_def = 0, 0, 0
    cost_equipment = 0
    known = not missing and all(eq.get(k + '_status', {}).get('status') == 'resolved' for k in ('weapons', 'armor'))
    resource_known = known
    for row in equipment['armor']:
        zones = protections.get(row['id'], {})
        typ, prot = _number(row.get('type')), _number(row.get('prot'))
        if typ in (5, 6, 8) and prot is None and not zones:
            known = False
        if typ == 6:
            p_head = prot if prot is not None else zones.get(1, 0)
        elif typ == 8:
            p_general = prot if prot is not None else zones.get(6, 0)
        elif typ == 5:
            p_body = prot if prot is not None else math.floor((zones.get(2, 0) + (zones.get(3, 0) + zones.get(4, 0)) / 2) / 2)
        armor_def += _number(row.get('def')) or 0
        armor_enc += _number(row.get('enc')) or 0
        if _number(row.get('rcost')) is None:
            resource_known = False
        else:
            cost_equipment += int(row['rcost'])
    attacks, ranged = [], []
    melee = []
    for row in equipment['weapons']:
        effect = effects.get(row.get('effect_record_id'), {})
        is_ranged = bool(_number(row.get('range')) or _number(effect.get('range_base')) or _number(effect.get('range_strength_divisor')))
        if is_ranged:
            ranged.append({'name': row.get('name'), **field(base('prec') + int(row['att']) if base('prec') is not None and _number(row.get('att')) is not None else None,
                                                          'Base precision plus ranged weapon modifier; range and combat modifiers omitted.')})
        else:
            bonus = _number(row.get('bonus')) or ((_number(effect.get('modifiers_mask')) or 0) & 134217728)
            melee.append((row, bool(bonus)))
    armed = [row for row, bonus in melee if not bonus]
    penalty = sum(_number(row.get('len')) or 0 for row in armed) if len(armed) > 1 else 0
    ambidextrous = resolved.get('specials', {}).get('ambidextrous', {}).get('value') or 0
    for trait in resolved.get('authored_traits', []):
        if trait.get('command') == '#ambidextrous' and trait.get('status') == 'authored' and trait.get('args'):
            value = trait['args'][0]
            ambidextrous = value.get('value', 0) if isinstance(value, dict) else value
    penalty = max(0, penalty - (_number(ambidextrous) or 0))
    for row, _ in melee:
        attacks.append({'name': row.get('name'), **field(base('att') + int(row['att']) - penalty if base('att') is not None and _number(row.get('att')) is not None else None,
                                                      'Base attack plus weapon modifier and static dual-wield penalty; conditional effects omitted.')})
    for row in equipment['weapons']:
        if any(row is entry for entry, _ in melee):
            weapon_def += _number(row.get('def')) or 0
        if _number(row.get('rcost')) is None:
            resource_known = False
        else:
            cost_equipment += int(row['rcost'])
    natural = base('prot')
    body = natural + p_body + p_general - natural * (p_body + p_general) / 40 if natural is not None and known else None
    head = natural + p_head + p_general - natural * (p_head + p_general) / 40 if natural is not None and known else None
    round_game = lambda value: math.floor(value + .5) if value is not None else None
    shapes, mounts = [], []
    donor = (unit.get('donor') or {}).get('catalog_row') or {}
    shape_commands = ('shapechange', 'firstshape', 'secondshape', 'secondtmpshape', 'landshape', 'watershape', 'forestshape', 'plainshape', 'xpshape', 'prophetshape', 'homeshape')
    refs = {key: _number(donor.get(key)) for key in (*shape_commands, 'mountmnr') if donor.get(key)}
    for s in block.statements:
        if s.command in (*shape_commands, 'mountmnr') and s.args:
            refs[s.command] = s.args[0].value
    for command, ident in refs.items():
        if not ident:
            continue
        row = catalog.row('units', ident) if catalog and isinstance(ident, int) else None
        entry = {'id': ident, 'name': (row or {}).get('name'), 'origin': (row or {}).get('_origin', 'catalog') if row else None,
                 'status': 'resolved' if row else 'unresolved', 'command': command,
                 'note': 'Referenced form; combat transformation and mount contributions are not simulated.'}
        (mounts if command == 'mountmnr' else shapes).append(entry)
    costs = resolved['costs']
    gold = costs['gold'].get('authored_value')
    resource = costs['resources'].get('authored_value')
    rp = costs['recruitment_points'].get('authored_value')
    size = base('size')
    for s in block.statements:
        if s.command == 'ressize' and s.args:
            size = s.args[0].value
    size = _number(donor.get('ressize')) or size
    fixed_gold = gold if gold is not None and gold < 5000 and not mounts else None
    resource_total = math.floor(resource + cost_equipment * size / 3) if resource_known and resource is not None and resource < 60000 and size is not None and not mounts else None
    if fixed_gold == 0:
        resource_total = 0
    return {'protection': {'body': round_game(body), 'head': round_game(head),
                           'average': round_game((4 * body + head) / 5) if body is not None and head is not None else None,
                           'status': 'estimated' if body is not None else 'unresolved',
                           'note': 'Static natural-plus-armour estimate; shield protection is separate. Conditional effects omitted.'},
            'attack': attacks, 'ranged_precision': ranged,
            'defence': field(base('def') + armor_def + weapon_def if known and base('def') is not None else None,
                             'Base plus equipment modifiers, including shield parry; conditional penalties omitted.'),
            'encumbrance': field(0 if base('enc') == 0 else base('enc') + armor_enc if known and base('enc') is not None and not mounts else None,
                                 'Melee encumbrance; casting and mounted calculations may differ.'),
            'costs': {'gold': field(fixed_gold, 'Fixed gold component; autocalculated and mounted totals unresolved.', 'resolved'),
                      'resources': field(resource_total, 'Base plus equipment scaled by resource size; mount and special economy modifiers omitted.'),
                      'recruitment_points': field(rp if rp is not None and rp < 1000 and not mounts else None,
                                                  'Explicit recruitment points; encoded autocalculation remains unresolved.', 'resolved')},
            'mounts': mounts, 'shapes': shapes,
            'notes': ['Static estimates may differ from in-game values when unmodelled abilities apply.'] +
                     [f"{entry['name']}: ranged precision {entry['value'] if entry['value'] is not None else '?'} (estimate)." for entry in ranged] +
                     (['Missing equipment: ' + ', '.join(missing)] if missing else [])}
