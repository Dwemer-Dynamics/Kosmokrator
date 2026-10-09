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
`data/res.trs`. It does not launch the game, modify game files, or change project `.dm` files.

The cache lives in `<workspace>/.kosmokrator-trait-icons/`. It is excluded from Git and is separate from
project assets and mod exports. Kosmokrator's source package includes mapping metadata and extraction
code, not Illwinter's graphics. Removing the cache restores text-only traits.

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

## API and fallback

`GET /api/trait-icons` returns the available command-to-image map. Each image is served only by its known
key through `GET /api/trait-icons/<command>.png`; request paths never select arbitrary game files.
Missing or corrupt cache files are omitted. The UI keeps trait text when the manifest or an image fails.
The manifest is loaded once at browser startup; restart the server after regenerating the cache.
