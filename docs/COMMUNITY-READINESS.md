# Community preview readiness

Local review: October 9, 2026. This repository publishes a source preview, not a tagged release.
Game loading, gameplay and balance remain unverified.

## Verified locally

- The independent `community_smoke` nation and a fresh repeat exercise create, reserve,
  preview/save, guarded editing, inspect, validate, export and import without Hebdomad assets.
- Original fixtures validate with zero errors, warnings or unverified references against
  the local 6.37 catalog. Reimports have four reservation warnings because game exports
  do not include the project's ID-reservation metadata; source and asset bytes match.
- Import now handles a real incoming mod banner without colliding with the default
  placeholder. Existing projects still cannot be overwritten.
- Hebdomad's Furnace Guard resistance ordering is corrected. Two copied mages explicitly
  target their own prophet identity; runtime self-target behavior remains untested.
- A newly built wheel installs into a fresh environment outside the source working
  directory. CLI demo creation, export and packaged resource access work.
- Wheel inspection checks required web/demo resources and excludes native archives,
  catalog data, local game files and personal machine paths.
- The 31 existing tests pass. Detailed local receipts are in `.local/community-readiness/`.
- An installed-wheel MCP stdio check with SDK 1.30.0 discovers 19 tools and executes
  read-only `inspect_mod` outside the source directory without changing workspace hashes.

The fixtures reuse IDs across independent projects. They are portability checks, not
compatible addons to enable together. Declare dependencies or remap IDs before combining.

## Remaining review and distribution work

1. Source licensing is GPL-3.0-only, selected October 9. Decide terms for original generated art.
   Copied command/trait prose has been replaced with original help while retaining
   technical schemas and source references. Keep that separation in future updates.
2. The public repository starts from the allowlisted, hashed source preview. Private
   development history and local workspaces are excluded; keep that publication boundary.
3. Produce a distribution inventory from that snapshot. Do not ZIP the working directory.
   Keep user-extracted icons, the Inspector checkout, local logs and game files out.
4. Include setup, third-party notices and tested-version/OS limits. The clean-install
   checks cover Windows, core CLI and MCP discovery plus one read-only call. Other MCP
   operations, client registration, operating systems and assistive technologies need separate evidence.
5. Describe the tool as a static authoring preview and the showcase as game-untested.
   Loading, gameplay and balance remain deferred. Do not imply multiplayer compatibility.

## Starter versus showcase

The installed `demo` command creates 13 definitions, including two custom pretenders.
The expanded local Hebdomad has 21 definitions with unique art; SevenRealms is a separate
map bundle. Showcase updates are exported separately and do not automatically become
starter-template changes. Repository docs are separate from wheel package resources.

Use [AGENT-TEAM.md](AGENT-TEAM.md) to assign the next bounded review/fix wave. License,
public release, repository publication and forum announcements require owner decisions.

## Reproduce the local source snapshot

Run `python scripts/build-source-preview.py --output preview.zip` from the source checkout.
The script uses an explicit allowlist, hashes every entry, fixes archive timestamps and
refuses to overwrite an existing archive. It includes runtime code, web/demo resources,
docs, examples and existing tests. It excludes local projects/catalogs/icons, historical
art sources and the optional sprite-processing script. The pretender checksum manifest
is included for the existing asset regression check. Asset-history links in the docs
therefore refer to the full development checkout, not bundled preview files.

The existing October 9 preview ZIP predates the GPL choice; regenerate it before sharing.
Original-art terms remain separate from the source GPL license. See
[COMMUNITY-QUICKSTART.md](COMMUNITY-QUICKSTART.md) and
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) before preparing a public preview.
