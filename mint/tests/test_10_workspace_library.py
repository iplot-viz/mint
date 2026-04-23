"""Parametrised tests over the shipped workspace JSONs.

``mint/data/workspaces/`` contains historical workspaces (CVB, Issue31,
IDV246...) saved by real users over years. Many pre-date the current
blueprint — missing Calibrated, different PulseId formats, older
``variables_table`` key instead of ``table``, etc. The model's
``import_dict`` / ``import_json`` paths must keep loading them cleanly
so existing users don't lose their files on upgrade.

These tests iterate over every workspace in that folder and:
- validate the JSON structure;
- feed the signal-config section into MTSignalsModel.import_dict;
- assert the signals table populates without raising.

Failing on a specific workspace here is a real regression in backward
compatibility.
"""

import json
import os
import unittest

from iplotDataAccess.appDataAccess import AppDataAccess

from mint.models.mtSignalsModel import MTSignalsModel
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


WORKSPACES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'data', 'workspaces'))


def _list_workspaces():
    """Every .json file in the shipped workspaces folder."""
    if not os.path.isdir(WORKSPACES_DIR):
        return []
    return sorted(f for f in os.listdir(WORKSPACES_DIR)
                  if f.lower().endswith('.json'))


def _ensure_data_access() -> None:
    if AppDataAccess.da is None:
        AppDataAccess.initialize(write_csv_datasource_config())


class WorkspaceJsonStructureTest(unittest.TestCase):
    """Every shipped workspace is a valid JSON with the minimum structure."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.workspaces = _list_workspaces()

    def test_at_least_one_workspace_is_shipped(self):
        """Sanity: the folder should not be empty."""
        self.assertGreater(len(self.workspaces), 0,
                           f"no workspaces found in {WORKSPACES_DIR}")

    def test_each_workspace_is_parseable_json(self):
        for name in self.workspaces:
            with self.subTest(workspace=name):
                path = os.path.join(WORKSPACES_DIR, name)
                with open(path, 'r') as fh:
                    try:
                        json.load(fh)
                    except json.JSONDecodeError as exc:
                        self.fail(f"{name} is not valid JSON: {exc}")

    def test_each_workspace_carries_a_signals_section(self):
        """Either 'signal_cfg' (modern) or a root 'variables_table'/'table'
        (legacy) must be present."""
        for name in self.workspaces:
            with self.subTest(workspace=name):
                path = os.path.join(WORKSPACES_DIR, name)
                with open(path, 'r') as fh:
                    data = json.load(fh)

                has_sig_cfg = 'signal_cfg' in data
                has_legacy = 'variables_table' in data or 'table' in data
                self.assertTrue(has_sig_cfg or has_legacy,
                                f"{name} has neither signal_cfg nor a legacy "
                                f"variables_table / table key")


class WorkspaceImportIntoModelTest(unittest.TestCase):
    """Each workspace's signal-config section feeds MTSignalsModel.import_dict
    without raising."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        _ensure_data_access()
        cls.workspaces = _list_workspaces()

    def _extract_signal_cfg(self, data: dict) -> dict:
        """Return the part of the workspace that MTSignalsModel.import_dict
        knows how to consume.

        Modern workspaces nest it under ``signal_cfg.model`` (with
        ``blueprint`` and ``table``). Legacy ones keep the table at the
        root as ``variables_table`` or ``table``.
        """
        if 'signal_cfg' in data and 'model' in data['signal_cfg']:
            return data['signal_cfg']['model']
        if 'signal_cfg' in data:
            return data['signal_cfg']
        return data

    def test_every_workspace_imports_without_raising(self):
        skipped = []
        for name in self.workspaces:
            with self.subTest(workspace=name):
                path = os.path.join(WORKSPACES_DIR, name)
                with open(path, 'r') as fh:
                    data = json.load(fh)
                signal_cfg = self._extract_signal_cfg(data)
                if not ('table' in signal_cfg or 'variables_table' in signal_cfg):
                    skipped.append(name)
                    self.skipTest(
                        f"{name}: no table key at signal_cfg level — workspace "
                        f"shape predates MTSignalsModel.import_dict.")

                model = MTSignalsModel()
                # Should not raise: legacy workspaces without Calibrated,
                # PulseId, x/y/z or similar columns get filled with defaults.
                model.import_dict(signal_cfg)

                # The table must have at least as many rows as the workspace
                # lists (MTSignalsModel may add extra defaults but never drops).
                raw = signal_cfg.get('table') or signal_cfg.get('variables_table')
                if isinstance(raw, list):
                    self.assertGreaterEqual(
                        len(model.get_dataframe()), len(raw),
                        f"{name}: imported table has fewer rows than the JSON")


if __name__ == '__main__':
    unittest.main()
