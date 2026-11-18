"""A row whose x, y or z use no alias of another row is built on its own, whatever else they name: ${self}, a value of
the row as ${startTime}, or a name the table does not define, which the row reports when it draws."""

import unittest

from iplotDataAccess.appDataAccess import AppDataAccess

from mint.gui.mtSignalConfigurator import MTSignalConfigurator
from mint.tests.fixtures import write_csv_datasource_config
from mint.tests.qAppSingleton import ensure_qapp


def _row(variable, alias, stack, x='', y=''):
    # DS, Variable, Stack, Row span, Col span, Envelope, Alias, PulseId, StartTime, EndTime, x, y
    return ['csv', variable, stack, '', '', '', alias, '', '', '', x, y]


class RowsUsingNoOtherAliasTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_qapp()
        AppDataAccess.initialize(write_csv_datasource_config())

    def _built(self, *rows):
        """The rows the build yields a signal for, in the order it builds them."""
        configurator = MTSignalConfigurator()
        self.addCleanup(configurator.deleteLater)
        configurator.import_dict({'model': {'table': list(rows)}})
        return [waypoint.idx for waypoint in configurator.build()]

    def test_a_row_using_values_of_the_row_is_built(self):
        built = self._built(_row('Signal:A', 'a', '1', x='(${self}.time - ${startTime}) / 1e9'),
                            _row('Signal:B', 'b', '2', y='${self}.data * 0 + ${endTime}'))

        self.assertEqual(sorted(built), [0, 1])

    def test_a_row_naming_what_the_table_does_not_define_is_built(self):
        self.assertEqual(self._built(_row('Signal:A', 'a', '1', x='${self}.time - ${nowhere}')), [0])

    def test_a_row_using_the_alias_of_another_is_built_after_it(self):
        built = self._built(_row('Signal:B', 'b', '1', y='${a}.data - ${startTime}'), _row('Signal:A', 'a', ''))

        self.assertEqual(built, [1, 0])


if __name__ == '__main__':
    unittest.main()
