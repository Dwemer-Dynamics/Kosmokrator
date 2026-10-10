# Local mod browser and editors

**Maps** imports and edits existing map bundles: planes, provinces, terrain, starts, connections and
scenario commands. It exports maps separately from mods. See [Maps and scenarios](MAPS.md) for formats,
safe saves and current limits. In the map viewer, connection lines are off by default so the map's own painted
borders stay readable; **Show connections** draws them (with the border-type key), and the selected province's
neighbours stay outlined either way. Connections are still edited in the province panel. The terrain look
preview shows a one-line status in plain words; image file names, bundle notes and the province's `#pb` clip are
under **Preview details**.

`kosmokrator serve` starts a small stdlib HTTP server on a loopback address. It lets you browse the
projects in a workspace: nations, units, sites, other parsed definitions, assets, validation, the raw
`.dm` source, and Markdown review/design docs. Reviewed writes include **Edit values**, **Edit nation**, **New unit / New god /
Duplicate**, **New nation**, and **Artwork: upload or replace frames**. **Export** packages the saved revision
into a new file under `<project>/exports/` (see [Build and export](#build-and-export)). Catalog definitions
are read-only; choosing a catalog donor creates a separate project definition.

**Spells** and **Items** have dedicated read-only Browse tabs with project-wide
counts and search by name, ID, selector or command. Expand a definition to see its
authored commands, saved source and JSON. These views list parsed blocks; they do
not interpret effects or prove engine behavior. Item artwork appears when its
saved sprite reference is associated with an asset. **Other definitions** still
includes these blocks alongside the other definition types.

**Items** uses a responsive icon-card grid with authored construction, path and slot metadata,
descriptions, search and expandable source details. **Balance** opens with a reading key (†, ≈, ?)
and an at-a-glance summary, then roster comparison bars, a fixed-magic heatmap and an interactive
cost-versus-capability scatter plot. Each nation keeps one colour and shape across the summary and
every chart. Project nations are all squares and reference nations cycle through five shapes, so with
several project nations or more than five references some nations share a shape and differ by colour
only; the legend, row labels and chart data table always name each nation. With forced colours the
plot marks lose their colour, so use the data table to tell nations apart. Choose troops or
commanders, a cost axis and a stat axis; chart data is also available as a table.

In the scatter plot each unit is drawn as its idle sprite, centred exactly on its value; points are never
nudged apart. The sprite comes from the project's `#spr` asset or the catalog. The sprite box has the
nation's colour, with the nation's legend shape in its corner. A unit with no sprite, or whose sprite fails
to load, shows the plain nation shape, and a note under the chart counts them. Hover or keyboard focus opens
the same unit card used in the tables: sprite, base stats, raw and estimated costs, equipment, magic, and
the unit's two plotted values with their estimate marks. Click, tap or Enter pins the card, and Escape or ×
closes it. The plot is one Tab stop; arrow keys, Home and End move between units in horizontal-axis order.
Each unit's accessible name gives its nation, source and both values. Markers that mostly cover one another
are still all reachable. The uppermost marker in a stack shows a +N badge. Each unit's card lists the units
overlapping it as buttons that open their cards. The chart data table lists every value. Unresolved values
are omitted, estimates are labelled, and original comparison tables remain below. These are
static design comparisons, not simulated win rates or campaign charts.

Optional [native trait icons](TRAIT-ICONS.md) are extracted locally from your installed game. Unit and
pretender sheets and the trait editor keep their text labels when no verified icon is available.

With a configured catalog, small native icons from its `images/` folder sit beside (never replace)
the text, using the same keys as the catalog's own formatter: `Path_<P>` for magic path skill and
spell, item and ritual requirements; `Gem_<P>` for gem amounts (site income, spell and ritual gem
costs); `Path_U` for random magic picks; the catalog's sacred badge when the trait cache is absent;
and `items/item<id>.png` for a `#selectitem` or `#copyspr <id>` item without its own `#spr`. Each
route rebuilds the file name from a fixed letter set or an integer id; nothing is bundled.

Stat labels use only verified native game icons. Gold, Resources and Recruitment points show the game's
own `misc.trs` art (frames 160, 161, 162; 166 for commanders) beside the unchanged text when the optional
local cache holds it; the game draws exactly these beside those labels (see
[native trait icons](TRAIT-ICONS.md#stat-and-cost-art)). This applies on unit and pretender sheets, unit
hover cards, the equipment panel, the cost tables, comparisons and the Balance roster. The game draws base
stats as text, so Hit points, Size, Protection, Magic resistance, Morale, Leadership, Strength, Attack,
Defence, Precision, Combat speed, Encumbrance and Map move are text labels with no icon; the browser does
not draw substitute pictograms or borrow unrelated trait icons for them. Without the cache, or if an image
fails to load, the cost labels are plain text too.
Icons are hidden from assistive technology; the text label is what is read. Weapon and armour rows,
raw commands, source and JSON stay text-only.

**Create & edit** also includes Items, Mercenaries, Events and Advanced commands. Unit and definition details
show references; sheets show supported equipped estimates with ≈; the compatibility section includes
reviewed dependency settings and activation order. See [universal authoring](UNIVERSAL-AUTHORING.md) for
command coverage, safe editing and calculation limits.

## Nation selection

Projects with several nations get a **Nation** selector above the section tabs. Overview, Nation, Units, Sites
and Pretenders all follow it (including the tab counts); Spells, Items, Other definitions, Assets, Source, Validation and Docs
are always project-wide and say so. Choices:

- one nation; **Not tied to a nation** (units and sites no nation references, and custom gods no nation lists);
  **All nations**.
- The choice is in the address (`#/p/<slug>/units/5002?n=151`), so it survives reloads, back/forward and
  bookmarks, and every link the page draws carries it. Without `?n=` the page uses the project's last choice
  (kept per project in the browser's local storage), else the first nation. `#/p/<slug>/nation/<id>` selects
  that nation. An unknown `n` falls back the same way.
- Changing the nation keeps the open section and any open unit, site or god detail. A detail outside the
  selection still opens and is marked "outside filter", with a link to show all nations.
- A unit or site belongs to every nation that explicitly references it, so shared definitions appear under each.
  Units: any nation-block command naming the monster (`#addrecunit`, `#addreccom`, `#startcom`, `#startscout`,
  `#startunittype1/2`, defence/wall/guard and terrain recruitment commands, `#addgod`, ...), plus
  `#homecom`/`#homemon`/`#com`/`#mon` on a site that is that nation's `#startsite`. Sites: the nations whose
  `#startsite` names them. Recruitment inherited through `#copystats` is never guessed. The model exposes this as
  `nations` on each monster (`{nation, via, line[, site]}`) and `start_site_of` on each site.
- Pretender lists are per nation. With **All nations** or **Not tied to a nation** the Pretenders tab shows
  per-nation totals and the project's custom gods instead of hiding them.

## Project readiness

The Overview opens with a **Project readiness** panel, so the default project page shows what still blocks an
export. It is read from the saved `.dm` and the files now in the mod folder (the server's `readiness` block); no
counts are fixed in the page. Each row links to the existing view that fixes it:

- **Validation:** error, warning and unverified counts for the saved revision; errors are listed with their lines
  (up to 12, the rest in the Validation report).
- **Referenced files:** files the `.dm` names (`#spr1`, `#flag`, `#icon` …) that are not in the mod folder, with
  the definitions that name them.
- **Unit sprites:** each monster's effective idle sprite is classified as *custom* (a `#spr1` file that exists),
  *vanilla* (the game's own sprite through `#copyspr`, a catalog `#copystats` donor, or a selected vanilla monster),
  *copied* (from another project monster) or *missing* (a named file is absent, or a new monster has no sprite
  source). Vanilla sprites are valid and listed apart from errors; no vanilla image is packaged. When a later
  `#copystats` overwrites an earlier `#spr1`/`#spr2`, the unit is listed as vanilla with a note naming both lines.
- **Shared sprites** (informational): one image file used by several units, or byte-identical files under
  different names. Sharing is allowed and never counts as a problem.
- **Latest export:** the newest entry in `<project>/exports`, read fresh with the project (the model cache does not
  cover exports), its age, and whether it was built from the saved `.dm` shown on the page. **Open export** goes
  to the Export & Workshop section; a new export updates this row.

The panel says **needs attention** only for validation errors, missing referenced files and units without a sprite.

## Build and export

**Export mod**, at the right of the project heading on every section (full width on narrow screens), opens the
**Export & Workshop** section (`#/p/<slug>/export`, also in the Edit tab group). Its badge shows **ready**, the
validation error count, or **re-validate**. The **Build and export** panel there (project-wide) works on the saved
`.dm` only:

- It shows the saved revision (`.dm` path and SHA-256) and the validation result for that exact revision.
  **Re-validate saved .dm** re-reads the file from disk. Export is disabled, with the reason shown, when
  validation has errors or describes another revision.
- Unsaved unit drafts are listed as **not included**. Exporting never touches them, and a refused export keeps them.
- **Export revision `<sha>`** sends `POST /api/projects/<slug>/export` with `{expected_sha256, format}` (`zip`,
  the default, or `folder`). Under the project lock the server checks the `.dm` still has that hash (else 409
  `sha_mismatch`: "Reload saved revision" shows the new one), snapshots the SHA-256 of every mod file, runs the
  unchanged core `export_mod` (which validates and refuses errors with 422 `validation_failed` plus the errors),
  and then re-snapshots. Every packaged file must hash to the pre-validation snapshot and the mod folder must be
  unchanged; otherwise the new export is deleted (409 `changed_during_export`). Editor saves and core patches
  take the same lock, so they are refused (409 `project_locked`) while an export runs, and vice versa. Files
  changed by a writer that ignores the lock are caught by the snapshot comparison (a change that is reverted
  before the second snapshot is not).
- Output goes to `<project>/exports/<slug>-<UTC stamp>-<8 hex>.zip` (plus `.zip.manifest.json`) or to a folder of
  that name with `kosmokrator-manifest.json`. Names are generated by the server, are unique, and are never
  overwritten; the browser cannot choose a path.
- The result shows the export id, the packaged `.dm` SHA-256 (marked if it is not the revision on the page), the
  archive SHA-256, every packaged file with bytes and SHA-256, warnings and unverified counts, the manifest's
  disclaimer and install hint. **Download ZIP** and **Manifest JSON** fetch it back. **Earlier exports** lists
  up to 20 exports in that folder with the revision each one records.
- Nothing is installed into the game, published or uploaded. Validation is static: it does not prove that the mod
  loads, plays or is balanced.

## Steam Workshop folder

The **Steam Workshop folder** panel below Build and export prepares an export for the game's own uploader. See
[WORKSHOP.md](WORKSHOP.md) for the folder rules, the install safety rules and the manual upload steps.

1. **Choose what goes in.** The source is the export of the revision on the page; when there is none, a ZIP export is
   made first through the same `/export` route. The banner is the `#icon` image. **dom6ws.txt** starts on
   **Choose…**, and **Prepare Workshop folder** stays disabled, with the reason shown, until a visibility is chosen.
   Only `Public` is offered, because it is the only value the creator guide documents for this file.
2. **Prepared folder.** It shows the banner preview, the absolute content folder path (**Copy path**), the source
   export, the hashes and a collapsed list of every file. **Download Workshop ZIP** and **Manifest JSON** fetch it back.
3. **Install locally (optional).** It shows the mods folder fixed by the server, the destination and its state:
   not installed yet, installed by Kosmokrator, identical, another folder is there, or unavailable. The button is
   disabled, with the reason, for a conflict or a missing mods folder. A refused install lists the files that are
   not from this project and says that nothing was changed.
4. **Upload from the game.** It lists the in-game upload steps, with **Launch Dominions 6 in Steam**
   (`steam://run/2511500`, opened only when you click it) and a link to the creator guide.

Earlier Workshop folders (newest 10) are listed under a disclosure. Results and errors move focus to their outcome
heading, and every step works with the keyboard.

## Editing

**Edit values** on a unit sheet or a project pretender sheet opens a form for one `#newmonster`/`#selectmonster`
block with an integer id:

- Base stats (`#hp` ... `#ap`), leadership (`#poorleader` ... `#superiorleader`), fixed magic paths
  (`#magicskill`), and pretender design (`#startdom`, `#pathcost`, `#gcost`).
- Every documented monster trait (519 of the 565 monster commands in Modding Manual 6.36; the rest are stats,
  leadership, magic, pretender fields, names, sprites, resets or equipment). See [TRAIT-COVERAGE.md](TRAIT-COVERAGE.md)
  for the full audit table. The table lists only traits present on the monster (authored lines, or inherited
  from modelled donor columns); a searchable picker grouped by manual section adds the rest. Flags take no value;
  others get one typed input per documented argument (tuples such as `#sailing <ship size> <max unit size>`),
  monster/spell/site/item references accept a name or number that must exist in the project or game catalog, and
  repeatable traits (`#startitem`, `#custommagic`, `#magicboost`, `#gemprod`, `#homerealm`, `#batstartsum*` max 3)
  are added, changed or removed one line at a time. Wrong arity or types, ranges the manual states, unknown
  references and undocumented negative monster numbers are rejected by the server. API changes are
  `{key, op: set|remove}` for single traits and `{key, op: add|replace|remove, line}` for repeatable ones.
- Changing a value rewrites only that argument on the existing line (comments and spacing kept). A new value is
  appended as an override just before `#end`, after any `#copystats`/`#clearspec`/`#clearmagic`. Removing deletes
  only the authored line; the review says what the field falls back to (donor value, or nothing after a reset).
- An ability that is only inherited from the donor cannot be removed: that would need `#clearspec`/`#clearmagic`,
  which also remove other values. The editor never adds `#clearspec`, `#clearmagic`, `#clear` or `#copystats`.
- Duplicate live commands, malformed lines, unclosed blocks, blocks opened twice and name-based
  `#selectmonster` blocks for the same monster are refused; fix those in the source.
- **Review changes** shows each change, the effective value before/after and the exact diff. **Save to .dm**
  re-parses the candidate in memory, then writes through the core patcher (project lock, expected SHA-256,
  backup in `.kosmokrator/backups/`). If the file changed meanwhile, the save is refused (409) and the form keeps
  your values; **Reload latest file** re-reads it without losing them. **Cancel** discards the draft.

This is not full game-ability support: only the listed commands are editable, and Dominions remains the
authority on what they do.

## Authoring: create, duplicate, nations, artwork

All three forms keep their draft through failed checks, conflicts and re-renders. **Review** asks the server for a
preview (tentative id, generated commands as a diff, warnings); nothing is written until you confirm. The write
then runs under the project lock in one transaction: the expected SHA-256 is re-checked (a stale page gets HTTP 409
and the form is kept), a free id is taken from the same allocator as `allocate_ids` (catalog, `.dm`, dependencies,
reservations; units and gods share the monster range), reserved in `kosmokrator.json`, and the `.dm` is backed up
and replaced. If the `.dm` write fails the reservation is rolled back; if even that fails the error says the ids
stay reserved. Generated lines must pass the curated argument checks and add no syntax problems.

- **New unit / New god** (`POST /api/projects/<slug>/create/monster`, `mode: "new"`): donor from a bounded catalog
  search (`GET /api/projects/<slug>/donors?q=`) or a `#newmonster` already in the project. Appends
  `#newmonster N`, `#copystats D`, `#copyspr D`, `#name`, optional `#descr`. A troop/commander gets exactly one
  recruitment line: `#addrecunit`/`#addreccom` in the chosen nation, or `#homemon`/`#homecom` in one of that
  nation's project start sites (capital only). A god also needs `#startdom` and `#pathcost` (optional `#gcost`,
  starting `#magicskill`), gets `#homerealm 0` and is added with `#addgod` to the chosen nation only.
- **Duplicate** (`mode: "duplicate"`): copies a project `#newmonster` block as written (unknown commands, comments,
  sprite paths, donor lines) and changes only the id, the live `#name` and optionally `#descr`. The copy shares the
  sprite files until you upload art for it; the originals are never changed. Recruitment is optional.
- **New nation** (`POST .../create/nation`): `#selectnation N` (150+), `#name`, `#epithet`, `#era`, optional
  `#descr`, then `#clearnation` and only what was ticked: up to four project start sites (by name), home realms
  (realm 10 only when ticked), custom gods, recruitable troops/commanders (units may be shared with other nations),
  `#startcom`, `#startscout`, up to two start squads. Missing start commander, roster, gods or sites are reported as
  warnings, never filled in. Flags and colours are not part of this form. Use docs/NATION-DESIGN.md for the
  design brief; the browser only drafts the commands.
- **Artwork** (`POST .../monsters/<id>/art`, the only route that accepts a body up to 6 MB): one or two PNG frames
  as base64. The server decodes each frame with a strict stdlib decoder (signature, chunk CRCs, IHDR first,
  consecutive IDAT, IEND last, no unknown critical chunks, bounded zlib, filter types) and requires 8-bit RGBA,
  1-256 px per side, at most 2 MB, alpha only 0 or 255 and at least one opaque pixel. Non-64x64 size, mismatched
  frame sizes and feet that do not reach the bottom edge are warnings; images are never altered. Files are created
  exclusively as `art/units|pretenders/<id>-<token>-<idle|attack>.png` (no links anywhere on the path, never an
  overwrite); `#spr1`/`#spr2` in that block are replaced or added and its `#copyspr` lines removed, so a monster
  that borrows its sprite needs both frames. Old files stay on disk. If the `.dm` write fails, only the files
  created by this request are removed. The preview is shown at native size with optional pixelated zoom.

## Edit an existing nation

**Edit nation** on the Nation tab (numbered `#selectnation` blocks, with the editor token) opens a form for one
nation block. State: `GET /api/projects/<slug>/nations/<id>/edit`; preview and save: `POST` on the same path with
`{expected_sha256, preview, changes: [{field, op, value}]}`, guarded exactly like the monster editor.

- Identity: `#name`, `#epithet`, `#era` (1-3), `#descr`, `#summary`, `#brief`. An existing line has only its argument
  rewritten, so its place before or after `#clearnation` is kept. A missing one goes right after `#selectnation` (or
  after the identity line that precedes it), before any reset. Text: no double quotes, `#` or line breaks; existing
  multi-line text stays as written unless changed.
- Lists, as checkboxes: fort troops `#addrecunit`, fort commanders `#addreccom`, custom gods `#addgod` (project
  monsters with `#startdom`/`#pathcost`), home realms `#homerealm` (realm 10 only when ticked), start sites
  `#startsite` (named project `#newsite`, at most 4). Ticking adds one line after the last live entry (or before
  `#end`); unticking deletes only that authored line. Entries that are not project options (vanilla ids, unresolved
  ids, name references) are listed with their raw label and can stay or be removed.
- Start army: `#startcom`, `#startscout`, squads `#startunittype1/2` + `#startunitnbrs1/2` (count 1-200, a sanity
  bound). Existing lines are rewritten in place; a new `#startcom` goes before the other start-army lines, because
  the manual says it removes the start army set before it.
- Removal is refused, with the reason, when deleting the line is not known to remove the entry: a vanilla nation
  (id below 150 or in the catalog) without the matching reset in the block (`#clearrec` for recruitment,
  `#clearsites`/`#clearnation` for sites, `#clearnation`/`#cleargods` for gods, `#clearnation` for realms) unless the
  entry is a project unit; duplicate live lines; malformed lines; removing `#startcom` when earlier start-army lines
  would become effective again. Lines before a reset are shown read-only as already cleared. No reset
  (`#clearnation`, `#clearrec`, `#clearsites`, `#cleargods`) is ever added.
- Capital-only recruitment (`#homecom`/`#homemon` on the nation's start sites) is shown read-only for context and is
  never changed by this form.
- Blocks selected twice, by name as well as by id, unclosed, with `#end` or `#selectnation` not on their own line, or
  with syntax problems are refused. No ids are allocated. Before writing, the candidate is re-parsed: text outside
  the block, and every line outside the requested fields (defence, walls, flags, colours, AI and unknown commands),
  must be identical, new lines must pass the curated checks and every requested value must read back. The write goes
  through the core patcher (project lock, expected SHA-256, backup). A stale page gets 409 and the draft is kept;
  **Reload latest file (keep my form)** compares it with the new file. **Cancel** discards the draft.

## Authoring tab: sites, spells, weapons, armour, heroes, reference, playtests

The **Authoring** tab (`#/p/<slug>/author/<sub>`) uses the shared functions in `kosmokrator/content.py`,
`playtest.py` and `importdm.py`; the CLI (`kosmokrator author|reference|import-dm`) and MCP (`author_state`,
`author_save`, `reference_game_data`, `import_mod`) call the same code. Every form previews first (`preview: true`
shows each change, warnings and the diff) and writes only on an explicit save, under the project lock, against the
expected SHA-256, with a backup. A stale page gets 409 and keeps the draft.

- **State:** `GET /api/projects/<slug>/content/{sites|spells|weapons|armors}` lists the project's blocks of that kind
  with their managed values (and source line), the copied template (with its raw catalog row, labelled as not
  effective in game), unmanaged lines verbatim, the block source, field specs with manual citations and ranges
  (ranges the manual does not state are labelled "sanity bound").
- **Write:** `POST` on the same path with `{expected_sha256, preview, mode: new|edit, target?, template?, values}`.
  `values` holds only the changed fields; `null` removes the authored line. Edits touch only the managed commands of
  one block: an existing line has only its statement rewritten (comments, spacing, unknown commands, encoding and
  line endings are kept), a removed line is deleted, new lines go just before `#end`. The candidate must keep every
  byte outside the block, add no syntax problems, pass the curated checks and read back the requested values.
- **Sites:** `#newsite N` (allocated 1700-3999), optional `#copysite`, then `#name`, `#path`, `#level` (0-4),
  `#rarity`, `#loc`, `#gems`, `#gold`, `#res`, `#homemon`, `#homecom`, `#summon`. The 15-attribute limit is not counted.
- **Spells:** a new spell is always `#newspell`, `#copyspell <catalog spell>`, `#name`, then overrides (`#descr`,
  `#details`, `#school`, `#researchlevel`, `#path`/`#pathlevel` 0 and 1, `#fatiguecost`, `#damage`, `#nreff`) and
  `#restricted <nation>` (required for new spells: national spells). Kosmokrator never writes `#effect`. **Summoned
  monster** sets `#damage` only when the template's catalog effect (effect number + ritual flag) is one the manual
  documents as "damage = monster number" (1, 31, 43, 126, 10001, 10021, 10037, 10038) with a positive monster;
  otherwise it is refused. `#newspell` has no number, so named project spells use a stable name fingerprint.
  Inserting earlier lines does not redirect a retained draft to another spell. Duplicate identities and unnamed
  anonymous spells require a source correction before browser editing. An authored effect override invalidates
  the friendly summon selector.
- **Weapons / armour:** `#newweapon N` (1000-3999) / `#newarmor N` (400-1999, the limits table; the `#newarmor`
  text says 300-999), optional `#copyweapon`/`#copyarmor`, then `#name` and the listed stats and flags. The manual
  says both "#name must be first" and "copy first"; Kosmokrator writes the copy first so it cannot overwrite the name.
- **Heroes:** `GET/POST /api/projects/<slug>/nations/<id>/heroes` edits `#hero1-10` and `#multihero1-7` of one
  nation block with project monsters. Removing writes `#heroN -1` on a vanilla nation (the manual's removal) and
  deletes the line on a new nation. When heroes appear in game is not modelled.
- **Reference:** `GET /api/projects/<slug>/reference?cat=spells|sites|weapons|armors&q=` and
  `.../reference/<cat>/<id>` show raw catalog rows, labelled columns, and for spells the effect record and a
  documented summon monster. These are the catalog's vanilla values, not effective values after any mod.
- **Playtests:** `GET/POST /api/projects/<slug>/playtests` appends a record (game version, tester, nation,
  opponents, map, turns, result summary, observations, evidence references with optional SHA-256) to
  `<project>/playtests/records.json`, outside the mod folder so exports never include it. The record stores the .dm
  SHA-256 it was made against (it must be the current one) and `"claims": "none: observation only"`. Evidence files
  are not opened or verified; no balance conclusion is drawn.
- **Import .dm** (`#/import`, `POST /api/import`, body up to 6 MB): one `.dm` plus asset files (relative paths
  inside the mod folder, no `..`, known asset extensions) become a NEW project. An existing slug is refused (409);
  the `.dm` bytes are copied unchanged; referenced but missing assets are listed. The CLI form reads the source and
  the assets it references from the source's own folder and never changes the source. If writing fails, only the
  folder this import created is removed.
- **External tools** (`#/tools`, `GET /api/tools`): status and guarded runs of administrator-configured Domerger,
  NationGen/SpriteGen installations from `integrations.py` (see TOOL-INTEGRATIONS.md). The browser cannot
  configure a tool or supply a path. Domerger support preview/run; SpriteGen
  provide manual handoffs. Receipts describe execution, not gameplay verification.

## Compare a unit with vanilla units

**Compare with vanilla units** on a unit sheet, and **Compare** next to project units in a nation's roster, open
`#/p/<slug>/units/<id>/compare?c=<id>[,<id>]`: the project unit beside one or two catalog units, found with the
donor search (prefilled with the unit's catalog donor). Read-only; it never changes the unit. Rows: native-size idle
and attack sprites, bottom-centred on equal stages (at least 64x64, else the largest canvas in the row; the stage
adds transparent padding, the figures stay 1x); base hp, strength, attack, defence, precision, natural protection, size, MR, morale,
encumbrance, AP, map move and leadership (with the project unit's raw difference); weapons and armour; fixed and
random magic; modelled abilities; recruitment (project fort, capital-only and shared, or the inspector's fort and
non-fort nation tables for vanilla units); cost components with their interpretation, and an explicit "not
computed" row for final gold, resources and recruitment cost. Unknown values are labelled. There is no balance
score. Catalog units go through the same resolver as donors (`GET /api/projects/<slug>/catalog-units/<id>`; sprites
at `.../catalog-units/<id>/sprite/{idle,attack}`, rebuilt from the integer id). It works offline with the local
catalog. Link: [NATION-DESIGN.md](NATION-DESIGN.md) for the criteria to apply.

These are static checks. Nothing here proves that the mod loads, that a god is selectable or that a unit is
balanced; test in Dominions 6.

## Copy and reset history (unit sheet)

Below the unit sheet, **Copy and reset history** summarises the `kosmokrator.inheritance/1` report for that monster
(`m.inheritance`, also `GET /api/projects/<slug>/inheritance`). The summary line counts copies, resets and modelled
fields that are retained from the donor, set in this `.dm`, cleared by a reset or unresolved; it is marked
**uncertain** when anything is unresolved. Opening it shows:

- **Donors:** each `#copystats`/`#selectmonster` target with line, catalog or project origin, catalog version and,
  for project donors, the reason the chain is not resolved and any ordering uncertainty.
- **History:** copies, resets (with their documented scope) and authored lines that were overwritten later, ended by a
  reset or are not modelled, in source order. Names, descriptions and sprites stay in **Authored commands**.
- **Modelled fields by origin**, grouped as retained, set, cleared and unresolved; unresolved and cleared groups open
  by default. Values and notes come from the resolver unchanged.
- **Transformations:** donor shape columns (`shapechange`, `firstshape`, `prophetshape` ...) and other notable donor
  abilities that are not modelled; whether a reset keeps them is labelled uncertain. Authored unmodelled commands,
  issues (including copy cycles) and the report's limits are listed last.

## Compatibility advice and reorder preview

The Validation tab's **Dependencies and compatibility** section reads `m.compatibility` from `resolution.py`:

- Summary counts as badges (hard id collisions, intentional overrides, ambiguous named definitions, unresolved and
  order-sensitive references, whatever the server reports). The section opens by itself when a hard collision exists.
- Each overlap is a card with its classification (**Hard ID collision**, **Intentional override**, **Ambiguous named
  definition**), contributors in activation order (project lines link to the source), the last selector contributor
  (`winner`), or **no safe winner** for collisions, the commands each contributor writes, and the server's actions
  (`remap_ids`, `declare_dependency`, `review_override`, `change_order`) with their reasons. Every action is labelled
  a manual step; the browser never remaps ids or reorders anything.
- `guidance` lists references to check with the same manual actions.
- **Edit dependency settings → Preview change** now adds **Predicted compatibility changes**: saved vs candidate counts,
  overlaps that appear or disappear, overlaps whose last contributor changes, and collisions that remain (reordering
  cannot repair a duplicate new id). The preview runs without the catalog, so unresolved counts are not compared and
  vanilla collisions are re-checked in the project view after saving.

## Balance comparison

**Balance** (Browse group, follows the nation selector) shows the `kosmokrator.balance/1` report: `m.balance` for the
default selection, or `GET /api/projects/<slug>/balance?references=<id>,<id>` for chosen reference nations. The choice
is kept in the address as `?r=8,13`.

- **Reference nations:** same-era catalog nations as checkboxes grouped by age (at most 12). **Compare selected**
  updates the address; **Default selection** returns to the server's first three per era (a reproducible convenience).
  An invalid id shows the server error with a link back to the default.
- **Reading key:** † raw cost component as written (`auto+N` = autocalc base), ≈ labelled estimate, ? unresolved (never
  zero). It sits beside the page heading, ahead of the data it explains.
- **At a glance:** troops, commanders, recruitable mages and fixed magic maxima per project and reference nation, with
  the nation's chart mark. The charts (roster bars, fixed-magic heatmap, cost and capability scatter) follow it.
- Per nation, a unit table grouped into commanders and troops: base HP/protection/MR/morale/attack/defence in separate
  right-aligned columns ("?" when unresolved); gold, resources and recruitment points as the
  raw component (†, `auto+N` = autocalc base) above the labelled estimate (≈) or "est. —" when unresolved; weapons,
  armour and the estimated protection; fixed paths and random picks with per-path chance only where the server gives it.
- Project nations add start-site gems and national summons: required paths, target, count, gem cost and path, and gems
  per unit only for simple rituals (others say "no per-unit estimate").
- There is no score, rating or OP badge. Limitations and warnings from the report are shown; test in Dominions 6.

## Map builds with an agent

The Maps index has a collapsed **Create with an agent** section (`GET/POST /api/projects/<slug>/map-builds`). The
browser does not draw maps, generate images or run a model; Codex or Claude build the files through the CLI/MCP.

- **New brief:** map id, title, theme, width, height, players, land/sea/cave provinces, wraparound and all layers, with
  the server's defaults and limits checked in the form. **Preview brief** (`action: create, preview: true`) shows the
  brief and the agent's steps; **Create job** (`preview: false`) writes an immutable job under `.kosmokrator/map-jobs`.
- **Jobs:** status (waiting for agent output / output staged), output folder, the agent instructions (`handoff`) with
  **Copy instructions** and **Download job JSON**.
- **Review output** (`action: review`) is read-only: ready state, output revision, brief compliance checks (pass, fail
  or needs human review), static validation and the file list with SHA-256. A job without output shows "No usable map
  output yet" instead of an error dump.
- **Preview import as new map** (`action: accept, preview: true`, with the reviewed `expected_output_revision`) shows
  the new map id, revision and validation; **Import as new map** (`preview: false`) adds it. An existing map is never
  overwritten.
- Every POST sends the jobs `expected_revision` read by the page. A changed revision or output is reported with
  **Reload map jobs**; nothing is retried automatically and earlier reviews are discarded on reload.
- Map editing and terrain previews are unchanged.

## Get started (agent handoff)

**Get started** in the top bar (also **New nation or map** in the sidebar) opens `#/start`. `#/start/nation` and
`#/start/map` are the two briefs; both routes survive reload and back/forward. The page contains no AI model, runs
no command and calls no write API. It states that no project is created; Codex or Claude does the work. Its steps
say to leave the launcher terminal running (the browser page can close and reopen), open the agent separately on
the extracted Kosmokrator folder, and paste the instructions into the agent conversation, not the server terminal.

- **Nation brief:** nation name, project slug (derived from the name until edited; must match the `create` slug rule
  and not exist in the workspace), era and theme (required), playstyle (optional).
- **Map brief:** a new project (slug, optional name) or an existing project from the list (`#/start/map?p=<slug>`
  preselects one; not required), then title, map ID (derived from the title until edited), geography and theme,
  dimensions, players, land/sea/cave provinces, wraparound and seasonal/terrain layers. Defaults and limits match
  the server's map-build brief, including the 128 MiB all-layer estimate.
- **Prepare agent instructions** checks the fields (errors are announced, linked to their inputs and the first is
  focused), then shows instructions built from the workspace in `GET /api/projects` and the chosen values. They
  follow the CLI/MCP contracts: read the design docs first and show a brief; `create_project`; `allocate_ids` before
  new definitions; `inspect_mod` / `expected_sha256` or `author_save` preview then save; validate and export for
  nations; `map-builds` create, review and accept with `expected_revision` / `expected_output_revision` for maps.
  User text is passed as design input. The instructions ask for one agent (multi-agent coordination is optional)
  and treat previews as the agent's own checks, not approval stops.
- **Command lines** in the instructions use the Python that launched the server (`runtime.python_executable` in
  `GET /api/meta`), quoted as a literal: on Windows PowerShell syntax with the `&` call operator and `'...'` (an
  apostrophe doubled), elsewhere POSIX `'...'` (an apostrophe as `'\''`). The shell is named, with a note to
  translate rather than paste into another shell. A server that does not report `runtime` gets a `<python>`
  placeholder and a note to find Python 3.11+ (`.venv\Scripts\python.exe` or `py -3` on Windows); the page never
  guesses an interpreter path and never runs a command.
- **Copy instructions** and **Download brief JSON** use the same patterns as
  map jobs. The JSON (`kosmokrator.design-brief/1`) is a design brief, not an `author_save` request. Editing a field
  hides an earlier result so copied text always matches the form. Drafts are kept in this tab's session storage.
- Optional agent setup, MCP and costs, and the JSON format, are in collapsed sections that link to
  [COMMUNITY-QUICKSTART.md](COMMUNITY-QUICKSTART.md), [AGENT_USAGE.md](AGENT_USAGE.md),
  [NATION-DESIGN.md](NATION-DESIGN.md) and [AGENT-MAPS.md](AGENT-MAPS.md).

Nothing on this page proves that a result loads, is balanced or plays well; review the new project's Validation,
then test it in Dominions 6.

## Start the downloaded source

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Then open <http://127.0.0.1:8765/>. Press Ctrl+C to stop. If installed, `kosmokrator serve ...` is the same.

| Option | Meaning |
| --- | --- |
| `--workspace/-w` | Required. The folder that holds projects (each with `kosmokrator.json`). |
| `--catalog` | Optional dom6inspector checkout (or `KOSMOKRATOR_CATALOG`). Without it, donor stats and vanilla references show as unresolved, and the header shows "no catalog". |
| `--docs` | Optional folder of `*.md` files to show read-only (e.g. this repo's `docs`). Project-local `*.md` files at the project root or in `<project>/docs/` are listed too. |
| `--port` | TCP port (default 8765; `0` picks a free one). |
| `--host` | `127.0.0.1` (default), `localhost` or `::1`. Non-loopback addresses are refused. |

## What you see

- **Sidebar:** one compact row per project: a small mod `#icon` banner thumbnail (4:1; an empty dashed box when the
  `.dm` has no `#icon` or the file is missing, never a nation flag), nation name, era, `#version`, validation status
  and slug. With more than five projects a **Filter projects** box narrows the list by name, nation, era or slug; the
  open project always stays listed. If a project's metadata can't be read, it gets an "unreadable" row with the error
  code. The rest of the list still loads. Below 820px the list starts collapsed (**Show projects**).
- **Home:** **Start a nation**, **Start a map** and **Import a .dm**, then a table of the workspace's projects with
  era, version and validation, and the workspace folder. An empty workspace shows the same start actions and the
  [Get started](#get-started-agent-handoff) steps instead of a command.
- **Project heading:** the mod's `#icon` banner (same rules as the sidebar) beside the mod name, on every
  tab. Nation flags appear only on the Nation tab.
- **Overview:** the [project readiness](#project-readiness) panel, counts for the selected nation and
  project-wide counts (labelled apart), **Dependencies and compatibility** (overlap
  count and the dependency editor; validation counts are in the readiness panel), then mod info, `.dm` SHA-256,
  catalog provenance and JSON links under Advanced.
- **Nation:** flag (native and 2x), description, summary, colours, clears, recruitable troops/commanders,
  start army, start sites and their gems, defence/wall/guard commands, other commands, source.
- **Units:** searchable list (name, id, role, donor; press `/` to focus search, arrows to move, Esc to
  clear). The detail view opens with a **unit sheet** laid out like the in-game unit information screen (and the
  dom6inspector unit overlay used as a visual reference): compact named base stats in three columns, weapons and
  armour, abilities, magic paths, recruitment and description, with the idle sprite at native 1x on a neutral
  backdrop. "Attack frame" (or clicking the sprite) swaps to `#spr2`; 1x/2x/3x is a crisp pixel zoom. Costs on
  the sheet are marked † because they are components as written (`auto+65` = autocalc base 65), not final costs;
  values set by this `.dm` are underlined, and hovering any value shows its source line. Stats are base,
  unequipped values. Everything else is in collapsible technical sections below the sheet: **Artwork** (both
  frames enlarged 1-4x on a transparency grid), stat resolution, authored commands, donor row, diagnostics, source
  block and JSON (copy, download, open). Those sections keep three layers separate:
  1. **Authored commands**, verbatim, with line number, manual status and the effect the browser applied.
  2. **Donor raw catalog row** for `#copystats` (collapsed, raw strings, not effective values).
  3. **Resolved fields**: stats, leadership, magic paths and random picks, weapons/armour, a subset of
     special abilities. Each field is marked donor or authored with its line. Overrides show the donor value they replaced.
  It also lists recruitment (via nation/site commands), costs, unsupported commands, unresolved
  dependencies, validation items for the block, and the source block.
  Monsters named only by nation god commands (`#addgod`) are **pretender forms**: they are grouped separately,
  never counted as troops or commanders, and the Units tab count is the roster without them.
  A "God fields" panel shows `#startdom`, `#pathcost`, `#homerealm` and donor columns that change shape, economy
  or god behaviour (e.g. `prophetshape`, `gemprod`, `alchemy`). Those columns are not modelled; their status
  after `#clearspec` is an assumption.
- **Pretenders:** per nation, the gods a static reading allows, in four separate groups: custom gods defined in
  the project, vanilla realm candidates, the nation's explicit god commands (with effects), and unresolved
  constraints. Cards show art, starting magic, dominion, new path cost and the design-point encoding. Filter by
  status (statically eligible, provisional, excluded) and source, or search (`/`). The detail view uses the same
  unit sheet (base physical stats, abilities, equipment for project gods, starting magic, path cost, dominion and
  the design-point encoding marked †), then availability with reasons; artwork, per-field sources, provenance and
  JSON are collapsible sections.
- **Sites, Other definitions, Assets, Source, Validation, Docs.** Assets show path, format,
  dimensions, bytes, SHA-256 and which definitions use each file. Missing referenced files are flagged.
- **Look:** quiet neutral dark surfaces with hairline borders, parchment serif headings, one warm accent for the
  current tab, selection and focus, and right-aligned tabular numbers, in the spirit of the Dominions 6 interface.
  Layout, chart marks and colours are plain CSS and SVG; native game icons (paths, gems, costs, traits, items) appear
  only where the local catalog or your installed game provides them, always beside their text labels. No game or
  inspector art, textures, fonts or code are bundled. The page needs no network access.

## JSON API (GET only)

All responses carry `schema` (`kosmokrator.browser/1`) and `provenance`: tool and manual version,
catalog dataset version and revision, the `.dm` path and SHA-256. Add `?download=1` to any URL to download it.

```
/api/meta                                     server, catalog status, global docs
/api/projects                                 project list (errors per project, never fatal)
/api/projects/<slug>                          whole model, plus latest_export (newest export, read fresh)
/api/projects/<slug>/{nations,monsters,sites,other_definitions,assets,validation,pretenders,readiness}
/api/projects/<slug>/monsters/<id>            one object (also nations/<id>, sites/<id>, other_definitions/<id>)
/api/projects/<slug>/pretenders/<god>         one god: project-5011, catalog-3416 or god:catalog:3416
/api/projects/<slug>/pretenders/catalog-<id>/sprite/{idle,attack}
                                              vanilla god sprite (PNG), only for gods listed in this project
/api/projects/<slug>/source                   raw .dm bytes (text/plain)
/api/projects/<slug>/assets/<path>            raw asset; add ?format=png to preview a TGA
/api/projects/<slug>/docs/<name>.md           project document
/api/docs/<name>.md                           document from --docs
/api/projects/<slug>/exports                  exports in <project>/exports (newest 20, with recorded revision)
/api/projects/<slug>/exports/<id>/manifest    one export's manifest (by fixed export id only)
/api/projects/<slug>/exports/<id>/archive     one ZIP export (application/zip, download)
/api/projects/<slug>/workshop                 Workshop status: prepared folders (newest 10), install destination, steps
/api/projects/<slug>/workshop/<id>/manifest   one prepared folder's manifest (fixed id <slug>-ws-<stamp>-<hex>)
/api/projects/<slug>/workshop/<id>/archive    the prepared Workshop ZIP (application/zip, download)
/api/projects/<slug>/workshop/<id>/banner.png the prepared banner.png, served only if it matches the manifest hash
/api/projects/<slug>/nations/<id>/edit         nation editor state (POST on the same path previews/saves)
/api/projects/<slug>/catalog-units/<id>       one catalog unit for comparison (read-only)
/api/projects/<slug>/catalog-units/<id>/sprite/{idle,attack}
/api/projects/<slug>/inheritance              copy/reset history for every project monster
/api/projects/<slug>/balance[?references=ID,ID]  nation comparison tables (same-era references, at most 12)
/api/projects/<slug>/map-builds               agent map jobs, defaults and limits (POST on the same path)
```

Stable identifiers are `uid` values such as `monster:5003`, `site:1700` and `nation:150`. Blocks without a number use
`<kind>:line<N>`. Gods are namespaced by origin: `god:project:5011` (a project monster, with `monster_uid`) and
`god:catalog:3416` (a catalog row, with catalog revision and dataset version in `provenance`).

Counts include `roster_units` (troops, commanders and unassigned monsters), `pretender_forms`,
`pretender_candidates` (gods listed for the first nation, excluding excluded ones) and `pretender_gods`. These
are project-wide; the page computes per-nation counts from `nations`/`start_site_of` and the per-nation
pretender views.

## Pretenders: what is modelled

Rules come from the manual (Pretender God Commands; nation Gods) and the dom6inspector tables and scripts
(`realms.csv`, `pretender_types_by_nation.csv`, `unpretender_types_by_nation.csv`, nation attributes 289/314/315,
`MNation.js`). Nation commands are read in order:

- `#clearnation` clears the home realm and god list. `#cleargods` clears the explicit list but not home realm
  gods. `#homerealm N` adds every catalog god of realm N, plus project monsters whose resolved `#homerealm`
  includes N. `#addgod` adds one god. `#delgod` removes a home realm god; if it targets a god that is also added
  explicitly, the result is marked provisional. `#cheapgod20/40` is shown as a discount, not applied to a total.
  `#noundeadgods` excludes undead gods. No other restriction is interpreted.
- Realm 10 (Default) is only included when declared. The catalog stores it per nation and some vanilla nations
  lack it.
- An existing vanilla nation (`#selectnation` of a catalog id, without `#clearnation`) starts from the catalog's
  per-nation tables, labelled as a catalog baseline. New nations start empty.
- A god needs `#startdom` and `#pathcost`. The manual says `#clearspec` clears both, so they must be set after it.
  A project god missing either is excluded; a catalog row missing either is provisional (trinity parts, defaults).
- Whether `#copystats` copies or `#clearspec` clears a home realm is not documented; such realms are unresolved
  unless the block sets `#homerealm` itself (`#homerealm 0` clears).
- `#gcost`/`basecost` is the design-point encoding: `autocalc_encoded` (10000 + base) or `fixed`. Final design
  points are never computed. "Statically eligible" does not mean the god appears in game.
- Only gods of the declared realms and explicit commands are listed, never the whole catalog. Era limits, game
  settings, `#disbless`, AI templates and gods added by other loaded mods are not modelled.

Vanilla god thumbnails are the catalog's own `images/sprites/NNNN_1|2.png`. The server rebuilds the path from the
integer id, and only for catalog gods listed in that project's model. There is no general catalog file route. A
missing file shows "no thumbnail". Custom gods use the project's `#spr1`/`#spr2` assets; `#copyspr` is not
followed, so a god using it shows no thumbnail.

## What "resolved" means (and does not)

This is **not** a Dominions interpreter. The resolver takes the `#copystats` donor row (or the selected
catalog monster), then applies the block's commands in order, for these fields only:

- `#hp #prot #mr #mor #str #att #def #prec #enc #mapmove #ap #size`, plus the `#xxxleader` leadership commands
  (Dominions 6 values: poor 10, ok 50, good 100, expert 150, superior 200). These are **base, unequipped** stats:
  `#prot` is natural protection without armour, and attack/defence/precision/encumbrance exclude weapon and
  armour modifiers. The separate equipped sheet estimates supported equipment modifiers.
- `#clearmagic`, `#magicskill <path> <level>` and `#custommagic <mask> <chance>`. Random picks are listed as written and their probabilities are not expanded.
- `#clearweapons`, `#weapon`, `#cleararmor` and `#armor`. Names are resolved against the catalog. Following the
  manual, `#weapon` without `#clearweapons` adds to the existing weapons. If `#armor` adds to inherited armour
  without `#cleararmor` (the manual says armour assignment then does not work correctly), or if more than three
  armours are listed, the armour list is marked **unresolved**. If the inherited equipment is unknown (an
  unresolved donor), both lists are marked unresolved and show only the authored items.
- `#clearspec` and a fixed list of same-named special abilities (e.g. `#holy`, `#fireres`, `#mountainsurvival`).
  The effect of `#clearspec` on creature-type flags (undead, inanimate, ...) is marked unresolved. Flags set by
  a later argument-less command (e.g. `#female`) are applied.
- `#startdom`, `#pathcost` and `#homerealm` (see Pretenders below). `#clearspec` clears dominion and path cost.
- A later `#copystats` resets supported donor-derived stats, equipment, magic, specials and cost components.
  The dependency overlay retains the destination identity, name, description and sprite fields.

Other monster commands are shown as **not modelled**. They may change values shown as resolved.
Supported project and dependency `#copystats` chains are layered in source order. Unknown donors remain unresolved.

**Raw cost components:** Each resolved cost component has `value`/`effective` set to `null`, and
shows only the authored component (`authored_value`), with `command`, `source` (`authored`, `donor`, `unset`
or `unresolved_donor`), `line` and an `interpretation`:

- `#gcost` (donor column `basecost`): `fixed` if below 5000 (the dom6inspector convention), otherwise
  `autocalc_encoded` with `base` = value - 10000 (the base can be negative, e.g. 9960). The game then adds
  leadership, magic, spy/assassin and sacred costs. The result differs for units and commanders.
- `#rcost`: `component`. This is the base resource value only. The game adds the resource cost of weapons and
  armour, so a donor `rcost` of 1 is a raw component and not the unit's resource cost.
- `#rpcost`: `conditional`. The manual describes "base price"*1000 values as autocalculated. That is not
  interpreted here.

The raw donor table labels `basecost`/`rcost`/`rpcost` as raw cost components. The equipped sheet separately
estimates supported fixed gold, equipment resources and explicit recruitment points. Encoded autocalculation
and unsupported conditions remain unresolved. See [Universal authoring](UNIVERSAL-AUTHORING.md).

Troop/commander roles come from nation and site commands (`#addrecunit`, `#homemon`, `#startunittype1`, ...
as troop; `#addreccom`, `#homecom`, `#startcom`, `#startscout`, `#defcom1`, ... as commander). A monster
that no command references is "not recruited".

## Safety

Equipment can be replaced from **Edit equipment** on a unit sheet (`GET/POST .../monsters/<id>/equipment`).
Choose complete weapon and/or armour lists, review the diff, then save. This explicitly clears inherited equipment
in the selected groups; unchecked groups and unrelated commands are preserved. It accepts project/catalog IDs,
keeps drafts on conflict reload, and is also exposed as `author ... equipment:<id>` through CLI/MCP.

**External tools** now supports Domerger preview and isolated runs, diagnostic receipts and output ZIPs.
SpriteGen remains interactive handoffs. Configuration is local administrator-owned; the browser cannot
provide executable paths. See [TOOL-INTEGRATIONS.md](TOOL-INTEGRATIONS.md) for setup, constraints and evidence.
Routes: `GET /api/tools`, `GET /api/tools/runs`, `GET /api/tools/runs/<id>`,
`GET /api/tools/runs/<id>/archive.zip`, `POST /api/tools/<tool>/preview` and `POST /api/tools/<tool>/run`.
Tool POSTs use the same origin/CSRF/body-size checks as editing. Preview creates no files; run creates a new
directory under workspace `tool-runs`. Downloads verify recorded output hashes. Original projects are preserved.

- Binds to loopback only. Requests whose `Host` header is not a loopback name are rejected (DNS-rebinding guard).
- GET/HEAD are read-only. Writes use `POST /api/projects/<slug>/monsters/<id>/edit` and `.../nations/<id>/edit` (editor state at
  `GET` on the same path), `/create/monster`, `/create/nation`, `/monsters/<id>/art`, `/content/<kind>`,
  `/nations/<id>/heroes`, `/monsters/<id>/equipment`, `/playtests`, `/map-builds`, `/export`, `/workshop/prepare` and
  `/workshop/<id>/install` under the same project prefix, plus `POST /api/import` and the fixed tool routes above. All require an exact same-origin `Origin`, `application/json`, a body of at most 64 KB
  (6 MB on the art and import routes only) and the per-server CSRF token embedded in the served page
  (`X-Kosmo-CSRF`; it changes on every restart and is never written to disk or logs). Bad input returns 400,
  origin/token failures 403, a stale SHA-256, a held lock or a mid-export change 409, validation errors on export
  422. Any other POST, and PUT/DELETE/PATCH/OPTIONS, return 405. There is no raw `.dm` or path write route, and
  export takes no path from the browser. The Workshop routes take only `expected_sha256`, a listed `export_id`, a
  documented `visibility` and a fixed Workshop id; the install destination comes from the server's start-up
  configuration.
- Exports are read back only by an export id that must match `<slug>-<stamp>[-<hex>]`. The file is looked up
  inside `<project>/exports`; a linked exports folder or linked entry is refused, and folder exports have no
  archive route.
- Request paths with `..`, encoded separators (`%2f`, `%5c`), backslashes, NUL, absolute or drive paths are rejected.
  Assets are resolved inside the project's mod folder with exact case, using the same containment helpers as the CLI.
  Symlinks/junctions anywhere on the path return 403, and linked project folders are not listed. Static files come from a fixed allow-list inside the
  package (`kosmokrator/web/`).
- Responses send `Content-Security-Policy` (self only, no inline script), `nosniff` and `no-store`. Non-PNG
  assets are served as downloads. The UI inserts all project text with `textContent`, never as HTML, and loads no external assets.
- Models are cached in a small LRU (6 entries) keyed by a fingerprint of the metadata and mod-folder file
  sizes/mtimes, so edited mods are re-read on the next request. **Reload** in the sidebar re-reads all projects.

## Limitations

- Nothing here proves that the mod loads, plays or is balanced. Test in Dominions 6.
- Only the fields listed above are resolved. Nation and site blocks are summarised from their commands, and
  other nation commands are listed but not interpreted. Dedicated forms cover common fields; Advanced
  commands exposes the wider manual index, including items, mercenaries and events. Unknown lines remain visible.
- Equipped combat values and supported costs are static estimates. Conditional abilities, blesses, spells,
  mounts and automatic costs can change the values in game.
- Donor data comes from the third-party dom6inspector catalog you supply and may differ from your game.
- TGA preview supports true-colour 24/32-bit, uncompressed or RLE (the formats the manual allows). Other variants
  show "preview unavailable". Browsers cannot display TGA directly, so previews are converted to PNG locally.
- Explicit dependencies are layered in their listed order. Other projects' dependencies are not followed recursively.
- The Markdown renderer is minimal: headings, paragraphs, lists, tables, code, quotes, bold/italic and links.

New projects include a default `#icon` banner. New nations generate a shaded hanging standard at `art/nations/<id>-flag.tga`; previews list the asset but do not write it. Flag creation and source saving share the project lock.
