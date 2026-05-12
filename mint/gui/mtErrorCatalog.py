import html
import json
import pkgutil
import re
from typing import Optional

from iplotLogging import setupLogger as setupLog

logger = setupLog.get_logger(__name__)


class ErrorCatalog:
    _instance: Optional["ErrorCatalog"] = None

    def __init__(self):
        self._entries = []
        self._compiled = []
        self._load()

    @classmethod
    def instance(cls) -> "ErrorCatalog":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load(self):
        try:
            raw = pkgutil.get_data('mint.data', 'help/errors.json')
            payload = json.loads(raw)
        except Exception as exc:
            logger.error(f"Could not load error catalog: {exc!r}")
            return

        for entry in payload.get('entries', []):
            patterns = entry.get('patterns', [])
            try:
                regexes = [re.compile(p, re.IGNORECASE) for p in patterns]
            except re.error as exc:
                logger.warning(f"Skipping catalog entry '{entry.get('id')}' with invalid regex: {exc}")
                continue
            self._entries.append(entry)
            self._compiled.append(regexes)

    def match(self, message: str) -> Optional[dict]:
        if not message:
            return None
        for entry, regexes in zip(self._entries, self._compiled):
            if any(rx.search(message) for rx in regexes):
                return entry
        return None

    def all_entries(self) -> list:
        return list(self._entries)

    @staticmethod
    def format_for_popup(entry: dict) -> str:
        lines = [entry.get('summary', '').strip()]
        steps = entry.get('what_to_do') or []
        if steps:
            lines.append("")
            lines.append("What to do:")
            for i, step in enumerate(steps, 1):
                lines.append(f"  {i}. {step}")
        tail = (entry.get('if_it_persists') or '').strip()
        if tail:
            lines.append("")
            lines.append("If it persists:")
            lines.append(f"  {tail}")
        return "\n".join(lines)

    @staticmethod
    def render_html(entry: dict) -> str:
        anchor = entry.get('manual_anchor', '')
        title = html.escape(entry.get('title', ''))
        summary = html.escape(entry.get('summary', '').strip())

        parts = [f'<h3 id="{html.escape(anchor)}">{title}</h3>',
                 f'<p>{summary}</p>']

        steps = entry.get('what_to_do') or []
        if steps:
            parts.append('<p><strong>What to do:</strong></p>')
            parts.append('<ol>')
            for step in steps:
                parts.append(f'  <li>{html.escape(step)}</li>')
            parts.append('</ol>')

        tail = (entry.get('if_it_persists') or '').strip()
        if tail:
            parts.append(f'<p><strong>If it persists:</strong> {html.escape(tail)}</p>')

        return "\n".join(parts)
