# Map building ruleset

Read this before creating or substantially rebuilding a Kosmokrator map. These are project design
criteria, not additional engine requirements. Use the [map workflow](MAPS.md) for import, editing and export.
For the complete seasonal and terrain image matrix, follow [MAP-LAYERS.md](MAP-LAYERS.md).

## 1. Set the brief before painting

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

## Current SevenRealms example

The local coastal demo is 1600x1000, with 21 land and 9 sea provinces (3 coastal, 6 deep), plus one
Lower Forge province. It retains two land-nation scenario starts and the linked forge gateway.
It is a small demonstration, not an underwater or multiplayer balance benchmark. The nine sea
provinces are connected and provide coastal access; no underwater start has been balance-tested.
Terrain art was generated, with explicit geometry reconciliation and static packaging checks.
In-game testing remains skipped.

## Reference comparisons

- [Illwinter Map Making Manual](https://www.illwinter.com/dom6/dom6mapman.pdf): image format, centre pixels,
  ownership, terrain masks and connection commands are engine requirements.
- [Illwinter vanilla screenshots](https://www.illwinter.com/dom6/): compare low-clutter terrain, subdued
  outlines and space around flags.
- [Peliwyr by Pymous](https://ko-fi.com/s/f0d38aae78): compare continuous landforms and readable dashed
  borders that respond to terrain. Reference the design, not copied artwork.
- [DreamAtlas](https://tlaloca.itch.io/dreamatlas): geography generation and province-shape tooling are useful
  inputs; imported or generated output still needs the checks above.
