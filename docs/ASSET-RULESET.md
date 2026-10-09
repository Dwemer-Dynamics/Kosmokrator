# Hebdomad unit asset rules

Current local expansion art: [hebdomad-expansion-v1](../assets/hebdomad-expansion-v1/preview.png),
eight additional unique idle/attack pairs. Original v6 and pretender art remain unchanged.
The local project now has 42 referenced frames for 21 definitions. Human bodies use 34 pixels;
the size-four Borrowed Flame Warden uses 40 pixels. Its spear was shortened by imagegen to fit
the 64-pixel frame. Source manifests retain prompts and measured anchors; prepared sheets only
translate intact poses into equal square cells before the existing mechanical converter runs.

Scope: five troops and six commanders; one idle and one attack PNG per roster entry. Original artwork, inspired by stock Dominions 6 rendering. Stock sprites are research references only and are excluded from distribution.

## Default instructions for new sprites

The user accepted [Hebdomad v6](../assets/hebdomad-v6/overview.png) as good for now. Use it as the approved visual reference for future sprites, alongside comparable vanilla units. The defaults below take precedence over earlier pass-specific experiments in this document; v6 is an accepted baseline, not a claim of exact vanilla parity.

Create original Dominions 6 unit sprites with these defaults:

- Prioritize silhouette, proportions and equipment readability at native game size.
- Use natural human anatomy: slender limbs, small heads, modest hands and feet. Avoid bulky armour and exaggerated boots.
- Use broad, deliberate pixel clusters with roughly 2-3 main shades per material. Add highlights sparingly.
- Use selective darker material colours for edges. Avoid a continuous black outline.
- Keep bronze and iron readable with restrained highlights. Shields have simple surfaces without glossy rings or bevels.
- Use a few uneven robe folds following the cloth's weight. Avoid repeated diagonal stripes.
- Give units distinct silhouettes and modestly varied resting poses. Keep attack motion clear.
- Preserve costume, equipment, palette and apparent scale between idle and attack frames.
- Simplify details that cannot survive reduction. Keep essential weapon shapes continuous and recognizable.
- Use transparent backgrounds with no ground shadow, labels, scenery or baked checkerboard.

### Production defaults

- Generate two poses per unit: idle left and attack right in the source sheet; export separate left-facing frames.
- Export 64 by 64 RGBA PNGs with binary transparency and aligned feet, leaving exactly two clear rows underneath.
- Measure ordinary human bodies at 34 pixels head-to-foot and the Archon at 54 pixels, excluding crests, crowns and raised weapons. Choose an appropriate documented scale for other creature sizes.
- Use nearest-neighbour resizing and one shared scale and palette per pair. The 128-colour ceiling is a technical limit, not a style target.
- Preserve source images, exact prompts, hashes and previous accepted versions.

### Review and stopping rule

Compare at native size and equal nearest-neighbour magnification, with aligned baselines and comparable vanilla units. Do not resize individual figures to make a comparison appear closer.

Reject concrete defects: clipped weapons, detached essential equipment, inconsistent uniforms, wrong scale or unreadable silhouettes. Accept reasonable artistic differences once the set looks coherent and works at native size. Exact vanilla parity is not required.

Colour reduction alone does not create the vanilla look. Shape, anatomy, shading placement and restraint matter more. Further passes should fix named problems on individual units rather than regenerate the whole roster. Keep successful parts of an accepted sprite intact.

## Evidence and style

Authority: https://illwinter.com/dom6/dom6modman.pdf (local extract 6.36). Visual sample: locally cached https://github.com/larzm42/dom6inspector sprites for Cardaces 199, Slinger 50, Myrmidon 1077, Iron Warrior 1156, Scout 431, Myrmidon Champion 1076, Mystic 311, Warrior Smith 1159, Archon 3116. Catalog revision 68904be9da4a683e93ceff6ae457d430be2e43dd, data marker 6.37.

Observed stock traits: left-facing side/three-quarter silhouettes; compact naturalistic bodies; discrete pixel shading; selective dark outlines; muted clothing with contrasting metallic highlights; little detail outside weapons, helmets, robe folds, and faces. Frames preserve identity and equipment. Stock extracted PNG canvases are cropped and vary; exported custom canvases follow manual recommendations.

Sampled stock colour counts (distinct opaque RGB, idle+attack pair) vary: 63-147 for the human references above and 536 for the Archon 3116 pair, against roughly 700-850 for our v1 pairs. There is no single vanilla colour rule. Follow the sampled vanilla look (v3 rules, kept for v4, v5 and v6):

- Soft, selective coloured edges (a darker tone of the local material where a shape needs separation), not dark continuous contours around the whole figure.
- Compact, natural anatomy and stance; slender limbs, small faces, simple silhouettes; short simple cloth folds.
- Subtle shading of about 4-6 tones per material where it helps form; 2-3 tones are enough for small or flat areas. Sparse highlights on metal; no gradients, bevels, speckled or noisy textures.
- Plain, ordinary shields and cuirasses: one boss or one simple device, no studs, scales, embossing or ornamental panels.
- Sacred or officer rank gets one clear motif (crest, mantle, sealed circle, crown), not layered ornament.
- Thin equipment (spear shafts, sling cords, bow limbs and strings) must be drawn thick enough in the source to survive uniform reduction to a 34 px body; lines narrower than one sampling step drop out or fragment.

v4 refines these rules per unit rather than by a global filter:

- Cleaner, larger and deliberately contiguous material clusters of about 3-4 major shades; no microtexture, speckled cloth or mottled metal.
- Brighter golden bronze against cool iron for readable material contrast; few, strategically placed bright pixels.
- Individual corrections: broader priest robes, shorter and lighter sling and bow, clearer archon face and hands, a small pointed bronze spear blade for the levy.
- Thin details that cannot survive reduction may be omitted when the remaining equipment still reads whole (v4 watcher bows have no drawn string; wooden bow and arrow are kept).

v5 keeps the v4 material colours and adds individual proportion corrections:

- Smaller, natural human heads, hands and feet; more slender forearms and lower legs; no mascot or chunky-knight proportions.
- Iron Warden: narrower shoulders and torso, smaller shield, softer selective mid-grey edges instead of a heavy dark perimeter.
- Priest and Archon robes: two or three broad, uneven, mostly vertical shadow regions with at most one asymmetric diagonal near the hem; no repeated parallel diagonal folds.
- Equipment and its omissions are kept from v4 (pointed levy spear, short connected slings, string-less watcher bow).

v6 keeps the v5 proportions, equipment and colour identity and adds individual shading and stance corrections:

- Softer material shading: medium local material tones instead of harsh highlight-to-shadow jumps, selective edges rather than full dark outlines, broad contiguous clusters of 2-3 major tones.
- Shields: flat, restrained bronze or dark iron planes with one small boss or the sealed circle; no bright rings, radial glow or bevelled rims.
- Slight idle stance variety for the Brazen Warden (relaxed upright guard), Sealbearer (shield closer, sword angled forward and up) and Strategos (officer upright pose, sword low near the legs); attack frames keep their thrusts.
- Archon gold trim softened to muted ochre and brass bands with few bright pixels; paler, lower-contrast face and hands.

The export colour cap is a technical ceiling, not a style rule: v3, v4, v5 and v6 use at most 128 opaque RGB per unit pair (v2: 64). The cap does not by itself prove a style match: quantizing a busy illustration still leaves a busy illustration. Generation must simplify shapes, materials and detail first; the cap only removes antialiasing noise from the export.

## Versions

- v1, [assets/hebdomad](../assets/hebdomad): first set, preserved unchanged for audit and comparison. Too much intricate armour and shading against stock.
- v2, [assets/hebdomad-v2](../assets/hebdomad-v2): second set, preserved unchanged. Simplified shapes with 2-3 shades per material, dark outlines and a 64-colour pair palette; flatter and more outlined than the stock samples.
- v3, [assets/hebdomad-v3](../assets/hebdomad-v3): third set, preserved unchanged. Regenerated under the v3 rules above (soft selective coloured edges, compact natural stance, subtle shading), converted with the same unchanged script and a 128-colour pair palette ceiling. Three sheets (hylic_spearman, smoke_slinger, watcher) were regenerated by imagegen correction so thin weapons survive reduction; prompts are recorded as `correction_prompt`. Same ids, slugs, filenames and roster; no lore or stat change. No exact parity with stock art is claimed.
- v4, [assets/hebdomad-v4](../assets/hebdomad-v4): fourth set, preserved unchanged. Each v3 sheet edited by imagegen under the v4 refinements above (individual unit corrections, clean 3-4 shade clusters), converted with the same unchanged script and the same 128-colour pair palette as a technical ceiling. Three sheets (hylic_spearman, smoke_slinger, watcher) received a further imagegen equipment correction (pointed spear blade; short continuous attack sling with the pouch near the head; bowstrings omitted), recorded as `correction_prompt`. Same ids, slugs, filenames and roster; no lore or stat change. No exact parity with stock art is claimed.
- v5, [assets/hebdomad-v5](../assets/hebdomad-v5): fifth set, preserved unchanged. Each v4 sheet edited by imagegen under the v5 individual corrections above (natural head, hand and foot size; slimmer Iron Warden with a smaller shield; uneven vertical robe folds), keeping the v4 colours, converted with the same unchanged script and the same 128-colour pair palette as a technical ceiling. Head anchors were measured afresh on the v5 sheets. Same ids, slugs, filenames and roster; no lore or stat change. No exact parity with stock art is claimed.
- v6, [assets/hebdomad-v6](../assets/hebdomad-v6): current set. Each v5 sheet edited by imagegen under the v6 individual corrections above (softer material shading and shields, slight idle stance variety, softer Archon gold trim), keeping the v5 proportions and equipment, converted with the same unchanged script and the same 128-colour pair palette as a technical ceiling. Head anchors were measured afresh on the v6 sheets. v6 correction: the first smoke_slinger sheet was rejected because its thin attack sling cord broke into a detached cord-and-pouch fragment after reduction; an imagegen correction of that sheet (compact, thicker sling arc from the raised hand with the pouch tucked beside the head; idle unchanged) replaced it, recorded as `correction_prompt` beside the original prompt, with its head anchor measured afresh. The final slinger attack frame is one connected component including the whole cord and pouch; at 34 px the pouch sits against the top of the head. Same ids, slugs, filenames and roster; no lore or stat change. No exact parity with stock art is claimed.

## File contract

- PNG RGBA, transparent background. No black or magenta color keys are needed with alpha.
- 64 by 64 pixels for human frames, nominal body height 32-36 pixels excluding tall helmets and weapons. Archon body 54 pixels (52-56); same 64 by 64 canvas, sufficient weapon clearance.
- Exactly two transparent rows beneath lowest foot. Equal foot baseline in both frames. No clipped weapons, ornaments or heads.
- Solid artwork alpha 255; transparency 0. No ground shadows or semitransparent fringes. No baked checkerboard, labels, border or scene.
- Facing left. Idle on left and attack on right in generated source pair. Final files separate, named <slug>_idle.png and <slug>_attack.png.
- Keep identical costume, anatomy, weapon, palette and apparent scale between frames. Attack motion must be unmistakable and anatomically plausible.
- Use #spr1 and #spr2 after #copystats. Remove #copyspr entirely; manual warns shared copied sprite references can alter the donor.

## Nation art direction

Early Age eastern Mediterranean forge-cities under seven brass heavens. Bronze, dark wrought iron, ash linen, burnt umber, restrained ember orange, occasional dull gold. Seven dots, a sealed circle or a tiny central spark serve as simple readable motifs. No modern firearms, medieval plate harness, oversized fantasy armour, photorealism, large glowing auras, text or random holy symbols. Keep motifs visible at actual game size; a full seven-dot design may be simplified.

## Roster silhouettes

| ID | Slug | Identity and equipment |
| --- | --- | --- |
| 5000 | hylic_spearman | Ash linen levy, plain bronze cap, spear and round shield; low rank, minimal decoration. |
| 5001 | smoke_slinger | Short soot-dark tunic, sling and belt knife, unarmoured, no shield. |
| 5002 | brazen_warden | Bronze cuirass and helmet, round bronze shield, bronze sword; disciplined gate guard. |
| 5003 | iron_warden | Dark iron scale armour, helmet, shield and maul; heavier angular silhouette. |
| 5004 | sealbearer | Sacred bronze guard, muted red mantle, sealed-circle shield, bronze sword, distinctive crest. |
| 5005 | watcher | Hooded ash-brown cloak, spear and bow consistent with inherited Scout equipment; no shield. |
| 5006 | strategos | Bronze officer, red shoulder mantle and crest, bronze sword and shield; more ornament than Warden. |
| 5007 | hierophant | Ash-white robes with dull-gold trim, bronze dagger, tiny concealed spark; priest silhouette. |
| 5008 | kindler | Ochre and charcoal novice robes, bronze dagger and a small lit lamp; modest flame. |
| 5009 | firmament_smith | Dark iron armour, leather smith apron, maul, muscular human; no shield. |
| 5010 | seventh_archon | Towering humanoid, brass/stone regalia and bare fists, seven-point solar crown; grounded feet and no wings. |

Equipment must be checked against resolved vanilla weapon and armour names before generation. This table may be corrected to those names without changing gameplay stats.

## Production and acceptance

Use built-in imagegen, one call per unit containing its two consistent frames. Persist raw outputs, exact prompts and output hashes. Mechanical conversion may split frames, crop transparent margins, nearest-neighbour resize, quantize alpha and align feet; it must not paint new content or redesign the image. Preserve original outputs for audit. If conversion loses a readable weapon or a frame changes identity, request an imagegen correction.

Scale comes from a recorded idle head-top anchor (helmet, hood or hair top; crests and crowns excluded), never from the bounding box including weapons: humans 34 px head-to-foot, archon 54 px. Optional source-manifest fields: `palette_max_opaque_colors` (v2: 64, v3, v4, v5 and v6: 128) reduces each idle+attack pair, after nearest sampling, to one shared palette through libimagequant (sharp, dither 0, highest quality meeting the cap), keeping the sampled binary alpha and storing truecolour RGBA PNGs; this is export colour-format quantization, not repainting. Absent fields reproduce v1 byte-for-byte.

Review both native 1x and nearest-neighbour enlarged images. Reject clipping, incorrect equipment, detached limbs, unreadable silhouettes, excessive glow, different uniforms, baked backgrounds, or blurry high-resolution illustration masquerading as pixel art. Exact stock stylistic parity is a visual judgement, not a file-validation guarantee.

Validate all 22 decoded PNGs, dimensions, alpha, baseline and referenced paths. Export complete demo mod with flag plus 22 frames. Run existing tests and isolated Dominions 6 load/game creation. Report graphical and combat checks separately; headless game creation cannot prove recruitment-screen appearance or combat balance.

## Default nation flags and mod banners

Nation flags use a 128x128 transparent canvas and occupy roughly the bottom 75% of its height.
Use a compact hanging cloth standard, central shaded staff, bronze crossbar, restrained cloth folds,
muted colours and a distinctive finial above the crossbar readable at map scale. Keep the cloth mostly plain. Avoid a large flat horizontal rectangle, tiny lore
illustrations, text and glow. Finials should remain compact but visually recognizable. Preserve the baseline at the bottom of the canvas.
The shared `nation_flag` generator creates original pixels; no third-party flag parts are packaged.
New browser-created nations receive their own ID-specific flag asset and source reference.

Every newly created project receives `#icon "mod_banner.tga"` and an original 256x64 default banner.
Hebdomad replaces it with its own title artwork. Keep titles large and inspect the final native-size
image. The mod banner is a separate asset from the nation flag. Validate both paths and dimensions,
export both, and verify the mod preferences/map appearance in-game separately from headless loading.
Manual basis: #icon p.5 (128x32 or 256x64), #flag p.43 (128x128, bottom positioned).
Style references: the Dom6 nation index flag images for EA Abysia (flame bowl), Arcoscephale (winged staff),
Ermor (eagle), Ulm (anvil), C'tis (serpent) and Vanheim (sword):
https://illwiki.com/dom5/dom6/nations . These images are hosted in the wiki's shared dom5 media directory;
they are visual references from its Dom6 index, not a verified extraction of the installed 6.37 build.
Also inspected local NationGen flag parts and FlagGen.java: it explicitly adds a top icon.
No reference pixels are copied into the distribution. Hebdomad uses an original bronze seven-rayed
seal enclosing a small flame. Default variants are sun, spear, anvil and flame.
