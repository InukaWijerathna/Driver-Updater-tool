"""Enumerate installed drivers via WMI/PowerShell."""

import subprocess
import json
import logging
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)

_PS_GET_DRIVERS = r"""
try {
    $drivers = Get-WmiObject Win32_PnPSignedDriver -ErrorAction Stop |
        Where-Object { $_.DeviceName -and $_.DeviceName.Trim() -ne "" } |
        Select-Object DeviceName, DriverVersion, Manufacturer, DeviceClass, HardWareID, InfName, DeviceID
    @($drivers) | ConvertTo-Json -Depth 2 -Compress
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
"""


@dataclass
class DriverInfo:
    device_name: str
    driver_version: str
    manufacturer: str
    device_class: str
    hardware_id: str
    inf_name: str
    device_id: str


def get_installed_drivers() -> List[DriverInfo]:
    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-NoProfile", "-Command", _PS_GET_DRIVERS],
            capture_output=True, text=True, timeout=90,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            logger.error("PowerShell WMI query failed: %s", result.stderr[:500])
            return []

        raw = result.stdout.strip()
        if not raw:
            return []

        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]

        drivers = []
        for item in data:
            if not item:
                continue
            drivers.append(DriverInfo(
                device_name=str(item.get("DeviceName") or ""),
                driver_version=str(item.get("DriverVersion") or ""),
                manufacturer=str(item.get("Manufacturer") or ""),
                device_class=str(item.get("DeviceClass") or ""),
                hardware_id=str(item.get("HardWareID") or ""),
                inf_name=str(item.get("InfName") or ""),
                device_id=str(item.get("DeviceID") or ""),
            ))

        return sorted(drivers, key=lambda d: (d.device_class.lower(), d.device_name.lower()))

    except subprocess.TimeoutExpired:
        logger.error("Timed out scanning installed drivers (>90s)")
        return []
    except json.JSONDecodeError as e:
        logger.error("Failed to parse driver list JSON: %s", e)
        return []
    except Exception as e:
        logger.error("Unexpected error scanning drivers: %s", e)
        return []
