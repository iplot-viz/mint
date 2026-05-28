import importlib.resources as resources
import pkgutil
import re
import tempfile
import typing
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor, QTextDocument
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
                               QSplitter, QTextBrowser, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from iplotLogging import setupLogger as setupLog
from mint.gui.mtErrorCatalog import ErrorCatalog

logger = setupLog.get_logger(__name__)

_TOC_PATTERN = re.compile(r"<(h[23])\s+id=\"([^\"]+)\"[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_TAG_PATTERN = re.compile(r"<[^>]+>")
_ERRORS_MARKER = "<!-- AUTO_ERRORS -->"


class MTHelp(QMainWindow):
    def __init__(self, parent: typing.Optional[QWidget] = None):
        super().__init__(parent=parent)
        self.setWindowTitle("MINT - User Manual")
        self.resize(1100, 750)

        self._image_dir_ctx = None
        self._image_dir: typing.Optional[Path] = None
        self._toc_items_by_anchor: typing.Dict[str, QTreeWidgetItem] = {}

        self._browser = QTextBrowser(self)
        self._browser.setOpenExternalLinks(True)
        self._browser.setOpenLinks(True)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Search in manual (Enter for next)...")
        self._search.returnPressed.connect(self._find_next)
        self._search.textChanged.connect(self._update_match_count)

        self._prev_btn = QToolButton(self)
        self._prev_btn.setText("▲")
        self._prev_btn.setToolTip("Previous match (Shift+Enter)")
        self._prev_btn.clicked.connect(self._find_prev)

        self._next_btn = QToolButton(self)
        self._next_btn.setText("▼")
        self._next_btn.setToolTip("Next match (Enter)")
        self._next_btn.clicked.connect(self._find_next)

        self._match_label = QLabel("", self)
        self._match_label.setStyleSheet("color: #666; padding: 0 6px;")

        for w in (self._prev_btn, self._next_btn):
            w.setAutoRaise(True)
            w.setFocusPolicy(Qt.NoFocus)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.addWidget(self._search, 1)
        search_row.addWidget(self._prev_btn)
        search_row.addWidget(self._next_btn)
        search_row.addWidget(self._match_label)

        self._toc = QTreeWidget(self)
        self._toc.setHeaderHidden(True)
        self._toc.itemClicked.connect(self._on_toc_clicked)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addLayout(search_row)
        left_layout.addWidget(self._toc)

        splitter = QSplitter(self)
        splitter.addWidget(left)
        splitter.addWidget(self._browser)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 820])

        close_btn = QPushButton("Close", self)
        # Required: otherwise Enter inside the search box would activate this button and close the dialog.
        close_btn.setAutoDefault(False)
        close_btn.setDefault(False)
        close_btn.clicked.connect(self.close)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close_btn)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addWidget(splitter)
        layout.addLayout(bottom)
        self.setCentralWidget(central)

        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.close)
        QShortcut(QKeySequence.Find, self, activated=self._focus_search)

    def _on_toc_clicked(self, item: QTreeWidgetItem, _column: int):
        anchor = item.data(0, Qt.UserRole)
        if anchor:
            self._scroll_to_anchor(anchor)

    def _focus_search(self):
        self._search.setFocus(Qt.ShortcutFocusReason)
        self._search.selectAll()

    def _find_next(self):
        needle = self._search.text().strip()
        if not needle:
            return
        if not self._browser.find(needle):
            cursor = self._browser.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self._browser.setTextCursor(cursor)
            self._browser.find(needle)

    def _find_prev(self):
        needle = self._search.text().strip()
        if not needle:
            return
        if not self._browser.find(needle, QTextDocument.FindBackward):
            cursor = self._browser.textCursor()
            cursor.movePosition(QTextCursor.End)
            self._browser.setTextCursor(cursor)
            self._browser.find(needle, QTextDocument.FindBackward)

    def _update_match_count(self, text: str):
        text = text.strip()
        if not text:
            self._match_label.setText("")
            return
        haystack = self._browser.toPlainText().lower()
        count = haystack.count(text.lower())
        self._match_label.setText(f"{count} match{'es' if count != 1 else ''}")

    def _resolve_image_dir(self) -> typing.Optional[Path]:
        try:
            ctx = resources.as_file(resources.files('mint.data').joinpath('help', 'images'))
            path = ctx.__enter__()
            self._image_dir_ctx = ctx
            return Path(path)
        except Exception as exc:
            logger.warning(f"Could not resolve manual images directory via importlib.resources: {exc!r}")

        try:
            tmp = Path(tempfile.mkdtemp(prefix="mint_manual_"))
            for name in self._packaged_image_names():
                data = pkgutil.get_data('mint.data', f'help/images/{name}')
                if data:
                    (tmp / name).write_bytes(data)
            return tmp
        except Exception as exc:
            logger.error(f"Could not stage manual images for the help dialog: {exc!r}")
            return None

    @staticmethod
    def _packaged_image_names() -> list:
        return [f"image_{i:02d}.png" for i in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 17, 18]]

    def _load_manual(self):
        try:
            html_bytes = pkgutil.get_data('mint.data', 'help/manual.html')
            html = html_bytes.decode('utf-8')
        except Exception as exc:
            logger.error(f"Could not load user manual: {exc!r}")
            self._browser.setHtml("<h2>User manual not available</h2>"
                                  f"<p>Could not load the embedded manual ({exc!r}).</p>")
            return

        html = self._inject_error_catalog(html)

        self._image_dir = self._resolve_image_dir()
        if self._image_dir is not None:
            self._browser.setSearchPaths([str(self._image_dir)])

        self._browser.setHtml(html)
        self._populate_toc(html)

    @staticmethod
    def _inject_error_catalog(html: str) -> str:
        if _ERRORS_MARKER not in html:
            return html
        entries = ErrorCatalog.instance().all_entries()
        if not entries:
            return html.replace(_ERRORS_MARKER, "<p><em>No catalogued entries available.</em></p>")
        rendered = "\n\n".join(ErrorCatalog.render_html(e) for e in entries)
        return html.replace(_ERRORS_MARKER, rendered)

    def _populate_toc(self, html: str):
        self._toc.clear()
        self._toc_items_by_anchor.clear()
        current_h2: typing.Optional[QTreeWidgetItem] = None
        for level, anchor, raw_title in _TOC_PATTERN.findall(html):
            title = _TAG_PATTERN.sub("", raw_title).strip()
            if not title:
                continue
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.UserRole, anchor)
            self._toc_items_by_anchor[anchor] = item
            if level.lower() == 'h2':
                self._toc.addTopLevelItem(item)
                current_h2 = item
            elif current_h2 is not None:
                current_h2.addChild(item)
            else:
                self._toc.addTopLevelItem(item)
        self._toc.expandAll()

    def show_at(self, anchor: str = None):
        if not self._browser.document().toPlainText():
            self._load_manual()
        self.show()
        self.raise_()
        self.activateWindow()
        if anchor:
            self._scroll_to_anchor(anchor)
        else:
            # Reset to the top so opening "User Manual" from the menu
            # always lands on the TOC, never on the last viewed section.
            QTimer.singleShot(0, lambda: self._browser.verticalScrollBar().setValue(0))
            self._toc.clearSelection()

    def _scroll_to_anchor(self, anchor: str):
        # Deferred to the next event tick: scrollToAnchor right after setHtml is unreliable in Qt6.
        QTimer.singleShot(0, lambda: self._browser.scrollToAnchor(anchor))
        self._highlight_toc_anchor(anchor)

    def _highlight_toc_anchor(self, anchor: str):
        item = self._toc_items_by_anchor.get(anchor)
        if item is None:
            return
        self._toc.setCurrentItem(item)
        self._toc.scrollToItem(item)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and ev.modifiers() & Qt.ShiftModifier:
            if self._search.hasFocus():
                self._find_prev()
                return
        super().keyPressEvent(ev)

    def showEvent(self, ev):
        if not self._browser.document().toPlainText():
            self._load_manual()
        super().showEvent(ev)

    def closeEvent(self, ev):
        if self._image_dir_ctx is not None:
            try:
                self._image_dir_ctx.__exit__(None, None, None)
            except Exception:
                pass
            self._image_dir_ctx = None
        super().closeEvent(ev)
