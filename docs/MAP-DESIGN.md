# Map building ruleset

Read this before creating or substantially rebuilding a Kosmokrator map. These are project design
criteria, not additional engine requirements. Use the [map workflow](MAPS.md) for import, editing and export.
For the complete seasonal and terrain image matrix, follow [MAP-LAYERS.md](MAP-LAYERS.md).

## 1. Set the brief before painting

### Default discovery flow

For a new map, use the same brief-first flow as nation creation. Ask three short
rounds of useful questions, with recommended defaults and a "choose for me"
option. Reuse answers already supplied; do not ask the user to configure every
terrain percentage. If the user delegates the choices, select and state them.

1. **Players, size and water:** ask total nations including AI, how many need
   underwater starts, compact/standard/spacious expansion room, and inland lakes,
   continent and oceans, archipelago or mostly underwater geography. Player count
   and starting environments drive the province budget; do not silently guess
   them unless the user delegates. Recommend standard expansion room and continent
   and oceans, adjusting to the theme and participating nations.
2. **Geography and playable layers:** ask single continent, several continents,
   islands or themed geography; surface only, surface plus caves or other verified
   engine-supported planes; fair natural starts, strict symmetry or deliberately
   uneven exploration; and supported wrapping. Recommend a single continent, fair
   natural starts, surface only and no wrapping. Do not add caves just because a
   theme sounds mystical. Verify requested topology and plane support before
   promising it.
3. **Theme and special features:** ask visual theme and defining landmarks or
   strategic features. Propose coherent terrain distribution, river crossings,
   mountain passes, special sites and independent difficulty from those answers.

Use these initial design targets, not established vanilla balance rules:

| Expansion room | Provinces per player |
| --- | --- |
| Compact | 10-12 |
| Standard (default) | 15-18 |
| Spacious | 20-25 |

Show both the ratio and total province count. Budget usable land and underwater
expansion separately, and state how cave/other-plane provinces contribute to the
total. Do not count inaccessible water or lower planes as ordinary expansion room
for every nation. Select water allocation from the participating nations and viable
routes, not a fixed percentage. Eight land nations and two underwater nations,
for example, require an explicit underwater budget and connected underwater routes,
not simply "20% water".

### Concrete proposal before generation

Present one compact brief for review before building: player count and starts by
environment; total provinces split by land/water and playable plane; expansion
targets; world shape and wrapping; connectivity and intended chokepoints; theme;
terrain and independent difficulty; complete required artwork; deliberate
asymmetry and tradeoffs. Resolve material outstanding choices before generation.
Proceed with existing authorization when the user has delegated or accepted the
choices; do not introduce a second mandatory approval step.

For caves or other playable planes, specify their province budget, eligible
starting nations, entrance count and placement, expansion room, routes between
entrances, and intentional advantages from controlling an entrance. Distinguish
these playable planes from artwork variants: summer/winter and terrain looks
reuse a plane's geography and do not add playable territory. Default to complete
required original artwork and the supported variant matrix in MAP-LAYERS.md;
record explicit scope exceptions and bundle limits before promising output.

Record intended player count, land/underwater/cave nation slots, map purpose, province counts by plane,
wraparound, starts, gateways, special sites and intended movement bottlenecks. Distinguish a small demo
from a multiplayer map. More image pixels improve readability; more provinces change gameplay.

Choose province counts from expansion room and intended game length. Do not use one fixed land/sea
percentage for every map. Underwater nations need usable expansion routes and enough connected sea;
an ornamental strip of water is not evidence of an underwater-balanced map.

## 2. Build continuous geography

- Sketch coastlines, river catchments, mountain chains, valleys and terrain regions first.
- Vary the coastline with bays and headlands, without repeating scallops at a fixed interval.
- Keep forests, plains and wastes coherent, with soft transitions. Avoid repeating terrain triplets.
- Put river mouths on the coast; distinguish freshwater inland water from ocean provinces.
- Use shallow coastal and deeper offshore water deliberately. Sea is bit 2 (4); deep sea is bit 11
  (2048), normally combined with Sea. Use the map terrain catalog, not the mod magic-site masks.
- Keep land and sea ownership on the correct side of the actual artwork coastline. Rivers inside land
  artwork are not automatically sea provinces. Review mouths, beaches and seasonal images closely.

## 3. Shape provinces around geography

- Scatter centres in usable clearings; avoid rows, equal rectangles and obvious hex/polygon tiling.
- Follow streams, ridges, valleys and woodland margins where useful. Rounded or noisy Voronoi cells
  alone are a draft, not proof of natural geography.
- Vary area and silhouette without thin fingers, tiny fragments or huge provinces containing several
  unrelated terrain regions. Every province must be connected and contain its own centre.
- Keep boundaries and centres clear of important landmarks. Match terrain settings to the dominant
  visible terrain. Generally use one adverse terrain type, at most two where justified.
- Maintain a single authoritative ownership mask. Derive area spans, border rendering and shared-edge
  adjacency from it. Do not separately improvise the three representations.

## 4. Render readable art and borders

Use miniature terrain symbols, restrained colors and open space for flags, armies and dominion overlays.
Avoid dense illustration, repeated province panels, oversized structures and cinematic lighting.

Use separate artwork, borders and province-marker layers. Draw each shared boundary once. For the
current hand-painted style, use short muted dark dashes with consistent spacing along the curve and a
subtle pale halo where necessary. Ocean borders may need a lighter treatment. Judge thickness at normal
viewing size and thumbnail scale; do not rely on one pixel width for every resolution. Coastlines should
read naturally, rather than looking like another thick administrative border.

Choose resolution for legible terrain, labels and centre spacing. The official manual gives 1600x1200
as an example suitable image size, not a mandatory size. Keep within Kosmokrator's current pixel and
bundle limits. A larger image is not a substitute for fixing clutter or increasing strategic depth.

Summer and winter share dimensions, ownership, markers and connections. Preserve river, coast and
landmark positions when changing seasons. Never carry forward an obsolete winter grid or old-size asset.

## 5. Review movement and balance

- Derive ordinary neighbours from shared area boundaries, then explicitly review passes, river borders,
  roads, impassable edges and intended exceptional links. Corner contact alone is not adjacency.
- Check the whole graph and the land-only and sea-only graphs independently. A connected combined graph
  does not prove ordinary land troops or aquatic troops can traverse it.
- Avoid accidental isolated seas or single-entry sea pockets. Compare coastal access and alternative
  routes; a sea connection does not give every land nation underwater movement.
- Compare starts by expansion choices, distance to rivals, terrain costs, accessible resources and
  special-site access. Flag asymmetric choke points and valuable-site concentrations for review.
- Do not award every thematic province extra sites or resources. Theme should create choices, not
  unbounded economic bonuses. Gateways and cave exits also affect access and balance.
- Keep scenario starts and named defenders intentional. State which mods and nation types are required.
- Report static balance observations separately from playtested balance. Do not claim balance from
  visual symmetry, equal province counts or zero validation errors alone.

## 6. Package and verify

Apply these completion gates in order:

- **Layout before detailed art:** check connected provinces, start eligibility,
  comparable reachable expansion space, rival distances and deliberate bottlenecks.
- **Water and plane access:** review land-only, underwater and plane travel
  separately, including isolated seas, entrances and movement restrictions.
- **Artwork:** derive readable borders, coasts, crossings and entrances from the
  approved geography. Inspect every supported requested seasonal/terrain variant
  for aligned centres, ownership and landmarks.
- **Delivery:** validate and export the complete bundle, provide a preview and
  export location, and test loading, starts, connections, plane transitions and
  visual alignment in-game where available. Report static, artwork, packaging and
  in-game evidence separately; disclose blocked or skipped checks. Neither an
  accepted import nor a successful export proves gameplay balance.

1. Back up the bundle and record its revision before changing geography.
2. Inspect the actual art and coastline, then reconcile the ownership mask to the final silhouette.
3. Check complete pixel coverage, connected regions, centre containment and land/sea classification.
4. Insert exactly one pure-white pixel per province; keep other artwork off-white. Export opaque 24-bit
   TGA with dimensions matching `#mapsize`.
5. Respect the game's province numbering order when adding or moving centres. Remap all affected
   province references, including starts, gates, special borders and ordered scenario selectors.
   Never renumber nation IDs, gate numbers, monster counts or unrelated command arguments.
6. Verify names, starts, gateways, sites and defender batches retain their semantic targets after remapping.
7. Derive connections, inspect local degrees and bottlenecks, and check land and water connectivity.
8. Validate every plane and seasonal asset; compare served images with saved images and exported bytes.
9. Review summer and winter at useful viewing scales. Record remaining visual and gameplay limitations.
10. Export a new bundle. Call it in-game verified only after an actual load/play check; if testing was
    skipped, say so explicitly.

## Reference comparisons

- [Illwinter Map Making Manual](https://www.illwinter.com/dom6/dom6mapman.pdf): image format, centre pixels,
  ownership, terrain masks and connection commands are engine requirements.
- [Illwinter vanilla screenshots](https://www.illwinter.com/dom6/): compare low-clutter terrain, subdued
  outlines and space around flags.
- [Peliwyr by Pymous](https://ko-fi.com/s/f0d38aae78): compare continuous landforms and readable dashed
  borders that respond to terrain. Reference the design, not copied artwork.
- [DreamAtlas](https://tlaloca.itch.io/dreamatlas): geography generation and province-shape tooling are useful
  inputs; imported or generated output still needs the checks above.
