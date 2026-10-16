"""Focused tests: lossless patching, path containment, validation and export guards.

Run: .venv/Scripts/python.exe -m unittest discover -s tests -v
Uses a tiny synthetic catalog, so no game data or network is needed.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

from kosmokrator import paths as paths_mod
from kosmokrator import project as project_mod
from kosmokrator.catalog import load_catalog
from kosmokrator.errors import KosmoError
from kosmokrator.export import export_mod
from kosmokrator.images import image_info
from kosmokrator.project import allocate_ids, apply_mod_patch, create_project, inspect_mod, open_project
from kosmokrator.tga import encode_tga
from kosmokrator.validate import validate_project


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write_catalog(root: Path) -> Path:
    g = root / "gamedata"
    g.mkdir(parents=True)
    tables = {
        "BaseU.csv": "id\tname\tholy\tF\tE\tH\tmask1\n199\tCardaces\t\t\t\t\t\n311\tMystic\t\t\t\t\t3712\n",
        "MagicSites.csv": "id\tname\tpath\tlevel\trarity\n1\tThe Smouldercone\tFire\t0\t5\n",
        "nations.csv": "id\tname\tepithet\tera\n5\tArcoscephale\tGolden Era\t1\n",
        "weapons.csv": "id\tname\n1\tSpear\n",
        "armors.csv": "id\tname\n1\tBuckler\n",
        "spells.csv": "id\tname\n1\tMinor Area Shock\n",
        "BaseI.csv": "id\tname\n1\tFire Sword\n",
    }
    for name, text in tables.items():
        (g / name).write_text(text, encoding="utf-8")
    return root


def tiny_tga(w: int = 128, h: int = 128) -> bytes:
    return encode_tga(w, h, [[(200, 50, 20, 255)] * w for _ in range(h)])


_MODS = tempfile.TemporaryDirectory()
_ENV = mock.patch.dict(os.environ, {"KOSMOKRATOR_DOMINIONS_MODS": str(Path(_MODS.name).resolve())})


def setUpModule() -> None:
    # Allocation scans installed mods; point it at an empty folder so a real game install never leaks in.
    _ENV.start()


def tearDownModule() -> None:
    _ENV.stop()
    _MODS.cleanup()


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name).resolve() / "ws"
        self.ws.mkdir()
        self.catalog = load_catalog(write_catalog(Path(self._tmp.name) / "cat"))
        create_project(self.ws, "demo_mod")
        self.dm = self.ws / "demo_mod" / "mod" / "demo_mod" / "demo_mod.dm"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def set_dm(self, data: bytes) -> str:
        self.dm.write_bytes(data)
        return sha(data)


class PatchTests(Base):
    def test_replace_preserves_untouched_bytes_crlf_latin1(self) -> None:
        original = b'-- caf\xe9 comment\r\n#modname "X"\r\n#description "d"\r\n#version 1.00\r\n'
        h = self.set_dm(original)
        res = apply_mod_patch(self.ws, "demo_mod", h, old="#version 1.00", new="#version 1.01\n-- added")
        data = self.dm.read_bytes()
        self.assertEqual(data, original.replace(b"#version 1.00", b"#version 1.01\r\n-- added"))
        self.assertEqual(res["after_sha256"], sha(data))
        backup = self.ws / "demo_mod" / res["backup"]
        self.assertEqual(backup.read_bytes(), original)

    def test_insert_appends_without_touching_last_line(self) -> None:
        original = b'#modname "X"\n#description "d"'  # no trailing newline
        h = self.set_dm(original)
        apply_mod_patch(self.ws, "demo_mod", h, insert_line=3, text="#version 1.00\n")
        self.assertEqual(self.dm.read_bytes(), original + b"\n#version 1.00\n")

    def test_replace_requires_unique_match_and_current_hash(self) -> None:
        h = self.set_dm(b"#end\n#end\n")
        with self.assertRaises(KosmoError) as cm:
            apply_mod_patch(self.ws, "demo_mod", h, old="#end", new="#x")
        self.assertEqual(cm.exception.code, "patch_not_unique")
        with self.assertRaises(KosmoError) as cm:
            apply_mod_patch(self.ws, "demo_mod", "0" * 64, old="#end\n#end", new="")
        self.assertEqual(cm.exception.code, "sha_mismatch")
        self.assertEqual(self.dm.read_bytes(), b"#end\n#end\n")

    def test_patch_target_cannot_escape(self) -> None:
        h = sha(self.dm.read_bytes())
        for bad in ("../../kosmokrator.json", "../other/x.dm", str(self.ws / "x.dm")):
            with self.assertRaises(KosmoError) as cm:
                apply_mod_patch(self.ws, "demo_mod", h, insert_line=1, text="#x\n", file=bad)
            self.assertIn(cm.exception.code, ("path_escape", "bad_target"))

    def _dir_link(self, target: Path, link: Path) -> None:
        """Directory symlink, or a Windows junction when symlinks need extra privileges."""
        try:
            os.symlink(target, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            try:
                import _winapi
                _winapi.CreateJunction(str(target), str(link))
            except (ImportError, OSError):
                self.skipTest("neither symlinks nor junctions can be created here")

    def test_linked_paths_rejected(self) -> None:
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        (outside / "flag.tga").write_bytes(tiny_tga())
        self._dir_link(outside, self.ws / "linked")
        with self.assertRaises(KosmoError) as cm:
            create_project(self.ws, "linked")
        self.assertIn(cm.exception.code, ("symlink_rejected", "path_escape"))
        self._dir_link(outside, self.dm.parent / "art")
        self.set_dm(b'#modname "X"\n#selectnation 150\n#name "N"\n#flag "art/flag.tga"\n#end\n')
        r = validate_project(self.ws, "demo_mod", catalog=self.catalog)
        codes = {i["code"] for i in r["errors"]}
        self.assertIn("symlink_in_mod", codes)
        self.assertIn("asset_symlink", codes)
        with self.assertRaises(KosmoError) as cm:
            export_mod(self.ws, "demo_mod", catalog=self.catalog)
        self.assertEqual(cm.exception.code, "validation_failed")

    def test_default_dm_symlink_rejected(self) -> None:
        outside = Path(self._tmp.name) / "outside.dm"
        outside.write_bytes(b"#newmonster 5000\n#end\n")
        self.dm.unlink()
        stack = contextlib.ExitStack()
        try:
            os.symlink(outside, self.dm)
        except (OSError, NotImplementedError):
            # No symlink privilege: keep a real file and make the link probe report it as linked.
            self.dm.write_bytes(outside.read_bytes())
            real = paths_mod.is_link
            fake = lambda p: Path(p) == self.dm or real(p)  # noqa: E731
            stack.enter_context(mock.patch.object(paths_mod, "is_link", fake))
            stack.enter_context(mock.patch.object(project_mod, "is_link", fake))
        with stack:
            for call in (lambda: inspect_mod(self.ws, "demo_mod"),
                         lambda: allocate_ids(self.ws, "demo_mod", "monster", 1),
                         lambda: validate_project(self.ws, "demo_mod"),
                         lambda: apply_mod_patch(self.ws, "demo_mod", sha(outside.read_bytes()), insert_line=1,
                                                 text="#x\n")):
                with self.assertRaises(KosmoError) as cm:
                    call()
                self.assertEqual(cm.exception.code, "symlink_rejected")
        self.assertEqual(outside.read_bytes(), b"#newmonster 5000\n#end\n")

    def test_linked_backups_dir_rejected_before_write(self) -> None:
        outside = Path(self._tmp.name) / "outside_backup"
        outside.mkdir()
        backups = self.ws / "demo_mod" / ".kosmokrator" / "backups"
        backups.rmdir()
        self._dir_link(outside, backups)
        original = self.dm.read_bytes()
        with self.assertRaises(KosmoError) as cm:
            apply_mod_patch(self.ws, "demo_mod", sha(original), insert_line=1, text="-- x\n")
        self.assertEqual(cm.exception.code, "symlink_rejected")
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(self.dm.read_bytes(), original)

    def test_preplanted_temp_link_not_followed(self) -> None:
        outside = Path(self._tmp.name) / "victim.txt"
        outside.write_bytes(b"untouched")
        planted = self.dm.with_name(f".{self.dm.name}.tmp-{os.getpid()}")  # the old predictable temp name
        try:
            os.symlink(outside, planted)
        except (OSError, NotImplementedError):
            planted.write_bytes(b"planted")  # no symlink privilege: a preplanted regular file must survive too
        apply_mod_patch(self.ws, "demo_mod", sha(self.dm.read_bytes()), insert_line=1, text="-- x\n")
        self.assertEqual(outside.read_bytes(), b"untouched")
        if not os.path.islink(planted):
            self.assertEqual(planted.read_bytes(), b"planted")
        self.assertTrue(self.dm.read_bytes().startswith(b"-- x\n"))
        leftovers = [n.name for n in self.dm.parent.iterdir() if n.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_create_refuses_overwrite(self) -> None:
        with self.assertRaises(KosmoError) as cm:
            create_project(self.ws, "demo_mod")
        self.assertEqual(cm.exception.code, "project_exists")


class ValidationTests(Base):
    def codes(self, text: str) -> dict[str, set[str]]:
        self.set_dm(text.encode("utf-8"))
        r = validate_project(self.ws, "demo_mod", catalog=self.catalog)
        return {sev: {i["code"] for i in r[sev]} for sev in ("errors", "warnings", "unverified")}

    def test_syntax_context_ranges_and_refs(self) -> None:
        c = self.codes(
            '#modname "X"\n#hp 10\n'
            '#newmonster 5000\n#copystats 199\n#name "A"\n#magicskill 12 1\n#custommagic 65536 100\n'
            '#weapon "No Such Blade"\n#startsite "Somewhere"\n#frobnicate 3\n#end\n'
            '#selectnation 150\n#name "N"\n#startsite 1\n#startsite "Nowhere"\n#era 7\n#end\n'
            '#newsite 1700\n#name "S"\n#homecom 9999\n'
        )
        e = c["errors"]
        for code in ("needs_block", "out_of_range", "priest_only_mask", "unresolved_reference", "wrong_context",
                     "bad_argument", "syntax"):
            self.assertIn(code, e)
        self.assertIn("unknown_command", c["unverified"])

    def test_duplicates_and_catalog_collision(self) -> None:
        c = self.codes('#newmonster 199\n#name "Dup"\n#end\n#newmonster 5000\n#name "Dup"\n#end\n'
                       '#newmonster 5000\n#name "Other"\n#end\n')
        self.assertIn("id_in_use", c["errors"])
        self.assertIn("out_of_range", c["errors"])
        self.assertIn("duplicate_definition", c["errors"])
        self.assertIn("duplicate_name", c["warnings"])

    def test_startsite_resolves_project_site_by_name(self) -> None:
        allocate_ids(self.ws, "demo_mod", "site", 1, catalog=self.catalog)
        allocate_ids(self.ws, "demo_mod", "nation", 1, catalog=self.catalog)
        c = self.codes('#newsite 1700\n#name "Forge Below"\n#gems 0 1\n#end\n'
                       '#selectnation 150\n#name "N"\n#startsite "forge below"\n#startsite "The Smouldercone"\n#end\n')
        self.assertEqual(c["errors"], set())

    def test_assets_case_traversal_and_header(self) -> None:
        mod = self.dm.parent
        (mod / "art").mkdir()
        (mod / "art" / "Flag.tga").write_bytes(tiny_tga())
        (mod / "art" / "bad.tga").write_bytes(b"\x00\x00\x01" + b"\x00" * 30)
        (mod / "art" / "small.tga").write_bytes(tiny_tga(64, 64))
        base = '#selectnation 150\n#name "N"\n#flag "{}"\n#end\n'
        self.assertIn("asset_case_mismatch", self.codes(base.format("art/flag.tga"))["errors"])
        self.assertIn("bad_asset_path", self.codes(base.format("../outside.tga"))["errors"])
        self.assertIn("bad_asset_path", self.codes(base.format("art\\Flag.tga"))["errors"])
        self.assertIn("bad_image", self.codes(base.format("art/bad.tga"))["errors"])
        self.assertIn("flag_size", self.codes(base.format("art/small.tga"))["errors"])
        self.assertIn("asset_missing", self.codes(base.format("art/none.tga"))["errors"])
        self.assertNotIn("asset_case_mismatch", self.codes(base.format("art/Flag.tga"))["errors"])


class ReservationTests(Base):
    def test_stale_snapshot_does_not_lose_reservations(self) -> None:
        stale = open_project(self.ws, "demo_mod")
        self.assertEqual(allocate_ids(self.ws, "demo_mod", "monster", 1)["ids"], [5000])
        with mock.patch.object(project_mod, "open_project", return_value=stale):
            self.assertEqual(allocate_ids(self.ws, "demo_mod", "monster", 1)["ids"], [5001])
        meta = open_project(self.ws, "demo_mod").meta
        self.assertEqual([r["id"] for r in meta["reservations"]["monster"]], [5000, 5001])

    def test_foreign_lock_is_not_removed(self) -> None:
        lock = self.ws / "demo_mod" / ".kosmokrator" / "lock"
        lock.write_text("someone-else")
        with self.assertRaises(KosmoError) as cm:
            allocate_ids(self.ws, "demo_mod", "monster", 1)
        self.assertEqual(cm.exception.code, "project_locked")
        self.assertEqual(lock.read_text(), "someone-else")

    def sibling(self, dm: bytes, reservations: dict | None = None) -> tuple[bytes, bytes]:
        create_project(self.ws, "other_mod")
        root = self.ws / "other_mod"
        (root / "mod" / "other_mod" / "other_mod.dm").write_bytes(dm)
        meta = json.loads((root / "kosmokrator.json").read_text("utf-8"))
        meta["reservations"] = reservations or {}
        (root / "kosmokrator.json").write_text(json.dumps(meta), "utf-8")
        return (root / "kosmokrator.json").read_bytes(), dm

    def test_sibling_projects_and_installed_mods_are_avoided_read_only(self) -> None:
        before = self.sibling(b"#newmonster 5000\n#end\n#newsite 1700\n#end\n",
                              {"monster": [{"id": 5001, "label": None, "reserved_utc": "x"}]})
        (self.ws / "broken_mod").mkdir()
        (self.ws / "broken_mod" / "kosmokrator.json").write_text("{", "utf-8")
        mods = Path(self._tmp.name) / "mods"
        (mods / "installed").mkdir(parents=True)
        (mods / "installed" / "installed.dm").write_bytes(b"#newmonster 5002\n#end\n")
        (mods / "loose.dm").write_bytes(b"#newweapon 1000\n#end\n")
        with mock.patch.dict(os.environ, {"KOSMOKRATOR_DOMINIONS_MODS": str(mods)}):
            res = allocate_ids(self.ws, "demo_mod", "monster", 2)
            self.assertEqual(allocate_ids(self.ws, "demo_mod", "site", 1)["ids"], [1701])
            self.assertEqual(allocate_ids(self.ws, "demo_mod", "weapon", 1)["ids"], [1001])
        self.assertEqual(res["ids"], [5003, 5004])  # lowest-first: sibling 5000/5001, installed 5002
        checked = res["checked"]
        self.assertEqual((checked["selection"], checked["workspace_projects"]), ("lowest", ["other_mod"]))
        self.assertEqual(checked["installed_mods"]["dm_files"], 2)
        self.assertFalse(checked["complete"])  # the unreadable project is disclosed, not treated as checked
        self.assertEqual(checked["unreadable"][0]["source"], "project:broken_mod")
        self.assertTrue(any("could not be read" in c for c in res["caveats"]))
        root = self.ws / "other_mod"
        self.assertEqual(before, ((root / "kosmokrator.json").read_bytes(),
                                  (root / "mod" / "other_mod" / "other_mod.dm").read_bytes()))
        self.assertEqual((mods / "installed" / "installed.dm").read_bytes(), b"#newmonster 5002\n#end\n")

    def test_nation_ids_are_random_and_exhaustion_is_refused(self) -> None:
        import random
        self.sibling(b"#selectnation 150\n#end\n")
        free = list(range(151, 500))
        with mock.patch.object(project_mod, "_NATION_RNG", random.Random(7)):
            res = allocate_ids(self.ws, "demo_mod", "nation", 3, catalog=self.catalog)
        self.assertEqual(res["ids"], sorted(random.Random(7).sample(free, 3)))
        self.assertEqual(res["checked"]["selection"], "random")
        self.assertTrue(any("cannot eliminate" in c for c in res["caveats"]))
        no_rng = mock.Mock(sample=mock.Mock(side_effect=AssertionError("non-nation kinds must not sample")))
        with mock.patch.object(project_mod, "_NATION_RNG", no_rng):
            self.assertEqual(allocate_ids(self.ws, "demo_mod", "site", 2)["ids"], [1700, 1701])
        left = [i for i in free if i not in res["ids"]]
        taken = [{"id": i, "label": None, "reserved_utc": "x"} for i in left[2:]]
        meta_path = self.ws / "other_mod" / "kosmokrator.json"
        meta = json.loads(meta_path.read_text("utf-8"))
        meta_path.write_text(json.dumps({**meta, "reservations": {"nation": taken}}), "utf-8")
        with self.assertRaises(KosmoError) as cm:
            allocate_ids(self.ws, "demo_mod", "nation", 3)
        self.assertEqual(cm.exception.code, "range_exhausted")
        self.assertEqual(allocate_ids(self.ws, "demo_mod", "nation", 2)["ids"], left[:2])


class ExportTests(Base):
    def test_export_refuses_errors_and_overwrite_and_self(self) -> None:
        self.set_dm(b'#modname "X"\n#newmonster 5000\n')  # unclosed block
        with self.assertRaises(KosmoError) as cm:
            export_mod(self.ws, "demo_mod", catalog=self.catalog)
        self.assertEqual(cm.exception.code, "validation_failed")

        mod = self.dm.parent
        (mod / "art").mkdir()
        (mod / "art" / "flag.tga").write_bytes(tiny_tga())
        allocate_ids(self.ws, "demo_mod", "nation", 1, catalog=self.catalog)
        self.set_dm(b'#modname "X"\r\n#selectnation 150\r\n#name "N"\r\n#flag "art/flag.tga"\r\n#end\r\n')
        res = export_mod(self.ws, "demo_mod", dest="out.zip", catalog=self.catalog)
        with zipfile.ZipFile(self.ws / "out.zip") as zf:
            self.assertEqual(sorted(zf.namelist()), ["demo_mod/art/flag.tga", "demo_mod/demo_mod.dm"])
            self.assertEqual(zf.read("demo_mod/demo_mod.dm"), self.dm.read_bytes())
        self.assertTrue((self.ws / "out.zip.manifest.json").is_file())
        self.assertEqual(res["manifest"]["archive_sha256"], sha((self.ws / "out.zip").read_bytes()))
        for dest, code in (("out.zip", "dest_exists"), ("demo_mod/mod/demo_mod/x.zip", "self_export"),
                           ("../escape.zip", "path_escape")):
            with self.assertRaises(KosmoError) as cm:
                export_mod(self.ws, "demo_mod", dest=dest, catalog=self.catalog)
            self.assertEqual(cm.exception.code, code)


class InspectTests(Base):
    def test_unknown_commands_retained_verbatim(self) -> None:
        self.set_dm(b'#modname "X"\n#newevent\n#weird 1 "two"\n#end\n#mystery  42 -- c\n')
        r = inspect_mod(self.ws, "demo_mod")
        raws = [u["raw"] for u in r["unverified_commands"]]
        self.assertIn("#mystery  42", raws)
        self.assertIn('#weird 1 "two"', raws)
        self.assertEqual(r["syntax_issues"], [])


class EditTests(Base):
    def test_web_edit_preserves_bytes_and_refuses_unsafe_changes(self) -> None:
        from kosmokrator.edit import apply_edit
        original = (b'-- caf\xe9\r\n#newmonster 5000\r\n#copystats 1\r\n#name "M"\r\n#hp 9 -- note\r\n#mystery 3\r\n'
                    b'#clearspec\r\n#flying\r\n#end\r\n#newmonster 5001\r\n#hp 1\r\n#hp 2\r\n#end\r\n')
        h = self.set_dm(original)

        def edit(mid: int, changes: list, digest: str, preview: bool = False) -> dict:
            return apply_edit(self.ws, "demo_mod", mid, None, {"expected_sha256": digest, "changes": changes,
                                                               "preview": preview})
        for mid, changes, code in [
                (5000, [{"key": "flying", "op": "set", "value": 0}], "bad_value"),
                (5000, [{"key": "female", "op": "remove"}], "edit_blocked"),
                (5001, [{"key": "hp", "op": "set", "value": 3}], "edit_blocked")]:  # duplicate #hp
            with self.assertRaises(KosmoError) as cm:
                edit(mid, changes, h)
            self.assertEqual(cm.exception.code, code)
        with self.assertRaises(KosmoError) as cm:
            edit(5000, [{"key": "hp", "op": "set", "value": 3}], "0" * 64)
        self.assertEqual(cm.exception.code, "sha_mismatch")
        edit(5000, [{"key": "hp", "op": "set", "value": 3}], h, preview=True)
        self.assertEqual(self.dm.read_bytes(), original)
        res = edit(5000, [{"key": "hp", "op": "set", "value": 12}, {"key": "flying", "op": "remove"},
                          {"key": "fireres", "op": "set", "value": 5}], h)
        self.assertEqual(self.dm.read_bytes(), original.replace(b"#hp 9 -- note", b"#hp 12 -- note")
                         .replace(b"#flying\r\n#end\r\n#newmonster 5001", b"#fireres 5\r\n#end\r\n#newmonster 5001"))
        self.assertEqual((self.ws / "demo_mod" / res["backup"]).read_bytes(), original)


def png_bytes(w: int, h: int, depth: int = 8, ctype: int = 6, rest: bytes = b"\x00\x00\x00") -> bytes:
    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBB", w, h, depth, ctype) + rest) + chunk(b"IEND", b"")


class PngTests(unittest.TestCase):
    def problems(self, data: bytes) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.png"
            f.write_bytes(data)
            return image_info(f)["problems"]

    def test_ihdr_validation(self) -> None:
        self.assertEqual(self.problems(png_bytes(128, 128)), [])
        self.assertEqual(self.problems(png_bytes(4, 4, depth=2, ctype=3, rest=b"\x00\x00\x01")), [])
        for bad in (png_bytes(0, 128), png_bytes(128, 0), png_bytes(4, 4, depth=4, ctype=6),
                    png_bytes(4, 4, ctype=5), png_bytes(4, 4, rest=b"\x01\x00\x00"),
                    png_bytes(4, 4, rest=b"\x00\x01\x00"), png_bytes(4, 4, rest=b"\x00\x00\x02")):
            self.assertTrue(self.problems(bad), bad[16:29])


class CatalogTests(unittest.TestCase):
    def test_dataset_version_extracted_or_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            known = write_catalog(Path(d) / "known")
            (known / "index.html").write_text('<a href="x">[ver 6.37]</a>', encoding="utf-8")
            self.assertEqual(load_catalog(known).meta["dataset_version"], "6.37")
            unknown = load_catalog(write_catalog(Path(d) / "unknown")).meta
            self.assertIsNone(unknown["dataset_version"])
            self.assertIn("unknown", unknown["dataset_version_source"])


class TgaTests(unittest.TestCase):
    def test_header(self) -> None:
        b = tiny_tga(16, 8)
        self.assertEqual(b[2], 2)
        self.assertEqual(struct.unpack("<HH", b[12:16]), (16, 8))
        self.assertEqual(b[16], 32)
        self.assertEqual(len(b), 18 + 16 * 8 * 4)



class DemoTests(unittest.TestCase):
    def test_demo_ships_packaged_pretender_frames(self) -> None:
        import json
        from kosmokrator import demo
        repo = Path(__file__).resolve().parents[1]
        manifest = json.loads((repo / "assets" / "hebdomad-pretenders" / "asset-manifest.json").read_text("utf-8"))
        expected = {Path(f["file"]).name: f["sha256"] for u in manifest["units"] for f in u["frames"].values()}
        self.assertEqual(sorted(p.name for p in demo.PRETENDER_ART_DIR.iterdir()), sorted(expected))
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d).resolve()
            demo.build_demo(ws)
            mod = ws / "hebdomad" / "mod" / "hebdomad"
            for name, digest in expected.items():
                self.assertEqual(sha((mod / "art" / "pretenders" / name).read_bytes()), digest)
            text = (mod / "hebdomad.dm").read_text("utf-8")
        self.assertEqual(text.count("#copyspr"), 11)
        self.assertEqual(text.count('#spr1 "art/pretenders/'), 2)
        demiurge = text.split("#newmonster 5011", 1)[1].split("#end", 1)[0]
        self.assertIn("#clearweapons\n#weapon 11\n#cleararmor\n#armor 100\n", demiurge)


def rgba_png(w: int, h: int, alpha: int = 255, filt: int = 0) -> bytes:
    """Real 8-bit RGBA PNG: transparent top row over an opaque block (filt=5 writes an invalid filter byte)."""
    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    rows = b"".join(bytes([filt]) + (bytes(4 * w) if y == 0 else bytes([90, 60, 30, alpha]) * w) for y in range(h))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


class AuthorTests(Base):
    """Create/duplicate/nation/art transactions: ids, stale hashes, rollback and file containment."""
    SRC = (b'#newmonster 5000\n#copystats 199\n#copyspr 199\n#name "Spear"\n#mystery 7 -- keep\n#end\n'
           b'#newmonster 5001\n#copystats 311\n#name "Mage"\n#spr1 "art/old1.png"\n#spr2 "art/old2.png"\n'
           b'#startdom 2\n#pathcost 40\n#end\n'
           b'#newsite 1700\n#name "Hall"\n#end\n'
           b'#selectnation 150\n#name "A"\n#epithet "E"\n#era 1\n#startsite "Hall"\n#end\n')

    def setUp(self) -> None:
        super().setUp()
        self.h = self.set_dm(self.SRC)
        self.mod = self.dm.parent

    def mk(self, **body):
        from kosmokrator.author import create_monster
        return create_monster(self.ws, "demo_mod", self.catalog, {"expected_sha256": self.h, **body})

    def test_create_duplicate_nation_and_stale(self) -> None:
        from kosmokrator.author import create_nation
        pv = self.mk(mode="new", role="troop", donor={"source": "catalog", "id": 199}, name="Pike", nation=150,
                     recruit="fort", preview=True)
        self.assertFalse(pv["written"])
        self.assertEqual(self.dm.read_bytes(), self.SRC)
        r = self.mk(mode="new", role="commander", donor={"source": "catalog", "id": 311}, name="Seer",
                    nation=150, recruit="site", site=1700)
        self.assertEqual(r["id"], 5002)
        text = self.dm.read_text("utf-8")
        self.assertTrue(text.startswith(self.SRC.decode().split("#newsite")[0]))
        self.assertIn('#newsite 1700\n#name "Hall"\n#homecom 5002\n#end', text)
        self.assertIn('#newmonster 5002\n#copystats 311\n#copyspr 311\n#name "Seer"\n#end', text)
        with self.assertRaises(KosmoError) as cm:  # stale hash: refused, nothing written
            self.mk(mode="new", role="troop", donor={"source": "catalog", "id": 199}, name="X", nation=150,
                    recruit="fort")
        self.assertEqual(cm.exception.code, "sha_mismatch")
        self.h = sha(self.dm.read_bytes())
        self.mk(mode="duplicate", role="god", source_id=5001, name="Mage Two", nation=150)
        text = self.dm.read_text("utf-8")
        block = text.split("#newmonster 5003\n", 1)[1].split("#end", 1)[0]
        self.assertEqual(block, '#copystats 311\n#name "Mage Two"\n#spr1 "art/old1.png"\n#spr2 "art/old2.png"\n'
                                '#startdom 2\n#pathcost 40\n')
        self.assertIn("#addgod 5003\n#end", text)
        self.h = sha(self.dm.read_bytes())
        self.mk(mode="duplicate", role="none", source_id=5000, name="Spear B")
        self.assertIn("#mystery 7 -- keep\n#end\n", self.dm.read_text("utf-8").split("#newmonster 5004", 1)[1])
        self.h = sha(self.dm.read_bytes())
        with self.assertRaises(KosmoError):  # a new god needs #startdom and #pathcost
            self.mk(mode="new", role="god", donor={"source": "catalog", "id": 311}, name="G", nation=150, god={})
        g = self.mk(mode="new", role="god", donor={"source": "catalog", "id": 311}, name="G", nation=150,
                    god={"startdom": 2, "pathcost": 60, "magic": {"F": 2}})
        self.assertIn("#homerealm 0\n#startdom 2\n#pathcost 60\n#magicskill 0 2\n#end", self.dm.read_text("utf-8"))
        meta = json.loads((self.ws / "demo_mod" / "kosmokrator.json").read_text("utf-8"))
        self.assertEqual([x["id"] for x in meta["reservations"]["monster"]], [5002, 5003, 5004, g["id"]])
        self.h = sha(self.dm.read_bytes())
        body = {"expected_sha256": self.h, "name": "B", "epithet": "Second", "era": 2, "sites": [1700],
                "troops": [5000], "commanders": [5002], "gods": [5003], "startcom": [5002],
                "startunits": [{"id": 5000, "count": 10}], "realms": [10]}
        pv = create_nation(self.ws, "demo_mod", self.catalog, {**body, "preview": True})
        n = create_nation(self.ws, "demo_mod", self.catalog, body)
        nid = n["id"]
        self.assertEqual(pv["id"], nid)  # the preview shows the id the create then writes
        self.assertTrue(150 < nid <= 499)
        self.assertEqual(n["id_checks"]["nation"]["checked"]["selection"], "random")
        self.assertIn(f'#selectnation {nid}\n#name "B"\n#epithet "Second"\n#era 2\n#clearnation\n#flag "art/nations/{nid}-flag.tga"\n#startsite "Hall"\n'
                      '#homerealm 10\n#addgod 5003\n#addrecunit 5000\n#addreccom 5002\n#startcom 5002\n'
                      '#startunittype1 5000\n#startunitnbrs1 10\n#end', self.dm.read_text("utf-8"))

    def test_failed_write_rolls_back_reservation_and_skips_collisions(self) -> None:
        meta_path = self.ws / "demo_mod" / "kosmokrator.json"
        meta = json.loads(meta_path.read_text("utf-8"))
        meta["reservations"] = {"monster": [{"id": 5002, "label": "elsewhere", "reserved_utc": "x"}]}
        meta_path.write_text(json.dumps(meta), "utf-8")
        before = json.loads(meta_path.read_text("utf-8"))
        body = dict(mode="new", role="troop", donor={"source": "catalog", "id": 199}, name="P", nation=150,
                    recruit="fort")
        with mock.patch("kosmokrator.author.write_dm_locked", side_effect=OSError("disk full")):
            with self.assertRaises(KosmoError) as cm:
                self.mk(**body)
        self.assertEqual(cm.exception.code, "write_failed")
        self.assertEqual(self.dm.read_bytes(), self.SRC)
        self.assertEqual(json.loads(meta_path.read_text("utf-8")), before)
        self.assertEqual(self.mk(**body)["id"], 5003)  # 5000/5001 defined, 5002 reserved

    def test_art_upload_validation_patch_and_export(self) -> None:
        from kosmokrator.author import upload_art
        from kosmokrator.export import export_revision
        (self.mod / "art").mkdir()
        old = rgba_png(64, 64)
        (self.mod / "art" / "old1.png").write_bytes(old)
        (self.mod / "art" / "old2.png").write_bytes(old)

        def up(mid, frames, digest=None):
            return upload_art(self.ws, "demo_mod", mid, self.catalog, {
                "expected_sha256": digest or self.h,
                "frames": {k: base64.b64encode(v).decode() for k, v in frames.items()}})
        good = rgba_png(64, 64)
        forged = good[:-20] + b"\x00" * 8 + good[-12:]  # IDAT bytes changed, CRC no longer matches
        for frames, code in [({"idle": rgba_png(64, 64, alpha=128)}, "bad_png"), ({"idle": forged}, "bad_png"),
                             ({"idle": rgba_png(300, 8)}, "bad_png"), ({"idle": png_bytes(64, 64)}, "bad_png"),
                             ({"idle": rgba_png(8, 8, filt=5)}, "bad_png"), ({"idle": bytes(64)}, "bad_png"),
                             ({"idle": good}, "edit_blocked")]:  # 5000 uses #copyspr: both frames needed
            with self.assertRaises(KosmoError) as cm:
                up(5000, frames)
            self.assertEqual(cm.exception.code, code)
        with self.assertRaises(KosmoError) as cm:
            up(5000, {"idle": good, "attack": good}, digest="0" * 64)
        self.assertEqual(cm.exception.code, "sha_mismatch")
        self.assertEqual(self.dm.read_bytes(), self.SRC)
        self.assertFalse((self.mod / "art" / "units").exists())
        r = up(5000, {"idle": good, "attack": good})
        text = self.dm.read_text("utf-8")
        self.assertNotIn("#copyspr", text.split("#newmonster 5001")[0])
        self.assertIn(f'#spr1 "{r["files"][0]}"', text)
        self.assertTrue(r["files"][0].startswith("art/units/5000-") and r["files"][0].endswith("-idle.png"))
        self.assertEqual((self.mod / r["files"][0]).read_bytes(), good)
        self.h = sha(self.dm.read_bytes())
        r2 = up(5001, {"attack": good})  # pretender form: one frame replaced, old files kept
        text = self.dm.read_text("utf-8")
        self.assertTrue(r2["files"][0].startswith("art/pretenders/5001-"))
        self.assertIn('#spr1 "art/old1.png"', text)
        self.assertIn(f'#spr2 "{r2["files"][0]}"', text)
        self.assertEqual((self.mod / "art" / "old2.png").read_bytes(), old)
        self.h = sha(self.dm.read_bytes())
        before = sorted(p.name for p in (self.mod / "art" / "units").iterdir())
        with mock.patch("kosmokrator.author.write_dm_locked", side_effect=OSError("disk full")):
            with self.assertRaises(KosmoError):
                up(5000, {"idle": good})
        self.assertEqual(sorted(p.name for p in (self.mod / "art" / "units").iterdir()), before)
        ex = export_revision(self.ws, "demo_mod", self.h, "zip", self.catalog)
        with zipfile.ZipFile(self.ws / "demo_mod" / ex["path"]) as z:
            packed = {n.split("/", 1)[-1]: z.read(n) for n in z.namelist()}
        self.assertEqual(sha(next(v for k, v in packed.items() if k.endswith(Path(r["files"][0]).name))), sha(good))

    def test_art_folder_link_rejected(self) -> None:
        from kosmokrator.author import upload_art
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        try:
            os.symlink(outside, self.mod / "art", target_is_directory=True)
        except (OSError, NotImplementedError):
            import subprocess
            if subprocess.run(["cmd", "/c", "mklink", "/J", str(self.mod / "art"), str(outside)],
                              capture_output=True).returncode:
                self.skipTest("cannot create a directory link here")
        with self.assertRaises(KosmoError) as cm:
            upload_art(self.ws, "demo_mod", 5001, self.catalog, {
                "expected_sha256": self.h, "frames": {"idle": base64.b64encode(rgba_png(64, 64)).decode()}})
        self.assertIn(cm.exception.code, ("symlink_rejected", "path_escape"))
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(self.dm.read_bytes(), self.SRC)


class NationEditTests(Base):
    """Existing-nation editor: lossless spans, inherited/ambiguous refusals, stale hash, hostile input."""
    SRC = (b'-- caf\xe9\r\n#newmonster 5000\r\n#copystats 199\r\n#name "Spear"\r\n#end\r\n'
           b'#newmonster 5001\r\n#copystats 311\r\n#name "Seer"\r\n#end\r\n'
           b'#newsite 1700\r\n#name "Hall"\r\n#homecom 5001\r\n#end\r\n'
           b'#selectnation 150\r\n#name "A"\r\n#era 1\r\n#clearnation\r\n#addrecunit 5000\r\n#clearrec\r\n'
           b'#flag "art/f.tga" -- keep\r\n#addrecunit 199 -- vanilla ok\r\n#addreccom 5001\r\n#addreccom 5001\r\n'
           b'#startscout 5000\r\n#defcom1 5001\r\n#mystery 3\r\n#end\r\n'
           b'#selectnation 5\r\n#addrecunit 199\r\n#addrecunit 5000\r\n#homerealm 3\r\n#end\r\n')

    def setUp(self) -> None:
        super().setUp()
        self.h = self.set_dm(self.SRC)

    def edit(self, nid: int, changes: list, preview: bool = False, digest: str | None = None) -> dict:
        from kosmokrator.nation_edit import apply_nation_edit
        return apply_nation_edit(self.ws, "demo_mod", nid, self.catalog,
                                 {"expected_sha256": digest or self.h, "changes": changes, "preview": preview})

    def code(self, nid: int, changes: list) -> str:
        with self.assertRaises(KosmoError) as cm:
            self.edit(nid, changes)
        self.assertEqual(self.dm.read_bytes(), self.SRC)
        return cm.exception.code

    def test_lossless_add_remove_and_start_army(self) -> None:
        ch = [{"field": "epithet", "op": "set", "value": "E"}, {"field": "troops", "op": "remove", "value": "199"},
              {"field": "troops", "op": "add", "value": 5001}, {"field": "realms", "op": "add", "value": 2},
              {"field": "startcom", "op": "set", "value": 5001}]
        self.assertTrue(self.edit(150, ch, preview=True)["changed"])
        self.assertEqual(self.dm.read_bytes(), self.SRC)  # preview writes nothing
        res = self.edit(150, ch)
        want = (self.SRC.replace(b'#name "A"\r\n#era 1', b'#name "A"\r\n#epithet "E"\r\n#era 1')
                .replace(b'#addrecunit 199 -- vanilla ok', b' -- vanilla ok\r\n#addrecunit 5001')
                .replace(b'#startscout 5000\r\n#defcom1', b'#startcom 5001\r\n#startscout 5000\r\n#defcom1')
                .replace(b'#mystery 3\r\n#end', b'#mystery 3\r\n#homerealm 2\r\n#end'))
        self.assertEqual(self.dm.read_bytes(), want)
        self.assertEqual((self.ws / "demo_mod" / res["backup"]).read_bytes(), self.SRC)
        self.assertIn(b"#homecom 5001", self.dm.read_bytes())  # capital-only recruitment untouched
        with self.assertRaises(KosmoError) as cm:  # stale hash after the save
            self.edit(150, [{"field": "era", "op": "set", "value": 2}])
        self.assertEqual(cm.exception.code, "sha_mismatch")

    def test_inherited_duplicate_and_hostile_refused(self) -> None:
        for nid, changes in [
                (5, [{"field": "troops", "op": "remove", "value": "199"}]),     # vanilla roster, no #clearrec
                (5, [{"field": "realms", "op": "remove", "value": "3"}]),      # vanilla realms, no #clearnation
                (150, [{"field": "troops", "op": "remove", "value": "5000"}]),  # already cleared by #clearrec
                (150, [{"field": "commanders", "op": "remove", "value": "5001"}]),  # duplicate live lines
                (150, [{"field": "troops", "op": "add", "value": 199}]),        # adds are project units only
                (5, [{"field": "startscout", "op": "remove"}])]:               # nothing authored; vanilla army
            self.assertEqual(self.code(nid, changes), "edit_blocked")
        self.edit(5, [{"field": "troops", "op": "remove", "value": "5000"}], preview=True)  # project unit: lossless
        for body_change, want in [({"field": "name", "op": "set", "value": 'a"b'}, "bad_value"),
                                  ({"field": "descr", "op": "set", "value": "x\ny"}, "bad_value"),
                                  ({"field": "clearrec", "op": "set", "value": 1}, "unsupported_field"),
                                  ({"field": "era", "op": "set", "value": True}, "bad_value"),
                                  ({"field": "squad1", "op": "set", "value": {"unit": 5000, "count": 0}}, "bad_value")]:
            self.assertEqual(self.code(150, [body_change]), want)
        self.set_dm(self.SRC + b"#selectnation 150\r\n#end\r\n")
        with self.assertRaises(KosmoError) as cm:
            self.edit(150, [{"field": "era", "op": "set", "value": 2}], digest=sha(self.dm.read_bytes()))
        self.assertEqual(cm.exception.code, "ambiguous_block")

    def test_browser_does_not_revive_cleared_roster_or_sites(self) -> None:
        from kosmokrator.browse import build_project_model
        from kosmokrator.nation_edit import editor_state
        extra = (b'#selectnation 151\r\n#name "B"\r\n#era 1\r\n'
                 b'#startsite "Hall"\r\n#clearnation\r\n#end\r\n')
        self.set_dm(self.SRC + extra)
        m = build_project_model(self.ws, "demo_mod", self.catalog)
        unit = next(x for x in m["monsters"] if x["id"] == 5000)
        self.assertFalse(any(x["via"] == "#addrecunit" and x["nation"] == "nation:150" for x in unit["nations"]))
        nation = next(x for x in m["nations"] if x["id"] == 151)
        self.assertEqual(nation["start_sites"], [])
        self.assertNotIn("nation:151", m["sites"][0]["start_site_of"])
        st = editor_state(self.ws, "demo_mod", 151, self.catalog)
        self.assertEqual(st["lists"]["sites"]["live"], [])
        self.assertEqual(len(st["lists"]["sites"]["dead"]), 1)


class AuthoringRegressionTests(Base):
    def test_copy_resets_and_spell_identity_survive_inserted_lines(self) -> None:
        from kosmokrator.content import content_state, save_content
        source = (b'-- caf\xe9\r\n#modname "Reset probe"\r\n#newweapon 1000\r\n#dmg 77\r\n'
                  b'#copyweapon 1\r\n#name "Blade"\r\n#dmg 5 -- preserve\r\n#unknowncmd 7\r\n#end\r\n'
                  b'#newspell\r\n#copyspell 1\r\n#effect 2\r\n#name "Alpha"\r\n#researchlevel 2\r\n#end\r\n')
        h = self.set_dm(source)
        state = content_state(self.ws, 'demo_mod', 'weapons', self.catalog)
        self.assertEqual(state['items'][0]['values']['dmg'], 5)
        save_content(self.ws, 'demo_mod', 'weapons', self.catalog, {
            'expected_sha256': h, 'preview': False, 'mode': 'edit', 'target': '1000', 'values': {'dmg': 7}})
        self.assertIn(b'#dmg 77\r\n#copyweapon 1', self.dm.read_bytes())
        self.assertIn(b'#dmg 7 -- preserve\r\n#unknowncmd 7', self.dm.read_bytes())
        spell = content_state(self.ws, 'demo_mod', 'spells', self.catalog)['items'][0]
        key = spell['key']
        h = self.set_dm(b'-- inserted before every block\r\n' + self.dm.read_bytes())
        self.assertEqual(content_state(self.ws, 'demo_mod', 'spells', self.catalog)['items'][0]['key'], key)
        before = self.dm.read_bytes()
        with self.assertRaises(KosmoError) as raised:
            save_content(self.ws, 'demo_mod', 'spells', self.catalog, {
                'expected_sha256': h, 'preview': False, 'mode': 'edit', 'target': key,
                'values': {'summon_monster': 199}})
        self.assertEqual(raised.exception.code, 'bad_value')
        self.assertEqual(self.dm.read_bytes(), before)
        save_content(self.ws, 'demo_mod', 'spells', self.catalog, {
            'expected_sha256': h, 'preview': False, 'mode': 'edit', 'target': key,
            'values': {'name': 'Beta', 'researchlevel': 3}})
        self.assertIn(b'#name "Beta"\r\n#researchlevel 3', self.dm.read_bytes())

    def test_equipment_preview_and_save_preserve_other_source(self) -> None:
        from kosmokrator.loadout import save_equipment
        source = (b'#modname "Equipment probe"\r\n#newweapon 1000\r\n#copyweapon 1\r\n#name "Blade"\r\n#end\r\n'
                  b'#newarmor 400\r\n#copyarmor 1\r\n#name "Mail"\r\n#end\r\n'
                  b'#newmonster 5000\r\n#copystats 199\r\n#name "Guard"\r\n#weapon 1 -- keep comment\r\n'
                  b'#unknowncmd 9\r\n#end\r\n-- tail\r\n')
        h = self.set_dm(source)
        request = {'expected_sha256': h, 'preview': True, 'weapons': [1000], 'armor': [400]}
        save_equipment(self.ws, 'demo_mod', 5000, self.catalog, request)
        self.assertEqual(self.dm.read_bytes(), source)
        save_equipment(self.ws, 'demo_mod', 5000, self.catalog, {**request, 'preview': False})
        result = self.dm.read_bytes()
        self.assertEqual(result.split(b'#newmonster')[0], source.split(b'#newmonster')[0])
        self.assertIn(b'-- keep comment', result)
        self.assertIn(b'#unknowncmd 9\r\n', result)
        self.assertIn(b'#clearweapons\r\n#weapon 1000\r\n#cleararmor\r\n#armor 400\r\n', result)
        self.assertTrue(result.endswith(b'#end\r\n-- tail\r\n'))


class WorkshopTests(Base):
    """Workshop folders come only from a hashed export of the shown revision; installs never clobber or publish."""

    def setUp(self) -> None:
        super().setUp()
        self.h = sha(self.dm.read_bytes())
        self.mods = Path(self._tmp.name) / "userdata" / "mods"
        self.mods.mkdir(parents=True)
        from kosmokrator.workshop import mods_dir_config
        self.config = mods_dir_config({"KOSMOKRATOR_DOMINIONS_MODS": str(self.mods)})

    def export(self) -> dict:
        from kosmokrator.export import export_revision
        return export_revision(self.ws, "demo_mod", self.h, "zip", self.catalog)

    def prepare(self, export_id: str, **extra):
        from kosmokrator.workshop import prepare_workshop
        return prepare_workshop(self.ws, "demo_mod", {"expected_sha256": self.h, "export_id": export_id,
                                                      "visibility": "Public", **extra})

    def install(self, wid: str, digest: str | None = None, config: dict | None = None):
        from kosmokrator.workshop import install_workshop
        return install_workshop(self.ws, "demo_mod", wid, {"expected_sha256": digest or self.h}, config or self.config)

    def code(self, call) -> str:
        with self.assertRaises(KosmoError) as cm:
            call()
        return cm.exception.code

    def test_prepare_allowlist_banner_and_regular_zip_unchanged(self) -> None:
        from kosmokrator.author import decode_png_rgba
        from kosmokrator.export import list_exports
        from kosmokrator.tga import decode_tga
        from kosmokrator.workshop import fit_banner
        ex = self.export()
        zpath = self.ws / "demo_mod" / ex["path"]
        zbytes = zpath.read_bytes()
        with zipfile.ZipFile(zpath) as zf:
            self.assertEqual(sorted(zf.namelist()), ["demo_mod/demo_mod.dm", "demo_mod/mod_banner.tga"])
        for vis in ("Private", "public", None):
            self.assertEqual(self.code(lambda: self.prepare(ex["export_id"], visibility=vis)), "bad_visibility")
        self.assertEqual(self.code(lambda: self.prepare(ex["export_id"], destination="C:/x")), "bad_request")
        r = self.prepare(ex["export_id"])
        content = self.ws / "demo_mod" / r["path"]
        self.assertEqual(sorted(p.name for p in content.iterdir()),
                         ["banner.png", "demo_mod.dm", "dom6ws.txt", "mod_banner.tga"])
        self.assertEqual((content / "dom6ws.txt").read_bytes(), b'Visibility = "Public"')
        self.assertEqual((content / "demo_mod.dm").read_bytes(), self.dm.read_bytes())
        self.assertEqual(sorted(os.listdir(content.parent)), ["demo_mod"])  # manifest and ZIP live outside
        with zipfile.ZipFile(self.ws / "demo_mod" / r["archive_path"]) as zf:
            self.assertEqual(sorted(zf.namelist()), sorted(f"demo_mod/{p.name}" for p in content.iterdir()))
        w, h, px = decode_png_rgba((content / "banner.png").read_bytes())
        sw, sh, src = decode_tga((self.dm.parent / "mod_banner.tga").read_bytes())
        self.assertEqual((w, h, sw, sh), (256, 256, 256, 64))
        self.assertEqual(px[3], 0)  # transparent letterbox
        self.assertEqual(px[96 * 256 * 4:160 * 256 * 4], src)  # source pixels unchanged, centred
        self.assertEqual(r["banner"]["method"], "centred unscaled on a transparent canvas")
        self.assertEqual(fit_banner(512, 128, bytes(512 * 128 * 4))[1]["placed_size"], [256, 64])
        self.assertEqual(fit_banner(100, 300, bytes(100 * 300 * 4))[1]["placed_size"], [85, 256])
        self.assertEqual(zpath.read_bytes(), zbytes)
        self.assertEqual([x["export_id"] for x in list_exports(self.ws, "demo_mod")], [ex["export_id"]])
        self.assertEqual(self.code(lambda: self.prepare(ex["export_id"], banner_asset="../kosmokrator.json")),
                         "banner_missing")

    def test_prepare_refuses_blocked_stale_tampered_and_traversal(self) -> None:
        self.set_dm(b'#modname "X"\n#newmonster 5000\n')  # unclosed block: export refuses, nothing prepared
        self.assertEqual(self.code(lambda: self.export()), "sha_mismatch")
        self.h = sha(self.dm.read_bytes())
        self.assertEqual(self.code(lambda: self.export()), "validation_failed")
        self.h = self.set_dm(b'#modname "X"\n#icon "mod_banner.tga"\n')
        ex = self.export()
        old = self.h
        self.h = self.set_dm(b'#modname "X"\n#icon "mod_banner.tga"\n-- changed\n')
        self.assertEqual(self.code(lambda: self.prepare(ex["export_id"], expected_sha256=old)), "sha_mismatch")
        self.assertEqual(self.code(lambda: self.prepare(ex["export_id"])), "stale_export")
        ex = self.export()
        for bad in ("../x", "demo_mod-ws-x", "", None, "a" * 200):
            self.assertIn(self.code(lambda: self.prepare(bad)), ("export_missing", "bad_request"))
        zpath = self.ws / "demo_mod" / ex["path"]
        zpath.write_bytes(zpath.read_bytes() + b"\x00")
        self.assertEqual(self.code(lambda: self.prepare(ex["export_id"])), "export_changed")
        self.assertFalse((self.ws / "demo_mod" / "exports" / "workshop").exists())
        self.h = self.set_dm(b'#modname "X"\n')  # no #icon and no banner.png
        self.assertEqual(self.code(lambda: self.prepare(self.export()["export_id"])), "banner_missing")
        for wid in ("../../x", "demo_mod-ws-20260101T000000Z-zzzzzzzz"):
            self.assertEqual(self.code(lambda: self.install(wid)), "workshop_missing")

    def test_install_new_identical_managed_conflict_and_pfid(self) -> None:
        from kosmokrator.workshop import mods_dir_config
        r1 = self.prepare(self.export()["export_id"])
        self.assertEqual(self.code(lambda: self.install(r1["workshop_id"], config=mods_dir_config(
            {"KOSMOKRATOR_DOMINIONS_MODS": "off"}))), "install_unavailable")
        self.assertFalse(mods_dir_config({"KOSMOKRATOR_DOMINIONS_MODS": "relative/mods"})["available"])
        from kosmokrator.workshop import install_workshop
        self.assertEqual(self.code(lambda: install_workshop(self.ws, "demo_mod", r1["workshop_id"], {
            "expected_sha256": self.h, "destination": str(self.ws)}, self.config)), "bad_request")
        dest = self.mods / "demo_mod"
        self.assertEqual(self.install(r1["workshop_id"])["result"], "installed")
        self.assertEqual(sorted(p.name for p in dest.iterdir()), ["banner.png", "demo_mod.dm", "dom6ws.txt", "mod_banner.tga"])
        again = self.install(r1["workshop_id"])
        self.assertEqual((again["result"], again["written"]), ("unchanged", []))
        (dest / "dom6ws_pfid").write_bytes(b"3141394816")  # written by the game after an upload
        self.h = self.set_dm(self.dm.read_bytes() + b"-- v2\n")
        r2 = self.prepare(self.export()["export_id"])
        self.assertEqual(self.code(lambda: self.install(r1["workshop_id"])), "stale_export")
        up = self.install(r2["workshop_id"])
        self.assertEqual((up["result"], up["written"], up["pfid_preserved"]), ("updated", ["demo_mod.dm"], True))
        self.assertEqual((dest / "dom6ws_pfid").read_bytes(), b"3141394816")
        self.assertEqual((dest / "demo_mod.dm").read_bytes(), self.dm.read_bytes())
        (dest / "notes.txt").write_bytes(b"mine")  # an unmanaged file blocks the managed update
        self.h = self.set_dm(self.dm.read_bytes() + b"-- v3\n")
        r3 = self.prepare(self.export()["export_id"])
        snap = {p.name: p.read_bytes() for p in dest.iterdir()}
        self.assertEqual(self.code(lambda: self.install(r3["workshop_id"])), "install_conflict")
        self.assertEqual({p.name: p.read_bytes() for p in dest.iterdir()}, snap)
        prepared = self.ws / "demo_mod" / r3["path"] / "dom6ws.txt"
        prepared.write_bytes(b'Visibility = "Private"')
        self.assertEqual(self.code(lambda: self.install(r3["workshop_id"])), "workshop_changed")

    def test_install_preserves_unmanaged_and_linked_destinations(self) -> None:
        r = self.prepare(self.export()["export_id"])
        dest = self.mods / "demo_mod"
        dest.mkdir()
        (dest / "demo_mod.dm").write_bytes(b"-- someone else's mod\n")
        (dest / "dom6ws_pfid").write_bytes(b"42")
        self.assertEqual(self.code(lambda: self.install(r["workshop_id"])), "install_conflict")
        self.assertEqual(sorted(p.name for p in dest.iterdir()), ["demo_mod.dm", "dom6ws_pfid"])
        self.assertEqual((dest / "demo_mod.dm").read_bytes(), b"-- someone else's mod\n")
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        for p in dest.iterdir():
            p.unlink()
        dest.rmdir()
        PatchTests._dir_link(self, outside, dest)
        self.assertEqual(self.code(lambda: self.install(r["workshop_id"])), "symlink_rejected")
        self.assertEqual(list(outside.iterdir()), [])


class ReferenceSnapshotTests(Base):
    """Project reference snapshots: catalog-free reuse, isolation, stale/tamper refusal and export exclusion."""

    PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40

    def setUp(self) -> None:
        super().setUp()
        root = Path(self._tmp.name) / "cat"
        (root / "LICENSE").write_text("GPL-3.0 test licence\n", encoding="utf-8")
        for folder, names in (("sprites", ["0199_1.png", "0311_1.png", "0003_rider_1.png"]),
                              ("magicicons", ["Gem_F.png", "Path_U.png"]), ("items", ["item1.png"])):
            (root / "images" / folder).mkdir(parents=True)
            for name in names:
                (root / "images" / folder / name).write_bytes(self.PNG)
        (root / "gamedata" / "unitdescr").mkdir()
        (root / "gamedata" / "unitdescr" / "0199.txt").write_text("descr", encoding="utf-8")
        self.set_dm(b'#modname "X"\n#newmonster 5000\n#copystats 199\n#name "Copy"\n#end\n')
        self.root = self.ws / "demo_mod"

    def body(self, **kw):
        from kosmokrator.reference import reference_status
        cur = reference_status(self.ws, "demo_mod", self.catalog)["snapshot"]
        return {"expected_sha256": sha(self.dm.read_bytes()), "expected_snapshot": cur, **kw}

    def test_snapshot_reused_without_live_catalog_and_never_exported(self) -> None:
        from kosmokrator.browse import build_project_model
        from kosmokrator.pretenders import catalog_sprite_path
        from kosmokrator.reference import create_snapshot, reference_status, resolve_catalog
        dm_before = self.dm.read_bytes()
        prev = create_snapshot(self.ws, "demo_mod", self.catalog, self.body(preview=True))
        self.assertFalse((self.root / ".kosmokrator" / "reference").exists())
        self.assertEqual(prev["scope"]["tables"], "complete")
        res = create_snapshot(self.ws, "demo_mod", self.catalog, self.body())
        manifest = json.loads((self.root / ".kosmokrator" / "reference" / res["snapshot"] / "manifest.json")
                              .read_text(encoding="utf-8"))
        paths = {f["path"] for f in manifest["files"]}
        self.assertTrue({"catalog/gamedata/BaseU.csv", "catalog/LICENSE", "catalog/images/sprites/0199_1.png",
                         "catalog/images/magicicons/Gem_F.png", "catalog/images/items/item1.png"} <= paths)
        self.assertNotIn("catalog/images/sprites/0311_1.png", paths)  # unreferenced: partial sprite scope
        self.assertFalse(any("unitdescr" in x or "rider" in x for x in paths))
        self.assertEqual(manifest["scope"]["sprites"], "referenced")
        self.assertIn({"kind": "sprite", "id": 199, "frame": "attack", "reason": "no sprite file in the source catalog"},
                      manifest["missing"])
        self.assertNotIn(str(self.ws).replace("\\", "\\\\"), json.dumps(manifest))  # no absolute local paths
        # No live catalog: the project still resolves vanilla data and sprites from its own snapshot.
        cat, err = resolve_catalog(self.ws, "demo_mod", None, {"code": "catalog_missing"})
        self.assertIsNone(err)
        self.assertTrue(cat.meta["catalog_path"].startswith(".kosmokrator/reference/"))
        m = build_project_model(self.ws, "demo_mod", cat)
        self.assertEqual(m["monsters"][0]["donor"]["name"], "Cardaces")
        self.assertIsNotNone(catalog_sprite_path(cat, 199, "idle"))
        self.assertEqual(reference_status(self.ws, "demo_mod", None, m)["state"], "offline")
        self.assertEqual(reference_status(self.ws, "demo_mod", self.catalog, m)["state"], "current")
        # Projects without a snapshot keep reading the live catalog unchanged.
        create_project(self.ws, "plain_mod")
        self.assertIs(resolve_catalog(self.ws, "plain_mod", self.catalog, None)[0], self.catalog)
        # Exports carry only the mod; the snapshot and its imagery stay local.
        out = export_mod(self.ws, "demo_mod", dest="out.zip", catalog=cat)
        with zipfile.ZipFile(self.ws / "out.zip") as zf:
            self.assertTrue(all(n.startswith("demo_mod/") and ".kosmokrator" not in n and not n.endswith(".png")
                                for n in zf.namelist()))
        self.assertTrue(out["manifest"]["catalog"]["catalog_path"].startswith(".kosmokrator/reference/"))
        self.assertEqual(self.dm.read_bytes(), dm_before)

    def test_stale_tampered_linked_and_live_differences_are_reported(self) -> None:
        from kosmokrator.reference import create_snapshot, read_verified, reference_status, resolve_catalog
        first = create_snapshot(self.ws, "demo_mod", self.catalog, self.body())
        for bad, code in (({"expected_snapshot": None}, "reference_changed"),
                          ({"expected_sha256": "0" * 64}, "sha_mismatch"), ({"sprites": "everything"}, "bad_request")):
            with self.assertRaises(KosmoError) as cm:
                create_snapshot(self.ws, "demo_mod", self.catalog, {**self.body(), **bad})
            self.assertEqual(cm.exception.code, code)
        with self.assertRaises(KosmoError) as cm:
            create_snapshot(self.ws, "demo_mod", None, self.body())
        self.assertEqual(cm.exception.code, "catalog_missing")
        second = create_snapshot(self.ws, "demo_mod", self.catalog, self.body(sprites="all"))
        ref = self.root / ".kosmokrator" / "reference"
        self.assertEqual(sorted(p.name for p in ref.iterdir()), ["current.json", second["snapshot"]])
        self.assertIn(first["snapshot"], second["removed"])
        # A different live catalog is reported as stale; the snapshot stays in use (versions are not mixed).
        other = write_catalog(Path(self._tmp.name) / "other")
        (other / "gamedata" / "nations.csv").write_text("id\tname\tepithet\tera\n5\tChanged\tX\t1\n", encoding="utf-8")
        live2 = load_catalog(other)
        self.assertEqual(reference_status(self.ws, "demo_mod", live2)["state"], "stale")
        self.assertEqual(resolve_catalog(self.ws, "demo_mod", live2, None)[0].row("nations", 5)["name"], "Arcoscephale")
        # A tampered file makes the snapshot invalid: it is not used and the live catalog is not substituted.
        target = ref / second["snapshot"] / "catalog" / "gamedata" / "nations.csv"
        original = target.read_bytes()
        target.write_bytes(original + b"6\tExtra\t\t1\n")
        cat, err = resolve_catalog(self.ws, "demo_mod", self.catalog, None)
        self.assertIsNone(cat)
        self.assertEqual(err["code"], "reference_invalid")
        self.assertEqual(reference_status(self.ws, "demo_mod", self.catalog)["state"], "invalid")
        target.write_bytes(original)
        cat, err = resolve_catalog(self.ws, "demo_mod", None, None)
        self.assertIsNone(err)
        sprite = cat.root / "images" / "sprites" / "0311_1.png"
        self.assertEqual(read_verified(cat, sprite), self.PNG)
        sprite.write_bytes(self.PNG + b"x")  # images are checked against the manifest on every read
        self.assertIsNone(read_verified(cat, sprite))
        sprite.write_bytes(self.PNG)
        # A link or junction inside a snapshot is refused as well.
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        PatchTests._dir_link(self, outside, ref / second["snapshot"] / "catalog" / "linked")
        self.assertEqual(resolve_catalog(self.ws, "demo_mod", None, None)[1]["code"], "reference_invalid")


class InspectorMercTests(Base):
    """Vanilla inspector paging/search (event id 0) and structured mercenary companies."""

    def setUp(self) -> None:
        super().setUp()
        g = self.catalog.gamedata
        (g / "events.csv").write_text("id\tname\trarity\tdescription\trequirements\teffects\tend\n"
                                      "0\tA festival\t-1\tA festival was held.\tminpop 50\tincdom 3\t\n"
                                      "1\tA statue\t1\tA statue was raised.\tland 1\tcom 199|B300 30\t\n",
                                      encoding="utf-8")
        (g / "Mercenary.csv").write_text("id\tname\tbossname\tcom\tunit\tnrunits\tlevel\tminmen\tminpay\txp\trandequip"
                                         "\trecrate\titem1\titem2\teramask\tend\n"
                                         "1\tStingers\tDante\t311\t199\t50\t0\t15\t250\t20\t1\t100\tFire Sword\t\t7\t\n",
                                         encoding="utf-8")

    def test_inspector_pages_search_and_event_zero(self) -> None:
        from kosmokrator import inspector
        from kosmokrator.catalog import search
        counts = {c["key"]: c["count"] for c in inspector.summary(self.catalog)["categories"]}
        self.assertEqual((counts["events"], counts["mercs"], counts["units"]), (2, 1, 2))
        page = inspector.list_rows(self.catalog, "events", per_page=1, page=1)
        self.assertEqual((page["total"], page["pages"], page["results"][0]["id"]), (2, 2, 0))
        self.assertEqual(inspector.list_rows(self.catalog, "events", per_page=1, page=9)["results"][0]["id"], 1)
        self.assertEqual([r["id"] for r in inspector.list_rows(self.catalog, "events", q="0")["results"]], [0])
        self.assertEqual([r["id"] for r in inspector.list_rows(self.catalog, "events", q="statue")["results"]], [1])
        self.assertEqual(search(self.catalog, "0", "events")["results"][0]["id"], 0)
        self.assertNotIn("events", {r["category"] for r in search(self.catalog, "a", "all")["results"]})
        ev = inspector.detail(self.catalog, "demo_mod", "events", 0)
        self.assertEqual((ev["description"], ev["effects"][0]["manual"]["command"]), ("A festival was held.", "#incdom"))
        fx = inspector.detail(self.catalog, "demo_mod", "events", 1)["effects"]
        self.assertEqual((fx[0]["unit"]["name"], fx[1]["raw"], "manual" in fx[1]), ("Cardaces", "B300 30", False))
        flt = inspector.list_rows(self.catalog, "units", field="mask1", op="has")
        self.assertEqual([r["id"] for r in flt["results"]], [311])
        merc = inspector.detail(self.catalog, "demo_mod", "mercs", 1)
        self.assertEqual((merc["commander"]["name"], merc["troop"]["name"], merc["items"][0]["id"]),
                         ("Mystic", "Cardaces", 1))
        self.assertEqual(inspector.detail(self.catalog, "demo_mod", "units", 199)["mercs"][0]["roles"], ["troop"])
        for bad in ({"cat": "files"}, {"cat": "units", "field": "nope"}, {"cat": "units", "q": "x" * 61}):
            with self.assertRaises(KosmoError):
                inspector.list_rows(self.catalog, bad.pop("cat"), **bad)
        with self.assertRaises(KosmoError) as cm:  # a catalog without the optional table stays usable otherwise
            inspector.list_rows(load_catalog(write_catalog(Path(self._tmp.name) / "plain")), "events")
        self.assertEqual(cm.exception.code, "catalog_incomplete")

    def test_inspector_conditions_sort_and_filter_meta(self) -> None:
        from kosmokrator import inspector
        ids = lambda **kw: [r["id"] for r in inspector.list_rows(self.catalog, **kw)["results"]]  # noqa: E731
        # Numeric ranges include zero and negatives; event id 0 survives sorting and paging.
        self.assertEqual(ids(cat="events", conditions=["rarity:between:-1..0"]), [0])
        self.assertEqual(ids(cat="events", conditions=["rarity:lt:0"]), [0])
        self.assertEqual(ids(cat="events", sort="rarity", order="desc"), [1, 0])
        self.assertEqual(ids(cat="events", sort="id", order="desc", per_page=1, page=2), [0])
        # Numbers, not text ("3712" < "400" as text); a blank cell counts as 0; AND with the original single filter.
        self.assertEqual(ids(cat="units", conditions=["mask1:gte:400"]), [311])
        self.assertEqual(ids(cat="units", conditions=["mask1:eq:0"]), [199])
        self.assertEqual(ids(cat="units", field="mask1", op="has", conditions=["mask1:none"]), [])
        page = inspector.list_rows(self.catalog, "units", conditions=["mask1:has"], sort="name")
        self.assertEqual((page["results"][0]["values"], page["conditions"][0]["text"], page["range"]),
                         ({"mask1": "3712"}, "mask1 has a value", [1, 1]))
        for bad in (["mask1:gt:x"], ["mask1:between:5..1"], ["name:gt:1"], ["nope:has"], ["mask1:has"] * 9):
            with self.assertRaises(KosmoError):
                inspector.list_rows(self.catalog, "units", conditions=bad)
        meta = inspector.filter_meta(self.catalog, "mercs")
        level = next(c for c in meta["common"] if c["field"] == "level")
        self.assertEqual((level["kind"], level["choices"][0]["value"], level["choices"][0]["count"]), ("choice", "0", 1))
        self.assertIn({"key": "minpay", "label": "Minimum pay", "kind": "number"}, meta["sorts"])

    def test_inspector_age_nation_role_filters(self) -> None:
        from kosmokrator import inspector
        g = self.catalog.gamedata
        (g / "nations.csv").write_text("id\tname\tepithet\tera\n0\tIndependents\tIndependents\t0\n"
                                       "5\tArcoscephale\tGolden Era\t1\n43\tArcoscephale\tThe Old Kingdom\t2\n",
                                       encoding="utf-8")
        (g / "MagicSites.csv").write_text("id\tname\tpath\tlevel\trarity\thcom1\n1\tThe Smouldercone\tFire\t0\t5\t311\n",
                                          encoding="utf-8")
        (g / "fort_troop_types_by_nation.csv").write_text("monster_number\tnation_number\n199\t5\n199\t43\n199\t0\n",
                                                          encoding="utf-8")
        (g / "attributes_by_nation.csv").write_text("nation_number\tattribute\traw_value\n43\t52\t1\n", encoding="utf-8")
        ids = lambda **kw: [r["id"] for r in inspector.list_rows(self.catalog, "units", **kw)["results"]]  # noqa: E731
        self.assertEqual(ids(age="1"), [199])  # a shared fort troop; independents (era 0) do not count
        self.assertEqual(ids(age="2"), [199, 311])
        self.assertEqual(ids(nation="43", role="capital"), [311])
        self.assertEqual(ids(nation="43", role="troop"), [199])
        self.assertEqual(ids(nation="national"), [199, 311])
        self.assertEqual(ids(nation="none"), [])
        self.assertEqual(ids(nation="5", conditions=["mask1:has"]), [])  # AND with column conditions
        row = inspector.list_rows(self.catalog, "units", age="2")["results"][0]
        self.assertEqual([n["id"] for n in row["nations"]], [43])
        ties = inspector.detail(self.catalog, "demo_mod", "units", 311)["nations"]
        self.assertEqual((ties[0]["id"], ties[0]["how"]), (43, ["commander", "capital only"]))
        for bad in ({"age": "4"}, {"nation": "5", "age": "2"}, {"nation": "none", "age": "1"}, {"nation": "x"},
                    {"nation": "0"}, {"role": "god"}):
            with self.assertRaises(KosmoError):
                inspector.list_rows(self.catalog, "units", **bad)
        with self.assertRaises(KosmoError):
            inspector.list_rows(self.catalog, "spells", nation="5")
        self.assertEqual([r["id"] for r in inspector.list_rows(self.catalog, "mercs", age="3")["results"]], [1])
        self.assertEqual([r["id"] for r in inspector.list_rows(self.catalog, "nations", age="2")["results"]], [43])
        simple = {s["key"]: s for s in inspector.filter_meta(self.catalog, "units")["simple"]}
        self.assertEqual([(c["value"], c["era"], c["count"]) for c in simple["nation"]["choices"]],
                         [("5", 1, 1), ("43", 2, 2)])
        self.assertEqual([c["count"] for c in simple["nation"]["special"]], [2, 0])

    def test_merc_company_preview_save_browse_export(self) -> None:
        from kosmokrator.command_edit import save_commands
        from kosmokrator.mercs import merc_state, save_merc
        original = self.dm.read_bytes() + b'#newmonster 5000\n#copystats 199\n#name "Sellsword"\n#oddcmd 7\n#end\n'
        h = self.set_dm(original)
        st = merc_state(self.ws, "demo_mod", self.catalog)
        mon = st["options"]["monsters"][0]
        company = {"name": "Iron Band", "bossname": "Hrolf", "commander": {"origin": "project", "key": mon["key"]},
                   "troop": {"origin": "catalog", "id": 199}, "nrunits": 20, "minmen": 5, "minpay": 150, "xp": 10,
                   "recrate": 100, "randequip": 1, "level": 0, "eramask": 7, "items": [{"origin": "catalog", "id": 1}]}
        prev = save_merc(self.ws, "demo_mod", self.catalog, {"expected_sha256": h, "preview": True, "company": company})
        self.assertFalse(prev["written"])
        self.assertIn('+#com "Sellsword"', prev["diff"])
        self.assertEqual(self.dm.read_bytes(), original)
        for bad, code in (({"expected_sha256": "0" * 64}, "sha_mismatch"),
                          ({"company": {**company, "eramask": 9}}, "bad_value"),
                          ({"company": {**company, "items": [{"origin": "catalog", "id": 1}] * 5}}, "bad_value"),
                          ({"company": {**company, "commander": {"origin": "catalog", "id": 4242}}}, "bad_value")):
            with self.assertRaises(KosmoError) as cm:
                save_merc(self.ws, "demo_mod", self.catalog, {"expected_sha256": h, "preview": True,
                                                              "company": company, **bad})
            self.assertEqual(cm.exception.code, code)
        res = save_merc(self.ws, "demo_mod", self.catalog, {"expected_sha256": h, "preview": False, "company": company})
        data = self.dm.read_bytes()
        self.assertTrue(res["written"] and data.startswith(original) and b"#newmerc\n#name \"Iron Band\"" in data)
        # The revision guard holds after the save, and #com by number is refused (the manual takes names).
        with self.assertRaises(KosmoError) as cm:
            save_merc(self.ws, "demo_mod", self.catalog, {"expected_sha256": h, "preview": True, "company": company})
        self.assertEqual(cm.exception.code, "sha_mismatch")
        with self.assertRaises(KosmoError) as cm:
            save_commands(self.ws, "demo_mod", self.catalog, {"expected_sha256": sha(data), "preview": True,
                                                              "context": "merc", "mode": "edit", "target": res["key"],
                                                              "changes": [{"op": "add", "command": "com", "args": [199]}]})
        self.assertEqual(cm.exception.code, "bad_argument")
        comp = merc_state(self.ws, "demo_mod", self.catalog)["companies"][0]
        self.assertEqual((comp["key"], comp["commander"]["candidates"][0]["id"], comp["troop"]["status"],
                          comp["items"][0]["status"]), (res["key"], 5000, "resolved", "resolved"))
        export_mod(self.ws, "demo_mod", dest="merc.zip", catalog=self.catalog)
        with zipfile.ZipFile(self.ws / "merc.zip") as zf:
            self.assertIn(b"#newmerc", zf.read("demo_mod/demo_mod.dm"))
            self.assertFalse(any(".kosmokrator" in n for n in zf.namelist()))


class HealthTests(Base):
    # Synthetic roster: a fort recruit with a missing sprite file, a capital-only unit, a hero, a national summon,
    # a pretender form, an unassigned unit and one broken name reference.
    DM = (b'#modname "Synthetic"\n#description "d"\n'
          b'#newmonster 5000\n#copystats 199\n#name "Unit A"\n#spr1 "art/unit_a.png"\n#end\n'
          b'#newmonster 5001\n#name "Unit B"\n#hp 10\n#end\n'
          b'#newmonster 5002\n#copystats 199\n#name "Unit C"\n#end\n'
          b'#newmonster 5003\n#copystats 199\n#name "Unit D"\n#end\n'
          b'#newmonster 5004\n#copystats 199\n#name "Unit E"\n#end\n'
          b'#newmonster 5005\n#copystats 199\n#name "Unit F"\n#end\n'
          b'#newsite 1700\n#name "Home Site"\n#path 0\n#level 0\n#rarity 5\n#homemon 5002\n#end\n'
          b'#selectnation 150\n#name "Nation A"\n#era 1\n#startsite "Home Site"\n#addrecunit 5000\n'
          b'#hero1 5003\n#addgod 5005\n#addreccom "Missing Unit"\n#end\n'
          b'#newspell\n#name "Call Unit E"\n#effect 10001\n#damage 5004\n#restricted 150\n#end\n')

    def setUp(self) -> None:
        super().setUp()
        self.set_dm(self.DM)
        (self.ws / "demo_mod" / "mod" / "demo_mod" / "mod_banner.tga").unlink(missing_ok=True)

    def health(self, catalog=..., **kw):
        from kosmokrator.health import build_health
        return build_health(self.ws, "demo_mod", self.catalog if catalog is ... else catalog, None, **kw)

    def test_findings_are_deduplicated_reconciled_and_stable_across_line_shifts(self) -> None:
        r = self.health()
        by_code = {f["code"]: f for f in r["findings"]}
        self.assertEqual(r["status"], "blocked")
        self.assertEqual(len({f["id"] for f in r["findings"]}), len(r["findings"]))
        # Validation and readiness both report the missing file; the graph and validation both report the name.
        missing = [f for f in r["findings"] if f["location"]["asset"] == "art/unit_a.png"]
        self.assertEqual(len(missing), 1)
        self.assertEqual((missing[0]["severity"], missing[0]["sources"]), ("error", ["assets", "validation"]))
        self.assertEqual(missing[0]["location"]["object"]["key"], "monster:5000")
        broken = [f for f in r["findings"] if f["category"] == "references" and f["severity"] == "error"]
        self.assertEqual(len(broken), 1)
        self.assertEqual((broken[0]["code"], broken[0]["location"]["object"]["key"]), ("unresolved_reference", "nation:150"))
        self.assertIn("references", broken[0]["sources"])
        # No hidden errors: every validation item is an occurrence of a finding at least as severe.
        v = validate_project(self.ws, "demo_mod", self.catalog)
        self.assertTrue(r["reconciliation"]["complete"])
        self.assertEqual(r["reconciliation"]["accounted"], v["counts"])
        self.assertEqual(r["counts"]["error"], sum(f["severity"] == "error" for f in r["findings"]))
        for f in r["findings"]:
            self.assertTrue(f["next_action"] and f["message"] and f["id"])
        self.assertIn("no_sprite_source", by_code)
        self.assertFalse(r["scope"]["complete"])
        self.assertIn("installed_mods", [x["check"] for x in r["scope"]["not_checked"]])
        # Inserting lines elsewhere keeps ids and order; the revision changes and an old one is reported stale.
        shifted = self.DM.replace(b"#newmonster 5001", b"-- note\n\n#newmonster 5001").replace(
            b'#description "d"\n', b'#description "d"\n\n\n')
        self.set_dm(shifted)
        r2 = self.health(expected_revision=r["revision"])
        self.assertEqual([f["id"] for f in r2["findings"]], [f["id"] for f in r["findings"]])
        self.assertNotEqual(r2["revision"], r["revision"])
        self.assertTrue(r2["stale"] and r2["identity"]["consistent"])
        self.assertFalse(self.health(expected_revision=r2["revision"])["stale"])

    def test_missing_catalog_makes_references_unverified_not_errors(self) -> None:
        r = self.health(catalog=None)
        codes = {(f["code"], f["severity"]) for f in r["findings"]}
        self.assertIn(("catalog_unavailable", "unverified"), codes)
        refs = [f for f in r["findings"] if f["category"] == "references"]
        self.assertTrue(refs)
        self.assertTrue(all(f["severity"] == "unverified" for f in refs))
        self.assertEqual(r["catalog"]["state"], "none")
        self.assertTrue(r["reconciliation"]["complete"])
        # The missing file is still an error without a catalog.
        self.assertTrue(any(f["code"].startswith("asset_") and f["severity"] == "error" for f in r["findings"]))

    def test_recruitment_classes_and_unassigned_is_info(self) -> None:
        r = self.health()
        classes = {u["id"]: u["classes"] for u in r["recruitment"]["units"]}
        self.assertEqual(classes, {5000: ["normal"], 5001: ["unassigned"], 5002: ["cap_only"], 5003: ["hero"],
                                   5004: ["summon"], 5005: ["pretender"]})
        unassigned = [f for f in r["findings"] if f["code"] == "unassigned_monster"]
        self.assertEqual([(f["severity"], f["location"]["object"]["key"]) for f in unassigned], [("info", "monster:5001")])

    def test_entry_points_agree(self) -> None:
        from kosmokrator.cli import main
        from kosmokrator.core import Kosmokrator
        cat = str(Path(self._tmp.name) / "cat")
        k = Kosmokrator(str(self.ws), cat)
        direct = k.project_health("demo_mod")
        state = k.author_state("demo_mod", "health")
        self.assertEqual([f["id"] for f in state["findings"]], [f["id"] for f in direct["findings"]])
        self.assertEqual(state["revision"], self.health()["revision"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--workspace", str(self.ws), "--catalog", cat, "health", "demo_mod", "--json"])
        res = json.loads(out.getvalue())
        self.assertEqual((code, res["ok"], res["result"]["revision"]), (1, True, direct["revision"]))


class RevisionTests(Base):
    # Synthetic latin-1 CRLF source with a donor copy, stats, traits, magic, equipment, description, artwork, an
    # unknown command and a nation recruitment line.
    DM = ('#modname "Synthetic"\r\n#description "d"\r\n'
          '#newmonster 5000\r\n#copystats 199\r\n#name "Unit \xc4"\r\n#hp 10\r\n#fireres 5\r\n#magicskill 0 1\r\n'
          '#weapon 1\r\n#descr "Old text"\r\n#spr1 "art/unit.tga"\r\n#weird 1 2\r\n#end\r\n'
          '#selectmonster 199\r\n#hp 12\r\n#end\r\n'
          '#selectnation 150\r\n#name "Nation A"\r\n#addrecunit 5000\r\n#end\r\n').encode("latin-1")

    def setUp(self) -> None:
        super().setUp()
        self.root = self.ws / "demo_mod"
        self.mod = self.root / "mod" / "demo_mod"
        self.set_dm(self.DM)
        (self.mod / "art").mkdir()
        (self.mod / "art" / "unit.tga").write_bytes(tiny_tga(32, 32))
        (self.root / "maps" / "test_map").mkdir(parents=True)
        (self.root / "maps" / "test_map" / "test_map.map").write_bytes(b"#dom2title Test\r\n#mapsize 256 256\r\n")
        (self.root / "maps" / "test_map" / "test_map.tga").write_bytes(tiny_tga(8, 8))
        (self.root / "playtests").mkdir()
        (self.root / "playtests" / "records.json").write_text("[]\n", encoding="utf-8")
        # Local state and exports are outside the checkpoint scope.
        (self.root / "exports").mkdir()
        (self.root / "exports" / "old.zip").write_bytes(b"zip")

    def rev(self, body: dict) -> dict:
        from kosmokrator.revisions import save_revisions
        return save_revisions(self.ws, "demo_mod", body, self.catalog)

    def tree(self) -> dict[str, bytes]:
        out = {}
        for p in sorted(self.root.rglob("*")):
            rel = p.relative_to(self.root).as_posix()
            if p.is_file() and not rel.startswith(".kosmokrator/"):
                out[rel] = p.read_bytes()
        return out

    def checkpoints(self) -> list[dict]:
        from kosmokrator.revisions import revision_state
        return revision_state(self.ws, "demo_mod")["checkpoints"]

    def restore(self, cid: str) -> dict:
        plan = self.rev({"action": "restore", "checkpoint": cid})
        return self.rev({"action": "restore", "checkpoint": cid, "preview": False, "confirm": True,
                         "expected_revision": plan["current_revision"], "plan_hash": plan["plan_hash"]})

    def test_roundtrip_restores_bytes_assets_maps_and_keeps_history(self) -> None:
        from kosmokrator.revisions import compare
        original = self.tree()
        cp = self.rev({"action": "checkpoint", "label": "start"})["checkpoint"]
        self.assertEqual(cp["totals"]["by_role"], {"asset": 2, "dm": 1, "map": 2, "metadata": 2})  # banner + unit art
        self.assertFalse(any("exports" in f["path"] for f in compare(self.ws, "demo_mod", cp["id"])["files"]))
        # Edits: source, a deleted and an added asset, a changed and deleted map file and a new bundle.
        self.set_dm(self.DM.replace(b"#hp 10", b"#hp 11"))
        (self.mod / "art" / "unit.tga").unlink()
        (self.mod / "art" / "new.tga").write_bytes(tiny_tga(16, 16))
        (self.root / "maps" / "test_map" / "test_map.map").write_bytes(b"#dom2title Test 2\r\n#mapsize 256 256\r\n")
        (self.root / "maps" / "test_map" / "test_map.tga").unlink()
        (self.root / "maps" / "other_map").mkdir()
        (self.root / "maps" / "other_map" / "other_map.map").write_bytes(b"#dom2title Other\n")
        c = compare(self.ws, "demo_mod", cp["id"])
        self.assertEqual(c["counts"], {"unchanged": 3, "modified": 2, "deleted": 2, "added": 2})
        self.assertEqual(c["dm"][0]["encoding"], {"before": "latin-1", "after": "latin-1"})
        self.assertEqual(c["dm"][0]["newlines"], {"before": "crlf", "after": "crlf"})
        self.assertEqual({(a["path"], a["status"]) for a in c["assets"]},
                         {("mod/demo_mod/art/unit.tga", "deleted"), ("mod/demo_mod/art/new.tga", "added")})
        new = next(a for a in c["assets"] if a["status"] == "added")
        self.assertEqual((new["image_after"]["width"], new["preview"]["checkpoint"]), (16, None))
        self.assertEqual({m["id"]: m["status"] for m in c["maps"]}, {"test_map": "modified", "other_map": "added"})
        self.assertIn("Test 2", next(f for m in c["maps"] for f in m["files"] if f["name"] == "test_map.map")["source"]["diff"])
        res = self.restore(cp["id"])
        self.assertEqual(res["counts"], {"add": 2, "replace": 2, "delete": 2})
        self.assertTrue(res["verified"] and res["candidate_check"]["ok"])
        self.assertEqual(self.tree(), original)  # byte-identical, latin-1 and CRLF kept
        self.assertFalse((self.root / "maps" / "other_map").exists())
        kinds = [x["kind"] for x in self.checkpoints()]
        self.assertEqual(kinds, ["restore", "pre-restore", "manual"])
        self.assertEqual(self.checkpoints()[0]["revision"], cp["revision"])
        # The pre-restore checkpoint can undo the restore: the edits come back.
        self.restore(res["pre_restore"]["id"])
        self.assertTrue((self.root / "maps" / "other_map" / "other_map.map").exists())
        self.assertIn(b"#hp 11", self.dm.read_bytes())

    def test_metadata_keeps_identity_and_unions_reservations(self) -> None:
        meta_path = self.root / "kosmokrator.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["reservations"] = {"monster": [{"id": 5100, "label": "old", "reserved_utc": "x"}]}
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        cp = self.rev({"action": "checkpoint"})["checkpoint"]
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.update(name="Renamed", target_game_version="9.99", reservations={"monster": [
            {"id": 5200, "label": "new", "reserved_utc": "y"}]})
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        plan = self.rev({"action": "restore", "checkpoint": cp["id"]})
        self.assertEqual(plan["metadata"]["restored_keys"], ["name", "dependencies"])
        self.restore(cp["id"])
        after = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertEqual((after["name"], after["target_game_version"], after["slug"]), ("Demo Mod", "9.99", "demo_mod"))
        self.assertEqual(sorted(r["id"] for r in after["reservations"]["monster"]), [5100, 5200])

    def test_stale_plan_missing_blob_and_unconfirmed_apply_write_nothing(self) -> None:
        cp = self.rev({"action": "checkpoint"})["checkpoint"]
        self.set_dm(self.DM.replace(b"#hp 10", b"#hp 13"))
        (self.mod / "art" / "unit.tga").write_bytes(tiny_tga(24, 24))
        plan = self.rev({"action": "restore", "checkpoint": cp["id"]})
        body = {"action": "restore", "checkpoint": cp["id"], "preview": False, "confirm": True,
                "expected_revision": plan["current_revision"], "plan_hash": plan["plan_hash"]}
        before, count = self.tree(), len(self.checkpoints())
        for change, code in ((dict(confirm=False), "confirm_required"), (dict(plan_hash="0" * 64), "plan_changed")):
            with self.assertRaises(KosmoError) as cm:
                self.rev({**body, **change})
            self.assertEqual(cm.exception.code, code)
        self.set_dm(self.DM.replace(b"#hp 10", b"#hp 14"))  # an edit after the preview
        with self.assertRaises(KosmoError) as cm:
            self.rev(body)
        self.assertEqual(cm.exception.code, "stale_revision")
        before = self.tree()
        # A missing historical blob refuses the preview and the apply.
        blob = self.root / ".kosmokrator" / "revisions" / "objects"
        target = sha(self.DM)
        (blob / target[:2] / target).unlink()
        from kosmokrator.revisions import revision_state
        current = revision_state(self.ws, "demo_mod")["current"]["revision"]
        for preview in (True, False):
            with self.assertRaises(KosmoError) as cm:
                self.rev({**body, "preview": preview, "expected_revision": current})
            self.assertEqual(cm.exception.code, "blob_missing")
        self.assertEqual(self.tree(), before)
        self.assertEqual(len(self.checkpoints()), count)

    def test_injected_write_failure_rolls_back_and_interrupted_restore_recovers(self) -> None:
        from kosmokrator import revisions
        cp = self.rev({"action": "checkpoint"})["checkpoint"]
        self.set_dm(self.DM.replace(b"#hp 10", b"#hp 15"))
        (self.mod / "art" / "unit.tga").write_bytes(tiny_tga(20, 20))
        (self.root / "maps" / "test_map" / "test_map.map").write_bytes(b"#dom2title Changed\n")
        edited = self.tree()
        real, calls = revisions._place, []

        def flaky(src, dest):
            calls.append(dest)
            if len(calls) == 2:
                raise OSError("disk full (injected)")
            real(src, dest)
        with mock.patch.object(revisions, "_place", flaky):
            with self.assertRaises(KosmoError) as cm:
                self.restore(cp["id"])
        self.assertEqual(cm.exception.code, "restore_failed")
        self.assertEqual(self.tree(), edited)  # the first replaced file was put back
        state = revisions.revision_state(self.ws, "demo_mod")
        self.assertEqual(state["interrupted_restores"], [])
        self.assertEqual([c["kind"] for c in state["checkpoints"]], ["pre-restore", "manual"])
        # A rollback that cannot finish leaves an interrupted journal; apply refuses until it is recovered.
        calls.clear()
        with mock.patch.object(revisions, "_place", flaky), \
                mock.patch.object(revisions, "_revert", return_value=[{"path": "x", "reason": "injected"}]):
            with self.assertRaises(KosmoError) as cm:
                self.restore(cp["id"])
        self.assertEqual(cm.exception.code, "restore_rollback_failed")
        self.assertNotEqual(self.tree(), edited)
        pending = revisions.revision_state(self.ws, "demo_mod")["interrupted_restores"]
        self.assertEqual(len(pending), 1)
        with self.assertRaises(KosmoError) as cm:
            self.restore(cp["id"])
        self.assertEqual(cm.exception.code, "restore_interrupted")
        res = self.rev({"action": "recover", "journal": pending[0]["id"], "confirm": True})
        self.assertEqual((res["state"], res["problems"]), ("recovered", []))
        self.assertEqual(self.tree(), edited)
        self.assertEqual(revisions.revision_state(self.ws, "demo_mod")["interrupted_restores"], [])

    def test_semantic_diff_separates_categories_donor_lines_and_raw_unknown_commands(self) -> None:
        from kosmokrator.revisions import compare
        cp = self.rev({"action": "checkpoint"})["checkpoint"]
        new = (self.DM.replace(b"#copystats 199", b"#copystats 311").replace(b"#hp 10", b"#hp 14")
               .replace(b"#fireres 5", b"#fireres 5\r\n#coldres 3").replace(b"#magicskill 0 1", b"#magicskill 0 2")
               .replace(b"#weapon 1", b"#weapon 2").replace(b'"Old text"', b'"New text"')
               .replace(b"#weird 1 2", b"#weird 3").replace(b"#addrecunit 5000", b"#addreccom 5000")
               .replace(b"#selectmonster 199\r\n#hp 12", b"#selectmonster 199\r\n#hp 9"))
        self.set_dm(new)
        objs = {o["key"]: o for o in compare(self.ws, "demo_mod", cp["id"])["dm"][0]["semantic"]["objects"]}
        unit = objs["monster:newmonster:5000"]
        got = {(c["command"], c["category"], c["change"]) for c in unit["changes"]}
        self.assertEqual(got, {("#copystats", "donor", "changed"), ("#hp", "stat", "changed"),
                               ("#coldres", "trait", "added"), ("#magicskill", "magic", "changed"),
                               ("#weapon", "equipment", "changed"), ("#descr", "description", "changed"),
                               ("#weird", "unknown", "changed")})
        weird = next(c for c in unit["changes"] if c["command"] == "#weird")
        self.assertEqual((weird["before"], weird["after"], weird["source"]), ("#weird 1 2", "#weird 3", "unknown_raw"))
        donor = next(c for c in unit["changes"] if c["command"] == "#copystats")
        self.assertEqual(donor["source"], "donor_reference")
        self.assertTrue(any("not recomputed" in n for n in unit["notes"]))
        self.assertEqual(unit["name"], "Unit \xc4")
        self.assertTrue(any("existing object" in n for n in objs["monster:selectmonster:199"]["notes"]))
        nation = objs["nation:selectnation:150"]
        self.assertEqual({(c["command"], c["category"], c["change"]) for c in nation["changes"]},
                         {("#addrecunit", "recruitment", "removed"), ("#addreccom", "recruitment", "added")})
        # Only authored lines are reported: no resolved values are invented for the donor.
        self.assertFalse(any("effective" in c or "resolved" in c for c in unit["changes"]))

    def test_review_baseline_records_declared_human_or_agent(self) -> None:
        from kosmokrator.revisions import compare, revision_state
        with self.assertRaises(KosmoError) as cm:
            self.rev({"action": "review", "expected_revision": "0" * 64})
        self.assertEqual(cm.exception.code, "bad_request")
        current = revision_state(self.ws, "demo_mod")["current"]["revision"]
        with self.assertRaises(KosmoError) as cm:
            self.rev({"action": "review", "reviewer_kind": "agent", "expected_revision": "0" * 64})
        self.assertEqual(cm.exception.code, "stale_revision")
        agent = self.rev({"action": "review", "reviewer_kind": "agent", "expected_revision": current})
        st = revision_state(self.ws, "demo_mod")
        self.assertEqual((st["review_baseline"]["reviewer_kind"], st["checkpoints"][0]["kind"]), ("agent", "review"))
        self.assertTrue(st["review_baseline"]["checkpoint_summary"]["matches_current"])
        manual = self.rev({"action": "checkpoint", "label": "later"})["checkpoint"]
        self.set_dm(self.DM.replace(b"#hp 10", b"#hp 16"))
        self.rev({"action": "review", "reviewer_kind": "human", "reviewer": "Tester", "checkpoint": manual["id"]})
        st = revision_state(self.ws, "demo_mod")
        self.assertEqual((st["review_baseline"]["reviewer_kind"], st["review_baseline"]["checkpoint"]), ("human", manual["id"]))
        c = compare(self.ws, "demo_mod", "baseline")
        self.assertEqual((c["baseline"]["reviewer_kind"], c["target"]["id"], c["counts"]["modified"]), ("human", manual["id"], 1))
        self.assertNotEqual(agent["checkpoint"]["id"], manual["id"])

    def test_capture_refuses_unsafe_paths_links_limits_and_midflight_edits(self) -> None:
        from kosmokrator import revisions
        (self.mod / "bad name.txt").write_bytes(b"x")
        with self.assertRaises(KosmoError) as cm:
            self.rev({"action": "checkpoint"})
        self.assertEqual(cm.exception.code, "bad_path")
        (self.mod / "bad name.txt").unlink()
        with mock.patch.object(revisions, "MAX_FILES", 2), self.assertRaises(KosmoError) as cm:
            self.rev({"action": "checkpoint"})
        self.assertEqual(cm.exception.code, "too_large")
        real = revisions._scan
        seq = iter([None, {"extra": (self.dm, 1, 1)}])

        def changing(project):
            out = real(project)
            out.update(next(seq) or {})
            return out
        with mock.patch.object(revisions, "_scan", changing), self.assertRaises(KosmoError) as cm:
            self.rev({"action": "checkpoint"})
        self.assertEqual(cm.exception.code, "changed_during_capture")
        self.assertEqual(self.checkpoints(), [])
        try:
            os.symlink(self.dm, self.mod / "linked.dm")
        except (OSError, NotImplementedError):
            try:  # Windows without symlink rights: a directory junction is also a link
                import _winapi
                _winapi.CreateJunction(str(self.root / "playtests"), str(self.mod / "linked"))
            except (ImportError, OSError, AttributeError):
                self.skipTest("symlinks and junctions unavailable")
        with self.assertRaises(KosmoError) as cm:
            self.rev({"action": "checkpoint"})
        self.assertEqual(cm.exception.code, "symlink_rejected")

    def test_entry_points_and_verified_previews(self) -> None:
        from kosmokrator.cli import main
        from kosmokrator.core import Kosmokrator
        from kosmokrator.revisions import preview_image
        k = Kosmokrator(str(self.ws), str(Path(self._tmp.name) / "cat"))
        cp = k.author_save("demo_mod", "revisions", {"action": "checkpoint", "actor": "agent"})["checkpoint"]
        self.assertEqual(cp["actor"], "agent")
        self.assertEqual(k.author_state("demo_mod", "revisions")["checkpoints"][0]["id"], cp["id"])
        self.assertTrue(k.author_state("demo_mod", f"revisions:{cp['id']}")["identical"])
        with self.assertRaises(KosmoError):
            k.author_save("demo_mod", "revisions", {"action": "checkpoint", "surprise": 1})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--workspace", str(self.ws), "author", "demo_mod", "revisions", "--json"])
        self.assertEqual((code, json.loads(out.getvalue())["result"]["checkpoints"][0]["id"]), (0, cp["id"]))
        old = sha((self.mod / "art" / "unit.tga").read_bytes())
        (self.mod / "art" / "unit.tga").write_bytes(tiny_tga(40, 40))
        png = preview_image(self.ws, "demo_mod", "checkpoint", "mod/demo_mod/art/unit.tga", old)
        self.assertTrue(png.startswith(b"\x89PNG"))
        with self.assertRaises(KosmoError) as cm:
            preview_image(self.ws, "demo_mod", "current", "mod/demo_mod/art/unit.tga", old)
        self.assertEqual(cm.exception.code, "stale_preview")
        blob = self.root / ".kosmokrator" / "revisions" / "objects" / old[:2] / old
        blob.write_bytes(b"tampered")
        with self.assertRaises(KosmoError) as cm:
            preview_image(self.ws, "demo_mod", "checkpoint", "mod/demo_mod/art/unit.tga", old)
        self.assertEqual(cm.exception.code, "blob_corrupt")
        with self.assertRaises(KosmoError) as cm:
            preview_image(self.ws, "demo_mod", "checkpoint", "../outside.png", old)
        self.assertEqual(cm.exception.code, "bad_path")

    def test_web_routes_guard_writes_and_serve_verified_previews(self) -> None:
        import http.client
        import threading
        from kosmokrator.webserver import make_server
        server = make_server(str(self.ws), None, None, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        host = f"127.0.0.1:{server.server_address[1]}"

        def call(method: str, path: str, body: dict | None = None, csrf: str | None = None):
            conn = http.client.HTTPConnection(host, timeout=10)
            headers = {"Host": host}
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                headers.update({"Content-Type": "application/json", "Origin": f"http://{host}",
                                "Content-Length": str(len(data))})
                if csrf:
                    headers["X-Kosmo-CSRF"] = csrf
            conn.request(method, path, body=data, headers=headers)
            res = conn.getresponse()
            raw = res.read()
            conn.close()
            return res.status, res.getheader("Content-Type"), raw
        try:
            base = "/api/projects/demo_mod/revisions"
            status, _ct, _raw = call("POST", base, {"action": "checkpoint"})
            self.assertEqual(status, 403)  # no editor token
            self.assertEqual(self.checkpoints(), [])
            status, _ct, raw = call("POST", base, {"action": "checkpoint", "label": "web"}, server.RequestHandlerClass.state.csrf)
            self.assertEqual(status, 200, raw)
            cid = json.loads(raw)["result"]["checkpoint"]["id"]
            art = self.mod / "art" / "unit.tga"
            old = sha(art.read_bytes())
            art.write_bytes(tiny_tga(12, 12))
            status, _ct, raw = call("GET", f"{base}/compare?target={cid}")
            asset = json.loads(raw)["result"]["assets"][0]
            self.assertEqual((status, asset["status"], asset["dimensions_changed"]), (200, "modified", True))
            status, ctype, png = call("GET", f"{base}/preview?side=current&path=mod/demo_mod/art/unit.tga&sha={asset['after']['sha256']}")
            self.assertEqual((status, ctype, png[:4]), (200, "image/png", b"\x89PNG"))
            status, _ct, _raw = call("GET", f"{base}/preview?side=current&path=mod/demo_mod/art/unit.tga&sha={old}")
            self.assertEqual(status, 409)
            status, _ct, raw = call("GET", base)
            self.assertEqual((status, json.loads(raw)["result"]["checkpoints"][0]["via"]), (200, "browser"))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
