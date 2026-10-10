"""Focused tests: lossless patching, path containment, validation and export guards.

Run: .venv/Scripts/python.exe -m unittest discover -s tests -v
Uses a tiny synthetic catalog, so no game data or network is needed.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
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
        n = create_nation(self.ws, "demo_mod", self.catalog, {
            "expected_sha256": self.h, "name": "B", "epithet": "Second", "era": 2, "sites": [1700],
            "troops": [5000], "commanders": [5002], "gods": [5003], "startcom": [5002],
            "startunits": [{"id": 5000, "count": 10}], "realms": [10]})
        self.assertEqual(n["id"], 151)
        self.assertIn('#selectnation 151\n#name "B"\n#epithet "Second"\n#era 2\n#clearnation\n#flag "art/nations/151-flag.tga"\n#startsite "Hall"\n'
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


if __name__ == "__main__":
    unittest.main()
