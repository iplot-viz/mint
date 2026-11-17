"""The preferences the assistant can set, as MINT's Preferences window offers them (iplotlib's canvas, plot and signal
forms): the key in the commands, the property it sets, its values, and how a card says it.

One catalogue for the grammar, the planner and the training cases; a test checks it against the forms.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

# Colours by name, and #rrggbb as the colour picker writes them.
COLORS = {"red": "#d62728", "blue": "#1f77b4", "green": "#2ca02c", "orange": "#ff7f0e", "purple": "#9467bd",
          "brown": "#8c564b", "pink": "#e377c2", "grey": "#7f7f7f", "gray": "#7f7f7f", "olive": "#bcbd22",
          "cyan": "#17becf", "black": "#000000", "white": "#ffffff", "yellow": "#ffd700", "magenta": "#ff00ff",
          "navy": "#000080", "teal": "#008080", "maroon": "#800000"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LINE_STYLES = {"solid": "Solid", "dotted": "Dotted", "dashed": "Dashed", "none": "None"}
LEGEND_PLACES = {"upper-right": "upper right", "upper-left": "upper left", "upper-center": "upper center",
                 "lower-right": "lower right", "lower-left": "lower left", "lower-center": "lower center",
                 "center-right": "center right", "center-left": "center left", "center": "center"}


@dataclass(frozen=True)
class Setting:
    key: str  # as the commands write it: "line"
    prop: str  # the property of the iplotlib object: "line_style"
    kind: str  # onoff, choice, int, color, text, num
    words: str  # as a card says it: "line style"
    choices: Dict[str, object] = field(default_factory=dict)  # for onoff and choice: command value -> property value
    low: int = 0
    high: int = 0

    def value(self, given: str):
        """The property value for what the command says; ValueError when it isn't one."""
        if self.kind in ("onoff", "choice"):
            if given not in self.choices:
                raise ValueError(f"{self.words} can be {_listed(self.choices)}")
            return self.choices[given]
        if self.kind == "int":
            number = int(float(given))
            if not self.low <= number <= self.high:
                raise ValueError(f"{self.words} goes from {self.low} to {self.high}")
            return number
        if self.kind == "num":
            return float(given)
        if self.kind == "color":
            color = COLORS.get(given.lower(), given)
            if not HEX.match(color):
                raise ValueError(f"{given} isn't a colour I know; say its name or #rrggbb")
            return color
        return given

    def said(self, given: str) -> str:
        if self.kind == "onoff":
            return f"{self.words} {given}"
        if self.kind == "text":
            return f"{self.words} \"{given}\""
        return f"{self.words} {given.replace('-', ' ')}"


ON_OFF = {"on": True, "off": False}
_MARKERS = {"on": "o", "off": "None", "x": "x", "o": "o"}
_STEPS = {"on": "post", "off": "linear"}


def _common(prefix_words: str = "") -> Tuple[Setting, ...]:
    """The line and marker of the signals, set on a plot (all its signals) or on one signal."""
    return (
        Setting("line", "line_style", "choice", "line style", LINE_STYLES),
        Setting("width", "line_size", "int", "line width", low=1, high=20),
        Setting("marker", "marker", "choice", "markers", _MARKERS),
        Setting("marker_size", "marker_size", "int", "marker size", low=1, high=20),
        Setting("steps", "step", "onoff", "steps (last value held)", _STEPS),
        Setting("vlines", "vertical_lines", "choice", "vertical lines", LINE_STYLES),
    )


# A plot (iplotlib PlotForm), its y axis included.
PLOT = {s.key: s for s in (
    Setting("log", "log_scale", "onoff", "log scale", ON_OFF),
    Setting("grid", "grid", "onoff", "grid", ON_OFF),
    Setting("legend", "legend", "onoff", "legend", ON_OFF),
    Setting("legend_at", "legend_position", "choice", "legend at", LEGEND_PLACES),
    Setting("title", "plot_title", "text", "title"),
    Setting("font", "font_size", "int", "font size", low=1, high=48),
    Setting("background", "background_color", "color", "background"),
    *_common(),
    Setting("ymin", "begin", "num", "y axis from"),
    Setting("ymax", "end", "num", "y axis up to"),
    Setting("ylabel", "label", "text", "y axis label"),
)}
# Those of the y axis, not of the plot itself.
AXIS_KEYS = ("ymin", "ymax", "ylabel")
# A signal (iplotlib SignalForm).
SIGNAL = {s.key: s for s in (
    Setting("color", "color", "color", "colour"),
    Setting("label", "label", "text", "legend name"),
    *_common(),
)}
# The canvas (iplotlib CanvasForm): what applies to it as a whole.
CANVAS = {s.key: s for s in (
    Setting("shared_time", "shared_x_axis", "onoff", "shared time", ON_OFF),
    Setting("round_hours", "round_hour", "onoff", "round hours", ON_OFF),
    Setting("title", "title", "text", "title"),
    Setting("font", "font_size", "int", "font size", low=1, high=48),
    Setting("background", "background_color", "color", "background"),
    Setting("legend_at", "legend_position", "choice", "legend at", LEGEND_PLACES),
)}


def grammar_values(setting: Setting) -> str:
    """The GBNF of a setting's values."""
    if setting.kind in ("onoff", "choice"):
        return " | ".join(f'"{v}"' for v in setting.choices)
    if setting.kind == "int":
        # The longest first: "12" is not "1" followed by something else.
        return " | ".join(f'"{n}"' for n in range(setting.high, setting.low - 1, -1))
    if setting.kind == "num":
        return "num"
    if setting.kind == "color":
        return " | ".join(f'"{c}"' for c in COLORS) + ' | "#" [0-9a-fA-F]{6}'
    return "str"


def parse_value(catalogue: Dict[str, Setting], key: str, given: str):
    setting = catalogue.get(key)
    if setting is None:
        raise ValueError(f"I can't set '{key}' there")
    return setting, setting.value(given)


def _listed(choices) -> str:
    names = [str(c) for c in choices]
    return ", ".join(names[:-1]) + f" or {names[-1]}" if len(names) > 1 else names[0]


def color_name(value: Optional[str]) -> str:
    """A colour as people say it, when it is one of the named ones."""
    for name, code in COLORS.items():
        if code == (value or "").lower():
            return name
    return value or ""
