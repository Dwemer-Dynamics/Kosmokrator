# Agent team workflow

This is an optional workflow for coordinated specialist work. One agent is enough
to build a nation or map; start with [AGENT_USAGE.md](AGENT_USAGE.md).
Use one coordinator and bounded specialists to prepare Kosmokrator for community use.
The coordinator owns the final decisions and verifies every claimed result. Specialists
return evidence, not independent release approval. This workflow does not require an
embedded model, paid service integration or a background agent daemon.

## Roles and goals

| Role | Goal | Deliverable |
| --- | --- | --- |
| Coordinator | Keep work scoped and reconcile findings | Prioritized tasks, file ownership, final evidence report |
| Rules and balance reviewer | Match commands to documented semantics and preserve nation identity | Source lines, manual/catalog version, correction proposals, unresolved balance questions |
| Authoring engineer | Prove the harness works for independent projects | Fresh-project create/edit/validate/export receipt; smallest confirmed defect fixes |
| UI specialist | Keep the interface understandable and usable | Bounded Claude review/implementation, desktop/mobile checks, changed paths |
| Community reviewer | Make setup and redistribution practical | Clean-install findings, documentation gaps, provenance and packaging inventory |
| Verification reviewer | Check the actual saved result | Tests, source/export comparisons, limits and reproducible commands |

Three specialists can work alongside the coordinator. Run additional roles in later
waves. Maintainer UI work follows the maintainer's local `delegate-ui-to-claude`
skill before coordinator review. Community users do not need that local skill or
a separate UI agent. An agent with no UI task should not expand into UI review.

## Task handoff

Give each specialist this brief:

```text
Goal:
Repository, branch and working directory:
Allowed files or read-only scope:
Current evidence and relevant docs:
Acceptance checks:
Deferred work:
Return: confirmed findings, changed paths, exact checks, remaining uncertainty.
```

Start reviewers read-only. Authorize implementation separately in the assigned brief.
Assign one writer per file. If two tasks need the same module, hand changes back to the
coordinator and serialize them. Preserve existing dirty work. Do not treat another
agent's completion message as proof: inspect its changes and verification receipts.

## Working loop

1. Record the user's outcome and acceptance criteria before dispatch.
2. Inspect current source, branch, dependencies and project state.
3. Dispatch independent research and checks with explicit boundaries.
4. Classify findings as confirmed defect, design decision, evidence gap or optional improvement.
5. Fix confirmed defects with guarded edits. Record intentional behavior and open decisions.
6. Run proportional existing checks, then inspect the result as a user would.
7. Export the exact saved revision and compare its payload to source files.
8. Report local completion separately from in-game proof and public release.

For nation source, reserve IDs and use current hashes. Never let two agents patch the
same `.dm` concurrently. Map changes use the complete bundle revision. Read
[AGENT_USAGE.md](AGENT_USAGE.md), [NATION-DESIGN.md](NATION-DESIGN.md) and the relevant
asset/map rules before editing those domains.

## Community preview criteria

- A clean environment can install the package and run the documented first-project flow.
- A second nation can be created, edited, validated and exported without demo-specific paths.
- Saved source, backups, validation and export receipts agree.
- Package contents include the web resources and declared demo assets.
- No local paths, credentials, extracted game resources or catalog checkout leak into the distributable.
- A source license and asset redistribution terms are explicitly chosen by the maintainer.
- Known limitations and tested OS/game/catalog versions accompany the preview.
- Loading and gameplay claims have corresponding in-game evidence. If testing is deferred,
  label the preview accordingly; static success cannot satisfy that criterion.

Publication, release tags and uploads remain separate user actions. Do not have agents
post to forums, contact mod authors or publish artifacts as a side effect of this workflow.
