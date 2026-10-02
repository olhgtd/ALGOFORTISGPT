"""Regression contract for the private/local AlgoFortis Windows desktop build.

The installed launcher already starts LOCAL_PRIVATE.  All desktop/install
certification must exercise that exact mode rather than PRODUCTION so the
qualification matches what the user double-clicks on a personal/family PC.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TestLocalPrivateDesktopBehavior(unittest.TestCase):
    def _read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_launcher_uses_local_private_runtime(self):
        source = self._read("build/tools/AlgoFortisLauncher.cs")
        self.assertIn("--mode LOCAL_PRIVATE", source)
        self.assertIn('RunController("stop")', source)
        self.assertIn("Global\\\\AlgoFortis_Desktop_App_Instance_Mutex", source)

    def test_installer_lifecycle_targets_local_private(self):
        source = self._read("build/tools/algofortis_installer.iss")
        self.assertGreaterEqual(source.count("--mode LOCAL_PRIVATE"), 2)

    def test_desktop_shell_certification_matches_local_private_runtime(self):
        source = self._read("build/tools/certify_desktop_shell.py")
        self.assertNotIn('"--mode", "PRODUCTION"', source)
        self.assertIn('"--mode", "LOCAL_PRIVATE"', source)

    def test_phase9_phase10_install_certification_matches_local_private_runtime(self):
        source = self._read("build/tools/certify_phase9_phase10_installation.py")
        self.assertNotIn('"--mode", "PRODUCTION"', source)
        self.assertIn('"--mode", "LOCAL_PRIVATE"', source)
        self.assertIn('content="LOCAL_PRIVATE"', source)
        self.assertIn('status_data["mode"] == "LOCAL_PRIVATE"', source)

    def test_manual_launch_probe_matches_local_private_runtime(self):
        source = self._read("build/tools/test_launch.ps1")
        self.assertNotIn("--mode PRODUCTION", source)
        self.assertIn("--mode LOCAL_PRIVATE", source)

    def test_private_installer_keeps_user_data_outside_program_files(self):
        source = self._read("build/tools/certify_phase9_phase10_installation.py")
        self.assertIn('Path(os.environ["LOCALAPPDATA"]) / "AlgoFortis"', source)
        self.assertIn("User data in LOCALAPPDATA was destroyed by uninstaller", source)


if __name__ == "__main__":
    unittest.main()
