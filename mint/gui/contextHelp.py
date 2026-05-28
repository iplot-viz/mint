"""F1 context-sensitive help.

A widget opts in by carrying the "help_anchor" Qt property
(set via QWidget.setProperty). When the shortcut fires, the
widget under the cursor is walked up its parent chain until
an anchor is found; that anchor is passed to the help opener.
With no anchor found, the focused widget is tried; failing
that, the manual opens at the TOC.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget

HELP_ANCHOR_PROPERTY = "help_anchor"


def find_anchor_for(widget: Optional[QWidget]) -> Optional[str]:
    while widget is not None:
        value = widget.property(HELP_ANCHOR_PROPERTY)
        if value:
            return str(value)
        widget = widget.parentWidget()
    return None


def resolve_context_anchor() -> Optional[str]:
    anchor = find_anchor_for(QApplication.widgetAt(QCursor.pos()))
    if anchor is None:
        anchor = find_anchor_for(QApplication.focusWidget())
    return anchor


def trigger_context_help(open_callback: Callable[[Optional[str]], None]) -> None:
    open_callback(resolve_context_anchor())
