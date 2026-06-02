"""Check NVIDIA (and future manufacturer) sites for newer driver versions."""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

from .driver_detector import DriverInfo

_NVIDIA_API = (
    "https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/"
    "AjaxDriverService.php"
)
# osID 57 = Windows 10/11 x64, languageCode 1033 = English
_NVIDIA_PARAMS_BASE = {"osID": 57, "languageCode": 1033, "isWHQL": 0, "ctk": 0}

# GPU model substring -> (product_series_id, product_family_id)
# Values correspond to NVIDIA's DriverManualLookup API parameters.
_NVIDIA_GPU_MAP: dict[str, Tuple[int, int]] = {
    # RTX 40 series (psid=127)
    "RTX 4090":         (127, 1003),
    "RTX 4080 SUPER":   (127, 1043),
    "RTX 4080":         (127, 1004),
    "RTX 4070 Ti SUPER":(127, 1057),
    "RTX 4070 Ti":      (127, 1006),
    "RTX 4070 SUPER":   (127, 1041),
    "RTX 4070":         (127, 1007),
    "RTX 4060 Ti":      (127, 1040),
    "RTX 4060":         (127, 1041),
    # RTX 30 series (psid=120)
    "RTX 3090 Ti":      (120, 1003),
    "RTX 3090":         (120, 964),
    "RTX 3080 Ti":      (120, 941),
    "RTX 3080":         (120, 902),
    "RTX 3070 Ti":      (120, 939),
    "RTX 3070":         (120, 933),
    "RTX 3060 Ti":      (120, 931),
    "RTX 3060":         (120, 928),
    "RTX 3050":         (120, 934),
    # RTX 20 series (psid=107)
    "RTX 2080 Ti":      (107, 800),
    "RTX 2080 SUPER":   (107, 818),
    "RTX 2080":         (107, 816),
    "RTX 2070 SUPER":   (107, 820),
    "RTX 2070":         (107, 819),
    "RTX 2060 SUPER":   (107, 828),
    "RTX 2060":         (107, 829),
    # GTX 16 series (psid=115)
    "GTX 1660 Ti":      (115, 877),
    "GTX 1660 SUPER":   (115, 879),
    "GTX 1660":         (115, 873),
    "GTX 1650 SUPER":   (115, 877),
    "GTX 1650":         (115, 876),
    # GTX 10 series (psid=98)
    "GTX 1080 Ti":      (98, 762),
    "GTX 1080":         (98, 771),
    "GTX 1070 Ti":      (98, 816),
    "GTX 1070":         (98, 772),
    "GTX 1060":         (98, 778),
    "GTX 1050 Ti":      (98, 781),
    "GTX 1050":         (98, 780),
    # GeForce MX series — mobile (Maxwell/Pascal/Turing)
    "MX550":            (120, 978),
    "MX450":            (115, 935),
    "MX350":            (115, 912),
    "MX330":            (115, 908),
    "MX250":            (98,  860),
    "MX230":            (98,  858),
    "MX150":            (98,  815),
    "MX130":            (86,  924),
    "MX110":            (86,  923),
    # GeForce 900M series laptops (psid=86)
    "940MX":            (86,  857),
    "930MX":            (86,  856),
    "920MX":            (86,  855),
}


@dataclass
class MfrDriverUpdate:
    device_name: str
    manufacturer: str
    current_version: str
    latest_version: str
    download_url: str
    source: str


# ---------------------------------------------------------------------------
# NVIDIA helpers
# ---------------------------------------------------------------------------

def _wmi_to_nvidia_version(wmi_ver: str) -> str:
    """Convert WMI 4-part version to NVIDIA short form.

    Example: "31.0.15.3623" -> "536.23"
    Formula: v3[-1] + v4[:2] + "." + v4[2:]  (v3/v4 zero-padded to 2/4 digits)
    """
    parts = wmi_ver.split(".")
    if len(parts) < 4:
        return wmi_ver
    v3 = parts[2].zfill(2)
    v4 = parts[3].zfill(4)
    return f"{v3[-1]}{v4[:2]}.{v4[2:]}"


def _find_nvidia_display_driver(drivers: List[DriverInfo]) -> Optional[DriverInfo]:
    for d in drivers:
        if "NVIDIA" in d.manufacturer.upper() and "Display" in d.device_class:
            return d
    for d in drivers:
        if "NVIDIA GeForce" in d.device_name or "NVIDIA Quadro" in d.device_name:
            return d
    return None


def _match_nvidia_ids(gpu_name: str) -> Optional[Tuple[int, int]]:
    upper = gpu_name.upper()
    for key in sorted(_NVIDIA_GPU_MAP, key=len, reverse=True):
        if key.upper() in upper:
            return _NVIDIA_GPU_MAP[key]
    return None


def _nvidia_latest_version(psid: int, pfid: int) -> Optional[str]:
    if not _HAS_REQUESTS:
        return None
    try:
        resp = _requests.get(
            _NVIDIA_API,
            params={"func": "DriverManualLookup", "psid": psid, "pfid": pfid,
                    **_NVIDIA_PARAMS_BASE},
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("Success") == 1:
            ids = data.get("IDS") or []
            if ids:
                return ids[0].get("downloadInfo", {}).get("Version")
    except Exception as e:
        logger.warning("NVIDIA API error: %s", e)
    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def check_manufacturer_updates(drivers: List[DriverInfo]) -> List[MfrDriverUpdate]:
    updates: List[MfrDriverUpdate] = []

    nvidia_drv = _find_nvidia_display_driver(drivers)
    if nvidia_drv:
        ids = _match_nvidia_ids(nvidia_drv.device_name)
        if ids:
            psid, pfid = ids
            latest = _nvidia_latest_version(psid, pfid)
            if latest:
                current = _wmi_to_nvidia_version(nvidia_drv.driver_version)
                if current != latest:
                    updates.append(MfrDriverUpdate(
                        device_name=nvidia_drv.device_name,
                        manufacturer="NVIDIA",
                        current_version=current,
                        latest_version=latest,
                        download_url="https://www.nvidia.com/Download/index.aspx",
                        source="NVIDIA",
                    ))
                # current == latest: no update needed, nothing to add
            # latest is None: API unreachable, fall through silently
        else:
            # GPU detected but not in map — Windows Update covers it
            logger.warning(
                "NVIDIA '%s' not in manufacturer map; Windows Update is the source",
                nvidia_drv.device_name,
            )

    return updates
