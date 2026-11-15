"""Enumerate installed drivers via WMI/PowerShell."""

import logging
from dataclasses import dataclass
from typing import List

from .powershell import ScanError, run_json_scan

logger = logging.getLogger(__name__)

_PS_GET_DRIVERS = r"""
try {
    $drivers = Get-WmiObject Win32_PnPSignedDriver -ErrorAction Stop |
        Where-Object { $_.DeviceName -and $_.DeviceName.Trim() -ne "" } |
        Select-Object DeviceName, DriverVersion, Manufacturer, DeviceClass, HardWareID, InfName, DeviceID
    ConvertTo-Json -InputObject @($drivers) -Depth 2 -Compress
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
    ConvertTo-Json -InputObject @($devices) -Depth 2 -Compress
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
    data = run_json_scan(_PS_GET_DRIVERS, "Installed driver scan", 90)
    drivers = [DriverInfo(
        device_name=str(item.get("DeviceName") or ""),
        driver_version=str(item.get("DriverVersion") or ""),
        manufacturer=str(item.get("Manufacturer") or ""),
        device_class=str(item.get("DeviceClass") or ""),
        hardware_id=str(item.get("HardWareID") or ""),
        inf_name=str(item.get("InfName") or ""),
        device_id=str(item.get("DeviceID") or ""),
    ) for item in data]
    return sorted(drivers, key=lambda d: (d.device_class.lower(), d.device_name.lower()))


def get_problem_devices() -> List[ProblemDevice]:
    """Return devices with configuration problems, including missing drivers."""
    data = run_json_scan(_PS_GET_PROBLEM_DEVICES, "Problem device scan", 90)
    devices = []
    try:
        for item in data:
            code = int(item.get("ConfigManagerErrorCode") or 0)
            devices.append(ProblemDevice(
                device_name=str(item.get("Name") or ""),
                device_class=str(item.get("PNPClass") or ""),
                error_code=code,
                description=_CM_PROBLEM_CODES.get(code, f"Device problem (code {code})"),
                device_id=str(item.get("DeviceID") or ""),
            ))
    except (TypeError, ValueError) as exc:
        raise ScanError(f"Problem device scan returned an invalid error code: {exc}") from exc
    return sorted(devices, key=lambda d: d.device_name.lower())
