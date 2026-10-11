"""Offline game-data catalog read from a user-supplied dom6inspector checkout.

Nothing is downloaded. The catalog is a third-party reference (GPL-3.0 repository by
larzm42); its data may lag or differ from the installed game. Results carry the
source path, origin URL and git revision when they can be read from disk.
"""

from __future__ import annotations

import csv
import io
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import KosmoError

# category -> (file, extra columns surfaced in search results)
CATEGORIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "units": ("BaseU.csv", ("hp", "size", "basecost", "leader", "holy", "F", "A", "W", "E", "S", "D", "N", "G", "B", "H")),
    "nations": ("nations.csv", ("epithet", "era")),
    "weapons": ("weapons.csv", ("att", "def", "len", "nratt")),
    "armors": ("armors.csv", ("type", "def", "enc")),
    "sites": ("MagicSites.csv", ("path", "level", "rarity", "F", "A", "W", "E", "S", "D", "N", "G", "B")),
    "spells": ("spells.csv", ("school", "researchlevel", "path1", "pathlevel1")),
    "items": ("BaseI.csv", ("type", "constlevel", "mainpath", "mainlevel")),
}
# Tables read on request only: they are not part of "all" searches or overlays, and a catalog without them stays
# usable. Mercenary companies and events (event id 0 is a real event).
OPTIONAL_CATEGORIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "mercs": ("Mercenary.csv", ("level", "nrunits", "minpay", "eramask")),
    "events": ("events.csv", ("rarity",)),
}
ALL_CATEGORIES: dict[str, tuple[str, tuple[str, ...]]] = {**CATEGORIES, **OPTIONAL_CATEGORIES}
SETUP_HINT = (
    "Supply a local dom6inspector checkout once (e.g. `git clone https://github.com/larzm42/dom6inspector`) "
    "and pass its path with --catalog or KOSMOKRATOR_CATALOG. Kosmokrator never downloads it for you."
)
MAX_RESULTS = 50
# dom6inspector's index.html links the game data it was built from as e.g. "[ver 6.37]".
_DATASET_VERSION_RE = re.compile(r"\[ver\s+(\d+(?:\.\d+)+)\]")


def _read_table(path: Path) -> list[dict[str, str]]:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    first = text.split("\n", 1)[0]
    # The inspector's ".csv" files are tab separated; detect rather than assume.
    delim = "\t" if first.count("\t") >= first.count(",") else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=delim))


def _git_info(repo: Path) -> dict[str, str | None]:
    """Read origin URL and HEAD revision from .git without running git."""
    info: dict[str, str | None] = {"source_url": None, "revision": None}
    git = repo / ".git"
    if not git.is_dir():
        return info
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(None, 1)[1]
            ref_file = git / ref
            if ref_file.is_file():
                info["revision"] = ref_file.read_text(encoding="utf-8").strip()
            elif (git / "packed-refs").is_file():
                for line in (git / "packed-refs").read_text(encoding="utf-8").splitlines():
                    if line.endswith(" " + ref):
                        info["revision"] = line.split()[0]
        else:
            info["revision"] = head
        cfg = (git / "config").read_text(encoding="utf-8")
        section = None
        for line in cfg.splitlines():
            line = line.strip()
            if line.startswith("["):
                section = line
            elif section == '[remote "origin"]' and line.startswith("url"):
                info["source_url"] = line.split("=", 1)[1].strip()
    except OSError:
        pass
    return info


def _dataset_version(repo: Path) -> dict[str, str | None]:
    """Game-data version as stated by the checkout's index.html; None (unknown) when absent."""
    index = repo / "index.html"
    try:
        m = _DATASET_VERSION_RE.search(index.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        m = None
    if m:
        return {"dataset_version": m.group(1), "dataset_version_source": f"{index} ('[ver {m.group(1)}]')"}
    return {"dataset_version": None,
            "dataset_version_source": "unknown: no '[ver X.YY]' marker found in the catalog's index.html"}


@dataclass
class Catalog:
    root: Path
    gamedata: Path
    meta: dict[str, Any]
    tables: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    # Derived read-only data (column kinds, filter metadata), computed once per catalog object. A snapshot catalog
    # object is replaced whenever its files change, so memoized values never outlive the data they came from.
    memo: dict[Any, Any] = field(default_factory=dict, repr=False, compare=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def table(self, category: str) -> list[dict[str, str]]:
        found = self.tables.get(category)
        if found is not None:
            return found
        # One parse per table even when several browser requests ask for it at once.
        with self._lock:
            if category not in self.tables:
                fname = ALL_CATEGORIES[category][0]
                path = self.gamedata / fname
                if not path.is_file():
                    raise KosmoError("catalog_incomplete", f"Catalog file missing: {path}", hint=SETUP_HINT)
                self.tables[category] = _read_table(path)
            return self.tables[category]

    def memoized(self, key: Any, build: Any) -> Any:
        """build() once per key for this catalog; the result must be treated as read-only by callers."""
        found = self.memo.get(key)
        if found is not None:
            return found
        with self._lock:
            if key not in self.memo:
                self.memo[key] = build()
            return self.memo[key]

    def has_table(self, category: str) -> bool:
        """True when the category's table is loaded or present on disk (optional tables may be absent)."""
        return category in self.tables or (category in ALL_CATEGORIES
                                           and (self.gamedata / ALL_CATEGORIES[category][0]).is_file())

    def ids(self, category: str) -> set[int]:
        out = set()
        for r in self.table(category):
            v = (r.get("id") or "").strip()
            if v.lstrip("-").isdigit():
                out.add(int(v))
        return out

    def names(self, category: str) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for r in self.table(category):
            v = (r.get("id") or "").strip()
            if v.lstrip("-").isdigit() and r.get("name"):
                out.setdefault(r["name"].strip().lower(), []).append(int(v))
        return out

    def row(self, category: str, ident: int) -> dict[str, str] | None:
        for r in self.table(category):
            if (r.get("id") or "").strip() == str(ident):
                return r
        return None


_CACHE: dict[str, Catalog] = {}


def resolve_catalog_path(path: str | os.PathLike[str] | None) -> Path | None:
    raw = path or os.environ.get("KOSMOKRATOR_CATALOG")
    return Path(raw).expanduser().resolve() if raw else None


def load_catalog(path: str | os.PathLike[str] | None, *, required: bool = True) -> Catalog | None:
    root = resolve_catalog_path(path)
    if root is None:
        if required:
            raise KosmoError("catalog_missing", "No game-data catalog configured.", hint=SETUP_HINT)
        return None
    gamedata = root / "gamedata" if (root / "gamedata").is_dir() else root
    if not (gamedata / "BaseU.csv").is_file():
        if required:
            raise KosmoError("catalog_missing", f"No dom6inspector gamedata found at {root}", hint=SETUP_HINT)
        return None
    key = str(gamedata)
    if key not in _CACHE:
        repo = gamedata.parent
        git = _git_info(repo)
        _CACHE[key] = Catalog(root, gamedata, {
            "catalog_path": str(root),
            "source": "dom6inspector (third-party, GPL-3.0); not affiliated with or owned by Kosmokrator",
            "source_url": git["source_url"],
            "revision": git["revision"],
            **_dataset_version(repo),
            "disclaimer": "Community-extracted data; may differ from the installed game version. "
                          "Not a guarantee of game parity.",
        })
    return _CACHE[key]


def search(catalog: Catalog, query: str, category: str = "all", limit: int = 20) -> dict[str, Any]:
    if category != "all" and category not in ALL_CATEGORIES:
        raise KosmoError("bad_category", f"Unknown category {category!r}", allowed=["all", *ALL_CATEGORIES])
    limit = max(1, min(int(limit), MAX_RESULTS))
    q = query.strip().lstrip("#")
    if not q:
        raise KosmoError("bad_query", "Query must not be empty.")
    want_id = int(q) if q.lstrip("-").isdigit() else None
    ql = q.lower()
    hits: list[dict[str, Any]] = []
    for cat in (CATEGORIES if category == "all" else [category]):
        extra = ALL_CATEGORIES[cat][1]
        for r in catalog.table(cat):
            rid = (r.get("id") or "").strip()
            name = (r.get("name") or "").strip()
            if (want_id is not None and rid == str(want_id)) or (want_id is None and ql in name.lower()):
                fields = {k: r[k] for k in extra if r.get(k) not in (None, "", "0")}
                hits.append({"category": cat, "id": int(rid) if rid.lstrip("-").isdigit() else rid,
                             "name": name, "fields": fields})
    # Exact name matches first, then by category/id; cap after sorting.
    hits.sort(key=lambda x: (x["name"].lower() != ql, x["category"], x["id"] if isinstance(x["id"], int) else 0))
    results = hits[:limit]
    return {"query": query, "category": category, "total_matches": len(hits), "returned": len(results),
            "truncated": len(hits) > len(results), "results": results, "catalog": catalog.meta}
