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
from src.driver_detector import get_installed_drivers, get_problem_devices
from src.windows_update import check_windows_update_drivers
from src.manufacturer_check import check_manufacturer_updates
from src.updater import run_interactive_menu


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def main() -> None:
    args = set(sys.argv[1:])
    debug = "--debug" in args
    # Optional/beta driver updates are included by default — Windows' own
    # Optional Updates page (and tools like Driver Easy) count these too,
    # and excluding them was the main reason this tool reported fewer
    # available updates than other scanners. Pass --stable-only to match
    # the old behaviour.
    include_beta = "--stable-only" not in args
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

    # 2. Find devices with missing/broken drivers (these never show up in the
    #    "installed drivers" scan above — Driver Easy and friends report them
    #    separately, which is why they tend to show more "missing" entries).
    with console.status("[bold green]Looking for devices with missing or broken drivers...", spinner="dots"):
        problem_devices = get_problem_devices()

    if problem_devices:
        console.print(
            f"[yellow]⚠[/yellow]  [bold]{len(problem_devices)}[/bold] device(s) "
            f"have missing or broken drivers.\n"
        )
    else:
        console.print("[green]✓[/green] No devices with missing/broken drivers found.\n")

    # 3. Check Windows Update
    beta_label = " [yellow](+optional)[/yellow]" if include_beta else " [dim](stable only)[/dim]"
    with console.status(
        f"[bold green]Checking Windows Update for driver updates{beta_label}"
        " [dim](may take up to 60 s)...[/dim]",
        spinner="dots",
    ):
        wu_updates = check_windows_update_drivers(include_beta=include_beta)

    if wu_updates:
        console.print(
            f"[green]✓[/green] Windows Update: "
            f"[bold]{len(wu_updates)}[/bold] driver update(s) available.\n"
        )
    else:
        console.print("[green]✓[/green] Windows Update: no pending driver updates.\n")

    # 4. Detect manufacturer GPUs (NVIDIA, AMD, Intel)
    with console.status("[bold green]Detecting GPU drivers...", spinner="dots"):
        mfr_updates = check_manufacturer_updates(drivers)

    if mfr_updates:
        gpu_names = ", ".join(u.device_name for u in mfr_updates)
        console.print(f"[green]✓[/green] Detected GPU(s): [bold]{gpu_names}[/bold]\n")
    else:
        console.print("[green]✓[/green] No discrete GPU drivers found.\n")

    # 5. Interactive menu
    run_interactive_menu(drivers, wu_updates, mfr_updates, problem_devices, is_admin=admin)


if __name__ == "__main__":
    main()
