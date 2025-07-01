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


# Description: Checks data access model
# Author: Jaswant Sai Panchumarti

from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__, level="INFO")


def check_data_range(model: dict):
    try:
        assert (model is not None)
    except AssertionError:
        logger.warning("model must be non-null")
        return False

    try:
        assert ("range" in model.keys())
    except AssertionError:
        logger.warning("model is corrupt. Cannot find range")
        return False

    try:
        assert ("mode" in model.get("range").keys())
    except (AssertionError, AttributeError) as e:
        logger.warning(f"{e} raised, model['range'] is corrupt.")
        return False

    try:
        assert ("value" in model.get("range").keys())
    except (AssertionError, AttributeError) as e:
        logger.warning(f"{e} raised, model['range'] is corrupt.")
        return False

    return True
