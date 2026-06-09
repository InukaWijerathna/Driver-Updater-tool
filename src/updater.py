"""Interactive update menu orchestration."""

import logging
from typing import List

from .display import console, print_updates_table, print_drivers_table, print_problem_devices_table
from .driver_detector import DriverInfo, ProblemDevice
from .windows_update import WUDriverUpdate, install_wu_updates
from .manufacturer_check import MfrDriverUpdate

logger = logging.getLogger(__name__)


def run_interactive_menu(
    drivers: List[DriverInfo],
    wu_updates: List[WUDriverUpdate],
    mfr_info: List[MfrDriverUpdate],
    problem_devices: List[ProblemDevice],
    is_admin: bool,
) -> None:
    while True:
        print_updates_table(wu_updates, mfr_info, drivers, problem_devices)
        _print_menu(wu_updates, problem_devices, is_admin)

        choice = _prompt("Enter choice")

        if choice == "1" and wu_updates:
            _install_all_wu(wu_updates, is_admin)

        elif choice == "2" and wu_updates:
            _install_selected_wu(wu_updates, is_admin)

        elif choice == "3":
            print_drivers_table(drivers)

        elif choice == "4":
            _show_manufacturer_links(mfr_info)

        elif choice == "5" and problem_devices:
            print_problem_devices_table(problem_devices)

        elif choice in ("6", "q", "Q", ""):
            console.print("[dim]Goodbye.[/dim]")
            break

        else:
            console.print("[red]Invalid choice — try again.[/red]\n")


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

def _print_menu(wu_updates: List[WUDriverUpdate], problem_devices: List[ProblemDevice], is_admin: bool) -> None:
    console.print("[bold]Options:[/bold]")
    if wu_updates:
        console.print("  [cyan][1][/cyan] Install all Windows Update driver updates")
        console.print("  [cyan][2][/cyan] Select specific updates to install")
    console.print("  [cyan][3][/cyan] View all installed drivers")
    console.print("  [cyan][4][/cyan] Show manufacturer download links")
    if problem_devices:
        console.print(f"  [cyan][5][/cyan] View devices with missing/broken drivers ({len(problem_devices)})")
    console.print("  [cyan][6][/cyan] Exit")

    if not is_admin and wu_updates:
        console.print(
            "\n[yellow]⚠  Not running as Administrator — "
            "run run_admin.bat to enable update installation.[/yellow]"
        )
    console.print()


def _prompt(label: str) -> str:
    try:
        return input(f"{label}: ").strip()
    except (KeyboardInterrupt, EOFError):
        return "5"


# ---------------------------------------------------------------------------
# Install flows
# ---------------------------------------------------------------------------

def _install_all_wu(wu_updates: List[WUDriverUpdate], is_admin: bool) -> None:
    if not _ensure_admin(is_admin):
        return
    console.print(f"[bold]Installing {len(wu_updates)} driver update(s) via Windows Update...[/bold]")
    with console.status("[bold green]Downloading and installing — please wait...", spinner="dots"):
        success, reboot = install_wu_updates([u.update_id for u in wu_updates])
    _report_wu_result(success, reboot)


def _install_selected_wu(wu_updates: List[WUDriverUpdate], is_admin: bool) -> None:
    console.print("[bold]Select updates to install (comma-separated numbers):[/bold]")
    for i, u in enumerate(wu_updates, 1):
        ver = f"  [{u.driver_version}]" if u.driver_version else ""
        console.print(f"  [cyan][{i}][/cyan] {u.title}{ver}")
    console.print()

    raw = _prompt("Selection (Enter to cancel)")
    if not raw:
        return

    try:
        indices = [int(x.strip()) - 1 for x in raw.split(",") if x.strip().isdigit()]
    except ValueError:
        console.print("[red]Invalid selection.[/red]\n")
        return

    selected = []
    for idx in indices:
        if 0 <= idx < len(wu_updates):
            selected.append(wu_updates[idx])
        else:
            console.print(f"[yellow]  Index {idx + 1} out of range — skipped.[/yellow]")

    if not selected:
        console.print("[yellow]No valid updates selected.[/yellow]\n")
        return

    if not _ensure_admin(is_admin):
        return

    console.print(f"[bold]Installing {len(selected)} update(s)...[/bold]")
    with console.status("[bold green]Downloading and installing...", spinner="dots"):
        success, reboot = install_wu_updates([u.update_id for u in selected])
    _report_wu_result(success, reboot)


def _show_manufacturer_links(mfr_info: List[MfrDriverUpdate]) -> None:
    if not mfr_info:
        console.print("[dim]No GPUs detected.[/dim]\n")
        return
    console.print("[bold]Manufacturer download links:[/bold]")
    for u in mfr_info:
        console.print(
            f"  [cyan]{u.device_name}[/cyan]  "
            f"installed: [yellow]{u.current_version}[/yellow]\n"
            f"    {u.download_url}"
        )
    console.print()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _ensure_admin(is_admin: bool) -> bool:
    if is_admin:
        return True
    console.print(
        "[red]Administrator privileges required.\n"
        "  Double-click run_admin.bat to restart with elevation.[/red]\n"
    )
    return False


def _report_wu_result(success: bool, reboot: bool) -> None:
    if success:
        console.print("[green]✓ Installation successful.[/green]")
        if reboot:
            console.print(
                "[yellow]⚠  A system restart is required to complete the installation.[/yellow]"
            )
    else:
        console.print(
            "[red]✗ Installation failed. "
            "Try installing manually via Settings → Windows Update → Advanced options → "
            "Optional updates.[/red]"
        )
    console.print()
