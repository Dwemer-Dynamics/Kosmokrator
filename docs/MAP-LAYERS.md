# Generated map layers

Read with [MAP-DESIGN.md](MAP-DESIGN.md) before generating seasonal or replacement terrain art.

## Supported filename inventory

Illwinter's [Map Making Manual 6.26](https://www.illwinter.com/dom6/dom6mapman.pdf), page 10
("Terrain Graphics"), documents these names: the default and default-winter images, eight terrain looks,
a `w` winter suffix for each look and the plane part placed first. The installed Dominions6.exe contains
the same filename strings. Neither source states switching thresholds.

| Appearance | Main plane | Additional plane |
| --- | --- | --- |
| Default | <map>.tga | <map>_plane2.tga |
| Default winter | <map>_winter.tga | <map>_plane2_winter.tga |
| Plain | <map>_plain.tga | <map>_plane2_plain.tga |
| Forest | <map>_forest.tga | <map>_plane2_forest.tga |
| Waste | <map>_waste.tga | <map>_plane2_waste.tga |
| Farm | <map>_farm.tga | <map>_plane2_farm.tga |
| Swamp | <map>_swamp.tga | <map>_plane2_swamp.tga |
| Highland | <map>_highland.tga | <map>_plane2_highland.tga |
| Kelp | <map>_kelp.tga | <map>_plane2_kelp.tga |
| Water | <map>_water.tga | <map>_plane2_water.tga |

Every terrain row also has a winter partner with `w` immediately after the terrain name:
`<map>_forestw.tga`, `<map>_plane2_waterw.tga`, and so on. Each plane has 18 images:
base, default winter and eight normal/winter terrain pairs. Do not invent `_hot`, `_cold`, `_sea`
or `_deepsea` suffixes merely because the gameplay has those concepts.

## Generation and packaging rules

1. Use the approved border-free base painting as an image-generation reference. Generate a separate
   painting for each requested terrain and season, rather than merely recoloring the base.
2. Replacement terrain must cover every area that could change to it. A forest layer showing trees
   only in the original forests cannot represent a newly forested plain.
3. Preserve composition, river course, coast silhouette and landmark positions. Ask explicitly for
   sparse symbols, clear ground and the existing muted art style. Review outputs for drift.
   Describe only the requested terrain in each prompt; listing all terrain styles together can mix
   unwanted plants or pools into a waste image. For seasonal edits, retain the terrain's visual identity
   rather than accepting generic snow that makes all variants look alike.
4. Treat water as flooded terrain and kelp as submerged vegetation. These paintings must also cover
   potentially flooded land, not just the ocean that already exists. They do not create connections
   or underwater movement capabilities; gameplay is controlled separately.
5. Adapt cave-plane art to its environment: fungal woods and cultivation, damp marsh floor, rock ridges,
   ash rubble and flooded caverns. Providing a winter file does not imply underground seasonal changes.
6. Package every image at exactly its plane dimensions, opaque 24-bit TGA. Restore original ocean
   pixels for surface land-terrain replacements so the existing sea remains consistent.
7. Composite the same authoritative border layer and insert the same exact white province centres.
   Sanitize other pure-white pixels. Never regenerate geography or scenario data for a terrain variant.
8. Keep generator prompts and source paths in a manifest; copy masters into the project workspace.
   Keep master PNGs and contact sheets outside the game bundle to avoid needless export growth.
9. Check the complete filename matrix, dimensions, marker coordinates, unique file hashes, unchanged
   map source and main images, whole-bundle validation, archive contents and bundle-size limits.
10. Share contact sheets for both planes. Record visual shortcomings and separate packaging success
    from actual in-game layer switching. Record which in-game checks were performed and which remain unverified.

Water and kelp must be visibly distinct: water has open flooded ground and sparse rock detail; kelp
has submerged vegetation. Reject plants in a barren waste layer. At small scale, heavy snow can obscure
differences between farm, forest and highland variants; inspect their full-size masters as well.

## Evidence and remaining verification

The suffix inventory is documented on page 10 of the official map manual and matches the terrain `.tga`
filename strings found read-only in the installed executable. The manual also says the default look is
used when a specific one is missing, and that a map containing only plains does not need `_plain.tga`.
It does not document when a province switches to its winter look or how looks are blended at borders.
[MapNuke's source repository](https://github.com/nuke-haus/mapnuke) and
[Illwinter's documentation](https://www.illwinter.com/dom6/docs.html) are further references. Early [mapmaker reports](https://steamcommunity.com/app/2511500/discussions/0/4132683013927541290/)
describe winter-layer issues; they are historical reports, not a current failure diagnosis.

Do not claim exact heat/cold switching thresholds, layer precedence, in-game border blending or cave
seasonal behavior from filenames alone. These require a current game check.

The web map's **Terrain look** preview (see [MAPS.md](MAPS.md#terrain-look-preview)) lets a reviewer
choose any of these images and a winter toggle, clipped to the selected province's `#pb` area or shown
on the whole map. It is a manual inspection aid only: it does not pick looks from province terrain,
simulate temperature or write `#terrain`.
