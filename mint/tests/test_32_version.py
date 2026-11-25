"""The version MINT shows is worked out from where its code is."""
import os
import subprocess
import unittest

import mint
from mint import _version


class VersionTest(unittest.TestCase):

    def test_a_checkout_reads_its_version_from_git(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(mint.__file__)))
        inside = subprocess.run(["git", "-C", root, "rev-parse", "--is-inside-work-tree"], capture_output=True,
                                text=True).stdout.strip() == "true"
        if not inside:
            self.skipTest("installed MINT: its version was written when it was built")
        self.assertNotEqual(_version.get_versions()["version"], "0+unknown")
        self.assertEqual(mint.__version__, _version.get_versions()["version"])
