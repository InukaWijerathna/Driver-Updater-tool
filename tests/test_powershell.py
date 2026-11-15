"""Exercise the real installation script with in-memory COM substitutes."""

import base64
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from src.windows_update import _PS_INSTALL

ID = "11111111-1111-1111-1111-111111111111"
OTHER_ID = "22222222-2222-2222-2222-222222222222"


@unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell required")
class PowerShellInstallTests(unittest.TestCase):
    def run_scenario(self, entries, targets=None, throw=False):
        config = json.dumps(dict(Updates=entries, ThrowOnInstall=throw))
        fixture = Path(__file__).with_name("fake_wua.ps1").read_text(encoding="utf-8")
        fixture = fixture.replace("__CONFIG__", config)
        targets = targets if targets is not None else [
            dict(UpdateID=entry["ID"], RevisionNumber=7, Title="Selected driver") for entry in entries
        ]
        encoded = base64.b64encode(json.dumps(targets).encode()).decode()
        script = fixture + "\n" + _PS_INSTALL.replace("__TARGETS__", encoded)
        script += '\nConvertTo-Json -InputObject @{Installed=$script:installedIDs; Downloads=$script:downloadCalls} -Compress'
        encoded_script = base64.b64encode(script.encode("utf-16-le")).decode()
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_script],
            capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2, result.stdout + result.stderr)
        return json.loads(lines[0]), json.loads(lines[1])

    def entry(self, update_id=ID, download=2, install=2, revision=7):
        return dict(ID=update_id, Revision=revision, DownloadCode=download, InstallCode=install)

    def test_success_records_each_update_and_reboot(self):
        report, state = self.run_scenario([self.entry()])
        self.assertEqual(report["Error"], "")
        self.assertEqual(report["InstallResultCode"], 2)
        self.assertTrue(report["RebootRequired"])
        self.assertFalse(report["StatusUnknown"])
        self.assertEqual(state["Installed"], [ID])

    def test_failed_download_is_never_installed(self):
        report, state = self.run_scenario([self.entry(), self.entry(OTHER_ID, download=4)])
        self.assertEqual(state["Installed"], [ID])
        self.assertEqual(report["DownloadResultCode"], 3)
        failed = next(item for item in report["Updates"] if item["UpdateID"] == OTHER_ID)
        self.assertEqual(failed["Stage"], "download")
        self.assertEqual(failed["ResultCode"], 4)

    def test_partial_install_is_reported_per_update(self):
        report, state = self.run_scenario([self.entry(), self.entry(OTHER_ID, install=4)])
        self.assertEqual(report["InstallResultCode"], 3)
        self.assertTrue(report["RebootRequired"])
        self.assertEqual(sorted(item["ResultCode"] for item in report["Updates"]), [2, 4])

    def test_changed_revision_stops_before_download(self):
        report, state = self.run_scenario([self.entry(revision=8)])
        self.assertEqual(state["Downloads"], 0)
        self.assertEqual(state["Installed"], [])
        self.assertIn("revisions changed", report["Error"])

    def test_missing_update_stops_entire_selection(self):
        targets = [dict(UpdateID=key, RevisionNumber=7, Title="Driver") for key in (ID, OTHER_ID)]
        report, state = self.run_scenario([self.entry()], targets=targets)
        self.assertEqual(state["Downloads"], 0)
        self.assertEqual(state["Installed"], [])
        self.assertTrue(report["Error"])

    def test_install_exception_preserves_uncertainty(self):
        report, _ = self.run_scenario([self.entry()], throw=True)
        self.assertTrue(report["StatusUnknown"])
        self.assertIn("Simulated installation exception", report["Error"])
