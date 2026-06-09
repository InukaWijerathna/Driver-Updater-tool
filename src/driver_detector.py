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

# ConfigManagerErrorCode != 0 marks a device with a driver problem (missing,
# disabled, failed to start, etc.) — these don't show up in Win32_PnPSignedDriver
# at all, which is why a plain "installed driver" scan misses them.
_PS_GET_PROBLEM_DEVICES = r"""
try {
    $devices = Get-WmiObject Win32_PNPEntity -ErrorAction Stop |
        Where-Object { $_.ConfigManagerErrorCode -ne 0 -and $_.Name } |
        Select-Object Name, ConfigManagerErrorCode, PNPClass, DeviceID
    @($devices) | ConvertTo-Json -Depth 2 -Compress
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
"""

# Common Win32_PNPEntity.ConfigManagerErrorCode values (CM_PROB_* in cfgmgr32.h).
_CM_PROBLEM_CODES = {
    1: "Device is not configured correctly",
    3: "Driver may be corrupted",
    10: "Device cannot start",
    12: "Not enough resources for this device",
    14: "Restart required to apply changes",
    18: "Reinstall the drivers for this device",
    19: "Registry may be corrupted",
    21: "Windows is removing this device",
    22: "Device is disabled",
    24: "Device is not present, not working, or missing drivers",
    28: "Drivers for this device are not installed",
    29: "Disabled by firmware",
    31: "Not working properly — drivers may not be installed",
    32: "Driver service for this device has been disabled",
    37: "Driver returned a failure status",
    38: "Driver could not be loaded — try restarting",
    39: "Driver may be missing or corrupted",
    40: "Driver service registry information is missing or invalid",
    41: "Best driver for this device could not be loaded",
    42: "Duplicate device detected",
    43: "Device reported problems",
    44: "Application or service has shut down this device",
    45: "Currently not connected",
    47: "Prepared for safe removal but not removed",
    48: "Driver for this device has been blocked",
    52: "Driver is not digitally signed",
}


@dataclass
class DriverInfo:
    device_name: str
    driver_version: str
    manufacturer: str
    device_class: str
    hardware_id: str
    inf_name: str
    device_id: str


@dataclass
class ProblemDevice:
    device_name: str
    device_class: str
    error_code: int
    description: str
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


def get_problem_devices() -> List[ProblemDevice]:
    """
    Devices Windows knows about but can't drive properly — missing, disabled,
    or failed drivers. These never appear in Win32_PnPSignedDriver, so a
    "what's installed" scan alone misses exactly the things tools like
    Driver Easy report as "missing drivers".
    """
    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-NoProfile", "-Command", _PS_GET_PROBLEM_DEVICES],
            capture_output=True, text=True, timeout=90,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            logger.error("PowerShell PNP entity query failed: %s", result.stderr[:500])
            return []

        raw = result.stdout.strip()
        if not raw:
            return []

        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]

        devices = []
        for item in data:
            if not item:
                continue
            code = int(item.get("ConfigManagerErrorCode") or 0)
            devices.append(ProblemDevice(
                device_name=str(item.get("Name") or ""),
                device_class=str(item.get("PNPClass") or ""),
                error_code=code,
                description=_CM_PROBLEM_CODES.get(code, f"Device problem (code {code})"),
                device_id=str(item.get("DeviceID") or ""),
            ))

        return sorted(devices, key=lambda d: d.device_name.lower())

    except subprocess.TimeoutExpired:
        logger.error("Timed out scanning problem devices (>90s)")
        return []
    except json.JSONDecodeError as e:
        logger.error("Failed to parse problem device list JSON: %s", e)
        return []
    except Exception as e:
        logger.error("Unexpected error scanning problem devices: %s", e)
        return []
