"""Shared PowerShell JSON scan handling."""

import json
import subprocess


class ScanError(RuntimeError):
    """A scan failed; its result must not be treated as an empty inventory."""


def run_json_scan(script: str, label: str, timeout: int) -> list[dict]:
    prefix = (
        "$ErrorActionPreference = 'Stop'; "
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
    )
    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-NoProfile", "-Command", prefix + script],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            raise ScanError(f"{label} failed: {result.stderr.strip()[:500] or 'PowerShell error'}")
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise ScanError(f"{label} returned an invalid result structure")
        return data
    except subprocess.TimeoutExpired as exc:
        raise ScanError(f"{label} timed out after {timeout} seconds") from exc
    except (ValueError, OSError) as exc:
        raise ScanError(f"{label} failed: {exc}") from exc
