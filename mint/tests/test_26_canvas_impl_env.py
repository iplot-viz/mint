"""The canvas implementation can be chosen without a command line through MINT_IMPL."""

import os
import unittest
from unittest import mock

from mint.app.createApp import default_canvas_impl


class DefaultCanvasImplTest(unittest.TestCase):

    def test_matplotlib_without_the_variable(self):
        with mock.patch.dict(os.environ):
            os.environ.pop('MINT_IMPL', None)
            self.assertEqual(default_canvas_impl(), 'matplotlib')

    def test_variable_selects_the_implementation(self):
        with mock.patch.dict(os.environ, {'MINT_IMPL': 'PyQt'}):
            self.assertEqual(default_canvas_impl(), 'pyqt')

    def test_unknown_value_falls_back_to_matplotlib(self):
        with mock.patch.dict(os.environ, {'MINT_IMPL': 'gnuplot'}):
            self.assertEqual(default_canvas_impl(), 'matplotlib')


if __name__ == '__main__':
    unittest.main()
