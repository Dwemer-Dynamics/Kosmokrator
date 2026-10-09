"""Curated, manual-grounded subset of Dominions 6 mod commands.

Every entry cites the section/page of the official Dominions 6 Modding Manual
(Illwinter, ver 6.36). This is deliberately a subset: commands outside it are kept
verbatim and reported as "unverified", never deleted or rewritten.

Argument DSL: "name:type" with optional "[min,max]" range, "{a,b,c-d}" allowed
values and a trailing "?" for optional arguments. Types:
int, float, str, mon (monster name|nbr), monid (monster nbr only), site (site name|nbr), sitename (name only),
weapon, armor, item (name|nbr), nation (nbr), img (image path), file (other path),
pathmask (sum of #custommagic path masks), locmask (sum of site locmask values).
Only ranges stated in the manual are encoded; nothing else is range-checked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import MANUAL_VERSION
from .docindex import MONSTER_DOCUMENTED, NATION_DOCUMENTED, SITE_DOCUMENTED

CORE_CONTEXTS = ("top", "monster", "site", "nation", "weapon", "armor", "spell")
DOCUMENTED = {"monster": MONSTER_DOCUMENTED, "site": SITE_DOCUMENTED, "nation": NATION_DOCUMENTED,
              "weapon": frozenset(), "armor": frozenset(), "spell": frozenset(),
              "top": frozenset({"modname", "description", "icon", "version", "domversion", "indepflag"})}

_ARG_RE = re.compile(r"^(?P<name>\w+):(?P<type>\w+)(?:\[(?P<lo>-?\d+(?:\.\d+)?),(?P<hi>-?\d+(?:\.\d+)?)?\])?"
                     r"(?:\{(?P<choices>[-\d,]+)\})?(?P<opt>\?)?$")


@dataclass(frozen=True)
class ArgSpec:
    name: str
    type: str
    lo: float | None = None
    hi: float | None = None
    choices: tuple[int, ...] | None = None
    optional: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "type": self.type, "optional": self.optional}
        if self.lo is not None:
            d["range"] = [self.lo, self.hi]
        if self.choices is not None:
            d["allowed"] = list(self.choices)
        return d


@dataclass(frozen=True)
class CommandSpec:
    name: str
    context: str
    args: tuple[ArgSpec, ...]
    section: str
    page: int
    summary: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": f"#{self.name}", "context": self.context,
            "args": [a.to_dict() for a in self.args], "summary": self.summary,
            "notes": self.notes or None,
            "source": {"document": "Dominions 6 Modding Manual", "version": MANUAL_VERSION,
                       "section": self.section, "page": self.page},
        }


def _parse_args(dsl: str) -> tuple[ArgSpec, ...]:
    out = []
    for tok in dsl.split():
        m = _ARG_RE.match(tok)
        if not m:
            raise ValueError(f"bad arg DSL {tok!r}")
        choices = None
        if m["choices"]:
            vals: list[int] = []
            for part in m["choices"].split(","):
                if re.fullmatch(r"-?\d+--?\d+", part):
                    a, b = re.match(r"(-?\d+)-(-?\d+)", part).groups()  # type: ignore[union-attr]
                    vals.extend(range(int(a), int(b) + 1))
                else:
                    vals.append(int(part))
            choices = tuple(vals)
        out.append(ArgSpec(m["name"], m["type"], float(m["lo"]) if m["lo"] else None,
                           float(m["hi"]) if m["hi"] else None, choices, bool(m["opt"])))
    return tuple(out)


REGISTRY: dict[tuple[str, str], CommandSpec] = {}


def _reg(context: str, section: str, page: int, rows: list[tuple[str, str, str] | tuple[str, str, str, str]]) -> None:
    for row in rows:
        name, dsl, summary = row[0], row[1], row[2]
        notes = row[3] if len(row) > 3 else ""
        REGISTRY[(context, name)] = CommandSpec(name, context, _parse_args(dsl), section, page, summary, notes)


# ---- Mod info (p.5) -------------------------------------------------------------------
_reg("top", "Mod Info", 5, [
    ("modname", "name:str", "Short mod name shown in mod preferences."),
    ("description", "text:str", "Description of what the mod does."),
    ("icon", "image:img", "Banner image, 128x32 or 256x64 TGA."),
    ("version", "version:float", "Mod version, e.g. 1.00."),
    ("domversion", "version:float", "Minimum Dominions version; leave out if unsure."),
])
_reg("top", "Nation Modding / Name, Era & General", 42, [
    ("indepflag", "image:img", "Replace the independents flag (128x128); only outside nation blocks."),
])

# ---- Monster modding -------------------------------------------------------------------
_reg("monster", "Monster Modding, Basic / Basic Commands", 13, [
    ("selectmonster", "monster:mon", "Select an existing monster; end with #end."),
    ("newmonster", "id:int[5000,19999]?", "Create a new monster; end with #end.",
     "Section text says 5000-8999; Modding Number Limits (p.64) says 0-19999 with 5000+ for modding. "
     "Without a number the game picks the first free id and references must then be by name."),
    ("end", "", "Close the current block."),
    ("name", "name:str", "Monster name; must be the first command for a new monster.",
     "#copystats overwrites previous commands, so put #name after #copystats."),
    ("fixedname", "name:str", "Fixed commander name."),
    ("descr", "text:str", "Description text (max 1999 characters, p.64)."),
])
_reg("monster", "Monster Modding, Basic / Visuals", 13, [
    ("spr1", "image:img", "Normal sprite image."),
    ("spr2", "image:img", "Attack sprite image."),
    ("drawsize", "percent:int", "Draw sprite larger/smaller by percent."),
])
_reg("monster", "Monster Modding, Basic / Clearing & Copying", 13, [
    ("clear", "", "Remove weapons, armor, stats, magic and special abilities."),
    ("clearweapons", "", "Remove all weapons; required before assigning replacement weapons."),
    ("cleararmor", "", "Remove all armor; required before assigning replacement armor."),
    ("clearmagic", "", "Remove all magic skills (including inherited random picks)."),
    ("clearspec", "", "Remove all special abilities (Holy, resistances, Awe...)."),
    ("copystats", "monster:monid", "Copy weapons, armor, stats, magic and abilities from a monster number.",
     "Overwrites all previous commands: use first after #newmonster."),
    ("copyspr", "monster:monid", "Copy the sprite of an existing monster number."),
])
_reg("monster", "Monster Modding, Basic / Pretender God Commands", 14, [
    ("pathcost", "points:int", "Design point cost per new path; makes the monster a selectable god."),
    ("startdom", "dominion:int", "Default dominion strength as a god; makes it selectable as god."),
    ("homerealm", "realm:int[0,10]", "Home realm of the god (0 clears)."),
])
_reg("monster", "Monster Modding, Basic / Recruitment Rules", 14, [
    ("slowrec", "", "Commander takes double commander points to recruit."),
    ("noslowrec", "", "Remove slowrec."),
    ("reclimit", "units:int", "Limit recruits per turn per province (0 = none)."),
    ("reqlab", "", "Recruiting requires a lab."),
    ("noreqlab", "", "Never requires a lab."),
    ("reqtemple", "", "Recruiting requires a temple."),
    ("noreqtemple", "", "Never requires a temple."),
    ("ainorec", "", "AI never recruits this monster."),
    ("aisinglerec", "", "AI recruits only one per batch."),
])
_reg("monster", "Monster Modding, Basic / Desertion", 15, [
    ("nowish", "", "Cannot be wished for."),
])
_reg("monster", "Monster Modding, Basic / Gold & Resource Cost", 15, [
    ("gcost", "gold:int", "Gold cost; 10000+base means autocalc."),
    ("rcost", "resources:int", "Resource cost (weapon/armor costs are added)."),
    ("rpcost", "points:int", "Recruitment point cost; base*1000 autocalculates."),
    ("ressize", "size:int[1,10]", "Size used for resource cost."),
])
_reg("monster", "Monster Modding, Basic / Basic Attributes", 16, [
    ("hp", "hp:int", "Hit points."),
    ("str", "value:int", "Strength."),
    ("att", "value:int", "Attack skill."),
    ("def", "value:int", "Defence skill."),
    ("prec", "value:int", "Precision."),
    ("prot", "value:int", "Natural protection."),
    ("size", "size:int[1,10]", "Size 1 (bug) to 10 (dragon)."),
    ("mr", "value:int", "Magic resistance."),
    ("mor", "value:int", "Morale (50 = mindless)."),
    ("enc", "value:int", "Encumbrance."),
    ("mapmove", "speed:int", "World map move (human 14)."),
    ("ap", "points:int", "Combat action points."),
    ("eyes", "eyes:int", "Number of eyes."),
])
_reg("monster", "Monster Modding, Basic / Weapons & Armor", 17, [
    ("weapon", "weapon:weapon", "Add a weapon (use #clearweapons first to replace)."),
    ("armor", "armor:armor", "Add an armor; up to three (use #cleararmor first to replace)."),
])
_reg("monster", "Monster Modding, Basic / Bodytype", 18, [
    ("humanoid", "", "Default humanoid body type."),
])
_reg("monster", "Monster Modding, Basic / Item Slots", 18, [
    ("startitem", "item:item", "Commander starts with this item."),
    ("itemslots", "mask:int", "Item slot bitmask."),
])
_reg("monster", "Monster Modding, Special Abilities / Creature Type & Status", 18, [
    ("female", "", "Female."),
    ("coldblood", "", "Cold blooded."),
    ("holy", "", "Sacred; can be blessed. Required for units with Holy magic."),
    ("holycost", "points:int[1,]", "Holy points to recruit (sacred units only)."),
    ("animal", "", "Animal."),
    ("unique", "", "Only one may exist."),
    ("undead", "", "Undead."),
    ("demon", "", "Demon."),
    ("magicbeing", "", "Magic being."),
    ("stonebeing", "", "Stone being."),
    ("inanimate", "", "Inanimate."),
])
_reg("monster", "Monster Modding, Special Abilities / Movement", 19, [
    ("float", "", "Floats; crosses rivers."),
    ("flying", "", "Flies."),
    ("amphibian", "", "Travels under and over water."),
    ("aquatic", "", "Lives only under water."),
    ("forestsurvival", "", "Forest survival."),
    ("mountainsurvival", "", "Mountain survival."),
    ("swampsurvival", "", "Swamp survival."),
    ("wastesurvival", "", "Waste survival."),
])
_reg("monster", "Monster Modding, Special Abilities / Stealth & Assassination", 20, [
    ("stealthy", "value:int", "Can sneak; scouts usually 10, spies 20 (stealth value bonus)."),
    ("spy", "", "Spy."),
    ("assassin", "", "Assassin."),
])
_reg("monster", "Monster Modding, Special Abilities / Age, Healing & Afflictions", 21, [
    ("startage", "age:int", "Start age (0 clears, -1 sets zero)."),
    ("maxage", "age:int", "Maximum age."),
    ("older", "age:int", "Start older/younger than calculated."),
    ("heal", "", "Recuperation (monster form takes no argument)."),
])
_reg("monster", "Monster Modding, Special Abilities / Damage Reduction", 22, [
    ("coldres", "prot:int", "Cold resistance."),
    ("fireres", "prot:int", "Fire resistance."),
    ("poisonres", "prot:int", "Poison resistance."),
    ("shockres", "prot:int", "Shock resistance."),
    ("reinvigoration", "points:int", "Fatigue recovery per combat turn."),
])
_reg("monster", "Monster Modding, Special Abilities / Combat Auras", 23, [
    ("heat", "value:int", "Heat aura (standard 3)."),
    ("cold", "value:int", "Chill aura (standard 3)."),
    ("awe", "bonus:int[1,]", "Awe (standard 1)."),
    ("fireshield", "damage:int", "Fire shield damage (standard 8)."),
])
_reg("monster", "Monster Modding, Leadership & Morale / Normal Leadership", 31, [
    ("noleader", "", "Cannot lead units (scouts, assassins)."),
    ("poorleader", "", "Leadership 10."),
    ("okleader", "", "Leadership 50 (default)."),
    ("goodleader", "", "Leadership 100."),
    ("expertleader", "", "Leadership 150."),
    ("superiorleader", "", "Leadership 200."),
    ("command", "value:int", "Increase leadership by value."),
])
_reg("monster", "Monster Modding, Leadership & Morale / Morale Related Abilities", 32, [
    ("inspirational", "bonus:int", "Morale bonus for led units."),
    ("formationfighter", "xsize:int", "Extra size points per square (human 2)."),
    ("standard", "bonus:int", "Squad morale bonus (normal 1)."),
])
_reg("monster", "Monster Modding, Magic / Magic Paths", 33, [
    ("magicskill", "path:int{0-9,50-53} level:int[1,10]",
     "Set a magic path level (0 F,1 A,2 W,3 E,4 S,5 D,6 N,7 G,8 B,9 Priest; 50-53 random groups).",
     "Units with Holy (path 9) magic must also have #holy."),
    ("custommagic", "mask:pathmask chance:int[1,]",
     "Random magic pick: mask is a sum of path masks (128 F ... 65536 Priest); chance >100 links levels.",
     "A priest-only mask (65536) crashes the mod according to the manual."),
    ("magicboost", "path:int{0-9,51-53} boost:int[-5,5]", "Boost or reduce magic paths."),
])
_reg("monster", "Monster Modding, Magic / Magic Research", 34, [
    ("fixedresearch", "value:int", "Research without magic skills."),
    ("researchbonus", "value:int", "Research bonus (sage 8)."),
])
_reg("monster", "Monster Modding, Magic / Gem Production", 34, [
    ("gemprod", "type:int[0,8] number:int", "Monthly gem production (0 fire ... 8 blood slaves)."),
])
_reg("monster", "Monster Modding, Magic / Other Magic Abilities", 35, [
    ("forgebonus", "percent:int", "Cheaper item forging (percent)."),
    ("fixforgebonus", "gems:int", "Gem reduction when forging."),
    ("mastersmith", "value:int", "Paths count higher when forging."),
    ("bonusspells", "spells:int[0,4]", "Innate spellcaster (max 4)."),
])

# ---- Magic site modding (pp.37-41) ----------------------------------------------------------
_reg("site", "Magic Site Modding / Basic Site Modding", 37, [
    ("selectsite", "site:site", "Select an existing site; end with #end."),
    ("newsite", "id:int[1700,3999]?", "Create a new site; end with #end.",
     "Without a number references must be by name."),
    ("end", "", "Close the current block."),
    ("name", "name:str", "Site name."),
    ("clear", "", "Clear site attributes."),
    ("copysite", "site:site", "Copy all stats from a site, including its name."),
    ("path", "path:int[0,9]", "Magic path associated with the site."),
    ("look", "sprite:int[-1,9]", "Site look (-1 default)."),
    ("loc", "locmask:locmask", "Terrain placement mask (735 land, 16384 unique)."),
    ("gems", "path:int[0,8] amount:int", "Gem income of a path."),
    ("gold", "amount:int", "Gold income."),
    ("res", "amount:int", "Resource bonus."),
    ("level", "level:int[0,4]", "Magic level needed to find it; 0 is auto-discovered."),
    ("rarity", "rarity:int{0,1,2,5,11,12,13}", "0 common, 1 uncommon, 2 rare, 5 never random, 11-13 thrones."),
    ("decunrest", "value:int", "Decrease unrest."),
    ("supply", "value:int", "Supply bonus."),
])
_reg("site", "Magic Site Modding / Monsters", 38, [
    ("homemon", "monster:mon", "Recruitable unit for the original owner only."),
    ("homecom", "monster:mon", "Recruitable commander for the original owner only."),
    ("mon", "monster:mon", "Recruitable unit for the owner."),
    ("com", "monster:mon", "Recruitable commander for the owner."),
    ("nat", "nation:nation", "Nation for following #natmon/#natcom."),
    ("natmon", "monster:mon", "Unit recruitable by the #nat nation."),
    ("natcom", "monster:mon", "Commander recruitable by the #nat nation."),
    ("summon", "monster:mon", "Mage of the site's path may summon this monster."),
    ("defcom", "monster:mon", "Extra province defence commander."),
    ("defunit", "monster:mon", "Extra province defence unit."),
    ("defmult", "multiplier:int", "Units per 10 defence points (default 10)."),
])
_reg("site", "Magic Site Modding / Scale Effects", 39, [
    ("incscale", "scale:int[0,5]", "Increase a scale (0 turmoil ... 5 drain)."),
    ("decscale", "scale:int[0,5]", "Decrease a scale."),
])
_reg("site", "Magic Site Modding / Special Effects", 40, [
    ("heal", "chance:int[0,100]", "Healing check chance (site form takes an argument)."),
    ("xp", "value:int", "Experience per turn for entering commanders."),
    ("lab", "", "Constructs a lab when discovered."),
    ("temple", "", "Constructs a temple when discovered."),
])

# ---- Nation modding (pp.41-50) ---------------------------------------------------------------
_reg("nation", "Nation Modding / Name, Era & General", 41, [
    ("selectnation", "nation:int[5,499]", "Select nation; 150+ creates a new nation without overwriting.",
     "Numbers 0-4 cannot be used."),
    ("newnation", "", "New nation using the first free number (text says 120+, limits table says 150+).",
     "Automatic numbering is unverified; prefer a fixed #selectnation in the unused 150+ range."),
    ("end", "", "Close the current block."),
    ("name", "name:str", "Nation name; must be the first command when changing it."),
    ("clearnation", "", "Clear special settings (not recruit lists)."),
    ("epithet", "epithet:str", "Nation epithet."),
    ("era", "era:int[0,3]", "1 early, 2 middle, 3 late, 0 disabled; set right after #name/#epithet."),
    ("descr", "text:str", "Full description."),
    ("summary", "text:str", "Summary of benefits."),
    ("brief", "text:str", "Very brief description."),
    ("color", "r:float[0,1] g:float[0,1] b:float[0,1]", "Primary colour (0.0-1.0 each)."),
    ("secondarycolor", "r:float[0,1] g:float[0,1] b:float[0,1]", "Secondary colour."),
    ("flag", "image:img", "Flag image, 128x128, flag at bottom."),
])
_reg("nation", "Nation Modding / Sites, Terrain, Temperature", 43, [
    ("clearsites", "", "Clear start sites."),
    ("startsite", "site:sitename", "Add a start site by name (max 4; numbers are not possible)."),
    ("futuresite", "site:sitename", "Show a future site in the overview."),
    ("islandsite", "site:sitename", "Start site only if starting on an island."),
    ("likesterr", "mask:int", "Preferred start terrain mask."),
    ("hatesterr", "mask:int", "Avoided start terrain mask."),
    ("idealcold", "cold:int[-3,3]", "Preferred temperature (-3 hot ... 3 cold)."),
    ("defchaos", "value:int[-5,5]", "Default turmoil scale."),
    ("defsloth", "value:int[-5,5]", "Default sloth scale."),
    ("defdeath", "value:int[-5,5]", "Default death scale."),
    ("defmisfortune", "value:int[-5,5]", "Default misfortune scale."),
    ("defdrain", "value:int[-5,5]", "Default drain scale."),
    ("moreorder", "value:int[-5,5]", "Shift allowed order scale range."),
    ("moreprod", "value:int[-5,5]", "Shift allowed productivity range."),
    ("moreheat", "value:int[-5,5]", "Shift allowed heat range."),
    ("moregrowth", "value:int[-5,5]", "Shift allowed growth range."),
    ("moreluck", "value:int[-5,5]", "Shift allowed luck range."),
    ("moremagic", "value:int[-5,5]", "Shift allowed magic range."),
])
_reg("nation", "Nation Modding / AI Hints", 44, [
    (f"ai{p}nation", "", f"AI hint: {p} magic is used a lot.")
    for p in ("fire", "air", "water", "earth", "astral", "death", "nature", "glamour", "blood")
])
_reg("nation", "Nation Modding / Unit Lists & Recruitment", 44, [
    ("clearrec", "", "Clear recruitable units and commanders."),
    ("startcom", "monster:mon", "Starting commander; also removes old start troops (use first)."),
    ("startscout", "monster:mon", "Extra starting commander/scout."),
    ("startunittype1", "monster:mon", "First starting squad type."),
    ("startunitnbrs1", "count:int", "First squad size (default 20)."),
    ("startunittype2", "monster:mon", "Second starting squad type."),
    ("startunitnbrs2", "count:int", "Second squad size (default 20)."),
    ("addrecunit", "monster:mon", "Add a recruitable unit."),
    ("addreccom", "monster:mon", "Add a recruitable commander."),
    ("addforeignunit", "monster:mon", "Unit recruitable only where there is no fort."),
    ("addforeigncom", "monster:mon", "Commander recruitable only where there is no fort."),
    ("uwrec", "monster:mon", "Unit recruitable in underwater forts."),
    ("uwcom", "monster:mon", "Commander recruitable in underwater forts."),
])
_reg("nation", "Nation Modding / Province Defense", 45, [
    ("defcom1", "monster:mon", "PD commander; also clears old defence settings (use first)."),
    ("defcom2", "monster:mon", "Extra PD commander at defence 20+."),
    ("defunit1", "monster:mon", "Standard PD unit."),
    ("defunit1b", "monster:mon", "Second standard PD unit."),
    ("defunit1c", "monster:mon", "Third standard PD unit."),
    ("defunit1d", "monster:mon", "Fourth standard PD unit."),
    ("defunit2", "monster:mon", "Bonus PD unit at defence 20+."),
    ("defunit2b", "monster:mon", "Second bonus PD unit."),
    ("defmult1", "multiplier:int", "Units per 10 defence (default 20)."),
    ("defmult1b", "multiplier:int", "Second unit multiplier (default 10)."),
    ("defmult1c", "multiplier:int", "Third unit multiplier."),
    ("defmult1d", "multiplier:int", "Fourth unit multiplier."),
    ("defmult2", "multiplier:int", "Bonus unit multiplier."),
    ("defmult2b", "multiplier:int", "Second bonus unit multiplier."),
    ("wallcom", "monster:mon", "Commander of wall defenders."),
    ("wallunit", "monster:mon", "Wall defender unit (follow with #wallmult)."),
    ("wallmult", "multiplier:int", "Multiplier for previous #wallunit (10 standard)."),
    ("guardcom", "monster:mon", "Commander of gate guards."),
    ("guardunit", "monster:mon", "Gate guard unit (follow with #guardmult)."),
    ("guardmult", "multiplier:int", "Multiplier for previous #guardunit."),
])
_reg("nation", "Nation Modding / Gods", 47, [
    ("cleargods", "", "Clear pretender list (not homerealm gods)."),
    ("addgod", "monster:mon", "Add a pretender (needs #startdom and #pathcost)."),
    ("delgod", "monster:mon", "Remove a homerealm pretender."),
    ("homerealm", "realm:int[1,10]", "Include pretenders of this realm."),
    ("cheapgod20", "monster:mon", "Pretender 20 points cheaper."),
    ("cheapgod40", "monster:mon", "Pretender 40 points cheaper."),
])
_reg("nation", "Nation Modding / Forts & Buildings", 48, [
    ("fortera", "era:int[0,4]", "Fort types the nation can build."),
    ("labcost", "gold:int", "Lab cost (default 600)."),
    ("templecost", "gold:int", "Temple cost (default 600)."),
    ("templepic", "pic:int", "Temple look."),
    ("templegems", "type:int[0,8]", "Temples produce gems of this type."),
    ("homefort", "fort:int[1,30]", "Starting fort type."),
    ("buildfort", "fort:int[1,30]", "Fort type to build."),
])
_reg("nation", "Nation Modding / Dominion", 49, [
    ("nationinc", "percent:int", "Extra gold income percent."),
    ("castleprod", "percent:int", "Fort resource bonus."),
])

_reg("weapon", "Weapon Modding", 6, [
    ("newweapon", "id:int[0,3999]", "Create a weapon; supported allocator uses 1000+."),
    ("selectweapon", "weapon:weapon", "Select a weapon by name or number."),
    ("copyweapon", "weapon:weapon", "Copy an existing weapon before setting overrides."),
    ("name", "name:str", "Set weapon name."), ("clear", "", "Clear weapon attributes."),
    ("dmg", "damage:int", "Base damage."), ("att", "attack:int", "Attack modifier."),
    ("def", "defence:int", "Defence modifier."), ("len", "length:int[0,5]", "Weapon length."),
    ("nratt", "attacks:int", "Attacks per round; negatives indicate slow attacks."),
    ("twohanded", "", "Uses two hands."),
])
_reg("weapon", "Weapon Modding", 7, [
    ("range", "range:int", "Missile range."), ("ammo", "ammo:int", "Ammunition."),
    ("rcost", "resources:int", "Resource cost."),
])
_reg("armor", "Armor Modding", 12, [
    ("newarmor", "id:int[0,1999]", "Create armour; supported allocator uses 400+."),
    ("selectarmor", "armor:armor", "Select existing armour."),
    ("copyarmor", "armor:armor", "Copy armour before setting overrides."),
    ("name", "name:str", "Armour name."), ("clear", "", "Clear armour."),
    ("type", "type:int{4,5,6,9}", "Shield, body, helmet or barding."),
    ("prot", "protection:int", "Protection."), ("def", "defence:int", "Defence modifier."),
    ("enc", "encumbrance:int", "Encumbrance."), ("rcost", "resources:int", "Resource cost."),
    ("magicarmor", "", "Magic armour."), ("ironarmor", "", "Iron armour."),
    ("woodenarmor", "", "Wooden armour."),
])
_reg("spell", "Spell Modding", 50, [
    ("newspell", "", "Create an anonymous new spell; refer to named spells by name."),
    ("selectspell", "spell:spell", "Select existing spell."),
    ("copyspell", "spell:spell", "Copy existing spell."),
    ("name", "name:str", "Set name before description."), ("descr", "description:str", "Description."),
    ("details", "details:str", "Yellow detail text."), ("clear", "", "Clear spell."),
    ("school", "school:int[-1,7]", "Research school."),
    ("researchlevel", "level:int[0,9]", "Research level."),
    ("path", "requirement:int[0,1] path:int[-1,9]", "Required magic path."),
    ("pathlevel", "requirement:int[0,1] level:int", "Required path level."),
    ("fatiguecost", "fatigue:int", "Fatigue or ritual gem cost (100 per gem)."),
])
_reg("spell", "Spell Effects", 51, [
    ("damage", "value:int", "Meaning depends on the effect; may be a summoned monster."),
    ("nreff", "effects:int", "Number of effects; special values scale with caster level."),
])
_reg("spell", "Spell Restrictions", 53, [
    ("restricted", "nation:nationref", "Restrict to a nation, or -1 for last manipulated nation."),
])
_reg("nation", "Nation Heroes", 45, [(f"hero{i}", "monster:monid", "Hero monster number; -1 removes it.")
                                     for i in range(1, 11)] +
     [(f"multihero{i}", "monster:monid", "Repeatable hero monster number.") for i in range(1, 8)])

ASSET_TYPES = {"img", "file"}
REF_TYPES = {"mon", "monid", "site", "sitename", "weapon", "armor", "item", "nation", "nationref", "spell"}


def documented_contexts(name: str) -> list[str]:
    return [ctx for ctx, names in DOCUMENTED.items() if name in names]


def get(context: str, name: str) -> CommandSpec | None:
    return REGISTRY.get((context, name))


def lookup(command: str, context: str | None = None) -> dict[str, Any]:
    """Return curated specs (or documented/unverified status) for one command name."""
    name = command.strip().lstrip("#").lower()
    if not re.fullmatch(r"[a-z0-9_]+", name or ""):
        from .errors import KosmoError
        raise KosmoError("bad_command", f"Not a command name: {command!r}")
    specs = [s for (ctx, n), s in REGISTRY.items() if n == name and (context is None or ctx == context)]
    documented = documented_contexts(name)
    if specs:
        status = "curated"
    elif documented:
        status = "documented_uncurated"
    else:
        status = "unverified"
    return {
        "command": f"#{name}", "status": status,
        "specs": [s.to_dict() for s in specs],
        "documented_in_contexts": documented,
        "note": {
            "curated": "Arguments, context and ranges are checked by validate_mod.",
            "documented_uncurated": "Name appears in the manual for these contexts; arguments are not checked.",
            "unverified": "Not in the curated subset or the indexed manual sections; it will be kept verbatim "
                          "and reported as unverified (it may still be valid, e.g. weapon/spell/item/event commands).",
        }[status],
    }


def list_commands(context: str | None = None) -> list[dict[str, Any]]:
    return [
        {"command": f"#{s.name}", "context": s.context, "summary": s.summary,
         "section": s.section, "page": s.page}
        for (ctx, _), s in sorted(REGISTRY.items()) if context is None or ctx == context
    ]
