"""Build mint/data/help/manual.html from manual.md.

Replaces AUTO_X markers with content extracted from the codebase
(version, shortcuts, access modes, data source types) so those
sections cannot drift from the source of truth.

AUTO_ERRORS is intentionally NOT processed here — MTHelp injects
the error catalogue at runtime from errors.json. This script
preserves the marker verbatim.

Usage:
    python -m mint.tools.build_manual           # build
    python -m mint.tools.build_manual --check   # exit 1 if HTML is stale
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable

HELP_DIR = Path(__file__).resolve().parent.parent / "data" / "help"
MANUAL_MD = HELP_DIR / "manual.md"
MANUAL_HTML = HELP_DIR / "manual.html"

ERRORS_MARKER = "<!-- AUTO_ERRORS -->"
KNOWN_MARKERS = {
    "<!-- AUTO_SHORTCUTS -->",
    "<!-- AUTO_ACCESS_MODES -->",
    "<!-- AUTO_DATASOURCES -->",
    ERRORS_MARKER,
}

# Same styling as the previous hand-edited manual.html so QTextBrowser
# rendering does not change. Kept here as the single source of truth.
HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>MINT - User Manual</title>
<style>
  body {{ font-family: sans-serif; color: #222; line-height: 1.45; padding: 0 12px; }}
  h1 {{ color: #1a4d80; border-bottom: 2px solid #1a4d80; padding-bottom: 4px; }}
  h2 {{ color: #1a4d80; margin-top: 1.6em; border-bottom: 1px solid #cdd; padding-bottom: 2px; }}
  h3 {{ color: #2a5d90; margin-top: 1.3em; }}
  h4 {{ color: #335; }}
  code, pre {{ font-family: Consolas, "Courier New", monospace; background: #f4f4f4; }}
  pre {{ padding: 8px; border-left: 3px solid #888; overflow-x: auto; }}
  table {{ border-collapse: collapse; margin: 8px 0; }}
  table, th, td {{ border: 1px solid #aaa; }}
  th, td {{ padding: 4px 8px; vertical-align: top; }}
  th {{ background: #e6eef7; }}
  .note {{ background: #fff8d6; border-left: 4px solid #d4a800; padding: 6px 10px; margin: 8px 0; }}
  .err-block {{ background: #fdecec; border-left: 4px solid #c0392b; padding: 6px 10px; margin: 8px 0; }}
  ul.toc {{ list-style: none; padding-left: 0; }}
  ul.toc li {{ margin: 2px 0; }}
  ul.toc a {{ text-decoration: none; }}
  img.inline-icon {{ vertical-align: middle; height: 18px; border: 0; }}
  figure {{ text-align: center; margin: 14px auto; }}
  figcaption {{ color: #555; font-size: 90%; font-style: italic; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))


# Curated user-facing descriptions for keyboard shortcuts. The static
# scan finds the combos in code, this dict explains what they do in
# words a scientist (not a developer) cares about. Adding a new
# shortcut to mint/gui/ without an entry here makes the build warn
# (or fail in --check mode).
SHORTCUT_DESCRIPTIONS = {
    "Ctrl+C": "Copy the current selection from the variable table to the clipboard",
    "Ctrl+V": "Paste from the clipboard into the variable table",
    "Ctrl+H": "Open the user manual at the section relevant to the focused area",
    "Standard: Find": "Open the search box in the user manual",
    "Standard: Quit": "Quit MINT",
}

# Cross-platform display for Qt standard keys (Windows/Linux default).
# Mac equivalents use the Command key instead of Ctrl.
STANDARD_KEY_DISPLAYS = {
    "Standard: Find": "Ctrl+F",
    "Standard: Quit": "Ctrl+Q",
    "Standard: Save": "Ctrl+S",
    "Standard: Open": "Ctrl+O",
    "Standard: Copy": "Ctrl+C",
    "Standard: Paste": "Ctrl+V",
    "Standard: Cut": "Ctrl+X",
    "Standard: Undo": "Ctrl+Z",
    "Standard: Redo": "Ctrl+Y",
    "Standard: SelectAll": "Ctrl+A",
    "Standard: HelpContents": "F1",
}

# Shortcuts the static scan cannot see (bound via Qt.Key_* enums or
# inherited from a base class). Keep this list short.
EXTRA_SHORTCUTS = [
    ("Esc", "Close the user manual window"),
]


def _iter_shortcut_combos() -> Iterable[str]:
    gui_dir = Path(__file__).resolve().parent.parent / "gui"
    seq_str = re.compile(r'QKeySequence\(\s*["\']([^"\']+)["\']\s*\)')
    seq_enum = re.compile(r'QKeySequence(?:\.StandardKey)?\.([A-Za-z_]+)')
    standard_keys = {"Find", "Quit", "Save", "Open", "Copy", "Paste", "Cut",
                     "Undo", "Redo", "SelectAll", "HelpContents"}
    seen: set[str] = set()
    for py in sorted(gui_dir.glob("*.py")):
        text = py.read_text(encoding="utf-8", errors="ignore")
        for combo in seq_str.findall(text):
            seen.add(combo)
        for name in seq_enum.findall(text):
            if name in standard_keys:
                seen.add(f"Standard: {name}")
    return sorted(seen)


def render_shortcuts() -> str:
    combos = list(_iter_shortcut_combos())
    undocumented = [c for c in combos if c not in SHORTCUT_DESCRIPTIONS]
    if undocumented:
        print(f"build_manual: WARNING — undocumented shortcut(s) found in "
              f"mint/gui/: {undocumented}. Add them to "
              f"SHORTCUT_DESCRIPTIONS in build_manual.py.", file=sys.stderr)
    rows = ['<tr><th>Shortcut</th><th>What it does</th></tr>']
    for combo in combos:
        display = STANDARD_KEY_DISPLAYS.get(combo, combo)
        desc = SHORTCUT_DESCRIPTIONS.get(combo, "(undocumented — see build_manual.py)")
        rows.append(f'<tr><td><code>{_escape(display)}</code></td>'
                    f'<td>{_escape(desc)}</td></tr>')
    for combo, desc in EXTRA_SHORTCUTS:
        rows.append(f'<tr><td><code>{_escape(combo)}</code></td>'
                    f'<td>{_escape(desc)}</td></tr>')
    return "<table>\n  " + "\n  ".join(rows) + "\n</table>"


def render_access_modes() -> str:
    try:
        from mint.models.accessModes.mtGeneric import MTGenericAccessMode
    except Exception:
        return "<p><em>Access modes unavailable.</em></p>"
    rows = ['<tr><th>Mode</th><th>Label</th><th>Description</th></tr>']
    for mode, label, tooltip in MTGenericAccessMode.meta():
        rows.append(f'<tr><td><code>{_escape(mode)}</code></td>'
                    f'<td>{_escape(label)}</td>'
                    f'<td>{_escape(tooltip)}</td></tr>')
    return "<table>\n  " + "\n  ".join(rows) + "\n</table>"


def render_datasources() -> str:
    try:
        import iplotDataAccess
    except Exception:
        return "<p><em>iplotDataAccess not importable — data source list unavailable.</em></p>"
    pkg_dir = Path(iplotDataAccess.__file__).parent
    cfg_path = pkg_dir / "data_sources.cfg"
    if not cfg_path.exists():
        return f"<p><em>data_sources.cfg not found at {_escape(str(cfg_path))}.</em></p>"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"<p><em>Could not parse data_sources.cfg: {_escape(str(exc))}.</em></p>"
    rows = ['<tr><th>Type</th><th>Module</th><th>Class</th></tr>']
    for source_type, entry in sorted(cfg.items()):
        rows.append(f'<tr><td><code>{_escape(source_type)}</code></td>'
                    f'<td><code>{_escape(str(entry.get("pymodule", "")))}</code></td>'
                    f'<td><code>{_escape(str(entry.get("class", "")))}</code></td></tr>')
    return "<table>\n  " + "\n  ".join(rows) + "\n</table>"


RENDERERS = {
    "<!-- AUTO_SHORTCUTS -->": render_shortcuts,
    "<!-- AUTO_ACCESS_MODES -->": render_access_modes,
    "<!-- AUTO_DATASOURCES -->": render_datasources,
}


def apply_markers(md_text: str) -> str:
    # Reject unknown markers early so typos surface as build failures.
    for found in re.findall(r"<!--\s*AUTO_[A-Z_]+\s*-->", md_text):
        canonical = re.sub(r"\s+", " ", found).strip()
        if canonical not in KNOWN_MARKERS:
            raise SystemExit(f"build_manual: unknown marker {canonical!r}")
    out = md_text
    for marker, renderer in RENDERERS.items():
        if marker in out:
            out = out.replace(marker, renderer())
    return out


def md_to_html(md_text: str) -> str:
    try:
        import markdown
    except ImportError as exc:
        raise SystemExit("build_manual: requires `markdown` package — "
                         "install with `pip install markdown`") from exc
    body = markdown.markdown(
        md_text,
        extensions=["attr_list", "tables", "fenced_code", "sane_lists", "def_list"],
        output_format="html5",
    )
    return HTML_TEMPLATE.format(body=body)


def build() -> str:
    if not MANUAL_MD.exists():
        raise SystemExit(f"build_manual: source not found: {MANUAL_MD}")
    md_text = MANUAL_MD.read_text(encoding="utf-8")
    md_with_autos = apply_markers(md_text)
    return md_to_html(md_with_autos)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if manual.html is out of date")
    args = parser.parse_args(argv)

    new_html = build()
    if args.check:
        current = MANUAL_HTML.read_text(encoding="utf-8") if MANUAL_HTML.exists() else ""
        if current.strip() != new_html.strip():
            msg = "manual.html is stale — run `python -m mint.tools.build_manual`"
            # Under GitHub Actions, emit the workflow-command form so the
            # message appears as an inline PR annotation, not just log noise.
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(f"::error file=mint/data/help/manual.html::{msg}",
                      file=sys.stderr)
            else:
                print(msg, file=sys.stderr)
            return 1
        return 0
    MANUAL_HTML.write_text(new_html, encoding="utf-8")
    print(f"wrote {MANUAL_HTML} ({len(new_html)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
