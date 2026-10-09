"""Non-mutating .dm parser.

Parses statements with source offsets so callers can report file/line and so that
edits never require re-serialising the file. Syntax follows the manual's Syntax
section (6.36, p.3): commands start with '#', '--' starts a comment, string
arguments are double-quoted (and may span lines, as long descriptions do).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

NAME_RE = re.compile(r"[A-Za-z0-9_]+")

# Block openers whose block context is understood. Any other #select*/#new*
# command is treated as an unverified block opener so that #end still pairs up.
OPENERS: dict[str, str] = {
    "selectmonster": "monster", "newmonster": "monster",
    "selectsite": "site", "newsite": "site",
    "selectnation": "nation", "newnation": "nation",
    "selectweapon": "weapon", "newweapon": "weapon",
    "selectarmor": "armor", "newarmor": "armor",
    "selectspell": "spell", "newspell": "spell",
    "selectitem": "item", "newitem": "item",
    "selectnametype": "nametype", "selectbless": "bless",
    "selectpoptype": "poptype", "newmerc": "merc",
    "selectsound": "sound", "newtemplate": "aitemplate",
    "newevent": "event", "selectevent": "event",
}


@dataclass
class Arg:
    kind: str  # "str" | "int" | "float" | "word"
    value: Any
    raw: str


@dataclass
class Statement:
    command: str          # lower-case name without '#'
    raw_command: str      # as written
    args: list[Arg]
    line: int             # 1-based line of the '#'
    end_line: int
    start: int            # char offsets into the decoded text
    end: int
    raw: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass
class Block:
    context: str          # monster/site/nation/... or "unknown"
    opener: Statement
    statements: list[Statement] = field(default_factory=list)
    end: Statement | None = None

    @property
    def new(self) -> bool:
        return self.opener.command.startswith("new")


@dataclass
class ParseResult:
    text: str
    statements: list[Statement]
    toplevel: list[Statement]
    blocks: list[Block]
    issues: list[dict[str, Any]]  # syntax problems: {severity, line, message}
    stray: list[dict[str, Any]]


def _classify(tok: str) -> Arg:
    if re.fullmatch(r"[+-]?\d+", tok):
        return Arg("int", int(tok), tok)
    if re.fullmatch(r"[+-]?(\d+\.\d*|\.\d+)", tok):
        return Arg("float", float(tok), tok)
    return Arg("word", tok, tok)


def parse(text: str) -> ParseResult:
    statements: list[Statement] = []
    issues: list[dict[str, Any]] = []
    stray: list[dict[str, Any]] = []
    n = len(text)
    i = 0
    line = 1

    def skip_comment(j: int) -> int:
        while j < n and text[j] != "\n":
            j += 1
        return j

    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r\f\v﻿":
            i += 1
            continue
        if text.startswith("--", i):
            i = skip_comment(i)
            continue
        if c != "#":
            j = i
            while j < n and text[j] != "\n" and not text.startswith("--", j):
                j += 1
            stray.append({"line": line, "text": text[i:j].strip()})
            i = j
            continue
        # Command
        start, start_line = i, line
        m = NAME_RE.match(text, i + 1)
        if not m:
            issues.append({"severity": "error", "line": line, "message": "'#' not followed by a command name"})
            i = skip_comment(i)
            continue
        raw_cmd = m.group(0)
        i = m.end()
        args: list[Arg] = []
        errors: list[str] = []
        end = i
        while i < n:
            ch = text[i]
            if ch == "\n":
                break
            if ch in " \t\r\f\v":
                i += 1
                continue
            if text.startswith("--", i):
                i = skip_comment(i)
                break
            if ch == "#":
                errors.append("another command starts on the same line")
                break
            if ch == '"':
                close = text.find('"', i + 1)
                if close == -1:
                    errors.append("unterminated string")
                    args.append(Arg("str", text[i + 1:], text[i:]))
                    line += text.count("\n", i)
                    i = end = n
                    break
                value = text[i + 1:close]
                line += value.count("\n")
                args.append(Arg("str", value, text[i:close + 1]))
                i = end = close + 1
                continue
            j = i
            while j < n and text[j] not in ' \t\r\n\f\v"' and not text.startswith("--", j):
                j += 1
            args.append(_classify(text[i:j]))
            i = end = j
        st = Statement(raw_cmd.lower(), raw_cmd, args, start_line, line, start, end, text[start:end], errors)
        statements.append(st)
        for e in errors:
            issues.append({"severity": "error", "line": start_line, "message": f"#{raw_cmd}: {e}"})

    toplevel: list[Statement] = []
    blocks: list[Block] = []
    current: Block | None = None
    for st in statements:
        cmd = st.command
        is_opener = cmd in OPENERS or ((cmd.startswith("select") or cmd.startswith("new")) and len(cmd) > 4)
        if is_opener:
            if current is not None:
                issues.append({"severity": "error", "line": st.line,
                               "message": f"#{st.raw_command} opens a block before #{current.opener.raw_command} "
                                          f"(line {current.opener.line}) was closed with #end"})
                blocks.append(current)
            current = Block(OPENERS.get(cmd, "unknown"), st)
            continue
        if cmd == "end":
            if current is None:
                issues.append({"severity": "error", "line": st.line, "message": "#end without an open block"})
            else:
                current.end = st
                blocks.append(current)
                current = None
            continue
        if current is None:
            toplevel.append(st)
        else:
            current.statements.append(st)
    if current is not None:
        issues.append({"severity": "error", "line": current.opener.line,
                       "message": f"#{current.opener.raw_command} block is never closed with #end"})
        blocks.append(current)
    return ParseResult(text, statements, toplevel, blocks, issues, stray)


def decode_dm(data: bytes) -> tuple[str, str]:
    """Decode bytes losslessly. UTF-8 when valid, else latin-1 (byte-preserving)."""
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def newline_style(text: str) -> str:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    if crlf and lf:
        return "mixed"
    return "crlf" if crlf else ("lf" if lf else "none")


def block_id(block: Block) -> int | str | None:
    a = block.opener.args
    if not a:
        return None
    return a[0].value if a[0].kind in ("int", "str") else a[0].raw


def block_name(block: Block) -> str | None:
    for st in block.statements:
        if st.command == "name" and st.args and st.args[0].kind == "str":
            return st.args[0].value
    return None


# kind -> (new opener, select opener)
DEFINING = {
    "monster": ("newmonster", "selectmonster"),
    "site": ("newsite", "selectsite"),
    "nation": ("newnation", "selectnation"),
    "weapon": ("newweapon", "selectweapon"),
    "armor": ("newarmor", "selectarmor"),
    "item": ("newitem", "selectitem"),
    "spell": ("newspell", "selectspell"),
}


def definitions(pr: ParseResult) -> list[dict[str, Any]]:
    """Objects created or selected by blocks: kind, id (int or None), name, line, new."""
    out = []
    for b in pr.blocks:
        for kind, (new_cmd, sel_cmd) in DEFINING.items():
            if b.opener.command not in (new_cmd, sel_cmd):
                continue
            ident = block_id(b)
            out.append({
                "kind": kind,
                "new": b.opener.command == new_cmd,
                "id": ident if isinstance(ident, int) else None,
                "selector": ident if isinstance(ident, str) else None,
                "name": block_name(b),
                "line": b.opener.line,
                "end_line": b.end.line if b.end else None,
            })
    return out
