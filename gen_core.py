#!/usr/bin/env python3
"""Translate the ladder maths in taper.py into the JavaScript block in index.html.

The maths used to be written twice, once in each language, and the two had
drifted before anyone noticed. Now it is written once — between the
`# --- CORE BEGIN ---` and `# --- CORE END ---` markers in taper.py — and this
script produces the JavaScript. Drift is not caught here; it is impossible.

    python3 gen_core.py            # write the block into index.html
    python3 gen_core.py --check    # exit 1 if the checked-in block is stale
    python3 gen_core.py --print    # write the block to stdout

Why a translator and not a shared library: index.html has to open from disk,
offline, with no external requests, and taper.py has to run on a bare Python
with no pip. Neither can load the other's code at runtime, so the only way to
have one authored copy is to generate the second one.

WHAT IT ACCEPTS

A deliberately small subset of Python — roughly what the core already uses:
plain functions, @dataclass records, if/for/break/return/raise, arithmetic,
comparisons, boolean operators, ternaries, list/dict/tuple literals, and a
short list of builtins. Anything else is a hard error naming the file, the
line and the construct. It never guesses, and it never emits JavaScript it is
not sure of: a translator that silently mistranslates one line of a dosing
calculation is worse than the duplication it replaced.

THE TRAPS IT IS BUILT AROUND

  truthiness   `[]` is falsy in Python and truthy in JavaScript. A bare value
               in a boolean position is rejected unless its type is known to
               be a number or a bool, so `if not rows:` cannot be written here
               — it has to say `len(rows) == 0`.
  int()        maps to Math.trunc, which rounds toward zero exactly as Python
               does, not Math.floor.
  //           maps to Math.floor, which rounds toward -Infinity exactly as
               Python does. The two are only the same for positive operands.
  x[-1]        becomes x[x.length - 1]; JavaScript has no negative indexing.
  naming       snake_case becomes camelCase throughout, including the string
               keys of dict literals, because every dict literal in the core
               is a record whose keys are field names.

Standard library only, like everything else in this repo.
"""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from typing import Optional

PY_FILE = "taper.py"
HTML_FILE = "index.html"

CORE_BEGIN = "# --- CORE BEGIN ---"
CORE_END = "# --- CORE END ---"
SKIP_MARK = "# gen: skip"

JS_BEGIN = "  /* ===== GENERATED CORE — do not edit by hand ===== */"
JS_END = "  /* ===== END GENERATED CORE ===== */"

# The mechanical snake_case -> camelCase rule renames these five in a way the
# display code around them does not expect. Overriding is cheaper and safer
# than renaming them in taper.py or chasing the reads through index.html —
# and check_overrides() fails the build if one of these Python names stops
# existing, so the table cannot quietly rot.
NAME_OVERRIDES = {
    # Names the display code around the block already reads, where the
    # mechanical rule would rename them.
    "film_2mg_mm": "film2Mm",            # index.html reads s.film2Mm in four places
    "n_below_3mg": "nBelow3",            # and s.nBelow3 in the warnings banner
    "DEFAULT_SWITCH_AT_MG": "SWITCH_AT_MG",
    "DEFAULT_RX_STRIPS": "RX_STRIPS",
    "DEFAULT_MONTH_DAYS": "MONTH_DAYS",
    # The two entry points. Python takes keyword arguments and the page has an
    # options object, so index.html wraps each of these in a hand-written
    # adapter that keeps the old name and does the mapping. The generated
    # function takes the -Core suffix so the adapter can have the plain one.
    "build_schedule": "buildScheduleCore",
    "compare_classic": "compareClassicCore",
}

# Builtins the core is allowed to call, and what they become.
CALLS = {
    "min": "Math.min",
    "max": "Math.max",
    "abs": "Math.abs",
    "int": "Math.trunc",     # toward zero, like Python's int()
    "float": "Number",
    "bool": "Boolean",
}

BINOPS = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "**",
}
CMPOPS = {
    ast.Eq: "===", ast.NotEq: "!==", ast.Lt: "<", ast.LtE: "<=",
    ast.Gt: ">", ast.GtE: ">=",
}
# Types whose Python truthiness matches JavaScript's. Anything else in a
# boolean position is a hard error — see the module docstring.
NUMERIC_TYPES = {"int", "float", "bool"}


class Unsupported(Exception):
    """A construct the translator will not guess at."""


def fail(node: ast.AST, what: str) -> None:
    line = getattr(node, "lineno", "?")
    raise Unsupported(
        f"{PY_FILE}:{line}: {what}\n"
        f"  The core is limited to what gen_core.py can translate exactly.\n"
        f"  Either write it another way, or teach gen_core.py this construct\n"
        f"  and add a case to TestCoreGenerator in test_taper.py."
    )


def camel(name: str) -> str:
    """snake_case -> camelCase, honouring NAME_OVERRIDES.

    Leading underscores are dropped (_fill_summary -> fillSummary). An ALL_CAPS
    constant keeps its shape, because that is the convention on both sides.
    """
    if name in NAME_OVERRIDES:
        return NAME_OVERRIDES[name]
    name = name.lstrip("_")
    if name.isupper() or (name.replace("_", "").isupper() and any(c.isalpha() for c in name)):
        return name
    head, *rest = name.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


# --------------------------------------------------------------------------
# Comments
# --------------------------------------------------------------------------

def collect_comments(src: str) -> dict[int, tuple[str, bool]]:
    """Map line number -> (comment text, is_own_line).

    ast throws comments away, and the comments inside build_schedule are the
    explanation of why the ladder does what it does. Losing them would leave
    index.html carrying four hundred lines nobody can read, so they are picked
    back up from the token stream and reattached by line.
    """
    out: dict[int, tuple[str, bool]] = {}
    lines = src.splitlines()
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type != tokenize.COMMENT:
            continue
        text = tok.string.lstrip("#").strip()
        own_line = lines[tok.start[0] - 1][: tok.start[1]].strip() == ""
        out[tok.start[0]] = (text, own_line)
    return out


# --------------------------------------------------------------------------
# Type inference — only enough to police boolean positions
# --------------------------------------------------------------------------

def ann_type(node: Optional[ast.AST]) -> Optional[str]:
    """An annotation as a plain string: "float", "CycleRow", "list[CycleRow]".

    Optional[X] is X — a None in a boolean position is caught by the truthiness
    rule anyway, and every Optional in the core is an Optional number.
    """
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Subscript):
        base = ann_type(node.value)
        if base == "Optional":
            return ann_type(node.slice)
        if isinstance(node.slice, ast.Tuple):
            return base
        inner = ann_type(node.slice)
        return f"{base}[{inner}]" if inner else base
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def base_of(t: Optional[str]) -> Optional[str]:
    """"list[CycleRow]" -> "list"."""
    return t.split("[", 1)[0] if t else t


def elem_of(t: Optional[str]) -> Optional[str]:
    """"list[CycleRow]" -> "CycleRow"; anything else -> None."""
    if t and t.startswith("list[") and t.endswith("]"):
        return t[5:-1]
    return None


class Scope:
    """Names in scope and what little is known about their types."""

    def __init__(self, parent: Optional["Scope"] = None) -> None:
        self.parent = parent
        self.types: dict[str, Optional[str]] = {}
        self.declared: set[str] = set()

    def lookup(self, name: str) -> Optional[str]:
        s: Optional[Scope] = self
        while s is not None:
            if name in s.types:
                return s.types[name]
            s = s.parent
        return None


# --------------------------------------------------------------------------
# Translator
# --------------------------------------------------------------------------

class Translator:
    def __init__(self, src: str) -> None:
        self.src = src
        self.comments = collect_comments(src)
        self.emitted_comments: set[int] = set()
        self.records: dict[str, list[tuple[str, Optional[ast.AST], Optional[str]]]] = {}
        self.functions: dict[str, ast.FunctionDef] = {}
        self.module = Scope()
        self.prev_kind = "block"
        self.cur_indent = 4
        self.flags: dict[int, str] = {}
        self.out: list[str] = []

    # -- helpers ----------------------------------------------------------

    def line(self, indent: int, text: str) -> None:
        self.out.append(" " * indent + text if text else "")

    def comment_block(self, indent: int, text: str) -> None:
        """A docstring as a JS block comment, wrapped the way the repo writes them."""
        lines = [l.rstrip() for l in text.strip("\n").split("\n")]
        while lines and not lines[-1]:
            lines.pop()
        pad = " " * indent
        if len(lines) == 1:
            self.line(indent, f"/* {lines[0]} */")
            return
        self.out.append(f"{pad}/* {lines[0]}")
        base = min((len(l) - len(l.lstrip()) for l in lines[1:] if l.strip()), default=0)
        for l in lines[1:]:
            self.out.append(f"{pad}   {l[base:]}" if l.strip() else "")
        self.out[-1] = self.out[-1] + " */"

    def leading_comments(self, node: ast.AST, indent: int) -> None:
        """Emit the run of own-line comments sitting directly above a statement."""
        start = getattr(node, "lineno", None)
        if start is None:
            return
        for dec in getattr(node, "decorator_list", []):
            start = min(start, dec.lineno)
        run = []
        ln = start - 1
        while ln in self.comments and self.comments[ln][1] and ln not in self.emitted_comments:
            if self.comments[ln][0].startswith("--- CORE"):
                run = []
                break
            run.append(ln)
            ln -= 1
        for ln in reversed(run):
            self.emitted_comments.add(ln)
            self.line(indent, f"// {self.comments[ln][0]}")

    def trailing_comment(self, node: ast.AST) -> str:
        ln = getattr(node, "end_lineno", None) or getattr(node, "lineno", None)
        if ln in self.comments and not self.comments[ln][1] and ln not in self.emitted_comments:
            self.emitted_comments.add(ln)
            return "  // " + self.comments[ln][0]
        return ""

    # -- module -----------------------------------------------------------

    def translate(self, nodes: list[ast.AST]) -> str:
        # Two passes. Python resolves a name at call time, so the core can call
        # a function defined further down the file; the translator has to know
        # every signature and record shape before it emits a single body.
        for node in nodes:
            self.register(node)
        for node in nodes:
            self.top_level(node)
        return "\n".join(self.out)

    def register(self, node: ast.AST) -> None:
        if isinstance(node, ast.ClassDef):
            self.records[node.name] = self.record_fields(node)
        elif isinstance(node, ast.FunctionDef):
            self.functions[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) == 1 and isinstance(targets[0], ast.Name):
                self.module.types[targets[0].id] = self.infer(node.value)
                self.module.declared.add(targets[0].id)

    def record_fields(self, node: ast.ClassDef):
        """Validate a @dataclass and return its (name, default, type) fields."""
        names = {d.id if isinstance(d, ast.Name) else getattr(d, "func", d).id
                 for d in node.decorator_list if isinstance(d, (ast.Name, ast.Call))}
        if "dataclass" not in names:
            fail(node, "only @dataclass classes are supported")
        fields = []
        for stmt in node.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                continue
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                fields.append((stmt.target.id, stmt.value, ann_type(stmt.annotation)))
                continue
            if isinstance(stmt, ast.FunctionDef):
                fail(stmt, "methods are not supported; make it a module-level function "
                           "outside the core markers")
            fail(stmt, f"unsupported statement in dataclass {node.name}")
        return fields

    def has_leading_comment(self, node: ast.AST) -> bool:
        ln = getattr(node, "lineno", 1) - 1
        return (ln in self.comments and self.comments[ln][1]
                and ln not in self.emitted_comments
                and not self.comments[ln][0].startswith("--- CORE"))

    def top_level(self, node: ast.AST) -> None:
        kind = "const" if isinstance(node, (ast.Assign, ast.AnnAssign)) else "block"
        if self.out and (kind == "block" or self.prev_kind == "block"
                         or self.has_leading_comment(node)):
            self.line(0, "")
        self.prev_kind = kind
        if isinstance(node, ast.ClassDef):
            self.dataclass(node)
        elif isinstance(node, ast.FunctionDef):
            self.function(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            self.leading_comments(node, 2)
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                fail(node, "only single-name module constants are supported")
            name = targets[0].id
            self.module.types[name] = self.infer(node.value)
            self.module.declared.add(name)
            value = self.expr(node.value, self.module)
            self.line(2, f"const {camel(name)} = {value};{self.trailing_comment(node)}")
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            pass  # a stray string, e.g. a module docstring
        else:
            fail(node, f"unsupported top-level {type(node).__name__}")

    def dataclass(self, node: ast.ClassDef) -> None:
        """Record the shape; emit a comment. A record is not a class in JS here.

        The dataclass is not translated into anything executable: constructions
        of it become plain object literals, which is exactly what index.html
        used to build by hand. The defaults declared here are what give the JS
        its empty-ladder defaults, instead of a second hand-written list of
        them that could drift.
        """
        fields = self.records[node.name]
        doc = ast.get_docstring(node)
        self.leading_comments(node, 2)
        if doc:
            self.comment_block(2, f"{node.name} — {doc}")
        self.line(2, "// Fields: " + ", ".join(camel(f) for f, _, _ in fields))

    def function(self, node: ast.FunctionDef) -> None:
        if node.decorator_list:
            fail(node, "decorated functions are not supported")
        self.functions[node.name] = node
        self.leading_comments(node, 2)
        doc = ast.get_docstring(node)
        if doc:
            self.comment_block(2, doc)
        scope = Scope(self.module)
        args = node.args
        if args.vararg or args.kwarg or args.kwonlyargs or args.posonlyargs:
            fail(node, "only plain positional parameters are supported")
        params = []
        pad = len(args.args) - len(args.defaults)
        for i, a in enumerate(args.args):
            scope.types[a.arg] = ann_type(a.annotation)
            scope.declared.add(a.arg)
            if i >= pad:
                params.append(f"{camel(a.arg)} = {self.expr(args.defaults[i - pad], scope)}")
            else:
                params.append(camel(a.arg))
        sig = f"function {camel(node.name)}({', '.join(params)}) {{"
        if len(sig) + 2 > 96:
            self.line(2, f"function {camel(node.name)}(")
            for i, p in enumerate(params):
                self.line(4, p + ("," if i < len(params) - 1 else ""))
            self.line(2, ") {")
        else:
            self.line(2, sig)
        body = node.body
        if doc and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]
        locals_ = self.collect_locals(node)
        for name in locals_:
            scope.declared.add(name)
        if locals_:
            # Declared together at the top because Python scopes locals to the
            # function and `let` scopes them to the block.
            chunks: list[str] = []
            line = ""
            for name in locals_:
                piece = camel(name)
                candidate = f"{line}, {piece}" if line else piece
                if line and len(candidate) > 82:
                    chunks.append(line + ",")
                    line = piece
                else:
                    line = candidate
            chunks.append(line + ";")
            for i, chunk in enumerate(chunks):
                self.line(4, ("let " if i == 0 else "    ") + chunk)
        self.body(body, 4, scope)
        self.line(2, "}")

    def collect_locals(self, fn: ast.FunctionDef) -> list[str]:
        """Every name the function assigns, in source order.

        Python scopes a local to the whole function; JavaScript scopes `let` to
        the block it sits in. Declaring at the point of first assignment would
        put `sliver` inside the `if linear:` arm and leave the `else` arm
        assigning a name that does not exist — so every local is declared once
        at the top instead, which is what Python is doing anyway.
        """
        params = {a.arg for a in fn.args.args}
        names: list[str] = []

        def add(name: str) -> None:
            if name not in params and name not in names:
                names.append(name)

        flag_n = 0
        for node in ast.walk(fn):
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = (node.targets if isinstance(node, ast.Assign)
                           else [node.target])
                for t in targets:
                    if isinstance(t, ast.Name):
                        add(t.id)
            elif isinstance(node, ast.For):
                for t in ast.walk(node.target):
                    if isinstance(t, ast.Name):
                        add(t.id)
        # for/else needs a flag apiece, named here so emission agrees.
        for node in ast.walk(fn):
            if isinstance(node, ast.For) and node.orelse:
                flag_n += 1
                flag = f"ranToEnd{flag_n}"
                self.flags[id(node)] = flag
                names.append(flag)
        return names

    # -- statements -------------------------------------------------------

    def body(self, stmts: list[ast.stmt], indent: int, scope: Scope) -> None:
        for stmt in stmts:
            self.stmt(stmt, indent, scope)

    def stmt(self, node: ast.stmt, indent: int, scope: Scope) -> None:
        self.leading_comments(node, indent)
        self.cur_indent = indent
        tail = self.trailing_comment(node)

        if isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                self.comment_block(indent, node.value.value)
                return
            self.line(indent, f"{self.expr(node.value, scope)};{tail}")
            return

        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) != 1:
                fail(node, "chained assignment is not supported")
            target = targets[0]
            if node.value is None:
                fail(node, "a declaration without a value is not supported")
            value = self.expr(node.value, scope)
            if isinstance(target, ast.Name):
                if isinstance(node, ast.AnnAssign):
                    scope.types[target.id] = ann_type(node.annotation)
                else:
                    inferred = self.infer(node.value, scope)
                    if target.id not in scope.types:
                        scope.types[target.id] = inferred
                    elif scope.types[target.id] != inferred:
                        scope.types[target.id] = None  # reassigned; stop claiming
                scope.declared.add(target.id)
                self.line(indent, f"{camel(target.id)} = {value};{tail}")
            elif isinstance(target, (ast.Attribute, ast.Subscript)):
                self.line(indent, f"{self.expr(target, scope)} = {value};{tail}")
            else:
                fail(node, f"unsupported assignment target {type(target).__name__}")
            return

        if isinstance(node, ast.AugAssign):
            op = BINOPS.get(type(node.op))
            if op is None:
                fail(node, f"unsupported augmented operator {type(node.op).__name__}")
            self.line(indent, f"{self.expr(node.target, scope)} {op}= "
                              f"{self.expr(node.value, scope)};{tail}")
            return

        if isinstance(node, ast.Return):
            if node.value is None:
                self.line(indent, f"return;{tail}")
            else:
                self.line(indent, f"return {self.expr(node.value, scope)};{tail}")
            return

        if isinstance(node, ast.Break):
            self.line(indent, f"break;{tail}")
            return

        if isinstance(node, ast.Pass):
            return

        if isinstance(node, ast.Raise):
            exc = node.exc
            if not (isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name)):
                fail(node, "only `raise SomeError(\"message\")` is supported")
            if len(exc.args) != 1:
                fail(node, "the raised error needs exactly one message argument")
            self.line(indent, f"throw new Error({self.expr(exc.args[0], scope)});{tail}")
            return

        if isinstance(node, ast.If):
            self.if_stmt(node, indent, scope, tail)
            return

        if isinstance(node, ast.For):
            self.for_stmt(node, indent, scope, tail)
            return

        fail(node, f"unsupported statement {type(node).__name__}")

    def if_stmt(self, node: ast.If, indent: int, scope: Scope, tail: str) -> None:
        self.line(indent, f"if ({self.boolean(node.test, scope)}) {{{tail}")
        self.body(node.body, indent + 2, scope)
        orelse = node.orelse
        while orelse:
            if len(orelse) == 1 and isinstance(orelse[0], ast.If):
                nxt = orelse[0]
                self.line(indent, f"}} else if ({self.boolean(nxt.test, scope)}) {{")
                self.body(nxt.body, indent + 2, scope)
                orelse = nxt.orelse
                continue
            self.line(indent, "} else {")
            self.body(orelse, indent + 2, scope)
            break
        self.line(indent, "}")

    def for_stmt(self, node: ast.For, indent: int, scope: Scope, tail: str) -> None:
        """for-over-range, for-over-sequence, enumerate, and for/else."""
        fell = None
        if node.orelse:
            fell = self.flags[id(node)]
            # Python's for/else: the else runs only when the loop was never
            # broken out of. There is no such thing in JavaScript, so it
            # becomes a flag that every `break` belonging to THIS loop clears.
            self.line(indent, f"{fell} = true;")

        it = node.iter
        target = node.target
        if isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range":
            if not isinstance(target, ast.Name):
                fail(node, "range loops need a single name target")
            if len(it.args) == 1:
                lo, hi = "0", self.expr(it.args[0], scope)
            elif len(it.args) == 2:
                lo, hi = self.expr(it.args[0], scope), self.expr(it.args[1], scope)
            else:
                fail(node, "range() with a step is not supported")
            var = camel(target.id)
            scope.declared.add(target.id)
            scope.types[target.id] = "int"
            self.line(indent, f"for ({var} = {lo}; {var} < {hi}; {var}++) {{{tail}")
            inner = indent + 2
        elif (isinstance(it, ast.Call) and isinstance(it.func, ast.Name)
              and it.func.id == "enumerate"):
            if not (isinstance(target, ast.Tuple) and len(target.elts) == 2
                    and all(isinstance(e, ast.Name) for e in target.elts)):
                fail(node, "enumerate() needs `for i, x in enumerate(seq)`")
            idx, item = (e.id for e in target.elts)
            if len(it.args) != 1:
                fail(node, "enumerate() with a start value is not supported")
            seq = self.expr(it.args[0], scope)
            for name in (idx, item):
                scope.declared.add(name)
            scope.types[idx] = "int"
            scope.types[item] = elem_of(self.infer(it.args[0], scope))
            ivar = camel(idx)
            self.line(indent, f"for ({ivar} = 0; {ivar} < {seq}.length; {ivar}++) {{{tail}")
            self.line(indent + 2, f"{camel(item)} = {seq}[{ivar}];")
            inner = indent + 2
        else:
            if not isinstance(target, ast.Name):
                fail(node, "sequence loops need a single name target")
            scope.declared.add(target.id)
            scope.types[target.id] = elem_of(self.infer(it, scope))
            self.line(indent, f"for ({camel(target.id)} of "
                              f"{self.expr(it, scope)}) {{{tail}")
            inner = indent + 2

        if fell:
            self.emit_body_with_break_flag(node.body, inner, scope, fell)
        else:
            self.body(node.body, inner, scope)
        self.line(indent, "}")
        if fell:
            self.line(indent, f"if ({fell}) {{")
            self.body(node.orelse, indent + 2, scope)
            self.line(indent, "}")

    def emit_body_with_break_flag(self, stmts, indent, scope, flag) -> None:
        """Emit a loop body, clearing `flag` at every break that belongs to it.

        Breaks inside a nested loop belong to that loop, not this one, so they
        are left alone — which is why this walks the statements rather than
        rewriting the text.
        """
        for stmt in stmts:
            if isinstance(stmt, ast.Break):
                self.leading_comments(stmt, indent)
                self.line(indent, f"{flag} = false;")
                self.line(indent, "break;")
            elif isinstance(stmt, ast.If):
                self.leading_comments(stmt, indent)
                self.line(indent, f"if ({self.boolean(stmt.test, scope)}) {{")
                self.emit_body_with_break_flag(stmt.body, indent + 2, scope, flag)
                if stmt.orelse:
                    self.line(indent, "} else {")
                    self.emit_body_with_break_flag(stmt.orelse, indent + 2, scope, flag)
                self.line(indent, "}")
            else:
                self.stmt(stmt, indent, scope)

    # -- expressions ------------------------------------------------------

    def boolean(self, node: ast.AST, scope: Scope) -> str:
        """An expression in a boolean position, with the truthiness rule applied."""
        self.check_truthy(node, scope)
        return self.expr(node, scope)

    def check_truthy(self, node: ast.AST, scope: Scope) -> None:
        """Reject anything whose Python truthiness would not survive in JS.

        An empty list is false in Python and true in JavaScript, and an empty
        string is false in both but a lone `"0"` is not — so a bare value is
        only allowed through when it is known to be a number or a bool. Write
        the comparison out instead.
        """
        if isinstance(node, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
            if isinstance(node, ast.BoolOp):
                for v in node.values:
                    self.check_truthy(v, scope)
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                self.check_truthy(node.operand, scope)
            return
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            return
        if isinstance(node, ast.Call):
            t = base_of(self.infer(node, scope))
            if t in NUMERIC_TYPES:
                return
            fail(node, "a call in a boolean position — its truthiness may differ "
                       "between Python and JavaScript; compare it explicitly")
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
            t = base_of(self.infer(node, scope))
            if t in NUMERIC_TYPES:
                return
            what = getattr(node, "id", None) or getattr(node, "attr", None) or "value"
            fail(node, f"`{what}` in a boolean position is {t or 'of unknown type'}; "
                       f"an empty list is falsy in Python and truthy in JavaScript, "
                       f"so write the comparison out (len(x) == 0, x is None, ...)")
        fail(node, f"unsupported boolean expression {type(node).__name__}")

    def infer(self, node: Optional[ast.AST], scope: Optional[Scope] = None) -> Optional[str]:
        """Just enough type inference to police boolean positions."""
        scope = scope or self.module
        if node is None:
            return None
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return "bool"
            if isinstance(node.value, int):
                return "int"
            if isinstance(node.value, float):
                return "float"
            if isinstance(node.value, str):
                return "str"
            return None
        if isinstance(node, ast.Name):
            return scope.lookup(node.id)
        if isinstance(node, ast.Attribute):
            owner = self.infer(node.value, scope)
            for fname, _, ftype in self.records.get(base_of(owner) or "", []):
                if fname == node.attr:
                    return ftype
            return None
        if isinstance(node, ast.Subscript):
            return elem_of(self.infer(node.value, scope))
        if isinstance(node, (ast.Compare, ast.BoolOp)):
            return "bool"
        if isinstance(node, ast.UnaryOp):
            return "bool" if isinstance(node.op, ast.Not) else self.infer(node.operand, scope)
        if isinstance(node, ast.BinOp):
            a, b = base_of(self.infer(node.left, scope)), base_of(self.infer(node.right, scope))
            if a in NUMERIC_TYPES and b in NUMERIC_TYPES:
                return "float" if "float" in (a, b) else "int"
            return None
        if isinstance(node, ast.IfExp):
            a, b = self.infer(node.body, scope), self.infer(node.orelse, scope)
            return a if a == b else (a if b is None else (b if a is None else None))
        if isinstance(node, (ast.List, ast.Tuple)):
            return "list"
        if isinstance(node, ast.Dict):
            return "dict"
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name in ("int", "len"):
                    return "int"
                if name == "float":
                    return "float"
                if name == "bool":
                    return "bool"
                if name in ("min", "max", "abs"):
                    return self.infer(node.args[0], scope) if node.args else None
                if name in self.records:
                    return name
                fn = self.functions.get(name)
                if fn is not None:
                    return ann_type(fn.returns)
            return None
        return None

    def expr(self, node: ast.AST, scope: Scope) -> str:
        if isinstance(node, ast.Constant):
            v = node.value
            if v is None:
                return "null"
            if v is True:
                return "true"
            if v is False:
                return "false"
            if isinstance(v, str):
                return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
            if isinstance(v, float):
                return repr(v)
            if isinstance(v, int):
                return str(v)
            fail(node, f"unsupported constant {v!r}")

        if isinstance(node, ast.Name):
            return camel(node.id)

        if isinstance(node, ast.Attribute):
            return f"{self.expr(node.value, scope)}.{camel(node.attr)}"

        if isinstance(node, ast.Subscript):
            base = self.expr(node.value, scope)
            idx = node.slice
            if isinstance(idx, ast.UnaryOp) and isinstance(idx.op, ast.USub):
                # JavaScript has no negative indexing.
                off = self.expr(idx.operand, scope)
                return f"{base}[{base}.length - {off}]"
            return f"{base}[{self.expr(idx, scope)}]"

        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.FloorDiv):
                # Python's // floors toward -Infinity, and so does Math.floor.
                return (f"Math.floor({self.expr(node.left, scope)} / "
                        f"{self.expr(node.right, scope)})")
            if isinstance(node.op, ast.Mult) and isinstance(node.left, ast.List):
                if len(node.left.elts) != 1:
                    fail(node, "list repetition only supports a single element")
                return (f"new Array({self.expr(node.right, scope)})"
                        f".fill({self.expr(node.left.elts[0], scope)})")
            op = BINOPS.get(type(node.op))
            if op is None:
                fail(node, f"unsupported operator {type(node.op).__name__}")
            return f"({self.expr(node.left, scope)} {op} {self.expr(node.right, scope)})"

        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return f"!{self.expr(node.operand, scope)}"
            if isinstance(node.op, ast.USub):
                return f"-{self.expr(node.operand, scope)}"
            if isinstance(node.op, ast.UAdd):
                return self.expr(node.operand, scope)
            fail(node, f"unsupported unary operator {type(node.op).__name__}")

        if isinstance(node, ast.BoolOp):
            op = "&&" if isinstance(node.op, ast.And) else "||"
            for v in node.values:
                self.check_truthy(v, scope)
            return "(" + f" {op} ".join(self.expr(v, scope) for v in node.values) + ")"

        if isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                fail(node, "chained comparisons are not supported")
            op, right = node.ops[0], node.comparators[0]
            left = self.expr(node.left, scope)
            if isinstance(op, (ast.Is, ast.IsNot)):
                if not (isinstance(right, ast.Constant) and right.value is None):
                    fail(node, "`is` is only supported against None")
                return f"{left} {'===' if isinstance(op, ast.Is) else '!=='} null"
            if isinstance(op, (ast.In, ast.NotIn)):
                inner = f"{self.expr(right, scope)}.includes({left})"
                return inner if isinstance(op, ast.In) else f"!{inner}"
            js = CMPOPS.get(type(op))
            if js is None:
                fail(node, f"unsupported comparison {type(op).__name__}")
            return f"{left} {js} {self.expr(right, scope)}"

        if isinstance(node, ast.IfExp):
            return (f"({self.boolean(node.test, scope)} ? {self.expr(node.body, scope)} "
                    f": {self.expr(node.orelse, scope)})")

        if isinstance(node, (ast.List, ast.Tuple)):
            return "[" + ", ".join(self.expr(e, scope) for e in node.elts) + "]"

        if isinstance(node, ast.Dict):
            parts = []
            for k, v in zip(node.keys, node.values):
                if k is None:
                    fail(node, "dict unpacking is not supported")
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    # Every dict literal in the core is a record, so its keys
                    # are field names and get the same camelCase treatment.
                    key = camel(k.value)
                elif isinstance(k, ast.Constant) and isinstance(k.value, (int, float)):
                    key = str(k.value)
                else:
                    fail(node, "dict keys must be string or number literals")
                parts.append(f"{key}: {self.expr(v, scope)}")
            return self.wrap_literal(parts)

        if isinstance(node, ast.Call):
            return self.call(node, scope)

        fail(node, f"unsupported expression {type(node).__name__}")

    def call(self, node: ast.Call, scope: Scope) -> str:
        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr != "append":
                fail(node, f"unsupported method .{func.attr}()")
            return (f"{self.expr(func.value, scope)}"
                    f".push({', '.join(self.expr(a, scope) for a in node.args)})")
        if not isinstance(func, ast.Name):
            fail(node, "only plain function calls are supported")
        name = func.id

        if name in self.records:
            return self.record_literal(node, name, scope)

        if name in CALLS:
            if node.keywords:
                fail(node, f"{name}() takes no keyword arguments")
            return f"{CALLS[name]}({', '.join(self.expr(a, scope) for a in node.args)})"

        if name == "len":
            if len(node.args) != 1:
                fail(node, "len() takes one argument")
            return f"{self.expr(node.args[0], scope)}.length"

        if name in self.functions:
            return f"{camel(name)}({', '.join(self.bind_args(node, self.functions[name], scope))})"

        fail(node, f"call to unknown name `{name}` — the core may only call "
                   f"itself and the whitelisted builtins")

    def bind_args(self, node: ast.Call, fn: ast.FunctionDef, scope: Scope) -> list[str]:
        """Map a Python call onto JavaScript positional arguments.

        Python lets you skip a middle parameter by naming the ones after it;
        JavaScript does not, so any gap is filled in with that parameter's own
        default rather than left for the reader to notice.
        """
        names = [a.arg for a in fn.args.args]
        defaults = fn.args.defaults
        pad = len(names) - len(defaults)
        supplied: dict[str, str] = {}
        for i, a in enumerate(node.args):
            supplied[names[i]] = self.expr(a, scope)
        for kw in node.keywords:
            if kw.arg is None:
                fail(node, "** unpacking is not supported")
            if kw.arg not in names:
                fail(node, f"`{kw.arg}` is not a parameter of {fn.name}()")
            supplied[kw.arg] = self.expr(kw.value, scope)
        last = max((names.index(k) for k in supplied), default=-1)
        out = []
        for i, nm in enumerate(names[: last + 1]):
            if nm in supplied:
                out.append(supplied[nm])
            elif i >= pad:
                out.append(self.expr(defaults[i - pad], scope))
            else:
                fail(node, f"{fn.name}() needs a value for `{nm}`")
        return out

    def record_literal(self, node: ast.Call, name: str, scope: Scope) -> str:
        """A @dataclass construction as an object literal, defaults included."""
        fields = self.records[name]
        values: dict[str, str] = {}
        for i, a in enumerate(node.args):
            values[fields[i][0]] = self.expr(a, scope)
        for kw in node.keywords:
            if kw.arg is None:
                fail(node, "** unpacking is not supported")
            values[kw.arg] = self.expr(kw.value, scope)
        parts = []
        for fname, default, _ in fields:
            if fname in values:
                parts.append(f"{camel(fname)}: {values[fname]}")
            elif default is not None:
                parts.append(f"{camel(fname)}: {self.default_expr(default, scope)}")
            else:
                fail(node, f"{name}() is missing a value for `{fname}`")
        return self.wrap_literal(parts)

    def wrap_literal(self, parts: list[str]) -> str:
        """An object literal on one line, or one field per line if it is long."""
        body = ", ".join(parts)
        if len(body) + self.cur_indent <= 88:
            return "{ " + body + " }"
        pad = " " * (self.cur_indent + 2)
        return "{\n" + ",\n".join(pad + p for p in parts) + "\n" + " " * self.cur_indent + "}"

    def default_expr(self, node: ast.AST, scope: Scope) -> str:
        """A dataclass default, seeing through field(default_factory=...)."""
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "field":
            for kw in node.keywords:
                if kw.arg == "default_factory":
                    if isinstance(kw.value, ast.Name) and kw.value.id == "list":
                        return "[]"
                    if isinstance(kw.value, ast.Name) and kw.value.id == "dict":
                        return "{}"
                    fail(node, "only list/dict default factories are supported")
                if kw.arg == "default":
                    return self.expr(kw.value, scope)
            fail(node, "field() needs a default or default_factory")
        return self.expr(node, scope)


# --------------------------------------------------------------------------
# Driving it
# --------------------------------------------------------------------------

def core_regions(src: str) -> list[tuple[int, int]]:
    """Line ranges (1-based, inclusive) between the CORE markers."""
    regions: list[tuple[int, int]] = []
    start: Optional[int] = None
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if stripped == CORE_BEGIN:
            if start is not None:
                raise Unsupported(f"{PY_FILE}:{i}: CORE BEGIN inside a core region")
            start = i
        elif stripped == CORE_END:
            if start is None:
                raise Unsupported(f"{PY_FILE}:{i}: CORE END without a CORE BEGIN")
            regions.append((start, i))
            start = None
    if start is not None:
        raise Unsupported(f"{PY_FILE}: CORE BEGIN at line {start} is never closed")
    if not regions:
        raise Unsupported(f"{PY_FILE}: no core regions found")
    return regions


def core_nodes(src: str) -> list[ast.AST]:
    """Top-level nodes inside the core regions, minus the skipped ones."""
    tree = ast.parse(src)
    regions = core_regions(src)
    lines = src.splitlines()
    out = []
    for node in tree.body:
        first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        if not any(lo < first < hi for lo, hi in regions):
            continue
        above = lines[first - 2].strip() if first >= 2 else ""
        if above.startswith(SKIP_MARK):
            continue
        out.append(node)
    return out


def check_overrides(src: str) -> None:
    """Every NAME_OVERRIDES key must still exist in taper.py.

    Without this the table would rot silently: rename a field in Python, and
    the override would stop matching, the mechanical rule would take over, and
    index.html would start reading a key that is no longer there.
    """
    missing = [k for k in NAME_OVERRIDES if not re.search(rf"\b{re.escape(k)}\b", src)]
    if missing:
        raise Unsupported(
            "NAME_OVERRIDES in gen_core.py names things that are not in "
            f"{PY_FILE} any more: {', '.join(missing)}. Update the table."
        )


HEADER = """\
  /* The ladder maths, translated from the CORE regions of taper.py by
     gen_core.py. Do not edit this block: `python3 gen_core.py --check` fails
     on any hand-edit, and `node test_parity.js` runs it against the Python it
     came from. To change the maths, change taper.py and regenerate.

     The comments below are the ones in taper.py, carried across so this reads
     as something other than machine output. The names are camelCase because
     the translator converts them; everything else is as it is written there. */
"""


def translate_source(src: str) -> str:
    """Translate the core regions of one source string.

    Split out from generate() so TestCoreGenerator can put a three-line snippet
    through the same path the real file takes, rather than testing a
    parallel one.
    """
    return Translator(src).translate(core_nodes(src))


def generate() -> str:
    src = open(PY_FILE, encoding="utf-8").read()
    check_overrides(src)
    return HEADER + "\n" + translate_source(src).rstrip() + "\n"


def splice(html: str, block: str) -> str:
    lo = html.find(JS_BEGIN)
    hi = html.find(JS_END)
    if lo == -1 or hi == -1 or hi < lo:
        raise Unsupported(f"{HTML_FILE}: generated-core markers not found")
    return html[: lo + len(JS_BEGIN)] + "\n" + block + html[hi:]


def current_block(html: str) -> str:
    lo = html.find(JS_BEGIN)
    hi = html.find(JS_END)
    if lo == -1 or hi == -1 or hi < lo:
        raise Unsupported(f"{HTML_FILE}: generated-core markers not found")
    return html[lo + len(JS_BEGIN) + 1: hi]


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--write"
    if mode not in ("--write", "--check", "--print"):
        print(__doc__)
        return 2
    try:
        block = generate()
    except Unsupported as e:
        print(f"gen_core.py: {e}", file=sys.stderr)
        return 1

    if mode == "--print":
        sys.stdout.write(block)
        return 0

    html = open(HTML_FILE, encoding="utf-8").read()
    try:
        have = current_block(html)
    except Unsupported as e:
        print(f"gen_core.py: {e}", file=sys.stderr)
        return 1

    if mode == "--check":
        if have == block:
            n = len(block.splitlines())
            print(f"OK — the generated core in {HTML_FILE} matches {PY_FILE} "
                  f"({n} lines)")
            return 0
        import difflib
        print(f"STALE — the generated core in {HTML_FILE} is not what {PY_FILE} "
              f"produces. Run: python3 gen_core.py", file=sys.stderr)
        diff = difflib.unified_diff(have.splitlines(), block.splitlines(),
                                    "index.html (checked in)", "generated from taper.py",
                                    lineterm="", n=2)
        for line in list(diff)[:60]:
            print(line, file=sys.stderr)
        return 1

    open(HTML_FILE, "w", encoding="utf-8").write(splice(html, block))
    print(f"wrote {len(block.splitlines())} lines into {HTML_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
