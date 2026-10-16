# Start your first project

Kosmokrator helps you and a coding agent build Dominions 6 nations and maps locally.
Codex or Claude does the creative and implementation work. Kosmokrator provides
project files, guarded edits, references, static checks and exports. No model is embedded.

## 1. Open the downloaded tool

Extract the source ZIP. Open PowerShell in the extracted `Kosmokrator` folder.
You need Python 3.11 or newer on your computer.

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

This creates `work/` if needed, starts the local server and opens
[the browser](http://127.0.0.1:8765/). Keep PowerShell open; press Ctrl+C to stop.
The launcher installs nothing and leaves existing projects intact. It uses a local
`.venv` when available, otherwise an installed Python. It does not change your
system execution policy or agent configuration.

To choose another folder or port:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Workspace 'D:\My Dom6 Projects' -Port 8767
```

Use `-NoBrowser` to start without opening a tab. If the port is occupied, select
another port. If Python is missing or too old, install Python 3.11 or newer and retry.

On other systems, or without the PowerShell launcher:

```sh
mkdir -p work
python3 -m kosmokrator serve --workspace work --docs docs --open-browser
```

The Windows launcher is tested. Other operating systems require separate verification.

## 2. Choose what to make

On the home page, choose **Start a nation** or **Start a map**. Fill in the brief,
then copy the agent instructions or download the brief. This prepares instructions;
it does not create or modify a project yet.

- **Nation:** describe its era, theme and playstyle. The agent plans recruitment,
  magic and weaknesses, reserves IDs, builds definitions and artwork, then checks
  inheritance, compatibility and balance references.
- **Map:** describe its geography, size, players and land/sea/cave provinces. The
  agent creates a map job, builds original geography and artwork, stages its files,
  reviews the bundle and imports the reviewed output as a new map.

Map creation stays with Codex or Claude. The browser records briefs and reviews
output; it is not a paint editor. A project can contain multiple nations and maps.

## 3. Give the brief to your agent

Leave the server's PowerShell window running. Open the extracted Kosmokrator folder
in your Codex or Claude Code app, or open a second terminal in that folder and start
your installed agent there. Paste the browser instructions into the agent's
conversation, not into PowerShell. Alternatively, attach the downloaded brief and
ask the agent to carry it out. You can close and reopen the browser while the server runs.
Have it read `AGENTS.md` and `docs/AGENT_USAGE.md` first. Your agent must have access
to the tool folder and the workspace shown in the browser.

The agent can use the CLI immediately from the source folder:

```powershell
py -3 -m kosmokrator create my_nation --workspace work --name 'My Nation'
py -3 -m kosmokrator inspect my_nation --workspace work --json
```

These Windows examples use the `py` launcher. If it is unavailable, replace `py -3`
with `.venv\Scripts\python.exe` or a verified Python 3.11+ executable. Browser
instructions use the running tool's Python and identify the shell; translate the
quoting if your agent uses another shell. Kosmokrator has no model charges of its
own; your agent's subscription or API billing still applies.

A new project starts as a mod container. Nation definitions or map jobs are created
in later steps. Existing slugs are refused; choose a new slug rather than deleting
or replacing another project. Handoffs use your actual workspace, not demo paths.

For agent rules, see [AGENT_USAGE.md](AGENT_USAGE.md).
For map jobs, see [AGENT-MAPS.md](AGENT-MAPS.md).

## 4. Review and export

Reload the browser after the agent saves changes, then open your project. Review
units and artwork, compare references in **Balance**, and inspect **Validation**.
Open Maps to review artwork, province connections and terrain layers. The agent
should explain unresolved mechanics and validation warnings.

Export nations as mods and maps as separate map bundles. Exports add new files in
`<project>/exports/` and never overwrite existing exports. Copy the exported mod
folder into the game's user-data `mods` directory; maps have separate installation
instructions in [MAPS.md](MAPS.md).

These are static checks. They do not prove game loading, gameplay or balance.
Record any later Dominions 6 testing separately.

## Optional: connect through MCP

Model Context Protocol (MCP) exposes the same operations as tools in your agent.
It is optional; the CLI remains available. Create a project-local environment:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[mcp]"
```

This installation downloads Python build dependencies and the optional MCP SDK.
Adapt [the Claude Code example](../examples/mcp.project.json) or
[the Codex example](../examples/codex-config.toml) with absolute paths to the
installed executable and your workspace. Both examples work without reference data.
The editable installation uses this extracted folder, so keep it in place.

- **Claude Code:** merge the example's `mcpServers` entry into `.mcp.json` in the
  project root. Check it with `claude mcp get kosmokrator`, then `/mcp` inside Claude.
  See the [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).
- **Codex:** add the example's server block to `.codex/config.toml` in a trusted
  project, or your user configuration at `~/.codex/config.toml` (normally
  `%USERPROFILE%\.codex\config.toml` on Windows). Check configured servers with
  `codex mcp list` and the active connection with `/mcp`. See the
  [Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

Preserve existing configuration when adding the entry. Kosmokrator does not edit
agent configuration. Reconnect your agent as needed; its client may ask you to
approve the server. To enable references later, add `--catalog` and the absolute
catalog path as two additional arguments. A single agent is enough; specialist
agents are an optional workflow described in [AGENT-TEAM.md](AGENT-TEAM.md).

## Optional: add reference data

The tool works without a catalog. Vanilla references then remain unverified and
reference comparisons are unavailable. Supply a separate
[dom6inspector](https://github.com/larzm42/dom6inspector) checkout to enable them:

```powershell
git clone https://github.com/larzm42/dom6inspector C:\data\dom6inspector
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Catalog C:\data\dom6inspector
```

The community dataset can differ from your installed game. The current default
project target is 6.37; this is not a game-compatibility guarantee. Native trait
icons are optional too; see [TRAIT-ICONS.md](TRAIT-ICONS.md).

## Optional: explore the sample demo

This builds a small generic sample nation in a new project:

```powershell
py -3 -m kosmokrator demo --workspace work
```

It contains two units, one site and one nation, and is a tooling fixture only.
It is game-untested.

Read [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for ownership and redistribution scope.
For a bug report, include the tool/Python version, exact command or browser action,
expected result and error. Remove personal paths and credentials from logs.
Share mod files only when you have permission to do so.
