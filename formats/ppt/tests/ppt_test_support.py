from __future__ import annotations

import os
import shutil
import subprocess


POWERSHELL = shutil.which("powershell.exe")
OPT_IN_ENV = "AGICO_RUN_POWERPOINT_COM_TESTS"


def powerpoint_com_tests_enabled() -> bool:
    """Enable real PowerPoint COM tests only after an explicit opt-in."""
    if os.environ.get(OPT_IN_ENV) != "1":
        return False
    if os.name != "nt" or not POWERSHELL:
        return False
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-Command",
            "if([type]::GetTypeFromProgID('PowerPoint.Application')){exit 0}else{exit 2}",
        ],
        capture_output=True,
    )
    return result.returncode == 0
