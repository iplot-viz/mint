"""A plain-data picture of the workspace, the only thing the assistant reads."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

STACK = re.compile(r'(\d+)(?:[.](\d+))?(?:[.](\d+))?$')
ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"]


def _in_line(index: int, count: int, first: str, last: str, counted: str) -> str:
    if index == 0:
        return f"the {first} plot"
    if index == count - 1:
        return f"the {last} plot"
    if index < len(ORDINALS):
        return f"the {ORDINALS[index]} plot {counted}"
    return f"plot {index + 1} {counted}"


@dataclass
class RowInfo:
    id: str
    index: int
    variable: str
    data_source: str = ""
    alias: str = ""
    stack: str = ""
    plot: Optional[str] = None
    x: str = ""
    y: str = ""
    envelope: bool = False
    plot_type: str = "PlotXY"
    uid: str = ""

    @property
    def is_expression(self) -> bool:
        return "${" in self.variable

    @property
    def derived(self) -> bool:
        """Computed from other data: processed in x or y, or an expression of other signals."""
        return bool(self.y or self.x or self.is_expression)

    @property
    def label(self) -> str:
        return self.alias or self.variable


@dataclass
class PlotInfo:
    id: str
    row: int
    col: int
    log_scale: Optional[bool] = None
    grid: Optional[bool] = None
    legend: Optional[bool] = None
    title: str = ""

    @property
    def stack(self) -> str:
        return f"{self.row}.{self.col}"


@dataclass
class Snapshot:
    rows: List[RowInfo] = field(default_factory=list)
    plots: List[PlotInfo] = field(default_factory=list)
    selected: List[str] = field(default_factory=list)
    range_text: str = ""
    range_seconds: Optional[float] = None
    pulse_mode: bool = False
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_action: str = ""
    # Rows left out of what the model is shown (see prompt.visible), still reachable by name.
    unlisted: List[RowInfo] = field(default_factory=list)

    @property
    def hidden_rows(self) -> int:
        return len(self.unlisted)

    def row(self, row_id: str) -> Optional[RowInfo]:
        return next((r for r in self.rows if r.id == row_id), None)

    def plot(self, plot_id: str) -> Optional[PlotInfo]:
        return next((p for p in self.plots if p.id == plot_id), None)

    def place(self, plot_id: Optional[str]) -> str:
        """A plot as people point at it on screen: "the top plot", "the bottom-right plot"..."""
        plot = self.plot(plot_id) if plot_id else None
        if plot is None:
            return "the table" if not plot_id else f"plot {plot_id[1:]}"
        if len(self.plots) == 1:
            return "the plot"
        rows = sorted({p.row for p in self.plots})
        cols = sorted({p.col for p in self.plots})
        r, c = rows.index(plot.row), cols.index(plot.col)
        if len(cols) == 1:
            return _in_line(r, len(rows), "top", "bottom", "from the top")
        if len(rows) == 1:
            return _in_line(c, len(cols), "left", "right", "from the left")
        vertical = {0: "top", len(rows) - 1: "bottom"}.get(r)
        horizontal = {0: "left", len(cols) - 1: "right"}.get(c)
        if vertical and horizontal:
            return f"the {vertical}-{horizontal} plot"
        return f"the plot in row {r + 1}, column {c + 1}"

    def aliases(self) -> set:
        return {r.alias for r in self.rows if r.alias}

    def next_free_plot_row(self) -> int:
        return max((p.row for p in self.plots), default=0) + 1


def parse_stack(stack: str):
    """(row, col, sub-stack) of a Stack cell, as MTSignalsModel reads it, or None."""
    m = STACK.match((stack or "").strip())
    if not m:
        return None
    row, col, sub = int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)
    if row == 0 or col == 0 or sub == 0:
        return None
    return row, col, sub


def _cell(table, i, name):
    if name not in table.columns:
        return ""
    value = table.iat[i, table.columns.get_loc(name)]
    return "" if value is None else str(value).strip()


def build(table, selected_indices=(), canvas=None, range_text="", range_seconds=None, pulse_mode=False,
          last_action="") -> Snapshot:
    """Snapshot of a signals table: rows r1, r2... in table order, plots p1, p2... row by row, left to right."""
    rows = []
    placed = {}
    for i in range(len(table.index)):
        variable = _cell(table, i, "Variable")
        alias = _cell(table, i, "Alias")
        if not variable and not alias:
            continue
        row = RowInfo(id=f"r{i + 1}", index=i, variable=variable, data_source=_cell(table, i, "DS"),
                      alias=alias, stack=_cell(table, i, "Stack"), x=_cell(table, i, "x"), y=_cell(table, i, "y"),
                      envelope=_cell(table, i, "Envelope") in ("1", "True", "true"),
                      plot_type=_cell(table, i, "Plot type") or "PlotXY", uid=_cell(table, i, "uid"))
        rows.append(row)
        position = parse_stack(row.stack)
        if position:
            placed.setdefault((position[0], position[1]), []).append(row)

    plots = []
    for n, (row_col, members) in enumerate(sorted(placed.items()), start=1):
        plot = PlotInfo(id=f"p{n}", row=row_col[0], col=row_col[1])
        for r in members:
            r.plot = plot.id
        drawn = canvas_plot(canvas, *row_col)
        if drawn is not None:
            plot.log_scale = getattr(drawn, "log_scale", None)
            plot.grid = getattr(drawn, "grid", None)
            plot.legend = getattr(drawn, "legend", None)
            plot.title = getattr(drawn, "plot_title", None) or ""
        plots.append(plot)

    by_index = {r.index: r.id for r in rows}
    selected = [by_index[i] for i in sorted(set(selected_indices)) if i in by_index]
    return Snapshot(rows=rows, plots=plots, selected=selected, range_text=range_text,
                    range_seconds=range_seconds, pulse_mode=pulse_mode, last_action=last_action)


def canvas_plot(canvas, row: int, col: int):
    """The canvas plot drawn for Stack row.col, if the canvas holds one."""
    try:
        for column in canvas.plots:
            for plot in column:
                if plot is not None and getattr(plot, "row", None) == row and getattr(plot, "col", None) == col:
                    return plot
    except (AttributeError, TypeError):
        pass
    return None
