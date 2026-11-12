"""Docs-as-tests: the embedded user manual cannot lie about the code.

These tests guarantee that:
- Every `manual_anchor` referenced by errors.json exists in manual.html.
- Every help_anchor wired into MTMainWindow widgets exists in manual.html.
- Every AUTO marker present in manual.md is one the build script knows.
- Running build_manual twice yields the same HTML (idempotent build).
- AUTO_ERRORS is preserved verbatim in the built HTML (MTHelp injects
  the catalogue at runtime, so the marker must survive the build).
"""
import json
import re
import unittest
from pathlib import Path

from mint.gui.mtErrorCatalog import ErrorCatalog
from mint.tools import build_manual

HELP_DIR = Path(build_manual.HELP_DIR)
MANUAL_HTML = build_manual.MANUAL_HTML
ERRORS_JSON = HELP_DIR / "errors.json"

# Widget anchors declared in MTMainWindow._install_help_anchors. Kept here
# (rather than imported) so tests do not require a QApplication.
WIRED_HELP_ANCHORS = {
    "table",
    "time-configuration",
    "draw-stream",
    "plotting-area",
}

_ID_PATTERN = re.compile(r'id="([^"]+)"')


def _built_html_anchors() -> set[str]:
    html = MANUAL_HTML.read_text(encoding="utf-8")
    return set(_ID_PATTERN.findall(html))


class ManualAnchorsTest(unittest.TestCase):
    def test_every_error_renders_its_anchor(self):
        # Each errors.json entry must declare a manual_anchor and the
        # renderer must emit it as an HTML id — that is what the popup's
        # "More info →" button jumps to via MTHelp.show_at(anchor).
        catalog = json.loads(ERRORS_JSON.read_text(encoding="utf-8"))
        for entry in catalog["entries"]:
            with self.subTest(entry_id=entry.get("id")):
                anchor = entry.get("manual_anchor")
                self.assertTrue(anchor,
                                f"entry {entry.get('id')!r} has no manual_anchor")
                rendered = ErrorCatalog.render_html(entry)
                self.assertIn(f'id="{anchor}"', rendered,
                              f"render_html() did not emit id={anchor!r}")

    def test_errors_section_exists_in_built_html(self):
        # The section that hosts the runtime-injected catalogue must exist.
        self.assertIn("errors", _built_html_anchors())

    def test_every_wired_help_anchor_exists_in_html(self):
        anchors = _built_html_anchors()
        missing = WIRED_HELP_ANCHORS - anchors
        self.assertFalse(
            missing,
            f"MTMainWindow wires F1 to anchor(s) not present in "
            f"manual.html: {missing}. Either add the section or remove "
            f"the wiring.")


class BuildManualTest(unittest.TestCase):
    def test_build_is_idempotent(self):
        first = build_manual.build()
        second = build_manual.build()
        self.assertEqual(first, second)

    def test_auto_errors_marker_survives_build(self):
        html = build_manual.build()
        self.assertIn(build_manual.ERRORS_MARKER, html,
                      "AUTO_ERRORS must remain in the built HTML — MTHelp "
                      "injects the catalogue at runtime, not at build time.")

    def test_unknown_marker_raises(self):
        md = "# Test\n\n<!-- AUTO_DOES_NOT_EXIST -->\n"
        with self.assertRaises(SystemExit):
            build_manual.apply_markers(md)


class ErrorCatalogConsistencyTest(unittest.TestCase):
    def test_every_colour_of_the_manual_has_one_for_a_dark_palette(self):
        # MTHelp shows the manual in them in a dark palette: a colour without one would stay light there.
        sources = build_manual.HTML_TEMPLATE + build_manual.MANUAL_MD.read_text(encoding="utf-8")
        colours = {colour.lower() for colour in build_manual.HEX_COLOR.findall(
            "".join(re.findall(r'<style>.*?</style>|style="[^"]*"', sources, re.S)))}
        self.assertTrue(colours)
        self.assertEqual(colours - set(build_manual.DARK_COLORS), set())

    def test_dark_colours_change_only_the_styles(self):
        html = '<style>body { color: #222; }</style><p style="color:#555;">#222 <a href="#add">#555</a></p>'
        self.assertEqual(build_manual.dark_colors(html),
                         '<style>body { color: #e6e6e6; }</style><p style="color:#b0b0b0;">#222 <a href="#add">#555</a></p>')

    def test_catalogue_loads(self):
        # Smoke check that the singleton can read errors.json without raising,
        # so the docs-as-tests above run against a real catalogue.
        catalog = ErrorCatalog.instance()
        self.assertTrue(catalog.all_entries(),
                        "errors.json appears empty — popup → manual chain broken.")


if __name__ == "__main__":
    unittest.main()
