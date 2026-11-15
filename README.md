# Windows Driver Update Tool

Scans your machine for outdated drivers, checks Windows Update for available updates, and installs them — all from the terminal.

## Features

- Enumerates all installed drivers via WMI (~100–200 on a typical machine)
- Queries the Windows Update Agent COM API for pending driver updates
- Excludes beta and optional-only updates by default (`--optional` and `--beta` enable each separately)
- Detects NVIDIA / AMD / Intel GPUs and shows current version + download link
- Interactive menu to install all updates or pick specific ones
- Requires elevation only for installation — scanning works without it

## Requirements

- Windows 10 or 11 (64-bit)
- Python 3.10+
- Internet access (for Windows Update queries)

## Setup

```
setup.bat
```

Or manually:

```
pip install -r requirements.txt
```

## Usage

**Scan only** (no admin needed):
```
python main.py
```

**Scan + install** (runs elevated):
```
run_admin.bat
```

**Flags:**

| Flag | Effect |
|------|--------|
| `--optional` | Include optional-only updates; beta updates remain excluded |
| `--beta` | Include beta updates; optional-only updates still require `--optional` |
| `--stable-only` | Explicit default filtering; cannot be combined with `--optional` or `--beta` |
| `--debug` | Show verbose logging (PowerShell calls, skipped updates, API errors) |

Use `python main.py --optional --beta` to include both categories. These flags
control availability filtering; a non-beta update is not a guarantee of stability.

## Validation

Run `python -m unittest discover -s tests -v`. Tests mock Windows Update and WMI;
they do not download or install drivers.

## How it works

1. **Driver scan** — `Get-WmiObject Win32_PnPSignedDriver` returns every signed driver with its version, manufacturer, and hardware ID.
2. **Windows Update check** — the Windows Update Agent COM API (`Microsoft.Update.Session`) searches for uninstalled driver-type updates. `IsBeta` and `BrowseOnly` flags are used to separate stable from beta updates.
3. **GPU detection** — NVIDIA, AMD, and Intel display drivers are identified and their WMI version strings are converted to the manufacturer's short form (e.g. `31.0.15.7602` → `576.02` for NVIDIA).
4. **Install** — the same WUA COM API downloads and installs selected updates. Per-update download and installation failures are reported, including HRESULT codes. A restart notice is shown if required, even after partial failure. Selected update IDs and revisions are rechecked before download. If installation status is unknown (for example after a timeout), the tool exits and asks you to rescan before retrying.

Scan failures are reported as errors and stop the session; they are never shown as an empty update list.

## Notes

- Installing drivers requires the tool to run as Administrator. Use `run_admin.bat` or right-click `main.py` → Run as administrator.
- NVIDIA's public driver lookup API no longer returns results without session tokens. The tool shows your current driver version and links directly to `nvidia.com/Download`.
- Windows Update already includes NVIDIA, Intel, and Realtek driver updates — it is the primary and most reliable source.

## Project structure

```
main.py                    Entry point
setup.bat                  Install dependencies
run_admin.bat              Launch elevated for installation
requirements.txt
src/
  driver_detector.py       WMI driver enumeration
  windows_update.py        Windows Update Agent check & install
  manufacturer_check.py    GPU detection (NVIDIA / AMD / Intel)
  display.py               Rich terminal tables
  updater.py               Interactive menu
```
