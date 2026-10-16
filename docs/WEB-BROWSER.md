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
`.dm` source, and Markdown review/design docs. Reviewed writes include **Edit**, **Edit nation**, **New unit / New god /
Duplicate**, **New nation**, and **Upload art**. **Export** packages the saved revision
into a new file under `<project>/exports/` (see [Build and export](#build-and-export)). Catalog definitions
are read-only; choosing a catalog donor creates a separate project definition.

**Spells** and **Items** have project-wide counts and search by name, ID, selector or
command. Expand a definition to see its authored commands, saved source and JSON. These
views list parsed blocks; they do not interpret effects or prove engine behavior. Item
artwork appears when its saved sprite reference is associated with an asset. **Other**
still includes these blocks alongside the other definition types.

**Spells**, **Sites**, **Items** and **Mercenaries** each browse and edit in one place. A
**Browse** / **Edit** switch sits at the top of the section. **Browse** shows the cards and a
**New** action (**New spell**, **New site**, **New item**, **New company**). Spell and site cards have
one **Edit** button that opens the structured field form directly (no second Edit click); **Close editor** and
**Cancel** keep it closed until you press Edit again, and opening or closing redraws only the editor, so the
scroll position and focus stay put. Items and existing mercenary companies have no structured form: their cards
say **Advanced edit**, the section's mode says **Advanced edit**, and the line editor is labelled **Advanced**
(raw manual commands, every change previewed as an exact diff). The editor lists every block of
that kind in the project, whatever nation is selected. Edit routes are
`#/p/<slug>/<section>/edit/<key>` (`~new` for a new block). Older `#/p/<slug>/author/<section>/...`
links still work and open the same editor in its section.

**Related content** on unit, site, spell, weapon, armour and advanced-editor pages is collapsed by default. Its
summary line counts what uses the entry and what it uses, how many entries come from dependencies, and flags
unresolved references with a warning badge. Inside, each relation is a sentence ("*Ember Guard* (unit) is armed
with this.", "This recruits *Ash Priest* (unit)."); entries from a dependency are marked "from *<file>*, read-only"
and vanilla entries "from the vanilla catalog, read-only"; neither gets an edit link. A vanilla entry shows its name
when the project model knows it, otherwise its type and ID (for example "Spell #1109"). An unresolved reference keeps
the written name or ID and the expected type. A spell's `#damage` reads as a summon only when it targets a unit. The
raw command, relation, status and source line are in the nested **Details: commands and source lines** table; the
source line belongs to the referring definition, so it links into Source only when that definition is in this project.

**Reviews and saves.** Every editor reviews before writing. **Back to the form** / **Back to editing** (and Escape
where the review is shown inside the editor) return to the form with focus on the button that opened the review
(**Remove entire block…** after a removal preview). A review that would change nothing says **Nothing to save**
and offers Back as its main action instead of a disabled save button. After a successful save, create or artwork
upload, a **save receipt** appears under the project heading: what was saved, the time, the file, the new
SHA-256 (or map revision), the new art files and the backup path. It stays across sections of that project until
**Dismiss**; up to four earlier receipts of the session are under **Earlier saves**. Receipts are per project, are
never shown in another project, and the toast is only a short echo of them.

**Items** uses a responsive icon-card grid with authored construction, path and slot metadata,
descriptions, search and expandable source details. **Balance** opens with a reading key (†, ≈, ?),
then roster comparison bars, a fixed-magic heatmap and an interactive cost-versus-capability scatter
plot; the detailed tables follow, collapsed. Each nation keeps one colour and shape across every
chart. Project nations are all squares and reference nations cycle through five shapes, so with
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
are omitted, estimates are labelled, and the detailed comparison tables remain below. The only live
announcement is the short count ("18 units plotted; 2 omitted (unresolved)."); how to read the markers is in a
closed **How to read this chart** disclosure. These are static design comparisons, not simulated win rates or
campaign charts.

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

## Page chrome and wording

The header shows only the Kosmokrator name, the **Get started** and **Docs** links, and a status badge when the
vanilla data needs attention (an available update, a snapshot that needs repair, or no data); ready data shows
nothing. There is no persistent footer. The sidebar offers **Create**, **Import** and **Tools**, the project list
and **Catalog**. Success states are plain text or absent: badges mark warnings, errors,
unsaved drafts, read-only entries and the current selection. Cards show name, art and the useful stats; raw ids,
commands, source lines, hashes and provenance sit under **Details** disclosures. Errors, write safeguards,
review-before-save and meaningful warnings are unchanged.

**Project header.** A compact heading: a small mod banner, the mod name with epithet, era and version, and on the
right the **Nation** selector (only on the sections it filters, see below) and an **N unsaved drafts** badge when
any editor holds unsaved input (it links to Export, which lists them). Below it, one row of section tabs:
Browse (Overview … Balance) and Build (**Advanced tools**, **Health**, **Changes**, **Validation**, **Export**),
labelled as groups for assistive technology (a wider gap separates them visually). The secondary sections **Source**, **Assets**, **Other definitions**
and **Docs** are under **More** at the end of the row: a button that opens a short list of links (Down arrow opens
it and focuses the current or first link, Up/Down move, Escape closes it and returns focus to the button; a click elsewhere or tabbing away also closes it).
On a secondary section the button reads **More: Source** and carries the current-section underline. Left/Right
move along the tabs and the More button. Below 640px the tab row scrolls sideways instead of wrapping, and the
banner shrinks, so the section content starts right under the header. After every route change the current tab is
centred inside the row (only the row scrolls, never the page; a section under More leaves it as it is). A side that
has more tabs shows a fade with a **‹** or **›** button ("Scroll section tabs left/right"), hidden when that side
has nothing more; keyboard focus moving onto a tab also scrolls it into view. Export is an ordinary Build tab; when
something blocks an export it shows a small flag (the error count, **re-validate** or **validation unavailable**).
Routes, query parameters and deep links are unchanged.

**Advanced tools** (`#/p/<slug>/author`, the former **Edit** tab) opens on an overview that says what each tool is
for, instead of opening Weapons: structured forms (Weapons, Armour, Heroes), advanced line editors (Events, All
manual commands; both labelled **Advanced**), and reference and records (Reference lookup, Playtests, with a link
to the Vanilla catalog). It also lists where the other structured editors live (unit and nation pages, site and
spell cards) and which sections use Advanced edit (items, existing mercenary companies). The **Tool** selector
switches between them; every existing `#/p/<slug>/author/<tool>` route still opens directly. Unit and definition
details show references; sheets show supported equipped estimates with ≈; the compatibility section includes
reviewed dependency settings and activation order. See [universal authoring](UNIVERSAL-AUTHORING.md) for
command coverage, safe editing and calculation limits.

**Unsaved drafts.** Every editor keeps its draft in this browser tab's memory (unit, nation, new unit/god/nation,
artwork upload, equipment, spell/site/weapon/armour forms, heroes, playtest, advanced line editors for items,
mercenaries, events and other contexts, new mercenary company, dependency settings, map edits, map import, map
job brief and .dm import). One registry decides what counts as unsaved: a draft that differs from the file. Typing a
value back, **Discard draft**, **Cancel** and a successful save all clear it; closing an editor without cancelling
keeps it (and its badge). Export lists every unsaved draft of the project with a link to it. Closing or reloading
the tab while any draft is unsaved triggers the browser's own leave-page warning; drafts are never written to disk
or browser storage, and preview and SHA-256 guards are unchanged.

## Nation selection

Projects with nations get a **Nation** selector in the project header, shown only on the sections that follow it:
Overview, Nation, Units, Pretenders, Sites and Balance, plus **Advanced tools → Heroes** (heroes are set per nation).
Those sections follow it, including their tab counts; Spells, Items, Mercenaries, Maps, Other definitions, Assets,
Source, Validation, Export and Docs are always project-wide (each tab's tooltip says whether it follows the
selector). Choices:

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

The Overview opens with a **Readiness** panel, so the default project page shows what still blocks an
export. It is read from the saved `.dm` and the files now in the mod folder (the server's `readiness` block); no
counts are fixed in the page. Rows that pass are left out; the **Latest export** row is always shown. Each problem
row links to the existing view that fixes it:

- **Validation:** error, warning and unverified counts for the saved revision; errors are listed with their lines
  (up to 12, the rest in the Validation report).
- **Referenced files:** files the `.dm` names (`#spr1`, `#flag`, `#icon` …) that are not in the mod folder, with
  the definitions that name them.
- **Unit sprites:** each monster's effective idle sprite is classified as *custom* (a `#spr1` file that exists),
  *vanilla* (the game's own sprite through `#copyspr`, a catalog `#copystats` donor, or a selected vanilla monster),
  *copied* (from another project monster) or *missing* (a named file is absent, or a new monster has no sprite
  source). Vanilla sprites are valid and listed apart from errors; no vanilla image is packaged. When a later
  `#copystats` overwrites an earlier `#spr1`/`#spr2`, the unit is listed as vanilla with a note naming both lines.
- **Shared sprites** (informational, in a collapsed list): one image file used by several units, or
  byte-identical files under different names. Sharing is allowed and never counts as a problem.
- **Latest export:** the newest entry in `<project>/exports`, read fresh with the project (the model cache does not
  cover exports), its age, and whether it was built from the saved `.dm` shown on the page. **Open export** goes
  to the Export section; a new export updates this row.

The panel says **needs attention** only for validation errors, missing referenced files and units without a sprite.

## Project health

**Build > Health** reads `GET /api/projects/<slug>/health` (the same `build_health` as CLI `health` and MCP
`author_state` kind `health`). It combines the existing validation, readiness, reference-graph, compatibility,
recruitment and catalog reports for one captured revision (source, metadata, mod files, declared dependencies and
catalog) into one list ordered blocker, warning, unverified, info. Each finding has a stable `id` and `code` that do
not depend on line numbers, a location (file, line, object, asset), occurrences, evidence and a next action.
Duplicates across reports (for example a missing file reported by validation and readiness) are merged; every
validation item is counted in `reconciliation`. Without a catalog, vanilla references are unverified, not errors.
Unassigned units are informational; `recruitment` classifies new units as recruitable, capital-only, site-only,
start army, defence, hero, summon, pretender, alternate form or other references. **Recheck** passes
`?expected_revision=` and says when files changed. The result lists what it did not check (installed mods,
unlisted enabled mods, game load, balance, revision history); it is static and proves nothing about the game.

## Changes (local checkpoints)

**Build > Changes** keeps an explicit, local history of one project. **Create checkpoint** stores every file in
`mod/<slug>/`, every complete map bundle in `maps/<id>/` and the authored metadata (`kosmokrator.json`,
`playtests/records.json`) as content-addressed blobs plus an immutable manifest in `.kosmokrator/revisions/`. Local
state, exports and other files are not captured; links, junctions, unsafe names and oversized trees are refused,
and a file that changes while it is read refuses the checkpoint. Viewing the page creates nothing, history is never
pruned, and changes made before the first checkpoint cannot be reconstructed. Single-file `.dm` backups are not
checkpoints.

**Compare** shows the current files (including edits made outside the browser) against a checkpoint or the latest
review baseline: added, changed and deleted files; authored definition changes grouped as stats, traits, magic,
equipment, recruitment, description, artwork, donor/copy, other and unknown (raw command text); artwork with
checkpoint and current previews and sizes; map bundles by file; metadata keys and reservations; and the raw `.dm`
diff. Donor and catalog values are not recomputed for a checkpoint; only authored lines are compared. Previews are
served only when the bytes still hash to the compared SHA-256.

**Mark current files reviewed** records a review baseline (a new checkpoint) with the reviewer kind you choose,
human or agent; it is recorded as declared, never assumed. **Restore…** previews the add/replace/delete plan, a
static pre-check of the restored source, and how metadata is merged (identity and configuration stay current; name
and dependencies come from the checkpoint; ID reservations are the union). Applying needs the confirmation box and
the same plan and current revision; a changed project is refused. A complete pre-restore checkpoint is stored first,
replacement files are staged and journaled, and a failure puts back the touched files. An interrupted restore is
shown with **Recover now**. This is not a filesystem-atomic transaction. Validation runs after the restore; an older
broken state may be restored deliberately.

## Reference snapshot (self-contained project)

Below readiness, the Overview's **Reference snapshot** disclosure (collapsed unless the snapshot is stale or
invalid, which also shows a badge on it) can **Make project self-contained**: it copies the
catalog data and local reference art the project needs into `<project>/.kosmokrator/reference/`, so the project can
be browsed and edited without the external catalog, for example after copying the project folder to another
machine. The panel states that the snapshot contains game imagery extracted from your own copy of Dominions 6, is a
local authoring reference only, and is separate from the distributable mod.

- **What is copied.** Every top-level `gamedata/*.csv` table of the live catalog, byte for byte (complete, so
  lookups, inheritance, search and comparisons read the same rows); the catalog `LICENSE`; every item icon; the
  gem and path icons and the sacred badge; and unit sprites either for the catalog units the project references
  (donors, `#copyspr`, selected monsters, recruit and other monster references, catalog pretenders and the default
  balance reference rosters) or, by choice, every catalog unit sprite (about 20 MB in
  about 9,000 files with the 6.37 catalog; more on disk). The verified native UI icon
  cache is copied when the workspace has one. Description text folders, site images, `.git`, scripts, manuals,
  game archives and other files are never copied. A referenced-only snapshot is labelled **partial** for sprites:
  catalog units picked later (for example in Compare) show no sprite until it is refreshed.
- **Preview size and coverage** reports files, size per group and the missing-dependency list (referenced units,
  sprites or item icons the source catalog does not have, or no native icon cache) without writing anything.
- **Writing** sends `POST /api/projects/<slug>/reference-snapshot` with
  `{expected_sha256, expected_snapshot, sprites: "referenced"|"all", preview}`. Under the project lock the server
  checks the saved `.dm` hash (409 `sha_mismatch`) and the current snapshot id (409 `reference_changed`), writes a
  new snapshot to a staging folder with bounded file count and size, verifies it, renames it into place and only then
  switches `current.json`; the previous snapshot is removed afterwards. Links, junctions and traversal are refused.
  A successful write leaves a save receipt with the snapshot folder, file count and size; it states that the `.dm`
  was not changed (no backup) and names any replaced snapshot, which is deleted rather than backed up.
  Creating or refreshing needs a live catalog (`--catalog`); without one the existing snapshot stays in use.
- **Manifest.** `manifest.json` records the source (dom6inspector, credential-free origin URL, git revision,
  dataset version, GPL-3.0 licence and attribution), the tool version, the `.dm` hash at snapshot time, the scope,
  totals, the missing-dependency report and the SHA-256 of every file. It holds project-relative paths only.
- **Use.** A project with a snapshot reads only its snapshot in every project route (sheets, comparisons, balance,
  donor and reference search, editors, validation and export), including project-scoped icon routes. The live
  catalog is never mixed in. Status is **Self-contained** (no live catalog configured, or matching it),
  **differs from live catalog** (stale: still using the snapshot until refreshed) or **failed verification**
  (a changed, missing, extra or linked file: the snapshot is not used and no live data is substituted). Tables are
  re-verified when they change on disk, and snapshot images are checked against the manifest on every read.
  Projects without a snapshot behave exactly as before.
- **Never packaged.** Exports and Workshop folders are built only from the mod folder, so the snapshot is never
  included; an export manifest names only the project-relative snapshot it was validated against. The project
  `.gitignore` already excludes `.kosmokrator/`.

## Vanilla inspector (read-only)

The left sidebar has a **Catalog** section directly under the project list. It opens the selected
project's inspector (`#/p/<slug>/inspector`); with no project selected it names the last selected, or else the
first readable, project it will open, and shows a prompt when none is readable.

The **Vanilla catalog** is its own reference context, not a project section: it has no project tabs, no Nation
selector and no project diagnostics. Its heading has an info-coloured frame, a **read-only reference** badge, the
title **Vanilla catalog**, where the data comes from ("Reading *<project>*'s reference snapshot (*id*)" or "Reading
the live catalog the server was started with, opened from *<project>*") and **← Back to *<project>***, which returns
to the exact project page you came from (else its Overview). The address and APIs are unchanged: the project in
`#/p/<slug>/inspector/...` only selects which snapshot or live catalog is read, and the list state stays in the
query. Only spell, site, weapon and armour entries offer **Use as template for a new …**, the same action as Advanced
tools → Reference; it starts a new draft in the project's form and writes nothing until you review and save. Units,
events, mercenaries, items and nations are for browsing only, and their detail says so. If an unsaved new draft of
that kind already has filled fields or another template, the button asks first: **Keep draft** (open it unchanged),
**Replace template** (keeps the filled fields, which override the new template's values) or **Start clean from …**
(discards the draft); **Cancel** or Escape closes the question. A deliberate replacement clears the old draft's
review and errors. The
Reference lookup links to the catalog (**Open in Vanilla catalog**) for filters and the other categories. The inspector is a local, offline
browser of every vanilla unit, site,
event, mercenary company, item, spell, weapon, armour and nation in the catalog that project reads (its reference
snapshot, or the live catalog when it has none). It is built into Kosmokrator, uses no network and does not embed
any website. Category buttons show the row counts; the list opens without a query and pages 40 entries at a time
(20, 40, 60 or 100 per page).

- **Search** matches an exact id or text in the name (for events, also the description). Event id 0 is a real
  event and is listed and searchable.
- **Everyday filters** are a few dropdowns per category. Units: **Age** (Early, Middle, Late), **Nation**,
  **Role** (troops, commanders, capital-only, heroes) and **Magic** path. Choosing an age narrows the nation list
  and clears a nation from another age; *Any nation* and *No nation* cover national and unaffiliated units.
  Mercenaries: age (#eramask) and availability (level). Nations: age. Spells: school, path, research. Items:
  slot, path, construction. Sites: path, rarity. Events: rarity. Armour: type. Weapons have search only.
- **Nation membership** uses only explicit catalog relations: the fort, non-fort and coastal recruitment tables,
  terrain and underwater recruits, national heroes and the capital site's recruits. A unit can belong to several
  nations. Pretender gods, summons, mercenaries and event units count as *No nation*. A unit's age is the age of
  the nations that list it, never its physical age.
- **Advanced** (closed by default) holds sort, page size, the column search and condition chips below.
- **Column search** finds any raw column by name or label (the full table has hundreds), shows its kind (number,
  text or blank in every row), how many rows fill it and its range, then offers the conditions that fit.
- **Conditions** are combined with AND (at most 8): *at least*, *at most*, *between*, *greater/less than*,
  *equals*, *does not equal*, *has a value* (not blank and not 0), *is blank or 0* and *contains*. Numeric
  conditions compare numbers, never text (`hp at least 100` does not match 20), and accept negative and decimal
  values; a blank cell counts as 0 because the catalog leaves zero values blank. Invalid input (not a number, a
  reversed range, an unknown column) is explained next to the editor and by the server.
- **Column filters** show as chips under Advanced: activate a chip to edit it, × to remove it, or **Reset all**.
  The status line reads "312 of 4,091 units · 41–80", plus the sort.
- **Sorting** by id, name or a useful numeric column (numbers descend first; the button reverses). Ties keep id
  order, so pages never overlap.
- **The address keeps the list state** (`q`, `age`, `nation`, `role`, repeated `c=column:op:value`, `sort`, `order`,
  `per`, `page` after
  `?n=`), so opening an entry, switching category and coming back, bookmarking and Back/Forward all return to the
  same filtered page. Each category remembers its own filters. Within a category the list and detail update in
  place: earlier results stay visible (dimmed) while the next page loads, obsolete requests are cancelled, and
  errors offer Retry and Reset. Values are the catalog's encoding, not interpreted game values.
- **Units** open on the same sheet layout as project units (base stats, gear, abilities, magic, idle/attack
  sprites, nations with how each recruits them) and list the vanilla companies that use them. List rows show
  readable stats (no raw cost encodings). Unit links show the shared hover card.
- **Mercenary companies** show the commander and troop sprites and names (resolved from the catalog's monster
  ids), the commander's items with icons, and every company field with the manual's meaning (p.63).
- **Events** show the full description, then requirements and effects as the catalog's raw tokens. A token whose
  name equals an Event Modding Manual command shows that entry; others (including hex codes) are shown as
  recorded and are not interpreted.
- **Items, spells, sites, weapons, armour and nations** show labelled values, native item and path icons where
  the snapshot has them, and the raw row in a closed disclosure.

Provenance (snapshot id or live catalog, dataset version, revision) and the dom6inspector (GPL-3.0) and Illwinter
attribution are in the collapsible data note below the list; per-entry notes are under *About this data*. Nothing is written; images use only the existing id-based sprite and icon
routes, and nothing from the inspector is exported with the mod.

## Mercenary companies

**Browse → Mercenaries** lists this project's `#newmerc` companies as cards: commander and troop (with sprites and
whether each name resolves to a project or vanilla monster, or is shared by several), troop count, replenishment,
experience, level, era mask and items. **New company** opens a structured form for the fields
documented on manual p.63: name, boss name, commander (`#com`), troop type (`#unit`), number of troops, minimum
men, minimum pay, experience, recruitment rate, random equipment, level, era mask and up to four items (`#item`).
Commander, troop and items are picked from named project definitions or searched in the vanilla catalog.

The manual's `#com`, `#unit` and `#item` take names, so the form writes the exact current name of the pick; the
review warns when several monsters share that name, because which one the game uses is not documented. A
`#newmerc` block has no numeric id and is addressed by its opener line. Saving uses the same preview, SHA-256
revision guard, parser/command preflight, project lock and backup as the advanced editor, and appends the block
without touching other lines. Existing companies are edited, and other lines added, with **Advanced edit** on a card or
the section's **Advanced edit** mode (the line editor), which now refuses numbers for those three commands. A company has no sprite
command of its own; new monsters it hires need their own original artwork.

## Build and export

The **Export** tab in the Build group opens the **Export** section (`#/p/<slug>/export`). A small flag on the tab
appears only when something blocks an export: the validation error count, **re-validate** or **validation
unavailable**. The **Export** panel there (project-wide) works on the saved `.dm` only:

- It shows the validation result for that exact revision; the `.dm` path and SHA-256 are under **Saved revision**.
  **Re-validate** re-reads the file from disk. Export is disabled, with the reason shown, when
  validation has errors or describes another revision.
- Every unsaved draft of the project (see [Unsaved drafts](#page-chrome-and-wording)) is listed as **not
  included**, each linking to its editor. Exporting never touches them, and a refused export keeps them.
- **Export** sends `POST /api/projects/<slug>/export` with `{expected_sha256, format}` (`zip`,
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

The **Steam Workshop** panel below Export prepares an export for the game's own uploader. See
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

**Edit** on a unit sheet or a project pretender sheet opens a form for one `#newmonster`/`#selectmonster`
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
- **Edit** / **Close editor** (and **Edit nation** on the Nation tab) open and close the form in place; the page is
  not re-rendered, so the scroll position and focus on the button are kept. A closed editor keeps its draft.

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
- **New nation** (`POST .../create/nation`): `#selectnation N` (a random free id in 150-499; preview and create
  agree while the `.dm` is unchanged), `#name`, `#epithet`, `#era`, optional
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

## Advanced tools: sites, spells, weapons, armour, heroes, reference, playtests

The **Advanced tools** tab (`#/p/<slug>/author/<sub>`; bare `#/p/<slug>/author` is its overview) and the Edit mode of
Spells and Sites (`#/p/<slug>/<section>/edit/<key>`; the field form opens directly)
use the shared functions in `kosmokrator/content.py`,
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
  **Use as template for a new …** (also on spell, site, weapon and armour entries of the Vanilla catalog) starts a
  new form draft, asking first when an unsaved new draft would be affected (see the Vanilla catalog above). The
  list's **unsaved draft** badge and the Export draft list use the same rule: a new draft counts once a field is
  filled or a template is chosen. **Open in Vanilla catalog** shows the same entry there.
- **Playtests:** `GET/POST /api/projects/<slug>/playtests` appends a record (game version, tester, nation,
  opponents, map, turns, result summary, observations, evidence references with optional SHA-256) to
  `<project>/playtests/records.json`, outside the mod folder so exports never include it. The record stores the .dm
  SHA-256 it was made against (it must be the current one) and `"claims": "none: observation only"`. Evidence files
  are not opened or verified; no balance conclusion is drawn.
- **Import** (sidebar; `#/import`, `POST /api/import`, body up to 6 MB): one `.dm` plus asset files (relative paths
  inside the mod folder, no `..`, known asset extensions) become a NEW project. An existing slug is refused (409);
  the `.dm` bytes are copied unchanged; referenced but missing assets are listed. The CLI form reads the source and
  the assets it references from the source's own folder and never changes the source. If writing fails, only the
  folder this import created is removed.
- **Tools** (sidebar; `#/tools`, `GET /api/tools`): status and guarded runs of administrator-configured Domerger,
  NationGen/SpriteGen installations from `integrations.py` (see TOOL-INTEGRATIONS.md). The browser cannot
  configure a tool or supply a path. Domerger support preview/run; SpriteGen
  provide manual handoffs. Receipts describe execution, not gameplay verification.

## Compare a unit with vanilla units

**Compare** on a unit sheet, and next to project units in a nation's roster, opens
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

## Inheritance (unit sheet)

Below the unit sheet, **Inheritance** summarises the `kosmokrator.inheritance/1` report for that monster
(`m.inheritance`, also `GET /api/projects/<slug>/inheritance`). The summary line counts copies, and resets and
unresolved fields when there are any; it is marked **uncertain** when anything is unresolved. Opening it shows:

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
- **Charts first:** roster comparison bars (recruitable troops, commanders, or recruits with magic/holy paths), the
  fixed-magic heatmap and the cost and capability scatter. The former "At a glance" table repeated the bars and
  heatmap and was removed.
- **Detailed tables** follow, collapsed. Each project nation keeps a visible roster line: "Compared here: 11
  recruitable troops · 7 recruitable commanders. Not compared: 1 hero · 2 summons · 1 pretender form (see Units)",
  using the same classification as Units and Overview. If the report's recruit counts differ from that
  classification, the line is badged **incomplete** and shows both counts instead of hiding the gap (for example a
  server started from an older checkout). Project items and each reference nation are closed disclosures too.
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

**Get started** in the top bar (also **Create** in the sidebar) opens `#/start`. `#/start/nation` and
`#/start/map` are the two briefs; both routes survive reload and back/forward. The page contains no AI model, runs
no command and calls no write API. It states that no project is created; Codex or Claude does the work. It also
says to leave the launcher terminal running (the browser page can close and reopen).

The work is shown as three steps, with a progress list at the top of each brief (done ✓, current step marked
`aria-current="step"`, next):

1. **Prepare the brief.** Fill in the form and press **Prepare agent instructions**. Nothing is created.
2. **Hand off to your agent.** The instructions appear under "Step 2"; **Copy instructions** marks this step done
   only when the browser confirms the copy, and **Download brief JSON** always does. If the clipboard is blocked, a
   persistent error says the instructions were not copied and offers **Select the instructions** (select them and
   copy by hand) and **I copied them manually**; step 3 stays closed until one of these. Paste them into Codex or
   Claude Code opened on the extracted Kosmokrator folder, not into the server terminal.
3. **Return and review.** "Step 3" offers **Reload projects and check**, which only re-reads the workspace: it shows
   **Open <slug>** once the project exists, or says it is not there yet (the agent may still be working; Kosmokrator
   does not run or track it). For a map in an existing project it links to that project's Maps. Then review
   Overview and Validation, and Export when validation has no errors.

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
  hides an earlier result (and returns the progress to step 1) so copied text always matches the form. Drafts are
  kept in this tab's session storage.
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
- **Project heading:** the mod's `#icon` banner (same rules as the sidebar, smaller on narrow screens) beside the
  mod name, on every project tab (not in the Vanilla catalog). Nation flags appear only on the Nation tab.
- **Overview:** the [readiness](#project-readiness) panel, the collapsed reference snapshot, roster tiles for the
  selected nation (recruitable troops, recruitable commanders, heroes, summons, start army/defence-only units,
  pretenders, sites; each roster tile opens Units with that role filter) and project-wide counts (labelled apart), **Dependencies** (overlap
  count and the dependency editor; validation counts are in the readiness panel), then mod info, `.dm` SHA-256,
  catalog provenance and JSON links under Details.
- **Nation:** flag (native and 2x), description, summary, colours, clears, fort troops/commanders
  (`#addrecunit`/`#addreccom`), **Other recruitment** (capital-site, terrain and coastal recruits, from the units'
  recruitment entries), start army, start sites and their gems, defence/wall/guard commands, other commands, source.
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
  One shared classification groups the list, the role filter, the Overview tiles and Balance's roster line:
  **Recruitable troops** and **Recruitable commanders** (a recruitment entry for the selected nation: fort,
  capital or other start site, terrain, foreign or coastal command), **Heroes** (live `#heroN`/`#multiheroN`),
  **Summons (not recruited)**, **Start army or defence only (not recruitable)**, **Not tied to a nation** and
  **Pretender forms (not recruitable)** (named only by nation god commands such as `#addgod`). Each group label shows
  its count, the status line summarises them ("22 units: 11 recruitable troops · 7 recruitable commanders · 1 hero ·
  2 summons · 1 pretender form") and the Units tab count is the same total as the list.
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
- **Sites, Other, Assets, Source, Validation, Docs.** Assets show path, format, dimensions, bytes and
  which definitions use each file (**Copy hash** copies the SHA-256). Missing referenced files are flagged.
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
/api/projects/<slug>/health                   project health (kosmokrator.health/1); ?expected_revision= reports staleness
/api/projects/<slug>/revisions               local checkpoints (kosmokrator.revisions/1); POST {action} creates, reviews, restores
/api/projects/<slug>/revisions/compare       ?target=<checkpoint id>|baseline (kosmokrator.compare/1)
/api/projects/<slug>/revisions/preview       ?side=current|checkpoint&path=&sha= PNG preview, hash-verified
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
/api/projects/<slug>/reference-snapshot       reference snapshot status, coverage and missing data (POST previews/writes)
/api/projects/<slug>/{gem-icons,path-icons,ability-icons,item-icons,trait-icons}/<key>.png
                                              native icons from the catalog this project reads (its snapshot if any)
/api/projects/<slug>/trait-icons              native UI icon map for this project
/api/projects/<slug>/inspector                vanilla inspector counts and catalog provenance
/api/projects/<slug>/inspector/<category>?q=&c=<column>:<op>[:<value>]&sort=&order=asc|desc&page=&per_page=
                                              &age=1|2|3 (units, mercs, nations)&nation=<id>|national|none&role=
                                              troop|commander|capital|hero (units)
                                              one bounded page (at most 100) of units, sites, events, mercs, items,
                                              spells, weapons, armors or nations; c repeats (AND, at most 8), ops
                                              has|none|eq|ne|contains|gt|gte|lt|lte|between (between takes
                                              low..high, e.g. rarity:between:-2..0); the original single
                                              field=&op=has|eq|contains&value= raw-text filter still works
/api/projects/<slug>/inspector/<category>/filters  everyday filters (`simple`), common filters, every column with its
                                              kind, and the sort choices, read from the catalog
/api/projects/<slug>/inspector/<category>/<id>  one readable catalog entry with its raw row
/api/projects/<slug>/mercs                    #newmerc companies with resolved names (POST previews/appends one)
```

`/api/meta` adds `project_references` (projects that read a snapshot, with state and dataset version), and the
project list adds `reference_snapshot` per project. The whole-project model adds `reference` (snapshot status).

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
that no command references is "not recruited". Recruitment entries (`recruitment` on each monster) come from
`#addrecunit`/`#addreccom`, site `#homemon`/`#homecom`/`#mon`/`#com`, and the terrain, foreign, underwater and
coastal commands the browser already reads as roster ties (`#addforeignunit`/`#addforeigncom`, `#forestrec`,
`#mountainrec`, `#swamprec`, `#wasterec`, `#caverec`, `#coastrec`, the matching `…com` commands, `#uwrec`/`#uwcom`,
`#landrec`/`#landcom`, and the deprecated `#coastunit1-3`/`#coastcom1-2`, labelled "deprecated command; confirm in
game"). Start army, defence, wall and guard commands are ties but not recruitment. Other terrain variants
(`#plainrec`, `#…fortrec`, …) are not read yet.

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
  other nation commands are listed but not interpreted. Dedicated forms cover common fields; **Advanced tools → All
  manual commands** (labelled Advanced) exposes the wider manual index, including items, mercenaries and events. Unknown lines remain visible.
- Equipped combat values and supported costs are static estimates. Conditional abilities, blesses, spells,
  mounts and automatic costs can change the values in game.
- Donor data comes from the third-party dom6inspector catalog you supply and may differ from your game.
- TGA preview supports true-colour 24/32-bit, uncompressed or RLE (the formats the manual allows). Other variants
  show "preview unavailable". Browsers cannot display TGA directly, so previews are converted to PNG locally.
- Explicit dependencies are layered in their listed order. Other projects' dependencies are not followed recursively.
- The Markdown renderer is minimal: headings, paragraphs, lists, tables, code, quotes, bold/italic and links.

New projects include a default `#icon` banner. New nations generate a shaded hanging standard at `art/nations/<id>-flag.tga`; previews list the asset but do not write it. Flag creation and source saving share the project lock.
