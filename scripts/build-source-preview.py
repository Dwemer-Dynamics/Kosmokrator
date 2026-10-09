"""Build an explicit, hashed local source preview without workspace/game data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    files = [root / n for n in ("README.md", "AGENTS.md", "pyproject.toml", ".gitignore", "start.ps1")]
    for folder, patterns in {
        "kosmokrator": ("*.py",), "kosmokrator/web": ("*.html", "*.js", "*.css", "*.svg"),
        "kosmokrator/demo_assets": ("*.tga",), "kosmokrator/demo_assets/pretenders": ("*.png",),
        "docs": ("*.md",), "examples": ("*.json", "*.toml"), "tests": ("*.py",),
    }.items():
        for pattern in patterns:
            files.extend((root / folder).glob(pattern))
    files.append(root / "docs/images/get-started.png")
    files.append(Path(__file__).resolve())
    # Existing packaged-art regression checks compare these independent source checksums.
    files.append(root / "assets/hebdomad-pretenders/asset-manifest.json")
    files.extend(p for p in (root / "LICENSE", root / "NOTICE") if p.is_file())
    payload: dict[str, bytes] = {}
    for path in sorted(set(files)):
        relative = path.relative_to(root)
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
            raise SystemExit(f"Refusing linked source: {relative}")
        data = path.read_bytes()
        if path.suffix not in (".png", ".tga"):
            lowered = data.lower().replace(b"\\\\", b"/").replace(b"\\", b"/")
            if Path.home().as_posix().lower().encode() in lowered:
                raise SystemExit(f"Personal path found: {relative}")
        payload[relative.as_posix()] = data
    pending = not (root / "LICENSE").is_file()
    payload["PREVIEW-STATUS.txt"] = (
        "Local source preview; not a published release.\n"
        + ("Source license undecided.\n" if pending else "Original source code: GPL-3.0-only. See LICENSE and third-party notices for scope.\n")
        + "Source licensing does not settle original-art or third-party resource terms.\n"
        + "Static tooling checks do not establish game loading, gameplay or balance.\n"
        + "Local projects, expanded showcase art/maps, extracted game icons and catalogs are excluded.\n"
    ).encode()
    manifest = {"schema": 1, "license_pending": pending,
                "source_license": None if pending else "GPL-3.0-only",
                "asset_terms": "See docs/THIRD-PARTY-NOTICES.md", "published": False, "files": [
        {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in sorted(payload.items())]}
    payload["source-manifest.json"] = json.dumps(manifest, indent=2).encode() + b"\n"
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo("Kosmokrator/" + name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for name, data in payload.items():
            assert archive.read("Kosmokrator/" + name) == data
    print(json.dumps({"archive": str(output), "files": len(payload),
                      "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                      "license_pending": pending, "published": False}, indent=2))


if __name__ == "__main__":
    main()
