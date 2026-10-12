# Nation asset rules

## Default for every new nation

Generate a complete original asset set from the user's nation prompt unless the
user explicitly asks for reused artwork or a prototype. This applies to all new
nations, with art direction derived from each nation’s brief.

- Create an original idle/attack pair for every troop, commander, summon, hero,
  pretender and alternate form that appears in the nation.
- Create an original nation flag and custom mod banner. Include other artwork
  required by the requested content; do not add unrelated assets or mechanics.
- Record a checklist mapping each roster ID/form to its two frame paths, and list
  the flag, banner and additional assets. Derive silhouettes, palette and equipment
  from the user's theme and the resolved gameplay loadouts.
- Use built-in imagegen for generated bitmap artwork and the production rules
  below. Keep exact prompts, raw outputs, hashes and mechanical conversion records.
- Treat stock sprites and generic/default graphics as temporary placeholders.
  Replace them before completion unless the user explicitly authorized reuse.
- Before export, inspect native-size and enlarged art, verify dimensions, binary
  alpha, baselines and equipment consistency, and confirm every source reference
  and exported file. Remove `#copyspr` before adding custom sprite paths.
- If any required asset is missing or generation is blocked, name the unfinished
  assets. Do not label a placeholder-art build as a complete nation.

## Magic item and spell artwork

For every newly created magic item, generate an original icon derived from its
name, lore and function, unless the user explicitly requests reused artwork or a
prototype. Track the item definition and icon path in the asset checklist. Use the
supported item `#spr` command with a centered 32x32 or 64x64 image; keep the item
itself within 40x40 pixels and use explicit alpha transparency. Review at native
size and enlarged, verify the saved reference and exported file, and retain the
prompt and original generation. Remove conflicting sprite-copy commands before
setting the custom icon. Missing required item icons are unfinished assets.

Spell definitions do not require an invented icon or custom effect texture.
Generate the original idle/attack artwork for every creature or form introduced
by a spell. Add other spell presentation artwork only when the requested content
uses a supported asset or the user asks for a separate illustration.

## Site and temple presentation

Choose theme-appropriate supported built-in site and temple visuals as part of
the nation presentation review. The documented site command `#look` selects a
built-in sprite (-1 for default, 0-9 for specific looks); it is not an image path.
Do not claim generated site illustrations replace in-game site textures. Browser
or guide illustrations are separate assets and are only required when requested.
Record the selected visuals and distinguish file inspection from in-game review.

## Default instructions for new sprites

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
- Measure ordinary human bodies at 34 pixels head-to-foot and large humanoids at approximately 54 pixels, excluding crests, crowns and raised weapons. Choose an appropriate documented scale for other creature sizes.
- Use nearest-neighbour resizing and one shared scale and palette per pair. The 128-colour ceiling is a technical limit, not a style target.
- Preserve source images, exact prompts, hashes and previous accepted versions.

### Review and stopping rule

Compare at native size and equal nearest-neighbour magnification, with aligned baselines and comparable vanilla units. Do not resize individual figures to make a comparison appear closer.

Reject concrete defects: clipped weapons, detached essential equipment, inconsistent uniforms, wrong scale or unreadable silhouettes. Accept reasonable artistic differences once the set looks coherent and works at native size. Exact vanilla parity is not required.

Colour reduction alone does not create the vanilla look. Shape, anatomy, shading placement and restraint matter more. Further passes should fix named problems on individual units rather than regenerate the whole roster. Keep successful parts of an accepted sprite intact.

## Reference selection

Compare with target-version vanilla units of similar anatomy, size and equipment.
Record reference IDs, catalog version and provenance in the projectâ€™s asset manifest.
Use references to assess proportions, silhouette, shading and scale; do not copy
reference pixels into original artwork. Palette limits alone do not establish a style match.

## File contract

- PNG RGBA, transparent background. No black or magenta color keys are needed with alpha.
- 64 by 64 pixels for human frames, nominal body height 32-36 pixels excluding tall helmets and weapons. Choose other body heights from creature size and comparable vanilla sprites; use a canvas with sufficient weapon clearance.
- Exactly two transparent rows beneath lowest foot. Equal foot baseline in both frames. No clipped weapons, ornaments or heads.
- Solid artwork alpha 255; transparency 0. No ground shadows or semitransparent fringes. No baked checkerboard, labels, border or scene.
- Facing left. Idle on left and attack on right in generated source pair. Final files separate, named <slug>_idle.png and <slug>_attack.png.
- Keep identical costume, anatomy, weapon, palette and apparent scale between frames. Attack motion must be unmistakable and anatomically plausible.
- Use #spr1 and #spr2 after #copystats. Remove #copyspr entirely; manual warns shared copied sprite references can alter the donor.

## Nation art direction

Record the briefâ€™s materials, clothing, equipment, palette and readable motifs before
generation. Give each role a distinct silhouette. Check equipment against the resolved
weapon and armour definitions; keep artwork and gameplay consistent.

## Production and acceptance

Use built-in imagegen, one call per unit containing its two consistent frames. Persist raw outputs, exact prompts and output hashes. Mechanical conversion may split frames, crop transparent margins, nearest-neighbour resize, quantize alpha and align feet; it must not paint new content or redesign the image. Preserve original outputs for audit. If conversion loses a readable weapon or a frame changes identity, request an imagegen correction.

Measure body height using recorded head and foot anchors, excluding raised weapons,
crests and crowns. Apply one scale to both frames. Use a shared pair palette with at
most 128 opaque colours by default; record any justified exception. Preserve binary
alpha and record conversion settings and output hashes in the asset manifest.

Review both native 1x and nearest-neighbour enlarged images. Reject clipping, incorrect equipment, detached limbs, unreadable silhouettes, excessive glow, different uniforms, baked backgrounds, or blurry high-resolution illustration masquerading as pixel art. Exact stock stylistic parity is a visual judgement, not a file-validation guarantee.

Validate every required frame, icon, flag and banner against the asset checklist.
Check dimensions, alpha, baseline, source references and exported bytes. Run relevant
existing checks and an isolated game load where available. Report graphical review,
engine loading and gameplay evidence separately; headless creation does not prove
recruitment-screen appearance or combat balance.

## Default nation flags and mod banners

Nation flags use a 128x128 transparent canvas and occupy roughly the bottom 75% of its height.
Use a compact hanging cloth standard, central shaded staff, bronze crossbar, restrained cloth folds,
muted colours and a distinctive finial above the crossbar readable at map scale. Keep the cloth mostly plain. Avoid a large flat horizontal rectangle, tiny lore
illustrations, text and glow. Finials should remain compact but visually recognizable. Preserve the baseline at the bottom of the canvas.
The shared `nation_flag` generator creates original pixels; no third-party flag parts are packaged.
New browser-created nations receive their own ID-specific flag asset and source reference.

Every newly created project receives `#icon "mod_banner.tga"` and an original 256x64 default banner.
This is a starter placeholder; a complete nation requires its own themed banner. Keep titles large and inspect the final native-size
image. The mod banner is a separate asset from the nation flag. Validate both paths and dimensions,
export both, and verify the mod preferences/map appearance in-game separately from headless loading.
Manual basis: #icon p.5 (128x32 or 256x64), #flag p.43 (128x128, bottom positioned).
Select comparable vanilla flags as visual references and record their provenance in
the project. Do not copy reference pixels into the distribution. Choose the standardâ€™s
materials and finial from the nation brief rather than prescribing one nationâ€™s motif.
