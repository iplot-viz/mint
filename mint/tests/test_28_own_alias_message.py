"""A row that refers to its own alias stops the table build with a message
that says where it does it and what to write instead."""

import unittest

from iplotDataAccess.appDataAccess import AppDataAccess

from mint.gui.mtSignalConfigurator import MTSignalConfigurator
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _row(variable, alias, y=''):
    # DS, Variable, Stack, Row span, Col span, Envelope, Alias, PulseId, StartTime, EndTime, x, y
    return ['csv', variable, '1.1', '', '', '', alias, '', '', '', '', y]


class OwnAliasMessageTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        AppDataAccess.initialize(write_csv_datasource_config())

    def _build(self, *rows):
        configurator = MTSignalConfigurator()
        self.addCleanup(configurator.deleteLater)
        messages = []
        configurator.buildAborted.connect(messages.append)
        configurator.import_dict({'model': {'table': list(rows)}})
        list(configurator.build())
        return messages

    def test_own_alias_with_other_aliases_points_to_self(self):
        messages = self._build(_row('Signal:A', 'a'),
                               _row('Signal:B', 'b', 'np.clip(${a}.data, 0, 1) + ${b}.data'))

        self.assertEqual(messages, ["Conflicted row: 2, column y uses the row's own alias ${b}. "
                                    "Write ${self} instead to use this row's own signal."])

    def test_self_with_other_aliases_builds(self):
        messages = self._build(_row('Signal:A', 'a'),
                               _row('Signal:B', 'b', 'np.clip(${a}.data, 0, 1) + ${self}.data'))

        self.assertEqual(messages, [])

    def test_own_alias_in_the_variable(self):
        messages = self._build(_row('Signal:A', 'a'), _row('${a}+${b}', 'b'))

        self.assertEqual(messages, ["Conflicted row: 2, its Variable uses the row's own alias ${b}, "
                                    "so the row would be defined from itself."])


if __name__ == '__main__':
    unittest.main()
