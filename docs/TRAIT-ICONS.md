# Native trait icons

The browser can show original Dominions 6 ability icons beside trait names on unit and pretender sheets,
in the trait editor, and in the selected add-trait preview. Labels and tooltips remain readable without art.
Images use native pixels, with no smoothing or generated replacements.

## Local setup

From the repository root, extract the verified images from your own installation:

```powershell
.venv\Scripts\python.exe -m kosmokrator trait-icons --workspace .local/projects --game "C:\Program Files (x86)\Steam\steamapps\common\Dominions6"
```

Restart `kosmokrator serve` with the same workspace, then refresh the page. The command reads only
`data/res.trs` and, optionally, `data/misc.trs` (stat cost art, below). It does not launch the game, modify game
files, or change project `.dm` files.

The cache lives in `<workspace>/.kosmokrator-trait-icons/`. It is excluded from Git and is separate from
project assets and mod exports. Kosmokrator's source package includes mapping metadata and extraction
code, not Illwinter's graphics. Removing the cache restores text-only traits.

A project reference snapshot copies the verified icons into `<project>/.kosmokrator/reference/<id>/trait-icons/`
(re-hashed against this manifest), so a self-contained project keeps them without the workspace cache. That copy
is served only through `GET /api/projects/<slug>/trait-icons[/<command>.png]`, stays local and is never exported.

## Coverage and evidence

- 237 of the 519 documented monster traits have reviewed native icon mappings.
- 263 API keys include those traits, catalog aliases and nine negative-value variants, using 249 images.
- The remaining 282 traits stay text-only. This means no mapping has been verified, not that every one
  necessarily lacks an in-game icon. Many mod commands control mechanics that do not have a separate badge.
- Negative elemental resistances, research bonus, formation fighter, patrol bonus and fortune use their
  native negative variants when the displayed value is negative.
- The native label/icon associations were read from the installed Linux `dom6_amd64` ability renderer.
  `trait_icon_data.py` records the icon index, native label and call address. Mod-command aliases were
  reviewed against the official modding manual's command descriptions.
- The mapping is pinned to the checked `res.trs` SHA-256. A different archive is refused until its indices
  are reviewed, preventing a future patch from silently assigning the wrong graphics.
- The extractor supports the checked TRS v4 RGB565 sparse encoding. Three newer alpha-format entries
  (360, 361, 363) are not supported; no substitute art is used. Sacred recruitment-cost variants and
  Glamour Manipulator therefore do not have separate icons in this build.

The archive association and decoded pixels have been checked locally. Every mapped trait has not been
compared against a live in-game stats screen. Value/state-dependent art beyond the listed variants remains
outside this first pass; for example, tattoo activation can change its native icon during play.

## Stat and cost art

The same command extracts four `misc.trs` frames when that archive matches its reviewed SHA-256
(`MISC_SHA256` in `trait_icons.py`); otherwise those labels are shown as text with no icon. In the 6.37
`dom6_amd64`, the unit and recruitment info boxes call the sprite routine at `0x4ad630` with sheet 27
(misc.trs; the terrain row at `0x2d38ab` draws frames 184-190 through the same call) and the frame index,
directly before the label text:

| API key | misc.trs frame | Label drawn after it | Call address |
| --- | --- | --- | --- |
| `stat_gold` | 160 | Gold | `0x1075e2`, `0x103635` |
| `stat_resources` | 161 | Resources; province panel "Resources: %d" | `0x107658`, `0x103672`, `0x158ecd` |
| `stat_recpoints` | 162 | Recruitment points | `0x1074c7` |
| `stat_compoints` | 166 | Recruitment points (other branch); province panel "Commander Points: %d" | `0x1036e5`, `0x158c94` |

The unit box picks 162 or 166 on a sign test that was not fully decoded. The browser uses 166 for units whose
role is commander, matching the province panel's "Commander Points" art, and 162 otherwise. Hit points, size,
protection, magic resistance, morale, leadership, strength, attack, defence, precision, combat speed,
encumbrance and map move are drawn as text with no sprite call in the stat box (`0x4b7270` text calls from
`0xf0455` and `0x100cd9`), so no native stat art exists to extract for them. The browser shows them as
text labels only and does not substitute drawn pictograms or other trait icons.

## API and fallback

`GET /api/trait-icons` returns the available command-to-image map. Each image is served only by its known
key through `GET /api/trait-icons/<command>.png`; request paths never select arbitrary game files.
Missing or corrupt cache files are omitted. The UI keeps trait text when the manifest or an image fails.
The manifest is loaded once at browser startup; restart the server after regenerating the cache.
