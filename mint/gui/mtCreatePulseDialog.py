"""Dialog to create a UDA pulse from the currently visible time range.

Built programmatically (no .ui) so the schema is explicit and easy to
test. Emits `submitted(dict)` when the user clicks Create with a valid
form; the host handler is responsible for the actual UDA write call.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

from PySide6.QtCore import Signal, Qt, QDate, QDateTime, QRegularExpression, QTime
from PySide6.QtGui import QFontMetrics, QIcon, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox, QCompleter, QDateTimeEdit, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
    QPlainTextEdit, QStyle, QToolButton, QVBoxLayout, QWidget,
)

PULSE_STATUS_OPTIONS = ["completed", "aborted", "terminated", "failed"]
DESCRIPTION_MAX_CHARS = 200
DEFAULT_PULSE_LOCATION = "ITER"
# Same two-part time entry as the From/To fields of the data range selector:
# a wall-clock UTC date-time plus the nanosecond remainder.
TIME_FORMAT = "yyyy-MM-ddThh:mm:ss"
NS_PER_SECOND = 1_000_000_000


def format_ns_range_for_humans(start_ns: int, end_ns: int) -> str:
    """e.g. '2026-05-15 10:30:00 UTC → 11:45:00 UTC (1h 15m)'."""
    # Whole seconds only: the sub-second digits have their own field, and
    # dividing a nanosecond epoch as a float would round them anyway.
    try:
        s = _dt.datetime.fromtimestamp(int(start_ns) // NS_PER_SECOND, _dt.timezone.utc)
        e = _dt.datetime.fromtimestamp(int(end_ns) // NS_PER_SECOND, _dt.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return f"{start_ns} ns → {end_ns} ns"
    s = s.strftime("%Y-%m-%d %H:%M:%S")
    e = e.strftime("%Y-%m-%d %H:%M:%S")
    if end_ns < start_ns:
        return f"{s} UTC → {e} UTC (invalid: end before start)"
    total_s = (int(end_ns) - int(start_ns)) // NS_PER_SECOND
    h, rem = divmod(total_s, 3600)
    m, sec = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if sec or not parts:
        parts.append(f"{sec}s")
    return f"{s} UTC → {e} UTC ({' '.join(parts)})"


def split_ns(ns: int) -> tuple[QDateTime, str]:
    """Split an epoch timestamp into the date-time shown by the editor and the
    9-digit nanosecond remainder."""
    seconds, fraction = divmod(int(ns), NS_PER_SECOND)
    moment = _dt.datetime.fromtimestamp(seconds, _dt.timezone.utc)
    # The editor reads its value as local time, so hand it the UTC wall clock
    # verbatim; a UTC-spec QDateTime would be shifted on display instead.
    shown = QDateTime(QDate(moment.year, moment.month, moment.day),
                      QTime(moment.hour, moment.minute, moment.second))
    return shown, str(fraction).zfill(9)


def join_ns(shown: QDateTime, fraction: str) -> int:
    """Inverse of :func:`split_ns`. Plain datetime arithmetic keeps this off the
    Qt time-zone API, whose signatures differ across the supported PySide6
    versions."""
    date, time = shown.date(), shown.time()
    moment = _dt.datetime(date.year(), date.month(), date.day(),
                          time.hour(), time.minute(), time.second(),
                          tzinfo=_dt.timezone.utc)
    return int(moment.timestamp()) * NS_PER_SECOND + int(fraction or 0)


class MTCategoryPicker(QDialog):
    """Filterable list of the pulse categories served by UDA.

    A plain drop-down is unusable once the server lists many categories, so
    the search button next to the category field opens this instead.
    """

    def __init__(self, categories: list[str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Find Pulse Category")

        self.filterEdit = QLineEdit(self)
        self.filterEdit.setPlaceholderText("Type to filter…")
        self.filterEdit.textChanged.connect(self._apply_filter)

        self.listWidget = QListWidget(self)
        self.listWidget.addItems(categories)
        self.listWidget.itemDoubleClicked.connect(lambda *_: self.accept())
        if categories:
            self.listWidget.setCurrentRow(0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.filterEdit)
        layout.addWidget(self.listWidget)
        layout.addWidget(buttons)

        # Production serves hundreds of categories: keep the window bounded so
        # the list scrolls instead of growing (still resizable by the user).
        self.resize(380, 480)

    def selected_category(self) -> Optional[str]:
        item = self.listWidget.currentItem()
        # Hiding a row leaves it current, so an invisible match must not be
        # returned as the user's choice.
        if item is None or item.isHidden():
            return None
        return item.text()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        first_visible = None
        for row in range(self.listWidget.count()):
            item = self.listWidget.item(row)
            hidden = bool(needle) and needle not in item.text().lower()
            item.setHidden(hidden)
            if not hidden and first_visible is None:
                first_visible = item
        if first_visible is not None:
            self.listWidget.setCurrentItem(first_visible)


class MTCreatePulseDialog(QDialog):
    """Modal dialog to collect pulse metadata before submitting it to UDA."""

    submitted = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Create Pulse")
        # Non-modal: some window managers drag the parent along with a modal child.

        self._pulse_id: Optional[str] = None
        self._categories: list[str] = []

        self.locationEdit = QLineEdit(self)
        self.locationEdit.setText(DEFAULT_PULSE_LOCATION)
        # Free text: the category catalog is not always served by UDA.
        self.categoryCombo = QComboBox(self)
        self.categoryCombo.setEditable(True)
        completer = self.categoryCombo.completer()
        if completer is not None:
            # Match anywhere in the name, not just on its first characters.
            completer.setCompletionMode(QCompleter.PopupCompletion)
            completer.setFilterMode(Qt.MatchContains)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.categorySearchButton = QToolButton(self)
        self.categorySearchButton.setIcon(self._search_icon())
        self.categorySearchButton.setAutoRaise(True)
        self.categorySearchButton.clicked.connect(self.browse_categories)
        self.pulseNumberEdit = QLineEdit(self)
        self.pulseNumberEdit.setPlaceholderText("automatic")
        self.pulseNumberEdit.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d*"), self))
        self.statusCombo = QComboBox(self)
        self.statusCombo.addItems(PULSE_STATUS_OPTIONS)

        self.rangePreview = QLabel("", self)
        self.rangePreview.setStyleSheet("color: #555; font-style: italic;")

        # Built before the editors below, which refresh it as soon as they change.
        fraction_validator = QRegularExpressionValidator(
            QRegularExpression(r"\d{0,9}"), self)
        self.startTime = QDateTimeEdit(self)
        self.startTime.setDisplayFormat(TIME_FORMAT)
        self.startTimeNs = QLineEdit(self)
        self.startTimeNs.setValidator(fraction_validator)
        self.endTime = QDateTimeEdit(self)
        self.endTime.setDisplayFormat(TIME_FORMAT)
        self.endTimeNs = QLineEdit(self)
        self.endTimeNs.setValidator(fraction_validator)
        for widget in (self.startTime, self.endTime):
            widget.dateTimeChanged.connect(self._refresh_range_preview)
        for widget in (self.startTimeNs, self.endTimeNs):
            widget.setFixedWidth(
                11 * QFontMetrics(widget.font()).horizontalAdvance("0"))
            widget.textChanged.connect(self._refresh_range_preview)

        self.descriptionEdit = QPlainTextEdit(self)
        self.descriptionEdit.setPlaceholderText(
            "Short description of this pulse (max 200 characters).")

        categoryLayout = QHBoxLayout()
        categoryLayout.addWidget(self.categoryCombo)
        categoryLayout.addWidget(self.categorySearchButton)

        form = QFormLayout()
        form.addRow("Location:", self.locationEdit)
        form.addRow("Category:", categoryLayout)
        form.addRow("Pulse number:", self.pulseNumberEdit)
        form.addRow("Status:", self.statusCombo)
        form.addRow("Start time:", self._time_row(self.startTime, self.startTimeNs))
        form.addRow("End time:", self._time_row(self.endTime, self.endTimeNs))
        form.addRow("Range:", self.rangePreview)
        form.addRow("Description:", self.descriptionEdit)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        self.buttons.button(QDialogButtonBox.Ok).setText("Create")
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

    # ---- Public API used by the host (MTMainWindow) ----

    def populate(self, categories: list[str], start_ns: int, end_ns: int,
                 pulse_id: Optional[str] = None,
                 current_status: Optional[str] = None,
                 current_description: Optional[str] = None) -> None:
        """Populate the form. Pass ``pulse_id`` to switch to update mode.

        ``categories`` are optional suggestions; entries with a location
        prefix ("ITER:local") are reduced to their category part.
        """
        self.categoryCombo.clear()
        suggestions = []
        for cat in categories or []:
            text = str(cat).split(":", 1)[-1].strip()
            if text and text not in suggestions:
                suggestions.append(text)
        self.categoryCombo.addItems(suggestions)
        self.categoryCombo.setCurrentText("")
        self._categories = suggestions
        self.locationEdit.setText(DEFAULT_PULSE_LOCATION)
        self.pulseNumberEdit.clear()
        self.set_range_ns(start_ns, end_ns)
        self.descriptionEdit.setPlainText(current_description or "")
        if current_status:
            idx = self.statusCombo.findText(current_status)
            if idx >= 0:
                self.statusCombo.setCurrentIndex(idx)
        self._configure_mode(pulse_id)
        self._refresh_range_preview()

    def set_range_ns(self, start_ns: int, end_ns: int) -> None:
        """Show a nanosecond range in the two-part time editors."""
        for time_edit, fraction_edit, ns in ((self.startTime, self.startTimeNs, start_ns),
                                             (self.endTime, self.endTimeNs, end_ns)):
            shown, fraction = split_ns(ns)
            for widget, setter, value in ((time_edit, time_edit.setDateTime, shown),
                                          (fraction_edit, fraction_edit.setText, fraction)):
                widget.blockSignals(True)
                setter(value)
                widget.blockSignals(False)
        self._refresh_range_preview()

    def range_ns(self) -> tuple[int, int]:
        return (join_ns(self.startTime.dateTime(), self.startTimeNs.text()),
                join_ns(self.endTime.dateTime(), self.endTimeNs.text()))

    def browse_categories(self) -> None:
        picker = MTCategoryPicker(self._categories, self)
        if picker.exec() != QDialog.Accepted:
            return
        chosen = picker.selected_category()
        if chosen:
            self.categoryCombo.setCurrentText(chosen)

    def result_dict(self) -> dict:
        number_text = self.pulseNumberEdit.text().strip()
        start_ns, end_ns = self.range_ns()
        return {
            "pulse_id": self._pulse_id,
            "location": self.locationEdit.text().strip(),
            "category": self.categoryCombo.currentText().strip(),
            "pulse_number": int(number_text) if number_text else None,
            "status": self.statusCombo.currentText(),
            "start_ns": start_ns,
            "end_ns": end_ns,
            "description": self.descriptionEdit.toPlainText().strip(),
        }

    def _configure_mode(self, pulse_id: Optional[str]) -> None:
        # Update mode locks the pulse identity (injectPulse can't change
        # location, category or number) and surfaces it in the title + OK label.
        self._pulse_id = pulse_id
        is_update = pulse_id is not None
        for widget in (self.locationEdit, self.categoryCombo, self.pulseNumberEdit):
            widget.setEnabled(not is_update)
        self._refresh_category_search()
        ok_button = self.buttons.button(QDialogButtonBox.Ok)
        if is_update:
            self.setWindowTitle(f"Update Pulse — {pulse_id}")
            ok_button.setText("Update")
            scope, _, number = pulse_id.rpartition("/")
            location, _, category = scope.partition(":")
            self.locationEdit.setText(location)
            self.categoryCombo.setCurrentText(category)
            self.pulseNumberEdit.setText(number)
        else:
            self.setWindowTitle("Create Pulse")
            ok_button.setText("Create")

    # ---- Internals ----

    def _search_icon(self) -> QIcon:
        icon = QIcon.fromTheme("edit-find")
        if icon.isNull():
            # Windows ships no icon theme; any platform style provides this one.
            icon = self.style().standardIcon(QStyle.SP_FileDialogContentsView)
        return icon

    def _time_row(self, time_edit: QDateTimeEdit, fraction_edit: QLineEdit) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(time_edit)
        row.addWidget(QLabel(".", self))
        row.addWidget(fraction_edit)
        row.addWidget(QLabel("ns", self))
        row.addStretch()
        return row

    def _refresh_category_search(self) -> None:
        # Nothing to browse when the server does not serve its category list.
        enabled = self.categoryCombo.isEnabled() and bool(self._categories)
        self.categorySearchButton.setEnabled(enabled)
        self.categorySearchButton.setToolTip(
            "Search the existing pulse categories" if enabled
            else "The server did not return any pulse category")

    def _refresh_range_preview(self) -> None:
        start, end = self.range_ns()
        self.rangePreview.setText(format_ns_range_for_humans(start, end))

    def _on_accept(self) -> None:
        data = self.result_dict()
        problem = self._validate(data)
        if problem:
            QMessageBox.warning(self, "Create Pulse", problem)
            return
        # The host accepts the dialog only after the server write succeeds,
        # so a rejected pulse returns to the form with the input intact.
        self.submitted.emit(data)

    @staticmethod
    def _validate(data: dict) -> Optional[str]:
        location = data.get("location") or ""
        if not location:
            return "Please enter a location (e.g. ITER)."
        if ":" in location or "/" in location:
            return "The location cannot contain ':' or '/'."
        if not data["category"]:
            return "Please enter a pulse category."
        if ":" in data["category"] or "/" in data["category"]:
            return "The category cannot contain ':' or '/'."
        if data["end_ns"] <= data["start_ns"]:
            return "End time must be strictly greater than start time."
        description = data["description"].strip()
        if not description:
            return "Please add a short description."
        if len(description) > DESCRIPTION_MAX_CHARS:
            return (f"Description is {len(description)} characters; "
                    f"the limit is {DESCRIPTION_MAX_CHARS}.")
        return None
