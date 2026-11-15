"""Check and install driver updates via the Windows Update Agent COM API."""

import subprocess
import json
import logging
from dataclasses import dataclass, field
from typing import List
import base64
from uuid import UUID

from .powershell import ScanError, run_json_scan

logger = logging.getLogger(__name__)

# WUA search criteria do not support filtering by WHQL directly.
# We fetch IsBeta per update and filter in Python instead.
_PS_SEARCH = r"""
try {
    $s = New-Object -ComObject Microsoft.Update.Session
    $r = $s.CreateUpdateSearcher().Search("IsInstalled=0 and Type='Driver'")
    if ([int]$r.ResultCode -ne 2) { throw "Windows Update search did not fully succeed (code $($r.ResultCode))" }
    $list = @()
    foreach ($u in $r.Updates) {
        $list += @{
            Title              = [string]$u.Title
            DriverClass        = if ($u.DriverClass)            { [string]$u.DriverClass }            else { "" }
            DriverManufacturer = if ($u.DriverManufacturerName) { [string]$u.DriverManufacturerName } else { "" }
            DriverModel        = if ($u.DriverModel)            { [string]$u.DriverModel }            else { "" }
            DriverProvider     = if ($u.DriverProvider)         { [string]$u.DriverProvider }         else { "" }
            DriverVersion      = if ($u.DriverVersion)          { [string]$u.DriverVersion }          else { "" }
            DriverVerDate      = if ($u.DriverVerDate)          { $u.DriverVerDate.ToString("yyyy-MM-dd") } else { "" }
            UpdateID           = [string]$u.Identity.UpdateID
            RevisionNumber     = [int]$u.Identity.RevisionNumber
            MaxDownloadSize    = [long]$u.MaxDownloadSize
            IsBeta             = [bool]$u.IsBeta
            BrowseOnly         = [bool]$u.BrowseOnly
        }
    }
    if ($list.Count -eq 0) { "[]" } else { $list | ConvertTo-Json -Depth 3 -Compress }
} catch {
    Write-Error "WU_ERROR: $($_.Exception.Message)"
    exit 1
}
"""


@dataclass
class WUDriverUpdate:
    title: str
    driver_class: str
    driver_manufacturer: str
    driver_model: str
    driver_provider: str
    driver_version: str
    driver_date: str
    update_id: str
    revision_number: int
    size_bytes: int
    is_beta: bool = False
    browse_only: bool = False


def check_windows_update_drivers(
    include_beta: bool = False, include_optional: bool = False,
) -> List[WUDriverUpdate]:
    """Return available updates; beta and optional updates require separate opt-ins."""
    data = run_json_scan(_PS_SEARCH, "Windows Update search", 120)
    updates = []
    for item in data:
        is_beta = bool(item.get("IsBeta", False))
        browse_only = bool(item.get("BrowseOnly", False))
        if (is_beta and not include_beta) or (browse_only and not include_optional):
            logger.debug("Skipped beta/optional update: %s", item.get("Title", ""))
            continue
        try:
            update_id = str(UUID(item["UpdateID"]))
            revision = int(item["RevisionNumber"])
            if revision < 0:
                raise ValueError("negative revision")
            updates.append(WUDriverUpdate(
                title=item.get("Title", ""),
                driver_class=item.get("DriverClass", ""),
                driver_manufacturer=item.get("DriverManufacturer", ""),
                driver_model=item.get("DriverModel", ""),
                driver_provider=item.get("DriverProvider", ""),
                driver_version=item.get("DriverVersion", ""),
                driver_date=item.get("DriverVerDate", ""),
                update_id=update_id,
                revision_number=revision,
                size_bytes=int(item.get("MaxDownloadSize", 0)),
                is_beta=is_beta,
                browse_only=browse_only,
            ))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ScanError(f"Windows Update returned an invalid update: {exc}") from exc
    return updates


@dataclass
class UpdateInstallResult:
    update_id: str
    title: str
    stage: str
    result_code: int
    hresult: int


@dataclass
class InstallationResult:
    updates: List[UpdateInstallResult] = field(default_factory=list)
    download_result_code: int = 0
    install_result_code: int = 0
    reboot_required: bool = False
    error: str = ""
    status_unknown: bool = False

    @property
    def success(self) -> bool:
        return (
            not self.error and not self.status_unknown
            and self.download_result_code == 2 and self.install_result_code == 2
            and bool(self.updates)
            and all(u.stage == "install" and u.result_code == 2 for u in self.updates)
        )


# Targets are encoded JSON, never interpolated as executable PowerShell text.
_PS_INSTALL = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$targets = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__TARGETS__')) | ConvertFrom-Json
$report = @{
    DownloadResultCode = 0; InstallResultCode = 0; RebootRequired = $false
    Updates = @(); Error = ""; StatusUnknown = $false
}
try {
    $s = New-Object -ComObject Microsoft.Update.Session
    $r = $s.CreateUpdateSearcher().Search("IsInstalled=0 and Type='Driver'")
    if ([int]$r.ResultCode -ne 2) { throw "Pre-install search did not fully succeed" }
    $col = New-Object -ComObject Microsoft.Update.UpdateColl
    foreach ($target in $targets) {
        $match = $null
        foreach ($u in $r.Updates) {
            if ($u.Identity.UpdateID -eq $target.UpdateID -and
                $u.Identity.RevisionNumber -eq $target.RevisionNumber) {
                $match = $u
                break
            }
        }
        if ($null -eq $match) {
            $report.Updates += @{
                UpdateID = $target.UpdateID; Title = $target.Title
                Stage = 'validation'; ResultCode = 0; HResult = 0
            }
        } else { $col.Add($match) | Out-Null }
    }
    # Never silently install a subset when the user's selection has changed.
    if ($col.Count -ne @($targets).Count) {
        throw "Selected updates are unavailable or their revisions changed. Rescan before installing."
    }
    $dl = $s.CreateUpdateDownloader()
    $dl.Updates = $col
    $download = $dl.Download()
    $report.DownloadResultCode = [int]$download.ResultCode
    $ready = New-Object -ComObject Microsoft.Update.UpdateColl
    for ($i = 0; $i -lt $col.Count; $i++) {
        $u = $col.Item($i)
        $dr = $download.GetUpdateResult($i)
        if ([int]$dr.ResultCode -eq 2 -and $u.IsDownloaded) {
            $ready.Add($u) | Out-Null
        } else {
            $report.Updates += @{
                UpdateID = $u.Identity.UpdateID; Title = $u.Title
                Stage = 'download'; ResultCode = [int]$dr.ResultCode; HResult = [int]$dr.HResult
            }
        }
    }
    if ($ready.Count -gt 0) {
        $inst = $s.CreateUpdateInstaller()
        $inst.Updates = $ready
        $report.StatusUnknown = $true
        $res = $inst.Install()
        $report.InstallResultCode = [int]$res.ResultCode
        $report.RebootRequired = [bool]$res.RebootRequired
        for ($i = 0; $i -lt $ready.Count; $i++) {
            $u = $ready.Item($i)
            $ir = $res.GetUpdateResult($i)
            $report.RebootRequired = $report.RebootRequired -or [bool]$ir.RebootRequired
            $report.Updates += @{
                UpdateID = $u.Identity.UpdateID; Title = $u.Title
                Stage = 'install'; ResultCode = [int]$ir.ResultCode; HResult = [int]$ir.HResult
            }
        }
        $report.StatusUnknown = $false
    }
} catch {
    $report.Error = $_.Exception.Message
}
ConvertTo-Json -InputObject $report -Depth 5 -Compress
"""


def install_wu_updates(updates: List[WUDriverUpdate]) -> InstallationResult:
    """Install the exact selected revisions and return per-update outcomes."""
    if not updates:
        return InstallationResult(error="No updates selected.")
    try:
        targets = {}
        for update in updates:
            update_id = str(UUID(update.update_id))
            revision = int(update.revision_number)
            if revision < 0:
                raise ValueError("negative revision")
            if update_id in targets and targets[update_id]["RevisionNumber"] != revision:
                raise ValueError("conflicting revisions for the same update")
            targets[update_id] = dict(
                UpdateID=update_id, RevisionNumber=revision, Title=update.title,
            )
    except (ValueError, TypeError, AttributeError) as exc:
        return InstallationResult(error=f"Invalid update selection: {exc}")

    encoded = base64.b64encode(json.dumps(list(targets.values())).encode("utf-8")).decode("ascii")
    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-NoProfile", "-Command",
             _PS_INSTALL.replace('__TARGETS__', encoded)],
            capture_output=True, text=True, timeout=600,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return InstallationResult(
                error=f"PowerShell failed: {result.stderr.strip()[:500]}", status_unknown=True,
            )
        data = json.loads(result.stdout)
        outcomes = [UpdateInstallResult(
            update_id=str(UUID(item["UpdateID"])), title=item["Title"],
            stage=item["Stage"], result_code=int(item["ResultCode"]),
            hresult=int(item["HResult"]),
        ) for item in data["Updates"]]
        report = InstallationResult(
            updates=outcomes, download_result_code=int(data["DownloadResultCode"]),
            install_result_code=int(data["InstallResultCode"]),
            reboot_required=data["RebootRequired"], error=data["Error"],
            status_unknown=data["StatusUnknown"],
        )
        if (not isinstance(report.reboot_required, bool)
                or not isinstance(report.status_unknown, bool)
                or not isinstance(report.error, str)):
            raise ValueError("invalid installation report")
        if not report.error and (
            len(outcomes) != len(targets)
            or {u.update_id for u in outcomes} != set(targets)
            or any(u.stage not in ("download", "install", "validation") for u in outcomes)
        ):
            raise ValueError("installation report does not match the selected updates")
        return report
    except subprocess.TimeoutExpired:
        return InstallationResult(
            error="Installation timed out after 600 seconds.", status_unknown=True,
        )
    except OSError as exc:
        return InstallationResult(error=f"Could not launch PowerShell: {exc}")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return InstallationResult(error=f"Invalid installation response: {exc}", status_unknown=True)
