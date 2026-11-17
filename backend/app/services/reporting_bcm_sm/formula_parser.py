"""Parseur des formules officielles BEA-SM — AST uniquement, pas d'évaluation Excel."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

_CELL = re.compile(r"^\$?([A-Z]{1,3})\$?([0-9]{1,7})$")


@dataclass(frozen=True)
class Number:
    value: Decimal


@dataclass(frozen=True)
class BoolLit:
    value: bool


@dataclass(frozen=True)
class CellRef:
    sheet: str | None
    address: str


@dataclass(frozen=True)
class RangeRef:
    sheet: str | None
    start: str
    end: str


@dataclass(frozen=True)
class Unary:
    op: str
    expr: object


@dataclass(frozen=True)
class BinOp:
    op: str
    left: object
    right: object


@dataclass(frozen=True)
class Compare:
    op: str
    left: object
    right: object


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple


class FormulaSyntaxError(ValueError):
    pass


class _Tok:
    def __init__(self, kind: str, value: str):
        self.kind = kind
        self.value = value

    def __repr__(self) -> str:
        return f"{self.kind}:{self.value}"


def tokenize(formula: str) -> list[_Tok]:
    s = formula.strip()
    if s.startswith("="):
        s = s[1:]
    toks: list[_Tok] = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "'":
            j = i + 1
            while j < n and s[j] != "'":
                j += 1
            if j >= n:
                raise FormulaSyntaxError("guillemet de feuille non fermé")
            toks.append(_Tok("SHEET", s[i + 1 : j]))
            i = j + 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and s[i + 1].isdigit()):
            j = i
            while j < n and (s[j].isdigit() or s[j] == "."):
                j += 1
            toks.append(_Tok("NUM", s[i:j]))
            i = j
            continue
        if ch.isalpha() or ch == "$":
            j = i
            while j < n and (s[j].isalpha() or s[j] == "$"):
                j += 1
            while j < n and s[j].isdigit():
                j += 1
            raw = s[i:j]
            up = raw.upper().replace("$", "")
            if up == "TRUE":
                toks.append(_Tok("TRUE", "TRUE"))
            elif up == "FALSE":
                toks.append(_Tok("FALSE", "FALSE"))
            elif up in ("SUM", "IF"):
                toks.append(_Tok("FUNC", up))
            elif _CELL.match(up):
                toks.append(_Tok("CELL", up))
            else:
                toks.append(_Tok("IDENT", raw))
            i = j
            continue
        two = s[i : i + 2]
        if two in ("<=", ">=", "<>"):
            toks.append(_Tok("OP", two))
            i += 2
            continue
        if ch in "+-*/%(),:!=<>":
            kind = {"(": "LP", ")": "RP", ",": "COMMA", ":": "COLON", "!": "BANG"}.get(ch, "OP")
            toks.append(_Tok(kind, ch))
            i += 1
            continue
        raise FormulaSyntaxError(f"caractère inattendu {ch!r} dans {formula!r}")
    toks.append(_Tok("EOF", ""))
    return toks


class _Parser:
    def __init__(self, toks: list[_Tok]):
        self.toks = toks
        self.i = 0

    def peek(self) -> _Tok:
        return self.toks[self.i]

    def take(self, kind: str | None = None) -> _Tok:
        tok = self.toks[self.i]
        if kind and tok.kind != kind:
            raise FormulaSyntaxError(f"attendu {kind}, obtenu {tok}")
        self.i += 1
        return tok

    def parse(self) -> object:
        expr = self.comparison()
        if self.peek().kind != "EOF":
            raise FormulaSyntaxError(f"reste non consommé: {self.peek()}")
        return expr

    def comparison(self) -> object:
        left = self.add()
        while self.peek().kind == "OP" and self.peek().value in ("=", "<>", "<", ">", "<=", ">="):
            op = self.take().value
            right = self.add()
            left = Compare(op, left, right)
        return left

    def add(self) -> object:
        left = self.mul()
        while self.peek().kind == "OP" and self.peek().value in ("+", "-"):
            op = self.take().value
            right = self.mul()
            left = BinOp(op, left, right)
        return left

    def mul(self) -> object:
        left = self.unary()
        while self.peek().kind == "OP" and self.peek().value in ("*", "/"):
            op = self.take().value
            right = self.unary()
            left = BinOp(op, left, right)
        return left

    def unary(self) -> object:
        if self.peek().kind == "OP" and self.peek().value in ("+", "-"):
            op = self.take().value
            return Unary(op, self.unary())
        return self.postfix()

    def postfix(self) -> object:
        expr = self.primary()
        while self.peek().kind == "OP" and self.peek().value == "%":
            self.take()
            expr = BinOp("/", expr, Number(Decimal("100")))
        return expr

    def primary(self) -> object:
        tok = self.peek()
        if tok.kind == "NUM":
            self.take()
            return Number(Decimal(tok.value))
        if tok.kind == "TRUE":
            self.take()
            return BoolLit(True)
        if tok.kind == "FALSE":
            self.take()
            return BoolLit(False)
        if tok.kind == "FUNC":
            return self.call()
        if tok.kind in ("CELL", "SHEET"):
            return self.cell_or_range()
        if tok.kind == "LP":
            self.take()
            expr = self.comparison()
            self.take("RP")
            return expr
        raise FormulaSyntaxError(f"terme inattendu {tok}")

    def call(self) -> object:
        name = self.take("FUNC").value
        self.take("LP")
        args: list = []
        if self.peek().kind != "RP":
            args.append(self.arg())
            while self.peek().kind == "COMMA":
                self.take()
                args.append(self.arg())
        self.take("RP")
        return Call(name, tuple(args))

    def arg(self) -> object:
        return self.comparison()

    def cell_or_range(self) -> object:
        sheet, addr = self._cell()
        if self.peek().kind == "COLON":
            self.take()
            sheet2, addr2 = self._cell()
            if sheet2 is not None and sheet is not None and sheet2 != sheet:
                raise FormulaSyntaxError("plage inter-feuilles non supportée")
            return RangeRef(sheet or sheet2, addr, addr2)
        return CellRef(sheet, addr)

    def _cell(self) -> tuple[str | None, str]:
        sheet = None
        if self.peek().kind == "SHEET":
            sheet = self.take().value
            self.take("BANG")
        tok = self.take("CELL")
        m = _CELL.match(tok.value.upper().replace("$", ""))
        if not m:
            raise FormulaSyntaxError(f"adresse invalide {tok.value}")
        return sheet, f"{m.group(1)}{m.group(2)}"


def parse_formula(formula: str) -> object:
    if not formula or not str(formula).strip():
        raise FormulaSyntaxError("formule vide")
    return _Parser(tokenize(str(formula))).parse()


def col_to_index(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n


def index_to_col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def split_addr(address: str) -> tuple[str, int]:
    m = _CELL.match(address.upper())
    if not m:
        raise FormulaSyntaxError(f"adresse invalide {address}")
    return m.group(1), int(m.group(2))


def expand_range(start: str, end: str) -> list[str]:
    c1, r1 = split_addr(start)
    c2, r2 = split_addr(end)
    i1, i2 = col_to_index(c1), col_to_index(c2)
    if i1 > i2:
        i1, i2 = i2, i1
    if r1 > r2:
        r1, r2 = r2, r1
    out: list[str] = []
    for i in range(i1, i2 + 1):
        for r in range(r1, r2 + 1):
            out.append(f"{index_to_col(i)}{r}")
    return out


def collect_cell_refs(ast: object, default_sheet: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []

    def walk(node: object) -> None:
        if isinstance(node, CellRef):
            refs.append((node.sheet or default_sheet, node.address))
        elif isinstance(node, RangeRef):
            sh = node.sheet or default_sheet
            for addr in expand_range(node.start, node.end):
                refs.append((sh, addr))
        elif isinstance(node, Unary):
            walk(node.expr)
        elif isinstance(node, (BinOp, Compare)):
            walk(node.left)
            walk(node.right)
        elif isinstance(node, Call):
            for a in node.args:
                walk(a)

    walk(ast)
    return refs
