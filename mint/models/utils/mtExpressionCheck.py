"""Why MINT can't use an x, y or z expression of the table, in words that say what to do about it: what the parser
refuses, what would fail for certain once computed, what computing it said when it failed, and what it gave when it
gave no values."""
import ast
import difflib
import importlib.util
import inspect
import re
import typing

import numpy as np

from iplotProcessing.tools import Parser

# A variable of an expression, as ${alias} or ${self}.
VARIABLE = re.compile(r"\$\{(.*?)\}")
# The name each variable takes to read the expression as Python (see _python).
_PLACEHOLDER = "mint_variable_"
# What a signal of an expression offers: its values, and those of an envelope or a contour.
SIGNAL_MEMBERS = ("time", "data", "data_store", "dmin", "dmax", "davg", "r", "z", "psi")
# What the parser refuses to evaluate, as it looks for it (see Parser.validate_pre_compile).
REFUSED = ("**", "for ", "if ", "__", "[]", "()", "{}")
# What computing an expression says of a module that hasn't the member it names.
NO_MEMBER = re.compile(r"module '([\w.]+)' has no attribute '(\w+)'")


def why_rejected(expression: str, error: str, known: dict, aliases: typing.Iterable[str]) -> str:
    """Why the parser rejected ``expression``, with ``error`` if it raised one, and what puts it right; '' when that
    can't be said.

    known: the names expressions can use (Parser.supported_members); aliases: those of the rows of the table.
    """
    aliases = set(aliases)
    if "${" not in expression and "}" not in expression:
        name = expression.strip()
        if name in aliases:
            return f"{name} is the alias of a row (write it as ${{{name}}})"
        return "it names no signal (write those it uses as ${alias})"
    if expression.count("${") != expression.count("}"):
        return "a ${ isn't closed with }"
    code = _python(expression)
    refused = next((token.strip() for token in REFUSED if token in code), "")
    if refused:
        return f"expressions can't use {refused}"
    try:
        tree = ast.parse(code, mode="eval")
    except SyntaxError as e:
        return f"it isn't written right ({e.msg})"
    undefined = error.partition("Undefined name ")[2].strip()
    if not undefined:
        return ""
    bound = _bound(tree)
    for chain in _chains(tree):
        said = _unknown_in(chain, known, aliases) if undefined in chain and chain[0] not in bound else ""
        if said:
            return said
    return f"MINT doesn't know {undefined}"


def call_problem(expression: str, known: dict) -> str:
    """What fails for certain in an expression the parser accepts, before it is computed: a module without the member
    named, or a function of Python given arguments it doesn't take. '' for none."""
    if "${" not in expression:
        return ""
    try:
        tree = ast.parse(_python(expression), mode="eval")
    except SyntaxError:
        return ""
    bound = _bound(tree)
    for chain in _chains(tree):
        if not chain[0].startswith(_PLACEHOLDER) and chain[0] not in bound and chain[0] in known:
            missing = _missing_member(chain, known)
            if missing:
                return missing
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            said = _wrong_arguments(node, known, bound)
            if said:
                return said
    return ""


def why_failed(column: str, said: str) -> str:
    """Why computing a row failed, from what its processing said: column is the x, y or z whose expression failed,
    '' for the expression of the variable."""
    said = " ".join(str(said or "").split())
    prefix = f"the {column} expression failed: "
    if column and said.startswith(prefix):
        said = said[len(prefix):]
    if said.startswith("Value error "):
        said = said[len("Value error "):]
    if said.startswith("Following keys are undefined"):  # what the parser says of a TypeError
        said = "a function or an operation in it got values it can't take"
    elif said.startswith("Undefined name "):
        said = f"MINT doesn't know {said[len('Undefined name '):]}"
    else:
        said = NO_MEMBER.sub(r"\1 has no \2", said)
    what = f"The {column} expression" if column else "The variable expression"
    return f"{what} failed: {said}" if said else f"{what} failed"


def without_values(signal, defaults: dict) -> typing.Tuple[str, str]:
    """For a signal computed with nothing to draw: the x, y or z whose expression gives something else than an array,
    as the tuple a function returns, and what it gives; ('', '') for none. Computing leaves such a result out without
    saying so. defaults: the expression of each that reads the signal as it is, which needs no computing."""
    # Computing again what uses other signals reads them and lines them up, which changes this one: only expressions
    # of the signal alone are computed again.
    if set(getattr(signal, "depends_on", None) or ()) - {"self"}:
        return "", ""
    expressions = {key: getattr(signal, f"{key}_expr", "") for key in ("x", "y", "z")}
    custom = {key: expression for key, expression in expressions.items() if expression and expression != defaults[key]}
    if not custom:
        return "", ""
    results = signal.compute(**custom)
    for key in custom:
        if not isinstance(results.get(key), np.ndarray):
            return key, f"it gives {_what(results.get(key))}, not an array of values"
    return "", ""


def _what(value) -> str:
    if isinstance(value, tuple):
        return f"a tuple of {len(value)}"
    if isinstance(value, (bool, int, float, complex, np.generic)):
        return "a single number"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, str):
        return "a text"
    return "None" if value is None else f"a {type(value).__name__}"


def _python(expression: str) -> str:
    """The expression as Python: each variable a name of its own, and a time as 10s a number, as the parser reads
    them."""
    names = {}
    code = VARIABLE.sub(lambda m: names.setdefault(m.group(1), f"{_PLACEHOLDER}{len(names)}"), expression)
    return re.sub(Parser.date_time_unit_pattern, lambda m: m.group(1), code)


def _chains(tree) -> typing.List[typing.List[str]]:
    """The dotted names of an expression in the order they are written: np.diff, mctf.slope, the variables and
    their members."""
    inner = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    chains = [(node.lineno, node.col_offset, _dotted(node)) for node in ast.walk(tree)
              if isinstance(node, (ast.Name, ast.Attribute)) and id(node) not in inner]
    return [chain for _, _, chain in sorted(chains, key=lambda found: found[:2]) if chain]


def _bound(tree) -> typing.Set[str]:
    """The names an expression gives values to itself, as the parameters of a lambda: not those MINT knows."""
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Lambda):
            arguments = node.args
            names.update(arg.arg for arg in arguments.posonlyargs + arguments.args + arguments.kwonlyargs)
            names.update(arg.arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None)
    return names


def _dotted(node) -> typing.List[str]:
    """[name, member, member...] of a name and the members taken from it, as mctf.slope; [] for anything else."""
    members = []
    while isinstance(node, ast.Attribute):
        members.insert(0, node.attr)
        node = node.value
    return [node.id] + members if isinstance(node, ast.Name) else []


def _unknown_in(chain, known: dict, aliases: set) -> str:
    """What of a dotted name MINT doesn't know, and how to put it right."""
    root = chain[0]
    if root.startswith(_PLACEHOLDER):
        if len(chain) > 1 and chain[1] not in SIGNAL_MEMBERS and chain[1] not in known:
            close = difflib.get_close_matches(chain[1], SIGNAL_MEMBERS, n=1, cutoff=0.6)
            return f"a signal has no {chain[1]}" + (f" (did you mean .{close[0]}?)" if close else "")
        return ""
    if root not in known:
        if root in aliases:
            return f"{root} is the alias of a row (write it as ${{{root}}})"
        if _importable(root):
            return f"{root} is a Python module that isn't loaded (add it with Load new module)"
        close = difflib.get_close_matches(root, [name for name in known if not name.startswith("_")], n=1,
                                          cutoff=0.8)
        return f"MINT doesn't know {root}" + (
            f" (did you mean {close[0]}?)" if close else " (if it is a module of yours, add it with Load new module)")
    return _missing_member(chain, known)


def _missing_member(chain, known: dict) -> str:
    """The first member of a dotted name that its module or object doesn't have."""
    obj = known[chain[0]]
    for i, member in enumerate(chain[1:], start=1):
        try:
            obj = getattr(obj, member)
        except AttributeError:
            owner = ".".join(chain[:i])
            names = [name for name in _members(obj) if not name.startswith("_")]
            close = difflib.get_close_matches(member, names, n=1, cutoff=0.6)
            return f"{owner} has no {member}" + (f" (did you mean {owner}.{close[0]}?)" if close else "")
        except Exception:
            # Not a member that is missing: what it is is known once computed.
            return ""
    return ""


def _members(obj) -> typing.List[str]:
    try:
        return dir(obj)
    except Exception:
        return []


def _importable(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _wrong_arguments(call: ast.Call, known: dict, bound: typing.Set[str]) -> str:
    """The arguments a function of Python doesn't take, as calling it would say. A function whose parameters can't
    be known for certain (of numpy in C, a class, a call with * or **) is left to the computation."""
    chain = _dotted(call.func)
    if not chain or chain[0].startswith(_PLACEHOLDER) or chain[0] in bound or chain[0] not in known:
        return ""
    if any(isinstance(arg, ast.Starred) for arg in call.args) or any(kw.arg is None for kw in call.keywords):
        return ""
    function = known[chain[0]]
    for member in chain[1:]:
        function = getattr(function, member, None)
    if not inspect.isfunction(function):
        return ""
    try:
        # What the function itself takes: that of a decorator, not of what it wraps.
        signature = inspect.signature(function, follow_wrapped=False)
    except (TypeError, ValueError):
        return ""
    try:
        signature.bind(*call.args, **{kw.arg: kw.value for kw in call.keywords})
    except TypeError as e:
        return _arguments_said(".".join(chain), signature, len(call.args), str(e))
    return ""


def _arguments_said(name: str, signature: inspect.Signature, given: int, error: str) -> str:
    positional = [p.name for p in signature.parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    quoted = re.search(r"'([^']+)'", error)
    if error.startswith("too many positional arguments"):
        takes = (f"{len(positional)} argument{'s' if len(positional) != 1 else ''} ({', '.join(positional)})"
                 if positional else "no arguments")
        return f"{name} takes {takes}, not {given}"
    if error.startswith("missing a required argument") and quoted:
        return f"{name} also needs {quoted.group(1)}"
    if "unexpected keyword argument" in error and quoted:
        return f"{name} has no argument {quoted.group(1)}"
    if "multiple values for argument" in error and quoted:
        return f"{name} gets {quoted.group(1)} twice"
    return f"{name} doesn't take these arguments"
