"""Train a small model for the MINT assistant (LoRA), end to end, where the workspaces are.

    python -m mint.tools.assistant_train data --out data.jsonl WORKSPACE.json ...
    python -m mint.tools.assistant_train paraphrase --teacher HF_DIR --data data.jsonl --out data_p.jsonl
    python -m mint.tools.assistant_train feedback --out feedback.jsonl RECORD.jsonl ...
    python -m mint.tools.assistant_train train --base HF_DIR --data data_p.jsonl --workspaces data_workspaces.json --out DIR
    python -m mint.tools.assistant_train merge --gguf BASE-BF16.gguf --adapter DIR --out merged-F16.gguf
    python -m mint.tools.assistant_train quantize --gguf merged-F16.gguf --out mint-assistant-Q4_K_M.gguf

Workspaces, requests and weights stay on the machine that runs this. Training needs torch, transformers and peft; merging needs gguf.
"""
import argparse
import json
import math
import random
import re
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from mint.assistant import commands, files, prompt, recipes
from mint.assistant.snapshot import FileInfo, FileVariable, RowInfo, build as build_snapshot

FORMAT = "qwen3-nothink"
LANGUAGES = [("English", 55), ("French", 12), ("Spanish", 10), ("Italian", 8), ("German", 8), ("Portuguese", 7)]
STYLES = ["short and informal", "polite", "terse, like a quick note", "a full sentence",
          "short, with one small typo that keeps the names intact"]
RANGES = [("last 2 hours", 7200), ("last 1 hours", 3600), ("last 1 days", 86400), ("last 30 minutes", 1800),
          ("last 7 days", 604800), ("pulse ITER:MCTB_PSS-TF07_FD/11", None), ("", None),
          ("2026-10-01 08:00 to 2026-10-01 12:00 UTC", 14400)]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
WINDOWS = [(1, "s"), (2, "s"), (5, "s"), (10, "s"), (20, "s"), (30, "s"), (1, "min"), (2, "min"), (5, "min"),
           (10, "min"), (15, "min"), (30, "min"), (1, "h"), (2, "h"), (250, "ms"), (500, "ms")]
UNIT_WORDS = {"s": "s", "min": "min", "h": "h", "ms": "ms"}
WORDED_WINDOWS = [("half a second", "500ms"), ("a second", "1s"), ("ten seconds", "10s"), ("half a minute", "30s"),
                  ("a minute", "1min"), ("two minutes", "2min"), ("five minutes", "5min"),
                  ("a quarter of an hour", "15min"), ("half an hour", "30min"), ("an hour", "1h")]
WINDOWED = {"moving_average", "gaussian", "savgol", "median"}
REPLACED_BY = {"moving_average": "moving average", "gaussian": "gaussian smoothing", "savgol": "savitzky-golay smoothing",
               "median": "median filter", "derivative": "derivative", "integral": "integral",
               "abs": "absolute value", "log10": "log10"}
# Unit changes, with what the signal must measure for them to make sense.
CONVERSIONS = [("l/s", "m3/h", 3.6, 0, "flow"), ("Pa", "mbar", 0.01, 0, "pressure"), ("mbar", "Pa", 100, 0, "pressure"),
               ("bar", "mbar", 1000, 0, "pressure"), ("kA", "A", 1000, 0, None), ("A", "kA", 0.001, 0, None),
               ("mA", "A", 0.001, 0, None), ("W", "kW", 0.001, 0, None), ("MW", "kW", 1000, 0, None),
               ("K", "°C", 1, -273.15, "temperature"), ("°C", "K", 1, 273.15, "temperature")]
SAYS = {
    "greeting": (["hi", "hello!", "good morning", "hey there"], "Hi! What do you need?"),
    "thanks": (["thanks", "perfect, thanks!", "great, thank you", "cheers"], "You're welcome!"),
    "help": (["what can you do?", "how can you help me?", "what are you for?"],
             "I can smooth or filter signals, combine them, change the plots, add variables and set the time "
             "range. What do you need?"),
    "fft": (["compute the FFT of {a}", "show me the spectrum of {a}"],
            "I can't compute spectra yet. I can smooth or filter it if that helps."),
    "stats": (["what's the maximum of {a}?", "what is the mean value of {a}"],
              "I can't compute statistics yet, but a ruler on the plot shows the values."),
    # Questions about the data itself: the assistant sees the table, never the values.
    "values": (["what is {a} doing?", "is {a} going up?", "what's the value of {a} right now?", "is {a} ok?"],
               "I can't see the data itself, but a ruler on the plot shows the values."),
    "unclear": (["asdfgh", "???", "hmm", "qwerty", "test"], "Sorry, I didn't get that. What would you like to do?"),
    "colour": (["make {a} red", "change the colour of {a} to blue"],
               "I can't change colours. The plot's settings can, from its right-click menu."),
    "export": (["export this to excel", "save the data as csv"],
               "I can't export myself, but the Export button next to Draw will."),
    "save": (["save the workspace", "save all this"], "Use File > Save Workspace for that."),
}



def load_workspace(path):
    """The snapshot MINT would take of a workspace file, or None if it has nothing to work on."""
    import pandas as pd
    with open(path, encoding="utf-8") as f:
        ws = json.load(f)
    model = (ws.get("signal_cfg") or {}).get("model") or {}
    names = [v.get("label") or k for k, v in (model.get("blueprint") or {}).items() if not k.startswith("$")]
    rows = [dict(zip(names, r)) for r in model.get("table") or []]
    if not rows:
        return None
    snap = build_snapshot(pd.DataFrame(rows))
    return snap if snap.rows and snap.plots else None


def name_of(row, rows):
    """How a user calls a row (its alias, else the end of its variable), if no other row answers to it."""
    name = row.alias or row.variable.split(":")[-1]
    if "${" in name or len(name) < 3:
        return None
    low = name.lower()
    if sum(low in (r.alias.lower(), r.variable.split(":")[-1].lower()) for r in rows) != 1:
        return None
    return name



class Maker:
    def __init__(self, snap, rng):
        self.snap = snap
        self.rng = rng
        self.extra_rows = []  # rows a request supposes were added before it (see copy)
        shown = prompt.visible(snap)
        self.listed = {r.id for r in shown.rows}
        self.rows = [r for r in snap.rows if r.plot and not r.envelope and r.plot_type in ("PlotXY", "")]
        self.named = [(r, n) for r in self.rows for n in [name_of(r, snap.rows)] if n]

    def pick(self, k=1):
        if len(self.named) < k:
            return None
        return self.rng.sample(self.named, k)

    def window(self):
        if self.rng.random() < 0.15:
            spoken, value = self.rng.choice(WORDED_WINDOWS)
            return spoken, f"window={value}"
        n, unit = self.rng.choice(WINDOWS)
        return f"{n} {UNIT_WORDS[unit]}", f"window={n}{unit}"

    # Each maker returns (request, answer, words to keep, kind) or None.

    def process(self):
        picked = self.pick()
        if not picked:
            return None
        (row, name), = picked
        text, recipe, keep = self.processing(name, prompt.measures(row))
        return text, f"process {row.id} {recipe}", [name] + keep, "process"

    def processing(self, name, measured=None, replace_ok=True):
        """A request to process what `name` says, the recipe part of its command, and units to keep.

        A unit change fits what the signal measures, when known: K to °C for a temperature.
        """
        r = self.rng
        conversions = [c for c in CONVERSIONS if c[4] == measured] if measured else CONVERSIONS
        recipe = r.choice(["moving_average"] * 4 + ["gaussian", "savgol", "median", "median", "lowpass", "lowpass",
                           "derivative", "derivative", "integral", "abs", "log10", "scale", "scale",
                           "relative_time"])
        keep, params = [], ""
        if recipe in ("moving_average", "gaussian", "savgol", "median"):
            # A quarter of these requests give no window: the answer leaves it out too, and MINT picks or asks.
            spoken, params = self.window()
            over = f" over {spoken}" if r.random() >= 0.25 else ""
            params = params if over else ""
            phrase = {"moving_average": ["smooth {n}{w}", "moving average of {n}{w}", "average {n}{w}"],
                      "gaussian": ["gaussian smoothing of {n}{w}", "smooth {n} gently{w}", "gaussian on {n}{w}"],
                      "savgol": ["savitzky-golay filter on {n}{w}", "smooth {n}{w} but keep the peaks"],
                      "median": ["remove the spikes of {n}{w}", "median filter on {n}{w}", "median of {n}{w}"]}[recipe]
            text = r.choice(phrase).format(n=name, w=over)
        elif recipe == "lowpass":
            hz = r.choice([0.1, 0.5, 1, 2, 5, 10, 50])
            if r.random() < 0.3:
                text, params = r.choice(["low-pass filter {n}", "filter the fast noise out of {n}"]).format(n=name), ""
            else:
                text = r.choice(["low-pass {n} at {hz} Hz", "filter {n}, keep what is slower than {hz} Hz",
                                 "cut everything above {hz} Hz on {n}"]).format(n=name, hz=recipes.number(hz))
                params = f"hz={recipes.number(hz)}"
        elif recipe == "scale" and r.random() < 0.15:
            # "scale X" with no number is not "log scale": MINT asks by how much.
            text = r.choice(["scale {n}", "rescale {n}", "apply a factor to {n}"]).format(n=name)
        elif recipe == "scale":
            if conversions and r.random() < 0.6:
                src, dst, factor, offset, _ = r.choice(conversions)
                text = r.choice(["{n} in {d} please, it is in {s}", "convert {n} from {s} to {d}"]).format(
                    n=name, s=src, d=dst)
                keep += [src, dst]
            else:
                factor, offset = r.choice([(2, 0), (10, 0), (0.5, 0), (-1, 0), (1, 5), (1, -2), (1000, 0)])
                text = (f"multiply {name} by {recipes.number(factor)}" if offset == 0 else
                        f"add {recipes.number(offset)} to {name}" if factor == 1 else
                        f"multiply {name} by {recipes.number(factor)} and add {recipes.number(offset)}")
            parts = ([f"factor={recipes.number(factor)}"] if factor != 1 else []) + \
                    ([f"offset={recipes.number(offset)}"] if offset else [])
            params = " ".join(parts)
        elif recipe == "relative_time":
            text = r.choice(["time axis from zero on the plot of {n}", "relative time for {n}",
                             "x axis starting at zero for {n}", "start the time of {n} at zero",
                             "seconds since the first point on the x axis of {n}"]).format(n=name)
        else:
            text = r.choice({"derivative": ["rate of change of {n}", "derivative of {n}", "how fast does {n} change"],
                             "integral": ["integrate {n}", "cumulative integral of {n}", "running total of {n}"],
                             "abs": ["absolute value of {n}", "make {n} positive"],
                             "log10": ["log10 of {n}", "base-10 logarithm of {n}"]}[recipe]).format(n=name)
        # Not on a copy the user names by its processing: "replace the original" would be read two ways.
        replace = replace_ok and recipe not in ("relative_time",) and r.random() < 0.18
        if replace and recipe in REPLACED_BY and r.random() < 0.5:
            # Said the other way round: what the original should become.
            what = (f"{spoken} " if recipe in WINDOWED and params else "") + REPLACED_BY[recipe]
            text = r.choice(["replace {n} with its {w}", "swap {n} for its {w}",
                             "show the {w} of {n} instead of the raw one"]).format(n=name, w=what)
        elif replace:
            text += r.choice([" and replace the original", " in place", ", overwrite it", " instead of the original"])
        return text, recipe + (f" {params}" if params else "") + (" replace" if replace else ""), keep

    def selected_process(self):
        if not self.rows:
            return None
        chosen = self.rng.sample(self.rows, min(len(self.rows), self.rng.choice([1, 1, 2, 3])))
        self.snap.selected = [r.id for r in sorted(chosen, key=lambda r: r.index)]
        spoken, params = self.window()
        text = self.rng.choice(["smooth {t} over {w}", "average {t} over {w}"]).format(
            t="this" if len(chosen) == 1 else "these", w=spoken)
        return text, f"process {' '.join(self.snap.selected)} moving_average {params}", [], "process"

    def combine(self):
        for _ in range(5):
            picked = self.pick(2)
            if not picked:
                return None
            (a, na), (b, nb) = picked
            if a.data_source == b.data_source:
                break
        else:
            return None
        op, phrase = self.rng.choice([("subtract", "{a} minus {b}"), ("subtract", "subtract {b} from {a}"),
                                      ("subtract", "difference between {a} and {b}"), ("divide", "ratio of {a} to {b}"),
                                      ("divide", "{a} divided by {b}"), ("add", "{a} plus {b}"),
                                      ("add", "sum of {a} and {b}"), ("multiply", "{a} times {b}")])
        return phrase.format(a=na, b=nb), f"combine {op} {a.id} {b.id}", [na, nb], "combine"

    def move(self):
        picked = self.pick(2)
        if not picked:
            return None
        (a, na), (b, nb) = picked
        r = self.rng.random()
        if r < 0.45 and a.plot != b.plot:
            text = self.rng.choice(["move {a} to the plot of {b}", "put {a} with {b}", "{a} in the same plot as {b}",
                                    "put {a} together with {b}", "group {a} with {b}"])
            return text.format(a=na, b=nb), f"move {a.id} to {b.plot}", [na, nb], "move"
        if r < 0.7:
            return (self.rng.choice(["put {a} in a new plot", "give {a} its own plot"]).format(a=na),
                    f"move {a.id} to new", [na], "move")
        targets = [p for p in self.snap.plots if p.id != a.plot]
        if not targets:
            return None
        plot = self.rng.choice(targets)
        return f"move {na} to {self.snap.place(plot.id)}", f"move {a.id} to {plot.id}", [na], "move"

    def remove(self):
        picked = self.pick(self.rng.choice([1, 1, 2]))
        if not picked:
            return None
        names = " and ".join(n for _, n in picked)
        text = self.rng.choice(["remove {n}", "delete {n}", "get rid of {n}"]).format(n=names)
        return text, "remove " + " ".join(r.id for r, _ in picked), [n for _, n in picked], "remove"

    def plot(self):
        r = self.rng
        key, value, phrase = r.choice([("log", "on", "log scale on {t}"), ("log", "on", "put {t} in log scale"),
                                       ("log", "off", "linear scale on {t}"), ("grid", "off", "no grid on {t}"),
                                       ("grid", "on", "show the grid on {t}"), ("legend", "off", "hide the legend on {t}"),
                                       ("legend", "on", "show the legend on {t}"), ("title", "", "title {t} \"{x}\"")])
        keep = []
        choice = r.random()
        if choice < 0.4 and len(self.snap.plots) > 1:
            plot = r.choice(self.snap.plots)
            target, ids = self.snap.place(plot.id), plot.id
        elif choice < 0.75 and self.named:
            (row, name), = self.pick()
            target, ids, keep = f"the plot of {name}", row.plot, [name]
        elif choice < 0.9:
            target, ids = r.choice(["all plots", "every plot", "all the plots"]), "all"
        else:
            plot = self.snap.plots[0]
            target, ids = self.snap.place(plot.id), plot.id
        if key == "title":
            title = r.choice(["Vacuum", "Cryo pressures", "TF coil current", "Overview", "Helium"])
            return phrase.format(t=target, x=title), f'plot {ids} title="{title}"', keep + [title], "plot"
        return phrase.format(t=target), f"plot {ids} {key}={value}", keep, "plot"

    def range(self):
        r = self.rng
        now = self.snap.now
        kind = r.random()
        if kind < 0.35:
            unit = r.choice(["minutes", "hours", "hours", "days"])
            n = r.choice({"minutes": [5, 10, 15, 30, 45], "hours": [1, 2, 3, 6, 12, 24, 48], "days": [1, 2, 3, 7]}[unit])
            text = r.choice(["show the last {n} {u}", "last {n} {u}", "go back {n} {u}"]).format(
                n=n, u=unit[:-1] if n == 1 else unit)
            return text, f"range last {n} {unit}", [str(n)], "range"
        if kind < 0.5:
            day = r.choice(["today", "yesterday"])
            text = {"today": r.choice(["show today", "today since midnight"]),
                    "yesterday": r.choice(["yesterday", "show me yesterday"])}[day]
            return text, f"range day {day}", [], "range"
        if kind < 0.65:
            d = now - timedelta(days=r.randint(2, 50))
            return (f"show {d.day} {MONTHS[d.month - 1]}", f"range day {d:%Y-%m-%d}", [str(d.day)], "range")
        if kind < 0.75:
            d = now.replace(day=1) - timedelta(days=r.randint(1, 200))
            return (f"the whole of {MONTHS[d.month - 1]} {d.year}", f"range month {d:%Y-%m}", [str(d.year)], "range")
        if kind < 0.9:
            start = (now - timedelta(days=r.randint(1, 20))).replace(hour=r.randint(0, 20), minute=r.choice([0, 30]))
            end = start + timedelta(hours=r.choice([1, 2, 6, 12, 26]))
            text = (f"from {start.day} {MONTHS[start.month - 1]} {start:%H:%M} "
                    f"to {end.day} {MONTHS[end.month - 1]} {end:%H:%M}")
            return (text, f'range from "{start:%Y-%m-%d %H:%M}" to "{end:%Y-%m-%d %H:%M}"',
                    [str(start.day), f"{start:%H:%M}", f"{end:%H:%M}"], "range")
        pulse = r.choice(["ITER:MCTB_PSS-TF07_FD/{}", "ITER:MCTB_PSS-PF4_FD/{}", "ITER:CRYO-TEST/{}"]).format(
            r.randint(1, 60))
        text = r.choice(["show pulse {p}", "load {p}", "switch to {p}", "open pulse {p}", "{p} instead"]).format(p=pulse)
        return text, f"range pulse {pulse}", [pulse], "range"

    def find(self):
        words = re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", " ".join(r.variable for r in self.snap.rows))
        words = [w for w in dict.fromkeys(words) if not w.isdigit()]
        if len(words) < 2:
            return None
        chosen = self.rng.sample(words, 2)
        text = self.rng.choice(["add the {w} signal", "find the {w} variable", "I need {w} in the table"]).format(
            w=" ".join(chosen))
        return text, "find " + " ".join(chosen), chosen, "find"

    def draw(self):
        return self.rng.choice(["redraw", "refresh the plots", "draw it again"]), "draw", [], "draw"

    def ask(self):
        if self.named and self.rng.random() < 0.25:
            # A name alone says which signal, not what to do with it.
            (_, name), = self.pick()
            return (self.rng.choice(["{n}", "{n}?", "the {n}"]).format(n=name),
                    f'ask "Sure, what should I do with {name}?"', [name], "ask")
        if len(self.named) < 2:
            return None
        self.snap.selected = []
        names = [n for _, n in self.rng.sample(self.named, min(3, len(self.named)))]
        text = self.rng.choice(["smooth it", "put that in log scale", "remove this one", "low-pass it",
                                "derivative of that", "move it to another plot", "put this in a new plot",
                                "average that one"])
        listing = ", ".join(names[:-1]) + f" or {names[-1]}" if len(names) > 1 else names[0]
        return text, f'ask "Sure, which one: {listing}?"', [], "ask"

    def on_rows(self, target, rows, replace_ok=True):
        """Process, move or remove the rows that `target` names (words like "the pressure")."""
        r = self.rng
        ids = " ".join(row.id for row in rows)
        measured = {prompt.measures(row) for row in rows}
        kind = r.random()
        if kind < 0.6:
            text, recipe, keep = self.processing(target, measured.pop() if len(measured) == 1 else None, replace_ok)
            return text, f"process {ids} {recipe}", keep
        if kind < 0.8:
            others = [p for p in self.snap.plots if p.id not in {row.plot for row in rows}]
            if others and r.random() < 0.5:
                plot = r.choice(others)
                return f"move {target} to {self.snap.place(plot.id)}", f"move {ids} to {plot.id}", []
            return r.choice(["put {t} in a new plot", "give {t} a plot of its own"]).format(t=target), \
                f"move {ids} to new", []
        return r.choice(["remove {t}", "delete {t}", "take {t} out of the table"]).format(t=target), f"remove {ids}", []

    def meaning(self):
        """Signals called by what they measure ("the pressure"), as the code in their name says (see prompt.MEASURES)."""
        r = self.rng
        groups = {}
        # The same rows MINT's hint points at: the whole table, without processed copies.
        for row in self.snap.rows:
            m = prompt.measures(row)
            if m and not row.derived:
                groups.setdefault(m, []).append(row)
        if not groups:
            return None
        m, rows = r.choice(sorted(groups.items()))
        if len(rows) > prompt.MAX_LOOSE or not all(row in self.rows for row in rows):
            # Too many to point at, or some not drawn: which one is the user's to say.
            named = [n for row in rows for n in [name_of(row, self.snap.rows)] if n]
            if len(named) < 2:
                return None
            names = r.sample(named, 3) if len(named) > 3 else named
            self.snap.selected = []
            text = r.choice(["smooth the {m}", "low-pass the {m}", "derivative of the {m}"]).format(m=m)
            return text, f'ask "Sure, which one: {", ".join(names[:-1])} or {names[-1]}?"', [], "ask"
        plots = sorted({row.plot for row in rows})
        if r.random() < 0.3 and len(plots) == 1 and len(self.snap.plots) > 1:
            key, value, phrase = r.choice([("log", "on", "put the {m} plot in log scale"),
                                           ("log", "on", "log scale on the {m} plot"),
                                           ("grid", "off", "no grid on the {m} plot"),
                                           ("grid", "on", "grid on the {m} plot"),
                                           ("legend", "off", "hide the legend of the {m} plot")])
            return phrase.format(m=m), f"plot {plots[0]} {key}={value}", [], "meaning"
        if len(rows) == 1 or r.random() < 0.5:
            text, answer, keep = self.on_rows(f"the {m}" if len(rows) == 1 else f"the {m}s", rows)
            return text, answer, keep, "meaning"
        # Several of them and "the pressure": which one is the user's to say.
        names = [name_of(row, self.snap.rows) for row in rows]
        if None in names:
            return None
        self.snap.selected = []
        text = r.choice(["smooth the {m}", "low-pass the {m}", "derivative of the {m}", "remove the {m}",
                         "put the {m} in a new plot"]).format(m=m)
        return text, f'ask "Sure, which one: {", ".join(names[:-1])} or {names[-1]}?"', [], "ask"

    def position(self):
        """Signals called by the plot they are in ("the signals in the top plot")."""
        if len(self.snap.plots) < 2:
            return None
        plot = self.rng.choice(self.snap.plots)
        rows = [row for row in self.snap.rows if row.plot == plot.id]
        # The model must see every one of them in the listing to know what the plot holds.
        if not rows or len(rows) > prompt.MAX_LOOSE or any(row not in self.rows or row.id not in self.listed
                                                           for row in rows):
            return None
        place = self.snap.place(plot.id)
        target = self.rng.choice(["the signal in {p}", "what is in {p}"] if len(rows) == 1 else
                                 ["the signals in {p}", "everything in {p}", "the signals of {p}"]).format(p=place)
        text, answer, keep = self.on_rows(target, rows)
        return text, answer, keep, "position"

    def copy(self):
        """A copy the assistant made earlier ("pirani_avg_2s"), and the user calling it "the smoothed pirani"."""
        if not self.named:
            return None
        r = self.rng
        (row, name), = self.pick()
        recipe, values, words = r.choice([
            ("moving_average", {"seconds": r.choice([2, 10, 30, 60, 900])}, ["smoothed", "averaged"]),
            ("lowpass", {"hz": r.choice([0.5, 1, 2, 10])}, ["filtered", "low-passed"]),
            ("median", {"seconds": r.choice([5, 30])}, ["despiked"])])
        made = recipes.render(recipe, {k: float(v) for k, v in values.items()})
        twin = RowInfo(id=f"r{len(self.snap.rows) + 1}", index=len(self.snap.rows), variable=row.variable,
                       alias=f"{name}_{made['alias']}", stack=row.stack, plot=row.plot,
                       data_source=row.data_source, y=made["expr"])
        self.snap.rows = self.snap.rows + [twin]
        self.extra_rows = [twin]
        word = r.choice(words)
        if r.random() < 0.7:
            target, ids, keep = f"the {word} {name}", twin.id, [word, name]
        else:
            target, ids, keep = f"the {r.choice(['original', 'raw'])} {name}", row.id, [name]
        text, answer, more = self.on_rows(target, [twin if ids == twin.id else row], replace_ok=False)
        return text, answer, keep + more, "copy"

    def same(self):
        """Repeating the change just applied ("Last applied: ...") on another signal or plot, or with another number."""
        r = self.rng
        if r.random() < 0.25 and len(self.snap.plots) > 1:
            a, b = r.sample(self.snap.plots, 2)
            key, value = r.choice([("log", "on"), ("log", "off"), ("grid", "off"), ("grid", "on"), ("legend", "off")])
            self.snap.last_action = f"plot {a.id} {key}={value}"
            text = r.choice(["same for {p}", "do the same on {p}", "and {p} too"]).format(p=self.snap.place(b.id))
            return text, f"plot {b.id} {key}={value}", [], "same"
        picked = self.pick(2)
        if not picked:
            return None
        (a, na), (b, nb) = picked
        text, recipe, keep = self.processing(na, prompt.measures(a), replace_ok=False)
        if recipe.split()[0] in WINDOWED | {"lowpass", "scale"} and "=" not in recipe:
            return None  # applied, it had its number: MINT asks for it or picks one first
        if not keep:  # a unit change is about one signal's units: not repeated on another
            if recipe.split()[0] in WINDOWED and "window=" in recipe and r.random() < 0.35:
                # The same processing again with another window.
                spoken, params = self.window()
                self.snap.last_action = f"process {a.id} {recipe}"
                again = recipe.split()[0] + " " + params
                text = r.choice(["now over {w}", "try {w} instead", "same but over {w}"]).format(w=spoken)
                return text, f"process {a.id} {again}", [], "same"
            self.snap.last_action = f"process {a.id} {recipe}"
            text = r.choice(["do the same for {b}", "same for {b}", "now {b}", "and {b} too", "the same with {b}"])
            return text.format(b=nb), f"process {b.id} {recipe}", [nb], "same"
        return None

    def rownum(self):
        """Rows called by their number in the table ("row 3"): MINT numbers them as the ids do."""
        rows = [row for row in self.rows if row.id in self.listed]
        if not rows:
            return None
        row = self.rng.choice(rows)
        keep = [f"row {row.index + 1}"]
        if self.rng.random() < 0.2:
            key, value, phrase = self.rng.choice([("log", "on", "log scale on the plot of {t}"),
                                                  ("grid", "off", "no grid on the plot of {t}")])
            return phrase.format(t=keep[0]), f"plot {row.plot} {key}={value}", keep, "rownum"
        target = self.rng.choice(["{t}", "the signal in {t}", "the signal on {t}"]).format(t=keep[0])
        text, answer, more = self.on_rows(target, [row])
        return text, answer, keep + more, "rownum"

    def say(self):
        key = self.rng.choice(list(SAYS))
        texts, reply = SAYS[key]
        text = self.rng.choice(texts)
        keep = []
        if "{a}" in text:
            if not self.named:
                return None
            (_, name), = self.pick()
            text, keep = text.format(a=name), [name]
        return text, f'say "{reply}"', keep, "say"

    def make(self, kinds=None):
        weights = {"process": 28, "selected": 4, "combine": 8, "move": 7, "remove": 5, "plot": 10, "range": 12,
                   "find": 4, "draw": 2, "ask": 6, "say": 6, "multi": 8, "meaning": 9, "position": 5, "rownum": 3,
                   "copy": 4, "same": 5}
        weights = {k: w for k, w in weights.items() if not kinds or k in kinds}
        kind = self.rng.choices(list(weights), list(weights.values()))[0]
        if kind == "multi":
            first, second = (self.rng.choice([self.process, self.plot, self.range, self.remove]) for _ in range(2))
            a, b = first(), second()
            if not a or not b or a[1].split()[0] == b[1].split()[0] == "range":
                return None
            return f"{a[0]} and {b[0]}", f"{a[1]}\n{b[1]}", a[2] + b[2], "multi"
        return (self.selected_process if kind == "selected" else getattr(self, kind))()


FILE_NAMES = ["report.pdf", "test_plan.pdf", "cooldown_report.pdf", "signals.xlsx", "sensors.csv", "list.csv",
              "commissioning.xlsx", "minutes.pdf", "procedure.pdf", "variables.txt"]
FILE_WORDS = ["the file", "this file", "the report", "the table", "the document", "the attached file", "the list",
              "this table", "the sheet"]
DESCRIPTIONS = {"temperature": ["temperature", "inlet temperature", "outlet temperature", "temp."],
                "pressure": ["pressure", "pirani", "inlet pressure", "vacuum pressure"],
                "flow": ["flow", "mass flow", "helium flow"], "level": ["level", "liquid level"]}
UNITS = {"temperature": ["K", "°C"], "pressure": ["mbar", "Pa", "bar"], "flow": ["g/s", "l/s"], "level": ["%", "mm"]}


def _variable_pool(workspaces):
    """(name, alias) of the plain ITER variables of the workspaces: what a file of the plant would list."""
    pool = {}
    for ws in workspaces.values():
        for row in ws.get("rows", []):
            name = row.get("variable", "")
            if files.NAME.fullmatch(name):
                pool.setdefault(name, row.get("alias", ""))
    return sorted(pool.items())


class FileMaker:
    """Requests about an attached file (see prompt.render_file), with the answer MINT's own code gives."""

    def __init__(self, snap, pool, rng):
        self.snap, self.pool, self.rng = snap, pool, rng

    def note(self, name, alias):
        """The words a file would have beside a name: a description, perhaps with its unit, or nothing."""
        r = self.rng
        meaning = prompt.measures(RowInfo(id="", index=0, variable=name))
        choice = r.random()
        if choice < 0.25:
            return ""
        if choice < 0.45 and alias and "${" not in alias:
            return alias.replace("_", " ")
        if meaning:
            words = r.choice(DESCRIPTIONS[meaning])
            return f"{words} {r.choice(UNITS[meaning])}" if r.random() < 0.5 else words
        return r.choice(["current", "voltage", "power", "position", "status", "valve opening", ""])

    def file(self, count=None, avoid=()):
        r = self.rng
        count = count if count is not None else r.choice([1, 2, 2, 3, 3, 4, 5, 6, 8, 10, 12, 16, 30])
        avoid = [a.lower() for a in avoid]
        names = [(n, a) for n, a in self.pool if not any(w in n.lower() or (a and w in a.lower()) for w in avoid)]
        chosen = r.sample(names, min(count, len(names)))
        variables = [FileVariable(f"v{i + 1}", n, self.note(n, a)) for i, (n, a) in enumerate(chosen)]
        times = []
        if r.random() < 0.6:
            start = (self.snap.now - timedelta(days=r.randint(1, 700))).replace(hour=r.randint(6, 20),
                                                                                 minute=r.choice([0, 15, 30, 45]))
            dated = r.random() < 0.3
            times.append(f"{start:%Y-%m-%d}" if dated else f"{start:%Y-%m-%d %H:%M}")
            if r.random() < 0.6:
                end = start + timedelta(hours=r.choice([2, 6, 12, 24, 30, 48, 72]))
                times.append(f"{end:%Y-%m-%d}" if dated else f"{end:%Y-%m-%d %H:%M}")
        pulses = [r.choice(["ITER:MCTB_PSS-TF07_FD/{}", "ITER:CRYO-TEST/{}"]).format(r.randint(1, 60))] \
            if r.random() < 0.15 else []
        return FileInfo(r.choice(FILE_NAMES), variables, sorted(set(times)), pulses, "codacuda")

    def make(self):
        r = self.rng
        info = self.file()
        self.snap.file = info
        listed = [v for v in info.variables if v.id in prompt.listed_file_variables(self.snap)]
        f = r.choice(FILE_WORDS)
        kinds = {"all": 14, "together": 8, "name": 16, "names": 10, "measure": 14, "position": 6, "range": 10,
                 "add_range": 7, "pulse": 3, "no_measure": 5, "empty": 3}
        kind = r.choices(list(kinds), list(kinds.values()))[0]
        if kind == "empty":
            info.variables = []
            text = r.choice(["add the signals of {f}", "plot the variables in {f}", "make a workspace from {f}"])
            return text.format(f=f), "say \"The file doesn't name any signal I can add.\"", [], "file-empty", info
        if not listed:
            return None
        if kind == "all":
            text = r.choice(["add the signals in {f}", "make a workspace with the variables of {f}",
                             "plot everything in {f}", "add them all", "add all the signals from {f}, one plot each",
                             "load the variables listed in {f}", "Add them, one plot each"])
            return text.format(f=f), "add all", [], "file-all", info
        if kind == "together":
            if len(info.variables) < 2:
                return None
            text = r.choice(["put all the signals of {f} in one plot", "add everything from {f} together",
                             "all the variables of {f} in a single plot", "Add them to one plot"])
            return text.format(f=f), "add all together", [], "file-all", info
        if kind in ("name", "names"):
            k = 1 if kind == "name" else min(len(listed), r.choice([2, 2, 3]))
            if k < (1 if kind == "name" else 2):
                return None
            # Now and then one past the listing: MINT's hint names it (see prompt.named_in_file).
            pool = info.variables if kind == "name" and r.random() < 0.15 else listed
            picked = r.sample(pool, k)
            codes = [self.code(v.name) for v in picked]
            if None in codes:
                return None
            together = kind == "names" and r.random() < 0.3
            said = " and ".join(codes) if k < 3 else f"{codes[0]}, {codes[1]} and {codes[2]}"
            if together:
                text = r.choice(["{c} from {f} in one plot", "put {c} of {f} together"])
            else:
                text = r.choice(["add {c} from {f}", "plot {c}", "I want {c} from {f}", "just {c} please",
                                 "add {c} of {f}"])
            ids = " ".join(v.id for v in picked)
            return text.format(c=said, f=f), f"add {ids}" + (" together" if together else ""), codes, "file-name", info
        if kind in ("measure", "no_measure"):
            groups = {}
            for v in info.variables:
                m = prompt.measures(RowInfo(id="", index=0, variable=v.name, alias=v.note))
                if m:
                    groups.setdefault(m, []).append(v)
            if kind == "no_measure":
                missing = [m for m in DESCRIPTIONS if m not in groups]
                if not missing:
                    return None
                m = r.choice(missing)
                text = r.choice(["add the {m}s from {f}", "plot the {m} signals of {f}"])
                return text.format(m=m, f=f), f"say \"I don't see any {m} in the file.\"", [], "file-none", info
            if not groups:
                return None
            m, chosen = r.choice(sorted(groups.items(), key=lambda g: g[0]))
            if any(v not in listed for v in chosen) or len(chosen) > commands.MAX_IDS:
                return None
            together = len(chosen) > 1 and r.random() < 0.3
            plural = f"{m}s" if len(chosen) > 1 else m
            if together:
                text = r.choice(["the {p} of {f} in one plot", "add the {p} from {f} together"])
            else:
                text = r.choice(["add the {p} from {f}", "plot the {p} of {f}", "only the {p}", "I need the {p}"])
            ids = " ".join(v.id for v in chosen)
            return (text.format(p=plural, f=f), f"add {ids}" + (" together" if together else ""), [],
                    "file-measure", info)
        if kind == "position":
            if len(listed) < 3:
                return None
            k = r.choice([1, 2, 3])
            if r.random() < 0.3:
                return f"add the last signal of {f}", f"add {listed[-1].id}", [], "file-position", info
            if k == 1:
                return r.choice(["add the first one", f"the first signal of {f}"]), "add v1", [], "file-position", info
            return (f"add the first {k} signals of {f}", "add " + " ".join(v.id for v in listed[:k]), [str(k)],
                    "file-position", info)
        if kind in ("range", "add_range"):
            if not info.times:
                return None
            period = f"range from t1 to t{len(info.times)}" if len(info.times) > 1 else "range day t1"
            if kind == "range":
                text = r.choice(["Show the time in the file", "over the dates in {f}", "set the time range of {f}",
                                 "show the period of {f}", "the same dates as {f}"])
                return text.format(f=f), period, [], "file-range", info
            text = r.choice(["add the signals of {f} over its dates", "plot everything in {f} for the dates in it",
                             "make a workspace from {f}, with its time range"])
            return text.format(f=f), f"add all\n{period}", [], "file-range", info
        if kind == "pulse":
            if not info.pulses:
                return None
            text = r.choice(["show the pulse of {f}", "load the pulse in {f}", "switch to the pulse of {f}"])
            return text.format(f=f), f"range pulse {info.pulses[0]}", [], "file-range", info
        return None

    def code(self, name):
        """How people write a variable of the file: its tag (MT0021), or its whole name."""
        if self.rng.random() < 0.3:
            return name
        tag = name.split(":")[-1].split("-")[0]
        same = [v for v in self.snap.file.variables if tag.lower() in prompt.WORD.findall(v.name.lower())]
        return tag if len(same) == 1 and len(tag) >= 4 and prompt.CODE_LIKE.search(tag.lower()) else None


def cmd_files(args):
    """Cases with an attached file; and the data's own (all its searches too) with an unrelated one, as they were."""
    from mint.tools.assistant_eval import snapshot_from_dict
    rng = random.Random(args.seed)
    with open(args.workspaces, encoding="utf-8") as f:
        workspaces = json.load(f)
    pool = _variable_pool(workspaces)
    cases = []
    for key, ws in workspaces.items():
        made = 0
        for _ in range(args.per_workspace * 3):
            if made == args.per_workspace:
                break
            snap = snapshot_from_dict(ws)
            snap.now = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=rng.randint(0, 600),
                                                                              hours=rng.randint(6, 20))
            snap.range_text, snap.range_seconds = rng.choice(RANGES)
            item = FileMaker(snap, pool, rng).make()
            if not item:
                continue
            request, answer, keep, kind, info = item
            snap.file = info
            if not _valid(answer, snap):
                continue
            cases.append({"ws": key, "selected": [], "now": snap.now.isoformat(), "range_text": snap.range_text,
                          "range_seconds": snap.range_seconds, "request": request, "canonical": request,
                          "answer": answer, "keep": keep, "kind": kind, "file": asdict(info)})
            made += 1
    with open(args.out, "w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case) + "\n")
    base = [json.loads(line) for line in open(args.data, encoding="utf-8")]
    distract = []
    shared = rng.sample(base, int(len(base) * args.distract))
    # All the searches as well: what a file doesn't name is still looked for in the data source.
    shared += [case for case in base if case["answer"].startswith("find") and case not in shared]
    for case in shared:
        if case["ws"] not in workspaces:
            continue
        snap = snapshot_from_dict(workspaces[case["ws"]])
        snap.now = datetime.fromisoformat(case["now"])
        info = FileMaker(snap, pool, rng).file(avoid=case.get("keep", []))
        distract.append(dict(case, file=asdict(info)))
    with open(args.out.replace(".jsonl", "_distract.jsonl"), "w", encoding="utf-8") as f:
        for case in distract:
            f.write(json.dumps(case) + "\n")
    kinds = {}
    for c in cases:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    print(json.dumps({"variables": len(pool), "cases": len(cases), "kinds": kinds, "distract": len(distract)}))


def cmd_data(args):
    rng = random.Random(args.seed)
    paths = list(args.workspaces)
    if args.list:
        with open(args.list, encoding="utf-8") as f:
            paths += [line.rstrip("\n") for line in f if line.strip()]
    workspaces, cases = {}, []
    for path in paths:
        try:
            snap = load_workspace(path)
        except Exception:
            continue
        if snap is None:
            continue
        key = f"w{len(workspaces)}"
        workspaces[key] = _plain(snap)
        base_rows = list(snap.rows)
        made = 0
        for _ in range(args.per_workspace * 3):
            if made == args.per_workspace:
                break
            snap.selected = rng.sample([r.id for r in snap.rows], 1) if rng.random() < 0.15 else []
            snap.now = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=rng.randint(0, 600),
                                                                              hours=rng.randint(6, 20))
            # The time range as MINT words it (see MintWorkspace.range_summary), as people leave it set.
            snap.range_text, snap.range_seconds = rng.choice(RANGES)
            snap.rows = list(base_rows)  # a case may suppose an extra row (see Maker.copy)
            snap.last_action = ""
            maker = Maker(snap, rng)
            item = maker.make(args.kinds.split(",") if args.kinds else None)
            if not item or not _valid(item[1], snap):
                continue
            request, answer, keep, kind = item
            cases.append({"ws": key, "selected": list(snap.selected), "now": snap.now.isoformat(),
                          "range_text": snap.range_text, "range_seconds": snap.range_seconds,
                          "request": request, "canonical": request, "answer": answer, "keep": keep, "kind": kind,
                          "extra_rows": [asdict(row) for row in maker.extra_rows], "last_action": snap.last_action})
            made += 1
    with open(args.out, "w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case) + "\n")
    with open(args.out.replace(".jsonl", "_workspaces.json"), "w", encoding="utf-8") as f:
        json.dump(workspaces, f)
    kinds = {}
    for c in cases:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    print(json.dumps({"workspaces": len(workspaces), "cases": len(cases), "kinds": kinds}))


def _plain(snap):
    d = asdict(snap)
    d.pop("unlisted", None)
    d["now"] = snap.now.isoformat()
    return d


def _valid(answer, snap):
    try:
        cmds = commands.parse(answer)
    except commands.CommandError:
        return False
    ids = {r.id for r in snap.rows} | {p.id for p in snap.plots} | {"all", "new"}
    ids |= {v.id for v in snap.file.variables} if snap.file else set()
    for cmd in cmds:
        if any(i not in ids for i in cmd.ids):
            return False
        if cmd.verb == "process":
            try:
                recipes.resolve_params(cmd.words[0], cmd.params, range_seconds=3600)
            except recipes.MissingParam:
                pass
            except recipes.RecipeError:
                return False
    return True



def cmd_paraphrase(args):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    rng = random.Random(args.seed)
    cases = [json.loads(line) for line in open(args.data, encoding="utf-8")]
    tok = AutoTokenizer.from_pretrained(args.teacher, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(args.teacher, torch_dtype=torch.float16, device_map={"": args.device})
    model.eval()
    # Only the request is rewritten: the assistant answers in English, like the rest of MINT,
    # whatever language it is asked in.
    jobs, langs = [], []
    for i, case in enumerate(cases):
        lang = rng.choices([l for l, _ in LANGUAGES], [w for _, w in LANGUAGES])[0]
        langs.append(lang)
        ask = (f"Rewrite this request to a plotting tool the way a control-room operator would type it, in {lang}, "
               f"{rng.choice(STYLES)}. ")
        if case["keep"]:
            ask += "Keep these exactly as written: " + ", ".join(f'"{k}"' for k in case["keep"]) + ". "
        ask += ("Keep every number and unit, and add nothing that is not in the request. "
                f"Answer with the rewritten request only, on one line.\n\nRequest: {case['canonical']}")
        jobs.append((i, ask))
    written = {}
    for start in range(0, len(jobs), args.batch):
        batch = jobs[start:start + args.batch]
        texts = [tok.apply_chat_template([{"role": "user", "content": j[1]}], tokenize=False,
                                         add_generation_prompt=True) for j in batch]
        enc = tok(texts, return_tensors="pt", padding=True).to(args.device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=96, do_sample=True, temperature=0.8, top_p=0.95,
                                 pad_token_id=tok.pad_token_id or tok.eos_token_id)
        for (i, _), seq in zip(batch, gen):
            written[i] = _first_line(tok.decode(seq[enc["input_ids"].shape[1]:], skip_special_tokens=True))
        print(f"{start + len(batch)}/{len(jobs)} written", flush=True)
    kept = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for i, case in enumerate(cases):
            request = written.get(i, "")
            if _keeps(case, request):
                case = dict(case, request=request, lang=langs[i])
                kept += 1
            else:
                case = dict(case, lang="English")  # the original English request, which is right
            out.write(json.dumps(case) + "\n")
    print(json.dumps({"cases": len(cases), "rewritten": kept}))


def _reply(case):
    return case["answer"].split('"', 1)[1][:-1]


def _candidates(case):
    """The names an "ask" offers to choose from."""
    if case["kind"] != "ask":
        return []
    m = re.search(r"which one: (.+)\?$", _reply(case))
    return re.split(r", | or ", m.group(1)) if m else []


def _first_line(text):
    lines = [line.strip().strip('"').strip() for line in text.splitlines() if line.strip()]
    line = lines[0] if lines else ""
    return re.sub(r"^(rewritten request|request|translation)\s*:\s*", "", line, flags=re.I).strip().strip('"')


def _keeps(case, request):
    """A rewrite is used only if it still says exactly the same thing."""
    if not request or len(request) > 200 or re.search(r"rewrit|request:|translat", request, flags=re.I):
        return False
    low = request.lower()
    if any(k.lower() not in low for k in case["keep"]):
        return False
    # An ambiguous request must stay ambiguous: no name of the rows it could mean.
    if any(n.lower() in low for n in _candidates(case)):
        return False
    # "The same for X" must still point back, or the model is not shown what to repeat (see prompt.build).
    if case.get("last_action") and not prompt.points_back(request):
        return False

    def numbers(text):
        for k in case["keep"]:
            text = re.sub(re.escape(k), " ", text, flags=re.I)
        return {n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", text)}

    # The same numbers as the original, none lost and none made up.
    return numbers(request) == numbers(case["canonical"])



def cmd_feedback(args):
    """The cards operators applied and did not undo, as training cases with the workspace they saw."""
    last = {}
    for path in args.records:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if "card" in entry:  # requests and answers ("turn") say nothing of what was kept
                    last[entry["card"]] = entry  # its final outcome: applied, then maybe undone
    workspaces, cases, outcomes = {}, [], {}
    for entry in last.values():
        outcomes[entry.get("outcome")] = outcomes.get(entry.get("outcome"), 0) + 1
        if entry.get("outcome") != "applied" or not entry.get("commands"):
            continue
        ws = entry["workspace"]
        key = f"f{len(workspaces)}"
        workspaces[key] = ws
        cases.append({"ws": key, "selected": ws.get("selected", []), "now": ws.get("now"),
                      "range_text": ws.get("range_text", ""), "range_seconds": ws.get("range_seconds"),
                      "request": entry["request"], "canonical": entry["request"], "answer": "\n".join(entry["commands"]),
                      "keep": [], "kind": "feedback", "last_action": ws.get("last_action", "")})
    with open(args.out, "w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case) + "\n")
    with open(args.out.replace(".jsonl", "_workspaces.json"), "w", encoding="utf-8") as f:
        json.dump(workspaces, f)
    print(json.dumps({"cards": len(last), "outcomes": outcomes, "cases": len(cases)}))



def render(case, workspaces):
    from mint.tools.assistant_eval import snapshot_from_dict
    ws = workspaces[case["ws"]]
    snap = snapshot_from_dict(dict(ws, rows=ws["rows"] + case.get("extra_rows", []), selected=case["selected"],
                                   now=case["now"], range_text=case.get("range_text", ""),
                                   range_seconds=case.get("range_seconds"), last_action=case.get("last_action", ""),
                                   file=case.get("file", ws.get("file"))))
    _, full = prompt.build(prompt.ChatFormat(FORMAT), prompt.visible(snap), case["request"], few_shot=False)
    return full, case["answer"] + "<|im_end|>"


def cmd_train(args):
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.manual_seed(args.seed)
    cases = [json.loads(line) for line in open(args.data, encoding="utf-8")]
    workspaces = {}
    for path in args.workspaces:  # the generated ones, and those of the feedback
        with open(path, encoding="utf-8") as f:
            workspaces.update(json.load(f))
    tok = AutoTokenizer.from_pretrained(args.base)
    examples = []
    for case in cases:
        prompt_text, answer = render(case, workspaces)
        p = tok(prompt_text, add_special_tokens=False)["input_ids"]
        a = tok(answer, add_special_tokens=False)["input_ids"]
        if len(p) + len(a) <= args.max_len:
            examples.append((p, a))
    random.Random(args.seed).shuffle(examples)
    held = max(1, len(examples) // 30)
    valid, train = examples[:held], examples[held:]
    model = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.float16, device_map={"": args.device})
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05,
                                             target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj",
                                                             "up_proj", "down_proj"], task_type="CAUSAL_LM"))
    for p in model.parameters():
        if p.requires_grad:
            p.data = p.data.float()  # LoRA weights in fp32, the frozen model in fp16 (no bf16 on a T4)
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.0)
    steps = math.ceil(len(train) / args.batch) * args.epochs
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda s: min(1.0, (s + 1) / max(1, steps // 30)) * 0.5 * (1 + math.cos(math.pi * s / steps)))
    scaler = torch.amp.GradScaler("cuda")

    def batch_of(items):
        width = max(len(p) + len(a) for p, a in items)
        ids = torch.full((len(items), width), tok.pad_token_id or 0, dtype=torch.long)
        labels = torch.full((len(items), width), -100, dtype=torch.long)
        mask = torch.zeros((len(items), width), dtype=torch.long)
        for i, (p, a) in enumerate(items):
            seq = p + a
            ids[i, :len(seq)] = torch.tensor(seq)
            labels[i, len(p):len(seq)] = torch.tensor(a)
            mask[i, :len(seq)] = 1
        return ids.to(args.device), labels.to(args.device), mask.to(args.device)

    def loss_on(items):
        ids, labels, mask = batch_of(items)
        with torch.autocast("cuda", dtype=torch.float16):
            return model(input_ids=ids, attention_mask=mask, labels=labels).loss

    step = 0
    for epoch in range(args.epochs):
        model.train()
        # Similar lengths together: less padding, same examples.
        order = sorted(range(len(train)), key=lambda i: len(train[i][0]) + random.random() * 64)
        batches = [order[i:i + args.batch] for i in range(0, len(order), args.batch)]
        random.Random(args.seed + epoch).shuffle(batches)
        for b in batches:
            loss = loss_on([train[i] for i in b])
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad(set_to_none=True)
            scheduler.step()
            step += 1
            if step % 50 == 0:
                print(json.dumps({"epoch": epoch, "step": step, "of": steps, "loss": round(loss.item(), 4)}), flush=True)
        model.eval()
        with torch.no_grad():
            losses = [loss_on(valid[i:i + args.batch]).item() for i in range(0, len(valid), args.batch)]
        print(json.dumps({"epoch": epoch, "valid_loss": round(sum(losses) / len(losses), 4)}), flush=True)
    model.save_pretrained(args.out)
    print(json.dumps({"saved": args.out, "train": len(train), "valid": len(valid)}))



GGUF_NAMES = {"self_attn.q_proj": "attn_q", "self_attn.k_proj": "attn_k", "self_attn.v_proj": "attn_v",
              "self_attn.o_proj": "attn_output", "mlp.gate_proj": "ffn_gate", "mlp.up_proj": "ffn_up",
              "mlp.down_proj": "ffn_down"}


def lora_deltas(adapter_dir):
    """{gguf tensor name: B @ A * scale} from a PEFT adapter."""
    import numpy as np
    from safetensors.numpy import load_file
    with open(f"{adapter_dir}/adapter_config.json", encoding="utf-8") as f:
        config = json.load(f)
    scale = config["lora_alpha"] / config["r"]
    weights = load_file(f"{adapter_dir}/adapter_model.safetensors")
    deltas = {}
    for key, a in weights.items():
        m = re.search(r"layers\.(\d+)\.(\w+\.\w+)\.lora_A\.weight$", key)
        if not m:
            continue
        b = weights[key.replace("lora_A", "lora_B")]
        deltas[f"blk.{m.group(1)}.{GGUF_NAMES[m.group(2)]}.weight"] = (b.astype(np.float32) @ a.astype(np.float32)) * scale
    return deltas


def soup(adapter_dirs):
    """The mean change of adapters trained alike from the same model (a model soup): steadier than any one alone."""
    total = lora_deltas(adapter_dirs[0])
    for adapter_dir in adapter_dirs[1:]:
        deltas = lora_deltas(adapter_dir)
        if set(deltas) != set(total):
            raise SystemExit(f"{adapter_dir} changes other tensors than {adapter_dirs[0]}")
        for name, delta in deltas.items():
            total[name] += delta
    return {name: delta / len(adapter_dirs) for name, delta in total.items()}


def cmd_merge(args):
    import numpy as np
    from gguf import GGMLQuantizationType, GGUFReader, GGUFValueType, GGUFWriter
    deltas = soup(args.adapter)
    reader = GGUFReader(args.gguf)
    arch = reader.fields["general.architecture"].contents()
    writer = GGUFWriter(args.out, arch)
    # How MINT must run it: its chat format, no worked examples, and the context the short prompt, the largest
    # workspace listing, a request and its answer need (--context).
    ours = {"mint.assistant.format": (FORMAT, GGUFValueType.STRING),
            "mint.assistant.few_shot": (False, GGUFValueType.BOOL),
            "mint.assistant.context": (args.context, GGUFValueType.UINT32),
            "mint.assistant.files": (args.files, GGUFValueType.BOOL),
            "general.finetune": ("mint-assistant", GGUFValueType.STRING)}
    for field in reader.fields.values():
        if field.name.startswith("GGUF.") or field.name == "general.architecture" or field.name in ours:
            continue
        vtype = field.types[0]
        if vtype == GGUFValueType.ARRAY:
            writer.add_key_value(field.name, field.contents(), vtype, sub_type=field.types[-1])
        else:
            writer.add_key_value(field.name, field.contents(), vtype)
    for key, (value, vtype) in ours.items():
        writer.add_key_value(key, value, vtype)
    merged = 0
    for t in reader.tensors:
        shape = [int(n) for n in reversed(t.shape.tolist())]
        if t.tensor_type == GGMLQuantizationType.BF16:
            data = (np.asarray(t.data).view(np.uint16).astype(np.uint32) << 16).view(np.float32).reshape(shape)
        else:
            data = np.asarray(t.data, dtype=np.float32).reshape(shape)
        if t.name in deltas:
            if deltas[t.name].shape != data.shape:
                raise SystemExit(f"{t.name}: delta {deltas[t.name].shape} does not fit {data.shape}")
            data = data + deltas[t.name]
            merged += 1
        writer.add_tensor(t.name, data.astype(np.float32 if data.ndim == 1 else np.float16))
    if merged != len(deltas):
        raise SystemExit(f"merged {merged} of {len(deltas)} LoRA tensors")
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()
    print(json.dumps({"merged_tensors": merged, "out": args.out}))


def cmd_quantize(args):
    import ctypes

    import llama_cpp
    params = llama_cpp.llama_model_quantize_default_params()
    params.ftype = llama_cpp.LLAMA_FTYPE_MOSTLY_Q4_K_M
    params.nthread = args.threads
    code = llama_cpp.llama_model_quantize(args.gguf.encode(), args.out.encode(), ctypes.byref(params))
    if code != 0:
        raise SystemExit(f"quantize failed with code {code}")
    print(json.dumps({"out": args.out}))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("data")
    p.add_argument("--out", required=True)
    p.add_argument("--per-workspace", type=int, default=40)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--list", help="a file with one workspace path per line (names may have spaces)")
    p.add_argument("--kinds", help="only these kinds of request, comma separated (e.g. meaning,position)")
    p.add_argument("workspaces", nargs="*")
    p = sub.add_parser("files")
    p.add_argument("--out", required=True)
    p.add_argument("--workspaces", required=True, help="the _workspaces.json of the data")
    p.add_argument("--data", required=True, help="the cases of the data, a share of which get an unrelated file")
    p.add_argument("--per-workspace", type=int, default=15)
    p.add_argument("--distract", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=11)
    p = sub.add_parser("paraphrase")
    p.add_argument("--teacher", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--batch", type=int, default=48)
    p.add_argument("--device", default="cuda:0")
    p.add_argument("--seed", type=int, default=7)
    p = sub.add_parser("feedback")
    p.add_argument("--out", required=True)
    p.add_argument("records", nargs="+", help="record.jsonl files (see mint.assistant.record)")
    p = sub.add_parser("train")
    p.add_argument("--base", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--workspaces", required=True, nargs="+", help="the _workspaces.json files of the data")
    p.add_argument("--out", required=True)
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--rank", type=int, default=16)
    p.add_argument("--max-len", type=int, default=1800)
    p.add_argument("--device", default="cuda:0")
    p.add_argument("--seed", type=int, default=7)
    p = sub.add_parser("merge")
    p.add_argument("--gguf", required=True)
    p.add_argument("--adapter", required=True, nargs="+", help="several, trained alike with other seeds: averaged")
    p.add_argument("--out", required=True)
    p.add_argument("--context", type=int, default=2048)
    p.add_argument("--files", action="store_true", help="trained on attached files too (see the files command)")
    p = sub.add_parser("quantize")
    p.add_argument("--gguf", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--threads", type=int, default=8)
    args = ap.parse_args(argv)
    {"data": cmd_data, "files": cmd_files, "paraphrase": cmd_paraphrase, "feedback": cmd_feedback, "train": cmd_train,
     "merge": cmd_merge, "quantize": cmd_quantize}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
