# Maps built by coding agents

Codex or Claude creates the map. Kosmokrator records the brief, reviews the staged
game files and imports the reviewed snapshot. It does not embed a model or replace
the agent's geography/art tools with an interactive paint editor.

## Workflow

Before creating a map job, follow the three-round discovery and concrete brief in
[MAP-DESIGN.md](MAP-DESIGN.md#default-discovery-flow). Reuse supplied answers or
delegated choices. Default to standard expansion room (15-18 provinces per player
as a design target), fair natural starts, surface only, no wrapping and complete
required artwork. Budget water from participating nations; distinguish playable
planes from seasonal/terrain images. Record detailed start, access and fairness
decisions in the design brief/handoff without inventing unsupported API fields.

1. Read `author_state(project, "map-builds")`, or open Maps in the browser.
2. Prepare a brief using the returned defaults. Send `author_save` with kind
   `map-builds`, `action: "create"`, `preview: true`, the current `expected_revision`
   and your `brief`. Inspect the plan, then save the same brief with `preview: false`.
3. Read the returned job's handoff. The job has an immutable request, a `work/`
   directory for masks, prompts, provenance and drafts, and an `output/` directory.
   Paths returned by the job are relative to the project root. Keep draft metadata
   out of `output/`, which accepts only finished, supported map files without subfolders.
4. Give the handoff to Codex or Claude. Follow [MAP-DESIGN.md](MAP-DESIGN.md) and
   [MAP-LAYERS.md](MAP-LAYERS.md). Create original geography and artwork; do not
   clone game art into exports. Use the agent's available image tools for art and
   deterministic code for ownership, adjacency, markers and packaging.
5. Review with `action: "review"`, `job_id` and the current job-state revision.
   Inspect validation, brief compliance, file hashes and the output revision.
6. Preview acceptance with `action: "accept"`, `preview: true`, `job_id`, current
   `expected_revision` and the reviewed `expected_output_revision`. Save with
   `preview: false` only for the reviewed output. A changed output must be reviewed
   again; a previously imported map is never overwritten.
7. Open the new map, inspect its images and province geometry, then export through
   the existing map exporter. Apply MAP-DESIGN.md's completion gates, deliver a
   preview and export location, and report in-game testing and remaining limits
   separately.

CLI and MCP use the same operations:

```powershell
py -3 -m kosmokrator author PROJECT map-builds --workspace work --json
py -3 -m kosmokrator author PROJECT map-builds --workspace work --body-file request.json --json
```

These examples use Windows PowerShell and the `py` launcher. If unavailable, use
`.venv\Scripts\python.exe` or another verified Python 3.11+ executable instead of
`py -3`. Browser handoffs use the running tool's Python executable and state the
required shell. Translate the quoting if your agent uses a different shell.

Example request (replace the revision with the value just read):

```json
{
  "action": "create",
  "preview": true,
  "expected_revision": "CURRENT_JOB_STATE_REVISION",
  "brief": {
    "map_id": "AshenCoast",
    "title": "Ashen Coast",
    "theme": "Volcanic uplands above a broad inhabited coast",
    "width": 1600,
    "height": 1000,
    "players": 4,
    "land_provinces": 48,
    "sea_provinces": 12,
    "cave_provinces": 0,
    "wraparound": false,
    "all_layers": true
  }
}
```

## Acceptance checks and limits

The review checks surface dimensions, land/sea and lower-plane counts, wrapping,
eligible start count, cave flags, ownership spans and existing map validation.
With all layers requested, it requires base/winter plus eight terrain looks in both
seasons on every plane. Supplied TGA variants must have identical dimensions and
exact white province centres. Total bundles remain bounded at 128 MiB; choose
smaller cave-plane images or fewer layers if necessary.

These checks cannot judge whether borders look natural, whether a snow layer
preserves a mountain, whether ownership matches a painted coastline or whether
starts are fair. Agents must compare contact sheets and masks before acceptance.
The shared `.map` ownership data stays authoritative; game terrain switching and
cross-plane travel remain untested until demonstrated in Dominions 6.

Requests and acceptance receipts stay under `.kosmokrator/map-jobs/` and do not
enter game exports. Accepted means a reviewed static bundle was imported; it does
not mean the map is balanced or verified in game. For revisions to an existing
map, create a new map ID and rebuild references consistently, then import as a new
bundle. Existing province/scenario edits retain their current guarded workflow.
