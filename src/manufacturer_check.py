"""
Manufacturer-specific driver info.

NVIDIA's DriverManualLookup API requires internal pfid values that change over
time and are not reliably obtainable without browser automation.  We therefore
detect the GPU, convert the current WMI version to NVIDIA short form, and
point the user to the official download page.  Windows Update (the primary
source) already offers NVIDIA driver updates when available.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

from .driver_detector import DriverInfo


@dataclass
class MfrDriverUpdate:
    device_name: str
    manufacturer: str
    current_version: str
    latest_version: str   # empty string when unknown
    download_url: str
    source: str
    note: str = ""


def _wmi_to_nvidia_version(wmi_ver: str) -> str:
    """Convert WMI 4-part version to NVIDIA short form.

    Formula: "31.0.15.3623" -> "536.23"
      v3 last digit + v4 first two digits + "." + v4 last two digits
    """
    parts = wmi_ver.split(".")
    if len(parts) < 4:
        return wmi_ver
    v3 = parts[2].zfill(2)
    v4 = parts[3].zfill(4)
    return f"{v3[-1]}{v4[:2]}.{v4[2:]}"


def _find_nvidia_display_driver(drivers: List[DriverInfo]) -> Optional[DriverInfo]:
    for d in drivers:
        if "NVIDIA" in d.manufacturer.upper() and d.device_class.casefold() == "display":
            return d
    for d in drivers:
        if "nvidia geforce" in d.device_name.casefold() or "nvidia quadro" in d.device_name.casefold():
            return d
    return None


def _find_amd_display_driver(drivers: List[DriverInfo]) -> Optional[DriverInfo]:
    for d in drivers:
        if d.device_class.casefold() == "display" and (
            "AMD" in d.manufacturer.upper() or
            "advanced micro" in d.manufacturer.casefold() or
            "radeon" in d.device_name.casefold()
        ):
            return d
    return None


def _find_intel_display_driver(drivers: List[DriverInfo]) -> Optional[DriverInfo]:
    for d in drivers:
        if d.device_class.casefold() == "display" and "intel" in d.manufacturer.casefold():
            return d
    return None


def check_manufacturer_updates(drivers: List[DriverInfo]) -> List[MfrDriverUpdate]:
    """
    Return known-GPU entries for display purposes.  'latest_version' is left
    empty because NVIDIA/AMD/Intel's public APIs require session tokens or
    internal product IDs that change without notice.  Windows Update already
    covers these GPUs reliably.
    """
    results: List[MfrDriverUpdate] = []

    nvidia = _find_nvidia_display_driver(drivers)
    if nvidia:
        current = _wmi_to_nvidia_version(nvidia.driver_version) if nvidia.driver_version else "—"
        results.append(MfrDriverUpdate(
            device_name=nvidia.device_name,
            manufacturer="NVIDIA",
            current_version=current,
            latest_version="",
            download_url="https://www.nvidia.com/Download/index.aspx",
            source="NVIDIA",
            note="Check Windows Update above or visit nvidia.com/drivers",
        ))

    amd = _find_amd_display_driver(drivers)
    if amd:
        results.append(MfrDriverUpdate(
            device_name=amd.device_name,
            manufacturer="AMD",
            current_version=amd.driver_version or "—",
            latest_version="",
            download_url="https://www.amd.com/en/support/download/drivers.html",
            source="AMD",
            note="Check Windows Update above or visit amd.com/support",
        ))

    intel_gpu = _find_intel_display_driver(drivers)
    if intel_gpu:
        results.append(MfrDriverUpdate(
            device_name=intel_gpu.device_name,
            manufacturer="Intel",
            current_version=intel_gpu.driver_version or "—",
            latest_version="",
            download_url="https://www.intel.com/content/www/us/en/download-center/home.html",
            source="Intel",
            note="Check Windows Update above or use Intel DSA",
        ))

    return results
