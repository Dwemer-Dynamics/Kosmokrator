# Kosmokrator agent entry point

Read `docs/AGENT_USAGE.md` for a first nation or map and before changing authoring
behavior. A single coding agent is enough. `docs/AGENT-TEAM.md` is optional, for
coordinated specialist work when requested. When used, keep explicit scope, file
ownership, acceptance checks and evidence handoffs; the coordinator verifies results.

For nation work read `docs/NATION-DESIGN.md`; for artwork read `docs/ASSET-RULESET.md`;
for maps read `docs/MAP-DESIGN.md` and `docs/MAP-LAYERS.md`.
For new maps, use MAP-DESIGN.md's three-round discovery and concrete brief before
generation. Default to standard expansion room, fair natural starts, surface only,
no wrapping and complete required artwork. Budget water for participating nations,
distinguish playable planes from visual variants, and apply all completion gates.

For a new nation request, generate the complete original artwork set from the user's
prompt by default: idle and attack frames for every troop, commander, summon, hero,
pretender and alternate form, plus a nation flag and a custom mod banner. Include
other artwork required by the requested content. Read `docs/ASSET-RULESET.md` and
track every asset in the design brief.
Generate an original icon for every new magic item and reference it with item
`#spr`; follow the asset rules for dimensions, review and export checks.
Vanilla sprites and default banners are
placeholders only unless the user explicitly requests reuse or a prototype. Do not
silently reduce the asset scope to finish sooner. Report blocked artwork explicitly;
a playable ruleset with placeholder art is not a completed nation.

For complete new nations, default to 10-12 distinct recruitable troop types,
including capital-only troops, with summons additional. Follow the compact and
expansive exceptions and roster prevention checks in `docs/NATION-DESIGN.md`.
Apply that document's generation requirements for distinct troop choices, national
magic beyond summons, recruitment geography, natural progression and presentation.
Apply its generation quality gates before bulk artwork and before delivery;
verify support access, booster chains and creature defaults, and capture campaign
checkpoints from the start rather than reconstructing missing evidence afterward.
Audit every advertised army's leadership and movement support, express the theme
in early play, compare competing gem uses, and write distinct individual lore.
Reconcile final guides against saved source so documented capabilities are real.
For generated nations, match the vanilla National Features labelled-line format:
Race, Military, Magic, Priests, Dominion, Buildings, in that order. Follow
`docs/NATION-DESIGN.md` for `#summary`, required coverage and the in-game check;
avoid duplicating the engine-provided Buildings line. A short unlabelled slogan
does not satisfy this requirement.

Preserve authoritative `.dm` bytes with guarded targeted edits. Reserve IDs within
the project and declared dependencies. Use complete map-bundle revisions for map
changes. Keep extracted game resources and user-supplied catalogs local.

Separate static, packaging, browser and in-game evidence. A validated export is not
proof of game loading or balance. Public release and external posts are separate
from local development. For maintainer UI work, follow any UI delegation instructions
the maintainer provides. Community users do not need a second agent or reviewer.
