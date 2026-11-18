# Description: A calendar to pick a range of days on, as booking sites do, and the icon that opens it.

import typing

from PySide6.QtCore import QDate, QEvent, QLocale, QPoint, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication, QPalette, QTextCharFormat
from PySide6.QtWidgets import QAbstractItemView, QCalendarWidget, QFrame, QLabel, QToolButton, QVBoxLayout, QWidget

from mint.gui.mtAppearance import blend, secondary_text_color
from mint.tools.icon_loader import create_icon

# In English, as MINT is, whatever the language of the system; weeks start on Monday, as in ISO 8601.
_ENGLISH = QLocale(QLocale.Language.English, QLocale.Country.UnitedKingdom)


class MTCalendarButton(QToolButton):
    """The calendar icon, in the grey of the palette."""

    def __init__(self, tooltip: str, parent: typing.Optional[QWidget] = None):
        super().__init__(parent)
        self.setIcon(create_icon('calendar', 'svg'))
        self.setAutoRaise(True)
        self.setToolTip(tooltip)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self.setIcon(create_icon('calendar', 'svg'))


class MTDayRangeCalendar(QFrame):
    """A month to pick a range of days on, as booking sites do. It opens on the range it is given. The first click
    picks a day, the range then follows the mouse, and the second click ends it, before or after the first; each
    click emits the range, so the fields show it at once. Two clicks on a day pick that day."""
    rangePicked = Signal(QDate, QDate)

    def __init__(self, first: QDate, last: QDate, parent: typing.Optional[QWidget] = None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.calendar = QCalendarWidget(self)
        self.calendar.setLocale(_ENGLISH)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.calendar.setSelectedDate(first)
        self.step = QLabel("Click the first day", self)
        self.summary = QLabel(self)
        # The colours of the theme: a style sheet gives them to the palette of a widget as it polishes it.
        self.ensurePolished()
        self.summary.setStyleSheet(f"color: {secondary_text_color(self.palette())};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 8)
        layout.setSpacing(2)
        layout.addWidget(self.calendar)
        layout.addSpacing(4)
        layout.addWidget(self.step)
        layout.addWidget(self.summary)

        self._first: typing.Optional[QDate] = None  # the day clicked first, until the second click
        self._range = tuple(sorted((first, last)))
        self._view = self.calendar.findChild(QAbstractItemView)
        self._view.ensurePolished()
        self._view.setMouseTracking(True)
        self._view.viewport().installEventFilter(self)
        self.calendar.clicked.connect(self._picked)
        self.calendar.activated.connect(self._picked)  # Enter
        self.calendar.currentPageChanged.connect(lambda *_: self._show_range(*self._range))
        self._show_range(*self._range)

    def show_under(self, widget: QWidget):
        """Under a widget, or over it where the screen ends there, as the calendar of a QDateTimeEdit opens."""
        size = self.sizeHint()
        under = widget.mapToGlobal(widget.rect().bottomLeft())
        over = widget.mapToGlobal(widget.rect().topLeft())
        screen = (QGuiApplication.screenAt(under) or QGuiApplication.primaryScreen()).availableGeometry()
        x = max(screen.left(), min(under.x(), screen.right() - size.width()))
        y = under.y() if under.y() + size.height() <= screen.bottom() else over.y() - size.height()
        self.move(QPoint(x, max(screen.top(), y)))
        self.show()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseMove and self._first is not None:
            day = self._day_at(event.position().toPoint())
            if day is not None:
                self._show_range(self._first, day)
        return super().eventFilter(obj, event)

    def _picked(self, day: QDate):
        # A double click is two clicks and an activation: the calendar is gone by the last.
        if not self.isVisible():
            return
        if self._first is None:
            self._first = day
            self.step.setText("Now click the last day")
            self._show_range(day, day)
            self.rangePicked.emit(day, day)
        else:
            first, last = sorted((self._first, day))
            self.close()
            self.rangePicked.emit(first, last)

    def _show_range(self, first: QDate, last: QDate):
        """Marks the days of a range on the month shown: both ends in the colour of the selection of the theme, the
        days between in a lighter one."""
        first, last = self._range = tuple(sorted((first, last)))
        palette = self._view.palette()
        between = QTextCharFormat()
        between.setBackground(blend(palette.color(QPalette.ColorRole.Base),
                                    palette.color(QPalette.ColorRole.Highlight), 0.3))
        end = QTextCharFormat()
        end.setBackground(palette.color(QPalette.ColorRole.Highlight))
        end.setForeground(palette.color(QPalette.ColorRole.HighlightedText))
        end.setFontWeight(QFont.Weight.Bold)
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())  # a null date clears them all
        # The grid shows six weeks from the week of the 1st, with days of the months around it.
        shown = QDate(self.calendar.yearShown(), self.calendar.monthShown(), 1)
        day, end_of_grid = max(first, shown.addDays(-7)), min(last, shown.addDays(42))
        while day <= end_of_grid:
            self.calendar.setDateTextFormat(day, end if day in (first, last) else between)
            day = day.addDays(1)
        self.summary.setText(self._said(first, last))

    @staticmethod
    def _said(first: QDate, last: QDate) -> str:
        """A range of days as people say it: "3 Nov → 18 Nov 2026 · 16 days"."""
        days = first.daysTo(last) + 1
        count = f"{days} day" if days == 1 else f"{days} days"
        if first == last:
            return f"{_ENGLISH.toString(first, 'd MMM yyyy')} · {count}"
        start = _ENGLISH.toString(first, 'd MMM' if first.year() == last.year() else 'd MMM yyyy')
        return f"{start} → {_ENGLISH.toString(last, 'd MMM yyyy')} · {count}"

    def _day_at(self, pos: QPoint) -> typing.Optional[QDate]:
        """The day of the cell at a point of the grid, which starts and ends with days of the months around."""
        index = self._view.indexAt(pos)
        if not index.isValid() or index.row() == 0 or not str(index.data()).isdigit():  # row 0: names of the days
            return None
        day = int(index.data())
        month = QDate(self.calendar.yearShown(), self.calendar.monthShown(), 1)
        if index.row() <= 2 and day > 20:
            month = month.addMonths(-1)
        elif index.row() >= 5 and day < 15:
            month = month.addMonths(1)
        return QDate(month.year(), month.month(), day)
