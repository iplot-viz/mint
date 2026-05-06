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
