# Copyright (c) 2020-2025 ITER Organization,
#               CS 90046
#               13067 St Paul Lez Durance Cedex
#               France
# Author IO
#
# This file is part of mint module.
# mint python module is free software: you can redistribute it and/or modify it under
# the terms of the MIT license.
#
# This file is part of ITER CODAC software.
# For the terms and conditions of redistribution or use of this software
# refer to the file LICENSE located in the top level directory
# of the distribution package
#


# Description: Sets up an application ready for testing.
# Author: Jaswant Sai Panchumarti

from PySide6.QtWidgets import QApplication
from iplotlib.qt.testing import QAppTestAdapter

_instance = None
_qvtk_canvas = None


class QAppOffscreenTestAdapter(QAppTestAdapter):
    """Helper class to provide QApplication instances"""

    qapplication = True

    def setUp(self):
        """Creates the QApplication instance"""

        # Simple way of making instance a singleton
        super().setUp()
        global _instance, _qvtk_canvas
        if _instance is None:
            _instance = QApplication(['QAppOffscreenTestAdapter', '-platform', 'offscreen'])

        self.app = _instance

    def tearDown(self):
        """Deletes the reference owned by self"""
        del self.app
        super().tearDown()
