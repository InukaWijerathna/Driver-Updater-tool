#!/usr/bin/env python3
"""Windows Driver Update Tool — entry point."""

import sys
import ctypes
import logging
from pathlib import Path

# Auto-install dependencies if missing
def _ensure_deps():
    try:
        import rich, requests  # noqa: F401
    except ImportError:
        import subprocess
        print("Installing required packages (rich, requests)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "rich", "requests"])
        print()

_ensure_deps()

sys.path.insert(0, str(Path(__file__).parent))

from src.display import console, print_banner
from src.driver_detector import get_installed_drivers
from src.windows_update import check_windows_update_drivers
from src.manufacturer_check import check_manufacturer_updates
from src.updater import run_interactive_menu


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def main() -> None:
    debug = "--debug" in sys.argv
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        format="%(levelname)s [%(name)s]: %(message)s",
    )

    print_banner()

    admin = is_admin()
    if not admin:
        console.print(
            "[yellow]Not running as Administrator — "
            "driver scanning works, but installing updates requires elevation.[/yellow]\n"
        )

    # 1. Enumerate installed drivers
    with console.status("[bold green]Scanning installed drivers...", spinner="dots"):
        drivers = get_installed_drivers()

    if not drivers:
        console.print(
            "[red]Failed to enumerate installed drivers.\n"
            "Make sure WMI is accessible (run as Administrator or check service status).[/red]"
        )
        sys.exit(1)

    console.print(f"[green]✓[/green] Found [bold]{len(drivers)}[/bold] installed drivers.\n")

    # 2. Check Windows Update
    with console.status(
        "[bold green]Checking Windows Update for driver updates "
        "[dim](may take up to 60 s)...[/dim]",
        spinner="dots",
    ):
        wu_updates = check_windows_update_drivers()

    if wu_updates:
        console.print(
            f"[green]✓[/green] Windows Update: "
            f"[bold]{len(wu_updates)}[/bold] driver update(s) available.\n"
        )
    else:
        console.print("[green]✓[/green] Windows Update: no pending driver updates.\n")

    # 3. Check manufacturer sites
    from src.manufacturer_check import _find_nvidia_display_driver  # noqa: PLC0415
    nvidia_gpu = _find_nvidia_display_driver(drivers)
    mfr_label = f"NVIDIA {nvidia_gpu.device_name}" if nvidia_gpu else "manufacturer sites"

    with console.status(
        f"[bold green]Checking {mfr_label} for updates...", spinner="dots"
    ):
        mfr_updates = check_manufacturer_updates(drivers)

    if mfr_updates:
        console.print(
            f"[green]✓[/green] Manufacturer check: "
            f"[bold]{len(mfr_updates)}[/bold] update(s) found.\n"
        )
    else:
        console.print("[green]✓[/green] Manufacturer check complete.\n")

    # 4. Interactive menu
    run_interactive_menu(drivers, wu_updates, mfr_updates, is_admin=admin)


if __name__ == "__main__":
    main()
