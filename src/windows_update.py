"""Check and install driver updates via the Windows Update Agent COM API."""

import subprocess
import json
import logging
from dataclasses import dataclass
from typing import List, Tuple

logger = logging.getLogger(__name__)

_PS_SEARCH = r"""
try {
    $s = New-Object -ComObject Microsoft.Update.Session
    $r = $s.CreateUpdateSearcher().Search("IsInstalled=0 and Type='Driver'")
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


def check_windows_update_drivers() -> List[WUDriverUpdate]:
    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-NoProfile", "-Command", _PS_SEARCH],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            logger.warning("Windows Update search failed: %s", result.stderr[:300])
            return []

        raw = result.stdout.strip()
        if not raw:
            return []

        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]

        updates = []
        for item in data:
            if not item:
                continue
            updates.append(WUDriverUpdate(
                title=item.get("Title", ""),
                driver_class=item.get("DriverClass", ""),
                driver_manufacturer=item.get("DriverManufacturer", ""),
                driver_model=item.get("DriverModel", ""),
                driver_provider=item.get("DriverProvider", ""),
                driver_version=item.get("DriverVersion", ""),
                driver_date=item.get("DriverVerDate", ""),
                update_id=item.get("UpdateID", ""),
                revision_number=item.get("RevisionNumber", 0),
                size_bytes=item.get("MaxDownloadSize", 0),
            ))

        return updates

    except subprocess.TimeoutExpired:
        logger.error("Windows Update search timed out (>120s)")
        return []
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Windows Update response: %s", e)
        return []
    except Exception as e:
        logger.error("Unexpected error in Windows Update check: %s", e)
        return []


def install_wu_updates(update_ids: List[str]) -> Tuple[bool, bool]:
    """
    Download and install the given WU driver updates.
    Returns (success, reboot_required). Requires admin privileges.
    """
    if not update_ids:
        return False, False

    ids_csv = ",".join(update_ids)
    ps_cmd = f"""
$TargetIDs = '{ids_csv}' -split ','
try {{
    $s = New-Object -ComObject Microsoft.Update.Session
    $r = $s.CreateUpdateSearcher().Search("IsInstalled=0 and Type='Driver'")
    $col = New-Object -ComObject Microsoft.Update.UpdateColl
    foreach ($u in $r.Updates) {{
        if ($TargetIDs -contains $u.Identity.UpdateID) {{ $col.Add($u) | Out-Null }}
    }}
    if ($col.Count -eq 0) {{ Write-Output "NONE"; exit 0 }}
    $dl = $s.CreateUpdateDownloader(); $dl.Updates = $col
    Write-Output "DOWNLOADING:$($col.Count)"
    $dl.Download() | Out-Null
    $inst = $s.CreateUpdateInstaller(); $inst.Updates = $col
    Write-Output "INSTALLING:$($col.Count)"
    $res = $inst.Install()
    Write-Output "DONE:$($res.ResultCode):$($res.RebootRequired)"
}} catch {{
    Write-Error $_.Exception.Message; exit 1
}}
"""
    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=600,
            encoding="utf-8", errors="replace",
        )
        out = result.stdout
        # ResultCode 2 = Succeeded, 3 = SucceededWithErrors
        if "DONE:2:" in out or "DONE:3:" in out:
            reboot = ":True" in out.split("DONE:")[-1]
            return True, reboot
        logger.error("Install output: %s | stderr: %s", out[:300], result.stderr[:300])
        return False, False
    except subprocess.TimeoutExpired:
        logger.error("Driver installation timed out (>600s)")
        return False, False
    except Exception as e:
        logger.error("Error during WU installation: %s", e)
        return False, False
