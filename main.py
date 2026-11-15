#!/usr/bin/env python3
"""Windows Driver Update Tool — entry point."""

import sys
import argparse
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
from src.driver_detector import get_installed_drivers, get_problem_devices
from src.windows_update import check_windows_update_drivers
from src.powershell import ScanError
from src.manufacturer_check import check_manufacturer_updates
from src.updater import run_interactive_menu


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--debug", action="store_true", help="Show verbose logging")
    parser.add_argument("--optional", action="store_true", help="Include optional driver updates")
    parser.add_argument("--beta", action="store_true", help="Include beta driver updates")
    parser.add_argument("--stable-only", action="store_true", help="Explicitly use default filtering")
    args = parser.parse_args(argv)
    if args.stable_only and (args.optional or args.beta):
        parser.error("--stable-only cannot be combined with --optional or --beta")
    return args


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s [%(name)s]: %(message)s",
    )

    print_banner()

    admin = is_admin()
    if not admin:
        console.print(
            "[yellow]Not running as Administrator — "
            "driver scanning works, but installing updates requires elevation.[/yellow]\n"
        )

    # Stop on scan errors so the menu never presents an unknown result as empty.
    try:
        with console.status("[bold green]Scanning installed drivers...", spinner="dots"):
            drivers = get_installed_drivers()
        console.print(f"[green]✓[/green] Found [bold]{len(drivers)}[/bold] installed drivers.\n")

        with console.status("[bold green]Looking for devices with configuration problems...", spinner="dots"):
            problem_devices = get_problem_devices()
        if problem_devices:
            console.print(f"[yellow]⚠[/yellow] {len(problem_devices)} device(s) have configuration problems.\n")
        else:
            console.print("[green]✓[/green] No device configuration problems found.\n")

        with console.status(
            "[bold green]Checking Windows Update for driver updates"
            " [dim](may take up to 120 s)...[/dim]", spinner="dots",
        ):
            wu_updates = check_windows_update_drivers(
                include_beta=args.beta, include_optional=args.optional,
            )
        if wu_updates:
            console.print(f"[green]✓[/green] Windows Update: {len(wu_updates)} driver update(s) available.\n")
        else:
            console.print("[green]✓[/green] Windows Update: no pending driver updates matching the selected filters.\n")
    except ScanError as exc:
        console.print(f"Scan failed: {exc}", style="red", markup=False)
        sys.exit(1)

    # 4. Detect manufacturer GPUs (NVIDIA, AMD, Intel)
    with console.status("[bold green]Detecting GPU drivers...", spinner="dots"):
        mfr_updates = check_manufacturer_updates(drivers)

    if mfr_updates:
        gpu_names = ", ".join(u.device_name for u in mfr_updates)
        console.print(f"[green]✓[/green] Detected GPU(s): [bold]{gpu_names}[/bold]\n")
    else:
        console.print("[green]✓[/green] No supported GPU drivers found.\n")

    # 5. Interactive menu
    run_interactive_menu(drivers, wu_updates, mfr_updates, problem_devices, is_admin=admin)


if __name__ == "__main__":
    main()
