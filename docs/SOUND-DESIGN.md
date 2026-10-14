# Default sound choices

Use suitable built-in Dominions 6 sounds by default. Original artwork does not
require original audio. Generate or import custom audio only when the user's
brief calls for it or no appropriate built-in sample exists.

## Authoring rules

- Audit every created unit's final weapons, including natural attacks, alternate
  forms and summoned creatures. Sounds belong to the weapon or spell definition;
  do not invent a monster sound command.
- Keep appropriate sounds on existing vanilla weapons. Do not modify a shared
  vanilla weapon just to change one unit's audio.
- For a custom weapon, inspect its copied template, if any. Keep a suitable sound
  or set weapon `#sound` explicitly after copying. Match the actual attack, not
  merely the unit's name or visual theme.
- For a custom spell, inspect inherited casting and impact sounds. Keep suitable
  choices or set spell `#sound` and `#strikesound` after copying. Changing sprites
  does not establish that the audio is correct.
- Equipment replacement requires another sound audit. A copied monster's weapon
  list is not evidence for the final loadout after resets or replacements.

## Documented starting choices

These are sample IDs, not weapon IDs:

| Attack | Built-in sample |
| --- | --- |
| Sword | 8 |
| Club or axe | 10 |
| Spear or pike | 12 |
| Bow | 14 |
| Sling | 15 |
| Claw, bite or kick | 38 |

Check other effects against the official table. Do not guess a sample number.
Existing weapons already carry their sound choices; avoid redundant overrides.

## Review and delivery

Record each custom weapon/spell's sound choice as retained vanilla, inherited
and checked, or explicitly assigned. Flag unknown template values rather than
claiming verification. Resolve definitions from the saved source and available
catalog; do not infer sound correctness from a clean validation alone.

Custom sample files, when needed, are assets: track provenance, check supported
format and references, reserve any new sample IDs against dependencies, and
confirm export inclusion. Do not extract and redistribute stock sound files.

Report static assignment checks separately from listening in Dominions 6.
Individual voices/death cries are not covered by a documented monster command
in the reviewed manual; leave their engine behavior unverified.

Source: [Illwinter's Dominions 6 modding manual](https://www.illwinter.com/dom6/dom6modman.pdf),
sound definitions pp. 5-6, weapons p. 7, monster copying p. 13, spells p. 52.
