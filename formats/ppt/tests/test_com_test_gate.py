from __future__ import annotations

import os
from unittest import mock
import unittest

from ppt_test_support import powerpoint_com_tests_enabled


class PowerPointComTestGateTests(unittest.TestCase):
    def test_default_test_run_does_not_probe_or_start_powerpoint(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
            "ppt_test_support.subprocess.run"
        ) as run:
            self.assertFalse(powerpoint_com_tests_enabled())

        run.assert_not_called()

    def test_explicit_opt_in_checks_powerpoint_availability(self):
        completed = mock.Mock(returncode=0)
        with mock.patch.dict(os.environ, {"AGICO_RUN_POWERPOINT_COM_TESTS": "1"}), mock.patch(
            "ppt_test_support.os.name", "nt"
        ), mock.patch("ppt_test_support.POWERSHELL", "powershell.exe"), mock.patch(
            "ppt_test_support.subprocess.run", return_value=completed
        ) as run:
            self.assertTrue(powerpoint_com_tests_enabled())

        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
