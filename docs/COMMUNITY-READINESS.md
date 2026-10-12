# Distribution readiness checklist

Use this checklist for each candidate release. Record actual results, versions and
receipts with that release; this page does not certify any particular build.

## Clean installation

- Install the packaged release into an isolated directory and workspace.
- Follow the first-project guide without relying on development-only files.
- Exercise the CLI, browser and optional MCP connection as applicable.
- Create, edit, validate, export and reimport an independent project.
- Verify required runtime resources and compare exported source and asset bytes.

## Distribution contents

- Build from an identified source revision using the supported packaging process.
- Check the file inventory, hashes, licenses and third-party notices.
- Exclude local projects, credentials, logs, caches and extracted game graphics.
- Distinguish optional reference data and demo resources from required runtime files.
- Check that documentation links and documented commands work in the distribution.

## Verification and reporting

- Record tested operating systems, game/manual/catalog versions and environments.
- Run relevant existing checks and retain their results.
- Report source, artwork, packaging, browser, engine and gameplay evidence separately.
- Record skipped checks and remaining limitations rather than implying full coverage.
- Recheck affected evidence whenever source or assets change.
- Treat publication, release tags and uploads as separately authorized actions.

See [COMMUNITY-QUICKSTART.md](COMMUNITY-QUICKSTART.md),
[AGENT-TEAM.md](AGENT-TEAM.md) and [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
