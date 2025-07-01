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


# Description: A helpful icon loader.
# Author: Jaswant Sai Panchumarti

import pkgutil

from PySide6.QtGui import QPixmap, QIcon


def create_pxmap(name, ext: str = 'png') -> QPixmap:
    pxmap = QPixmap()
    pxmap.loadFromData(pkgutil.get_data("mint.gui", f"icons/{name}.{ext}"))
    return pxmap


def create_icon(name, ext: str = 'png') -> QIcon:
    return QIcon(create_pxmap(name, ext))
