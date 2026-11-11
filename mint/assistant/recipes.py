"""Processing recipes: expression templates the model fills only with a recipe name and bounded numbers."""
import json
import math
import os
import re
from functools import lru_cache

RECIPES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "assistant",
                            "recipes.json")

# Time in seconds from the first sample and median sample period in seconds. Absolute
# times are nanoseconds (above 1e12) and pulse times are seconds: both give seconds.
TIME_SCALE = "np.where(np.abs(${self}.time[0]) > 1e12, 1e9, 1.0)"
TIME_S = f"((${{self}}.time - ${{self}}.time[0]) / {TIME_SCALE})"
# A plain number: on MINT's data a median comes back as a one-element array, which a window
# length (an integer) or a sampling frequency does not accept.
DT_S = f"np.ravel(np.median(np.diff({TIME_S})))[0]"
SELF_DATA = "${self}.data"


class RecipeError(ValueError):
    pass


class MissingParam(RecipeError):
    """A number the user did not give; the message is the question to ask them."""

    def __init__(self, question: str, param: str):
        super().__init__(question)
        self.param = param


@lru_cache(maxsize=1)
def load() -> dict:
    with open(RECIPES_FILE, "r", encoding="utf-8") as f:
        recipes = json.load(f)
    return {k: v for k, v in recipes.items() if not k.startswith("_")}


def number(value) -> str:
    """A finite number written for an expression: plain, short and exact enough."""
    v = float(value)
    if not math.isfinite(v):
        raise RecipeError("the value must be a finite number")
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return format(v, ".6g")


def nice_window(seconds: float) -> float:
    """Round a duration to 1, 2 or 5 times a power of ten."""
    if seconds <= 0:
        return 1.0
    exponent = math.floor(math.log10(seconds))
    for step in (1, 2, 5, 10):
        candidate = step * 10 ** exponent
        if candidate >= seconds * 0.75:
            return float(candidate)
    return float(10 ** (exponent + 1))


def resolve_params(name: str, given: dict, range_seconds=None) -> dict:
    """Validated numeric parameters of a recipe, with defaults filled in."""
    recipes = load()
    if name not in recipes:
        raise RecipeError(f"unknown recipe {name!r}")
    specs = recipes[name].get("params", {})
    unknown = set(given) - set(specs)
    if unknown:
        raise RecipeError(f"{name} does not take {', '.join(sorted(unknown))}")
    values = {}
    for pname, spec in specs.items():
        raw = given.get(pname)
        if raw is None or raw == "":
            if spec.get("auto") == "window" and range_seconds:
                values[pname] = nice_window(range_seconds / 100.0)
                continue
            if "default" in spec:
                values[pname] = float(spec["default"])
                continue
            # A number the user did not give: ask for it rather than guess.
            raise MissingParam(spec.get("ask") or f"{name} needs {pname}", pname)
        try:
            v = float(raw)
        except (TypeError, ValueError):
            raise RecipeError(f"{raw} isn't a number I can use. Could you give me another one?")
        if not math.isfinite(v) or v < spec.get("min", -math.inf) or v > spec.get("max", math.inf):
            too = "small" if math.isfinite(v) and v < spec.get("min", -math.inf) else "large"
            raise RecipeError(f"{raw} is too {too} for this. Could you give me another number?")
        values[pname] = v
    if name == "scale" and values.get("factor") == 1 and not values.get("offset"):
        raise MissingParam(specs["factor"].get("ask") or "scale needs a factor", "factor")
    return values


def human_duration(seconds: float) -> str:
    """A duration as people say it: 900 -> "15 min", 5400 -> "1.5 h", 0.25 -> "250 ms"."""
    for unit, size in (("days", 86400), ("h", 3600), ("min", 60), ("s", 1)):
        amount = seconds / size
        if amount >= 1 and round(amount, 1) == amount:
            text = number(amount)
            return f"{text} {'day' if unit == 'days' and amount == 1 else unit}"
    if seconds < 1:
        return f"{number(round(seconds * 1000, 3))} ms"
    return f"{number(round(seconds, 3))} s"


def _fill(text: str, fields: dict) -> str:
    for key, value in fields.items():
        text = text.replace("{" + key + "}", value)
    # "x × 3.6 + 0" reads "x × 3.6", and "+ -2" reads "− 2".
    return re.sub(r" \+ 0$", "", text).replace("+ -", "− ")


def render(name: str, values: dict, data_expr: str = "") -> dict:
    """Expression, axis, alias suffix and descriptions of a recipe applied to data_expr.

    "describe" is kept in the table's Comment column; "title" and "plain" are for the card.
    """
    recipe = load()[name]
    source = f"({data_expr})" if data_expr and data_expr != SELF_DATA else SELF_DATA
    fields = {pname: number(v) for pname, v in values.items()}
    expr = recipe["expr"]
    for key, value in fields.items():
        expr = expr.replace("{" + key + "}", value)
    expr = expr.replace("{dt}", DT_S).replace("{t}", TIME_S).replace("{x}", source)
    alias = recipe.get("alias", "")
    for key, value in fields.items():
        alias = alias.replace("{" + key + "}", value.replace(".", "p").replace("-", "m"))
    describe = _fill(recipe.get("describe", name), fields)
    # The card says durations as people do ("15 min"), the Comment column keeps seconds.
    spoken = dict(fields, **({"duration": human_duration(values["seconds"])} if "seconds" in values else {}))
    return {"axis": recipe.get("axis", "y"), "expr": expr, "alias": alias, "describe": describe,
            "label": recipe.get("label", name), "title": recipe.get("title", recipe.get("label", name)),
            "plain": _fill(recipe.get("plain", describe), spoken)}
