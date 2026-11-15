"""Regression checks use mocked subprocesses; no real drivers are touched."""

import io
import json
import subprocess
import unittest
from dataclasses import replace
from unittest.mock import patch

from rich.console import Console

import main
from src import driver_detector, manufacturer_check, updater, windows_update as wu
from src.powershell import ScanError

ID = "11111111-1111-1111-1111-111111111111"
OTHER_ID = "22222222-2222-2222-2222-222222222222"


def update(update_id=ID):
    return wu.WUDriverUpdate("Test driver", "Display", "Intel", "", "", "1", "", update_id, 7, 100)


def completed(data, code=0):
    return subprocess.CompletedProcess([], code, json.dumps(data), "test error" if code else "")


def outcome(update_id=ID, stage="install", code=2):
    return dict(UpdateID=update_id, Title="Test driver", Stage=stage, ResultCode=code, HResult=0)


def report(outcomes=None, **kwargs):
    data = dict(DownloadResultCode=2, InstallResultCode=2, RebootRequired=False,
                StatusUnknown=False, Error="", Updates=outcomes if outcomes is not None else [outcome()])
    data.update(kwargs)
    return data


class ScanTests(unittest.TestCase):
    def test_scan_errors_are_not_empty_results(self):
        scans = (driver_detector.get_installed_drivers, driver_detector.get_problem_devices,
                 wu.check_windows_update_drivers)
        responses = (completed([], 1), subprocess.CompletedProcess([], 0, "bad JSON", ""),
                     completed(None), completed([None]), subprocess.CompletedProcess([], 0, "", ""))
        for scan in scans:
            for response in responses:
                with self.subTest(scan=scan.__name__, response=response.stdout):
                    with patch("src.powershell.subprocess.run", return_value=response):
                        with self.assertRaises(ScanError):
                            scan()

    def test_empty_scans_succeed(self):
        with patch("src.powershell.subprocess.run", return_value=completed([])):
            self.assertEqual(driver_detector.get_installed_drivers(), [])
            self.assertEqual(driver_detector.get_problem_devices(), [])
            self.assertEqual(wu.check_windows_update_drivers(), [])

    def test_timeout_and_missing_powershell(self):
        for error in (subprocess.TimeoutExpired("powershell", 120), FileNotFoundError("powershell")):
            with patch("src.powershell.subprocess.run", side_effect=error):
                with self.assertRaises(ScanError):
                    wu.check_windows_update_drivers()

    def test_single_driver_and_non_ascii_name(self):
        with patch("src.powershell.subprocess.run", return_value=completed({"DeviceName": "音声"})):
            self.assertEqual(driver_detector.get_installed_drivers()[0].device_name, "音声")

    def test_optional_and_beta_are_independent(self):
        data = [dict(UpdateID=ID, RevisionNumber=1, Title=f"{beta}:{optional}",
                     IsBeta=beta, BrowseOnly=optional)
                for beta in (False, True) for optional in (False, True)]
        for beta, optional, count in ((False, False, 1), (False, True, 2),
                                      (True, False, 2), (True, True, 4)):
            with self.subTest(beta=beta, optional=optional):
                with patch("src.powershell.subprocess.run", return_value=completed(data)):
                    self.assertEqual(len(wu.check_windows_update_drivers(beta, optional)), count)

    def test_invalid_update_identity_fails_scan(self):
        with patch("src.powershell.subprocess.run", return_value=completed({"Title": "driver"})):
            with self.assertRaises(ScanError):
                wu.check_windows_update_drivers()


class InstallTests(unittest.TestCase):
    def install(self, payload, selection=None):
        with patch.object(wu.subprocess, "run", return_value=completed(payload)):
            return wu.install_wu_updates(selection if selection is not None else [update()])

    def test_success(self):
        self.assertTrue(self.install(report()).success)

    def test_partial_failure_preserves_reboot_and_individual_results(self):
        result = self.install(report([outcome(), outcome(OTHER_ID, code=4)],
                                     InstallResultCode=3, RebootRequired=True),
                              [update(), update(OTHER_ID)])
        self.assertFalse(result.success)
        self.assertTrue(result.reboot_required)
        self.assertEqual(result.updates[1].result_code, 4)

    def test_aggregate_partial_result_is_not_success(self):
        self.assertFalse(self.install(report(InstallResultCode=3)).success)

    def test_download_failure_is_not_success(self):
        result = self.install(report([outcome(stage="download", code=4)],
                                     DownloadResultCode=4, InstallResultCode=0))
        self.assertFalse(result.success)
        self.assertEqual(result.updates[0].stage, "download")

    def test_stale_selection_is_reported(self):
        result = self.install(report([outcome(stage="validation", code=0)],
                                     Error="Selected revision changed", InstallResultCode=0))
        self.assertFalse(result.success)
        self.assertIn("revision changed", result.error)

    def test_missing_or_duplicate_results_never_report_success(self):
        for items in ([], [outcome(OTHER_ID)], [outcome(), outcome()]):
            with self.subTest(items=items):
                result = self.install(report(items))
                self.assertFalse(result.success)
                self.assertTrue(result.status_unknown)

    def test_nonzero_process_exit_overrides_success_payload(self):
        with patch.object(wu.subprocess, "run", return_value=completed(report(), 1)):
            result = wu.install_wu_updates([update()])
        self.assertFalse(result.success)
        self.assertTrue(result.status_unknown)

    def test_timeout_has_unknown_status(self):
        with patch.object(wu.subprocess, "run", side_effect=subprocess.TimeoutExpired("powershell", 600)):
            result = wu.install_wu_updates([update()])
        self.assertTrue(result.status_unknown)
        self.assertFalse(result.success)

    def test_exception_during_install_is_unknown(self):
        result = self.install(report(Error="COM exception", StatusUnknown=True))
        self.assertTrue(result.status_unknown)
        self.assertFalse(result.success)

    def test_invalid_selection_never_launches_powershell(self):
        with patch.object(wu.subprocess, "run") as run:
            for selection in ([], [replace(update(), update_id="'; bad command")],
                              [update(), replace(update(), revision_number=8)]):
                self.assertFalse(wu.install_wu_updates(selection).success)
            run.assert_not_called()


class MenuTests(unittest.TestCase):
    def test_eof_and_interrupt_exit_menu(self):
        for error in (EOFError, KeyboardInterrupt):
            with patch("builtins.input", side_effect=error) as prompt, \
                    patch.object(updater, "console"), patch.object(updater, "print_updates_table"):
                updater.run_interactive_menu([], [], [], [], False)
                self.assertEqual(prompt.call_count, 1)

    def test_cancel_selection_never_installs_sixth_update(self):
        for error in (EOFError, KeyboardInterrupt):
            with patch("builtins.input", side_effect=error), patch.object(updater, "console"), \
                    patch.object(updater, "install_wu_updates") as install:
                updater._install_selected_wu([update()] * 6, True)
                install.assert_not_called()

    def test_partial_failure_display_includes_error_and_reboot(self):
        result = wu.InstallationResult(
            updates=[wu.UpdateInstallResult(ID, "Test driver", "install", 4, -2145124329)],
            reboot_required=True,
        )
        output = io.StringIO()
        with patch.object(updater, "console", Console(file=output, width=150)):
            updater._report_wu_result(result)
        self.assertNotIn("Installation successful", output.getvalue())
        self.assertIn("HRESULT 0x", output.getvalue())
        self.assertIn("restart is required", output.getvalue())

    def test_installed_updates_removed_from_menu(self):
        updates = [update(), update(OTHER_ID)]
        result = wu.InstallationResult(updates=[wu.UpdateInstallResult(ID, "driver", "install", 2, 0)])
        updater._remove_installed(updates, result)
        self.assertEqual([u.update_id for u in updates], [OTHER_ID])

    def test_unknown_status_exits_session(self):
        with patch.object(updater, "console"), patch.object(updater, "install_wu_updates",
                return_value=wu.InstallationResult(status_unknown=True)):
            with self.assertRaises(SystemExit):
                updater._install_all_wu([update()], True)


class EntryPointTests(unittest.TestCase):
    def test_default_flags_exclude_beta_and_optional(self):
        args = main.parse_args([])
        self.assertFalse(args.beta)
        self.assertFalse(args.optional)

    def test_optional_flag_does_not_enable_beta(self):
        args = main.parse_args(["--optional"])
        self.assertTrue(args.optional)
        self.assertFalse(args.beta)

    def test_conflicting_flags_rejected(self):
        with patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
            main.parse_args(["--stable-only", "--beta"])

    def test_scan_error_is_not_shown_as_no_updates(self):
        output = io.StringIO()
        with patch("sys.argv", ["main.py"]), \
                patch.object(main, "console", Console(file=output)), \
                patch.object(main, "get_installed_drivers", return_value=[]), \
                patch.object(main, "get_problem_devices", return_value=[]), \
                patch.object(main, "check_windows_update_drivers", side_effect=ScanError("Unavailable")), \
                patch.object(main, "print_banner"), \
                patch.object(main, "run_interactive_menu") as menu:
            with self.assertRaises(SystemExit):
                main.main()
            menu.assert_not_called()
        self.assertIn("Scan failed", output.getvalue())
        self.assertNotIn("no pending driver updates", output.getvalue())


class GpuTests(unittest.TestCase):
    def test_case_insensitive_gpu_detection(self):
        for manufacturer, name in (("INTEL", "Intel UHD"), ("advanced micro devices", "Radeon"),
                                   ("nViDiA", "NVIDIA RTX")):
            with self.subTest(manufacturer=manufacturer):
                driver = driver_detector.DriverInfo(name, "31.0.15.7602", manufacturer, "DISPLAY", "", "", "")
                self.assertEqual(len(manufacturer_check.check_manufacturer_updates([driver])), 1)


if __name__ == "__main__":
    unittest.main()
