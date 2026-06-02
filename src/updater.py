"""Interactive update menu orchestration."""

import ctypes
import logging
import sys
from typing import List

from .display import console, print_updates_table, print_drivers_table
from .driver_detector import DriverInfo
from .windows_update import WUDriverUpdate, install_wu_updates
from .manufacturer_check import MfrDriverUpdate

logger = logging.getLogger(__name__)


def run_interactive_menu(
    drivers: List[DriverInfo],
    wu_updates: List[WUDriverUpdate],
    mfr_updates: List[MfrDriverUpdate],
    is_admin: bool,
) -> None:
    while True:
        print_updates_table(wu_updates, mfr_updates, drivers)
        _print_menu(wu_updates, mfr_updates, is_admin)

        choice = _prompt("Enter choice")

        if choice == "1":
            if wu_updates or mfr_updates:
                _install_all(wu_updates, mfr_updates, is_admin)
            else:
                console.print("[yellow]No updates to install.[/yellow]\n")

        elif choice == "2":
            if wu_updates or mfr_updates:
                _install_selected(wu_updates, mfr_updates, is_admin)
            else:
                console.print("[yellow]No updates available.[/yellow]\n")

        elif choice == "3":
            print_drivers_table(drivers)

        elif choice in ("4", "q", "Q", ""):
            console.print("[dim]Goodbye.[/dim]")
            break

        else:
            console.print("[red]Invalid choice — try again.[/red]\n")


# ---------------------------------------------------------------------------
# Menu helpers
# ---------------------------------------------------------------------------

def _print_menu(
    wu_updates: List[WUDriverUpdate],
    mfr_updates: List[MfrDriverUpdate],
    is_admin: bool,
) -> None:
    has_updates = bool(wu_updates or mfr_updates)
    console.print("[bold]Options:[/bold]")
    if has_updates:
        console.print("  [cyan][1][/cyan] Install all updates")
        console.print("  [cyan][2][/cyan] Select updates to install")
    console.print("  [cyan][3][/cyan] View all installed drivers")
    console.print("  [cyan][4][/cyan] Exit")
    if not is_admin and has_updates:
        console.print(
            "\n[yellow]⚠  Not running as Administrator — "
            "installation will fail without elevation.[/yellow]"
        )
    console.print()


def _prompt(label: str) -> str:
    try:
        return input(f"{label}: ").strip()
    except (KeyboardInterrupt, EOFError):
        return "4"


# ---------------------------------------------------------------------------
# Install flows
# ---------------------------------------------------------------------------

def _install_all(
    wu_updates: List[WUDriverUpdate],
    mfr_updates: List[MfrDriverUpdate],
    is_admin: bool,
) -> None:
    if wu_updates:
        if not _ensure_admin(is_admin):
            return
        console.print(f"[bold]Installing {len(wu_updates)} Windows Update driver(s)...[/bold]")
        with console.status("[bold green]Downloading and installing — please wait...", spinner="dots"):
            success, reboot = install_wu_updates([u.update_id for u in wu_updates])
        _report_wu_result(success, reboot)

    if mfr_updates:
        _show_mfr_links(mfr_updates)


def _install_selected(
    wu_updates: List[WUDriverUpdate],
    mfr_updates: List[MfrDriverUpdate],
    is_admin: bool,
) -> None:
    all_entries = [(u, "wu") for u in wu_updates] + [(u, "mfr") for u in mfr_updates]

    console.print("[bold]Select updates (comma-separated numbers, e.g. 1,3):[/bold]")
    for i, (u, kind) in enumerate(all_entries, 1):
        label = u.title if kind == "wu" else f"{u.device_name} ({u.manufacturer})"
        console.print(f"  [cyan][{i}][/cyan] {label}")
    console.print()

    raw = _prompt("Your selection (Enter to cancel)")
    if not raw:
        return

    try:
        indices = [int(x.strip()) - 1 for x in raw.split(",") if x.strip().isdigit()]
    except ValueError:
        console.print("[red]Invalid selection.[/red]\n")
        return

    selected_wu: List[WUDriverUpdate] = []
    selected_mfr: List[MfrDriverUpdate] = []

    for idx in indices:
        if idx < 0 or idx >= len(all_entries):
            console.print(f"[yellow]  Index {idx + 1} out of range — skipped.[/yellow]")
            continue
        update, kind = all_entries[idx]
        if kind == "wu":
            selected_wu.append(update)
        else:
            selected_mfr.append(update)

    if selected_wu:
        if not _ensure_admin(is_admin):
            return
        console.print(f"[bold]Installing {len(selected_wu)} update(s)...[/bold]")
        with console.status("[bold green]Downloading and installing...", spinner="dots"):
            success, reboot = install_wu_updates([u.update_id for u in selected_wu])
        _report_wu_result(success, reboot)

    if selected_mfr:
        _show_mfr_links(selected_mfr)

    console.print()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _ensure_admin(is_admin: bool) -> bool:
    if is_admin:
        return True
    console.print(
        "[red]Administrator privileges required.\n"
        "Re-launch the tool with: right-click → Run as administrator[/red]\n"
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
            "Run with --debug for details, or install manually via Windows Update.[/red]"
        )
    console.print()


def _show_mfr_links(updates: List[MfrDriverUpdate]) -> None:
    console.print("[bold]Manufacturer updates — manual download required:[/bold]")
    for u in updates:
        console.print(
            f"  [cyan]{u.device_name}[/cyan]  "
            f"[dim]{u.current_version}[/dim] → [green]{u.latest_version}[/green]  "
            f"[link={u.download_url}]{u.download_url}[/link]"
        )
    console.print()
