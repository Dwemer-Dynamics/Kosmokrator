"""Full monster trait catalogue for the unit editor, built from traits_data.ROWS (Modding Manual 6.36, pp.13-36).

Every documented monster command is either an editable trait here (typed arguments, references, repeatable
lines) or excluded with a stated reason (block structure, identity, visuals, resets, equipment, or a command
already edited by a dedicated stats/leadership/magic/pretender field). coverage() is the audit table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import MANUAL_VERSION
from . import commands as cmdreg
from .traits_data import ROWS

INT_LIMIT = 2_147_483_647  # technical bound only: the game stores these as 32-bit integers
REF_TYPES = {"mon", "monneg", "spell", "site", "item"}
# Negative monster numbers documented in "Negative Monster Numbers" (p.29) and the #montag range (p.29).
NEG_TABLE = range(-26, -1)
MONTAG_RANGE = (1000, 100000)
EXCLUDE_REASONS = {
    "block": "Opens a monster block; not a trait.",
    "identity": "Name/description text; not a trait (kept verbatim).",
    "visual": "Sprite or look; not a trait (kept verbatim; edited with the artwork tools).",
    "reset": "Reset/copy command. Never written by the editor because it also removes or replaces other values.",
    "equipment": "Equipment, not a trait (kept verbatim; edited by the equipment loadout tool).",
    "field": "Edited by the dedicated stats, leadership, magic path or pretender field of the same editor.",
}
# Groups for the picker, in manual order.
GROUPS = ["Pretender God Commands", "Recruitment Rules", "Desertion", "Gold & Resource Cost", "Basic Attributes",
          "Bodytype", "Item Slots", "Creature Type & Status", "Movement", "Stealth & Assassination",
          "Age, Healing & Afflictions", "Damage Reduction", "Immortality", "Combat Auras", "Seasonal Powers",
          "Elemental & Scale Powers", "Combat Abilities", "Non-Combat Abilities", "Shape Changing",
          "Monster Summoning", "Mounts & Riders", "Mount commands", "Normal Leadership", "Magic Leadership",
          "Undead Leadership", "Morale Related Abilities", "Magic Paths", "Spell Range", "Magic Research",
          "Gem Production", "Other Magic Abilities", "New Abilities for Dominions 5"]
_ARG = re.compile(r"^(\w+):(\w+)(?:\[(-?\d+)?,(-?\d+)?\])?(?:\{([-\d,]+)\})?$")
MAGIC_RESETS = ("copystats", "clear", "clearspec", "clearmagic")
SPEC_RESETS = ("copystats", "clear", "clearspec")
_MAGIC_CMDS = {"custommagic", "magicboost"}
# Notes for documented prerequisites or dependencies; shown in the editor, never enforced beyond the manual.
NOTES = {
    "holycost": "Manual: can only be used on sacred units (#holy).",
    "homerealm": "Repeatable here because a god may have several home realms (catalog realm1-realm3); 0 clears.",
    "montagweight": "Manual: use after a #montag command. Default weight 1.",
    "custommagic": "Chance above 100 links levels (Magic Paths p.33). A priest-only mask (65536) crashes the mod.",
    "magicboost": "One line per path; 51-53 are the random-group path numbers.",
    "stormimmune": "Redundant with #stormpower.",
    "cleanshape": "Manual: must be on the monster's first shape.",
    "shapechange": "Manual: the other form must be given #shapechange back to this monster.",
    "triplegodmag": "Pretender (trinity god) command.",
    "onebattlespell": "Manual: commanders only; requires an original Dominions 6 spell, not a new mod spell.",
    "3castbattlespell": "Manual: commanders only; requires an original Dominions 6 spell and at least three of this type in battle.",
}


@dataclass(frozen=True)
class Arg:
    name: str
    type: str
    lo: int | None = None
    hi: int | None = None
    choices: tuple[int, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "type": self.type}
        if self.lo is not None or self.hi is not None:
            d["range"] = [self.lo, self.hi]
        if self.choices is not None:
            d["allowed"] = list(self.choices)
        return d


@dataclass(frozen=True)
class Trait:
    command: str
    section: str
    page: int
    args: tuple[Arg, ...]
    summary: str
    repeat: int | None  # None single value, 0 unlimited lines, n at most n lines
    family: str | None

    @property
    def bounds(self) -> tuple[str, ...]:
        return MAGIC_RESETS if self.command in _MAGIC_CMDS else SPEC_RESETS

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"command": self.command, "group": self.section, "page": self.page,
                             "args": [a.to_dict() for a in self.args], "summary": self.summary,
                             "repeatable": self.repeat is not None, "family": self.family}
        if self.repeat:
            d["max_lines"] = self.repeat
        if self.command in NOTES:
            d["note"] = NOTES[self.command]
        if any(a.lo is None and a.hi is None and a.choices is None and a.type == "int" for a in self.args):
            d["range_note"] = "The manual states no range for some arguments; only whole numbers are checked."
        return d


def _parse(dsl: str) -> tuple[Arg, ...]:
    out = []
    for tok in dsl.split():
        m = _ARG.match(tok)
        if not m:
            raise ValueError(f"bad trait arg {tok!r}")
        choices = None
        if m[5]:
            vals: list[int] = []
            for part in m[5].split(","):
                r = re.fullmatch(r"(-?\d+)-(-?\d+)", part)
                vals.extend(range(int(r[1]), int(r[2]) + 1) if r else [int(part)])
            choices = tuple(vals)
        out.append(Arg(m[1], m[2], int(m[3]) if m[3] else None, int(m[4]) if m[4] else None, choices))
    return tuple(out)


TRAITS: dict[str, Trait] = {}
EXCLUDED: dict[str, dict[str, Any]] = {}
for _c, _sec, _page, _dsl, _why, _sum, _rep, _fam in ROWS:
    if _dsl is None:
        EXCLUDED[_c] = {"section": _sec, "page": _page, "reason": _why, "summary": _sum, "family": _fam}
    else:
        TRAITS[_c] = Trait(_c, _sec, _page, _parse(_dsl), _sum, 0 if _c == "homerealm" else _rep, _fam)
assert set(TRAITS).isdisjoint(EXCLUDED)
assert {t.section for t in TRAITS.values()} <= set(GROUPS), {t.section for t in TRAITS.values()} - set(GROUPS)


def public_catalogue() -> dict[str, Any]:
    return {"manual": f"Dominions 6 Modding Manual {MANUAL_VERSION}", "groups": GROUPS,
            "traits": {k: t.to_dict() for k, t in TRAITS.items()}}


def coverage() -> dict[str, Any]:
    """Audit table: every documented monster command and whether/how the editor covers it."""
    rows = [{"command": f"#{k}", "status": "editable_trait", "section": t.section, "page": t.page,
             "args": [f"{a.name}:{a.type}" for a in t.args], "repeatable": t.repeat is not None, "family": t.family}
            for k, t in TRAITS.items()]
    rows += [{"command": f"#{k}", "status": "excluded" if x["reason"] != "field" else "editable_field",
              "section": x["section"], "page": x["page"], "reason": EXCLUDE_REASONS[x["reason"]],
              "family": x["family"]} for k, x in EXCLUDED.items()]
    return {"total": len(rows), "editable_traits": len(TRAITS),
            "editable_fields": sum(1 for x in EXCLUDED.values() if x["reason"] == "field"),
            "excluded": sum(1 for x in EXCLUDED.values() if x["reason"] != "field"), "rows": rows}


# ---- value checking -------------------------------------------------------------------------------------------

class TraitValueError(ValueError):
    pass


def _check_int(a: Arg, v: Any, label: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise TraitValueError(f"{label}: {a.name} must be a whole number.")
    if not -INT_LIMIT <= v <= INT_LIMIT:
        raise TraitValueError(f"{label}: {a.name} is outside the 32-bit integer range.")
    if a.choices is not None and v not in a.choices:
        raise TraitValueError(f"{label}: {a.name} must be one of {_fmt_choices(a.choices)} (manual).")
    if a.lo is not None and v < a.lo:
        raise TraitValueError(f"{label}: {a.name} must be at least {a.lo} (manual).")
    if a.hi is not None and v > a.hi:
        raise TraitValueError(f"{label}: {a.name} must be at most {a.hi} (manual).")
    return v


def _fmt_choices(ch: tuple[int, ...]) -> str:
    return ", ".join(str(c) for c in ch) if len(ch) <= 12 else f"{ch[0]}..{ch[-1]} (see manual)"


def check_value(t: Trait, value: Any, refs: "RefIndex") -> list[Any]:
    """Normalise a client value to an argument list and validate it against the manual and the references."""
    label = f"#{t.command}"
    if not t.args:
        if value is not True:
            raise TraitValueError(f"{label} takes no value: set it with true, or remove it.")
        return []
    vals = value if isinstance(value, list) else [value]
    if len(vals) != len(t.args):
        raise TraitValueError(f"{label} takes exactly {len(t.args)} value(s): "
                              + " ".join(f"<{a.name}>" for a in t.args) + ".")
    out: list[Any] = []
    for a, v in zip(t.args, vals):
        if a.type in REF_TYPES:
            if t.command in ("onebattlespell", "3castbattlespell"):
                # These commands can target modified base spells, but never newly defined mod spells (p.35).
                out.append(RefIndex({}, refs.catalog).check(a, v, label + " (original game spell only)"))
            else:
                out.append(refs.check(a, v, label))
        else:
            out.append(_check_int(a, v, label))
    if t.command == "custommagic" and out[0] == 65536:
        raise TraitValueError("#custommagic: a priest-only mask (65536) crashes the mod (manual p.33).")
    if t.command == "custommagic" and (out[0] <= 0 or out[0] & ~130944):
        raise TraitValueError("#custommagic: use only the documented path mask bits, 128 through 65536 (p.33).")
    return out


def render(t: Trait, args: list[Any]) -> str:
    parts = [f"#{t.command}"]
    for a, v in zip(t.args, args):
        parts.append(f'"{v}"' if isinstance(v, str) else str(v))
    return " ".join(parts)


def statement_args(t: Trait, st: Any) -> list[Any] | None:
    """Parse an authored statement into an argument list, or None if it does not match the documented form."""
    if len(st.args) != len(t.args):
        return None
    out: list[Any] = []
    for a, x in zip(t.args, st.args):
        if a.type in REF_TYPES:
            if x.kind == "int" or x.kind == "str":
                out.append(x.value)
            else:
                return None
        elif x.kind == "int":
            out.append(x.value)
        else:
            return None
    return out


class RefIndex:
    """Reference validity for monster/spell/site/item arguments: the project .dm first, then the catalog."""

    CAT = {"mon": "units", "monneg": "units", "spell": "spells", "site": "sites", "item": "items"}

    def __init__(self, local: dict[str, tuple[set[int], set[str]]], catalog: Any | None):
        self.local, self.catalog = local, catalog

    def _cat(self, kind: str) -> tuple[set[int], set[str]] | None:
        if self.catalog is None:
            return None
        try:
            cat = self.CAT[kind]
            return self.catalog.ids(cat), set(self.catalog.names(cat))
        except Exception:
            return None

    def check(self, a: Arg, v: Any, label: str) -> Any:
        kind = "mon" if a.type == "monneg" else a.type
        what = {"mon": "monster", "spell": "spell", "site": "site", "item": "item"}[kind]
        if isinstance(v, bool) or not isinstance(v, (int, str)):
            raise TraitValueError(f"{label}: give a {what} number or name.")
        if isinstance(v, str):
            v = v.strip()
            if not v or '"' in v or "\n" in v or "\r" in v or "#" in v or "--" in v or len(v) > 100:
                raise TraitValueError(f"{label}: {what} names cannot be empty or contain quotes, #, -- or newlines.")
            if re.fullmatch(r"-?\d+", v):
                v = int(v)
        if isinstance(v, int) and v < 0:
            if a.type != "monneg":
                raise TraitValueError(f"{label}: negative {what} numbers are not documented for this command.")
            if v in NEG_TABLE or MONTAG_RANGE[0] <= -v <= MONTAG_RANGE[1]:
                return v
            raise TraitValueError(f"{label}: negative numbers must be -2..-26 (Negative Monster Numbers, p.29) "
                                  "or a montag (-1000..-100000).")
        ids, names = self.local.get(kind, (set(), set()))
        hit = v in ids if isinstance(v, int) else v.lower() in names
        if not hit:
            cat = self._cat(kind)
            if cat is None:
                raise TraitValueError(f"{label}: {what} {v!r} is not defined in this project and no game catalog "
                                      "is loaded to check it.")
            hit = v in cat[0] if isinstance(v, int) else v.lower() in cat[1]
            if not hit:
                raise TraitValueError(f"{label}: {what} {v!r} is not in this project or the game catalog.")
        return v


def manual_spec(cmd: str) -> Any:
    return cmdreg.get("monster", cmd)
