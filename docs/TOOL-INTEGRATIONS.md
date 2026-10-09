# Optional local tool integrations

Kosmokrator uses administrator-configured external installations. It does not bundle their code or assets, install into Dominions, or treat a successful tool run as proof of game compatibility or balance.

## Configuration

Create `.kosmokrator-tools.json` in the **workspace directory** (the directory containing project folders). Executable paths are relative to each configured installation. The browser cannot change this configuration or supply executable paths.

```json
{
  "tools": {
    "domerger": {
      "directory": "C:/tools/domerger",
      "executable": "dominions-merger.exe",
      "version": "1.0.4"
    },
    "spritegen": {
      "directory": "C:/tools/nationgen",
      "executable": "spritegen.jar",
      "version": "0.14.4"
    }
  }
}
```

Versions in configuration are operator labels, not automatically verified version claims. Executable SHA-256 values identify the actual binaries. Preview fingerprints include runtime data and options.

## Supported operations

| Tool | Operation | Input | Output |
| --- | --- | --- | --- |
| Domerger | Preview and run merge | 1–20 distinct Kosmokrator projects | Remapped `.dm` files and assets in a new run directory, logs and receipt |
| SpriteGen | Interactive handoff | Open the external composer | Export idle/attack frames, then use the existing unit artwork importer |

Domerger requires its `gamedata` directory. Each run copies data into `workspace/tool-runs/<run-id>/runtime`; merging also snapshots selected project inputs. Original projects and external tool installations are not modified. Fixed argument lists are used without a shell. Runs have a five-minute timeout, captured stdout/stderr, exit status and output hashes.

Preview does not create a run directory. Run requires the exact preview SHA. A changed configuration, executable, runtime data or project input requires a fresh preview. Generated or merged mods are separate outputs; importing them is a separate operation.

## Limits

- Domerger documents unresolved name-reference conflicts and some event cases. Preserve its reported activation order; merging does not prove compatibility.
- SpriteGen has interactive workflows. No unattended sprite generation API is claimed here.
- Inspector and Domerger repositories specify GPL-3.0. SpriteGen redistribution permissions were not established in this review; no third-party source, binary or asset pack is added to the Kosmokrator distribution.
- External executables are trusted local programs, not sandboxed programs. Their paths can only be selected through administrator-owned configuration.

## Sources and local evidence

Reviewed 2026-10-07:

- [Domerger README](https://github.com/Leiriri/domerger): CLI workflow, dependencies, load order and limitations. Local v1.0.4 `--help` confirms `--mods-path` and `--target-path`.
- [SpriteGen source](https://github.com/elmokki/nationgen/blob/master/src/nationGen/GUI/SpriteGen.java): interactive composition and PNG/TGA export.

Disposable probes are retained under `.local/tool-probes/`. Domerger successfully produced two remapped mods from projects deliberately sharing monster/nation IDs. These are tool execution checks, not in-game playtests.

## CLI, browser and MCP

Open **External tools** in the browser to preview options, run, inspect history and download output ZIPs.
CLI examples (append `--workspace` and `--catalog` for your local paths):

```powershell
python -m kosmokrator tools status
python -m kosmokrator tools preview --tool domerger --body-file merge-options.json
python -m kosmokrator tools run --tool domerger --body-file merge-options.json --expected-preview-sha256 PREVIEW_HASH
python -m kosmokrator tools history
python -m kosmokrator tools receipt --run-id RUN_ID
python -m kosmokrator import-dm output/example.dm --slug imported-example --preview
```

Domerger options: `{"projects":["hebdomad"]}`. The run hash must come from the current preview.
MCP exposes `external_tools`, `preview_external_tool`, `run_external_tool` and `external_tool_runs`.
HTTP routes are listed in [WEB-BROWSER.md](WEB-BROWSER.md).

The local Domerger probe remapped one nation to ID 149. Output receipts flag IDs below 150;
review these warnings and validate imported outputs before enabling them in the game.
