"""Rich-based display components."""

from typing import List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from .driver_detector import DriverInfo
from .windows_update import WUDriverUpdate
from .manufacturer_check import MfrDriverUpdate

console = Console()


def print_banner() -> None:
    title = Text("  Windows Driver Update Tool  ", style="bold white on blue")
    sub = Text("  Detect and install driver updates  ", style="dim white on blue")
    content = Text.assemble(title, "\n", sub)
    console.print(Panel(content, box=box.DOUBLE, style="blue", padding=(0, 2)))
    console.print()


def print_drivers_table(drivers: List[DriverInfo]) -> None:
    table = Table(
        title=f"Installed Drivers ({len(drivers)})",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=False,
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Device", min_width=30)
    table.add_column("Version", min_width=14)
    table.add_column("Manufacturer", min_width=18)
    table.add_column("Class", min_width=14)

    for i, d in enumerate(drivers, 1):
        table.add_row(
            str(i),
            d.device_name or "[dim]Unknown[/dim]",
            d.driver_version or "[dim]—[/dim]",
            d.manufacturer or "[dim]—[/dim]",
            d.device_class or "[dim]—[/dim]",
        )

    console.print(table)
    console.print()


def print_updates_table(
    wu_updates: List[WUDriverUpdate],
    mfr_updates: List[MfrDriverUpdate],
    installed: List[DriverInfo],
) -> None:
    total = len(wu_updates) + len(mfr_updates)

    if total == 0:
        console.print(
            Panel("[bold green]All drivers are up to date![/bold green]",
                  box=box.ROUNDED, style="green")
        )
        console.print()
        return

    table = Table(
        title=f"Available Driver Updates — {total} found",
        box=box.ROUNDED,
        header_style="bold yellow",
        show_lines=False,
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Device / Update Title", min_width=38)
    table.add_column("Current", min_width=13)
    table.add_column("Available", min_width=13)
    table.add_column("Source", min_width=11)
    table.add_column("Size", min_width=8, justify="right")

    idx = 1
    installed_lower = {d.device_name.lower(): d for d in installed}

    for u in wu_updates:
        # Try to match update to an installed driver to show current version
        current_ver = "—"
        model_lower = u.driver_model.lower() if u.driver_model else ""
        if model_lower and model_lower in installed_lower:
            current_ver = installed_lower[model_lower].driver_version or "—"

        new_ver = u.driver_version or "[dim]see WU[/dim]"
        size_str = _fmt_size(u.size_bytes)

        table.add_row(
            str(idx),
            u.title,
            current_ver,
            f"[green]{new_ver}[/green]",
            "[cyan]Windows Update[/cyan]",
            size_str,
        )
        idx += 1

    for u in mfr_updates:
        table.add_row(
            str(idx),
            u.device_name,
            u.current_version,
            f"[green]{u.latest_version}[/green]",
            f"[magenta]{u.source}[/magenta]",
            "—",
        )
        idx += 1

    console.print(table)
    console.print()


def _fmt_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "—"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"
