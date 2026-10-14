# Kosmokrator agent entry point

Start with [agent usage](docs/AGENT_USAGE.md). One agent is enough; use the
[team workflow](docs/AGENT-TEAM.md) only for requested specialist coordination.

## Read for your task

- Nations and balance: [nation design](docs/NATION-DESIGN.md), including roster
  defaults, progression, support access, quality gates and National Features format.
- Sprites, flags, banners and item icons: [asset rules](docs/ASSET-RULESET.md).
  Complete original artwork is the default unless reuse or a prototype was requested.
- Unit, weapon and spell audio: [sound defaults](docs/SOUND-DESIGN.md).
  Reuse appropriate vanilla sounds; original visuals do not require custom audio.
- Maps: [map design](docs/MAP-DESIGN.md), [image layers](docs/MAP-LAYERS.md) and
  [agent map jobs](docs/AGENT-MAPS.md). Reuse supplied answers and delegated choices.
- Delivery: [completion checklist](docs/COMPLETION-CHECKLIST.md).

Preserve authoritative `.dm` bytes with guarded targeted edits. Reserve IDs within
project/dependency scope. Use complete map-bundle revisions for map changes.
Keep extracted game resources and reference snapshots local.
Keep user-authored nations, content, assets, projects, references and anecdotes
local: never copy them into source, docs, tests, commits or PRs. Use synthetic
generic fixtures for tests and examples.

Follow the user's scope and testing limits. Separate static, artwork, packaging,
browser, engine and gameplay evidence. A validated export does not prove game
loading or balance. Publishing, releases, game installation and external posts
require their own authorization. Maintainer UI work follows the maintainer's
applicable delegation rules; community users do not need a second agent.
