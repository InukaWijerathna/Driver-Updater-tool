"""Rich-based display components."""

from typing import List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from .driver_detector import DriverInfo, ProblemDevice
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


def print_problem_devices_table(problems: List[ProblemDevice]) -> None:
    table = Table(
        title=f"Devices With Missing/Broken Drivers ({len(problems)})",
        box=box.ROUNDED,
        header_style="bold red",
        show_lines=False,
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Device", min_width=30)
    table.add_column("Class", min_width=14)
    table.add_column("Problem", min_width=30)

    for i, d in enumerate(problems, 1):
        table.add_row(
            str(i),
            d.device_name or "[dim]Unknown device[/dim]",
            d.device_class or "[dim]—[/dim]",
            f"[red]{d.description}[/red] [dim](code {d.error_code})[/dim]",
        )

    console.print(table)
    console.print()


def print_updates_table(
    wu_updates: List[WUDriverUpdate],
    mfr_info: List[MfrDriverUpdate],
    installed: List[DriverInfo],
    problem_devices: List[ProblemDevice],
) -> None:
    # ── Devices with missing/broken drivers ─────────────────────────────────
    if problem_devices:
        panel_lines = "\n".join(
            f"  • [bold]{d.device_name}[/bold] — {d.description} (code {d.error_code})"
            for d in problem_devices
        )
        console.print(
            Panel(
                f"[bold red]{len(problem_devices)} device(s) have missing or broken drivers:[/bold red]\n"
                f"{panel_lines}\n\n"
                "[dim]These won't appear in Windows Update — try the manufacturer's "
                "support site for the device/model, or option [4] for known GPU links.[/dim]",
                box=box.ROUNDED,
                style="red",
                title="Missing Drivers",
            )
        )
        console.print()

    # ── Windows Update updates ──────────────────────────────────────────────
    if wu_updates:
        wu_table = Table(
            title=f"Windows Update — {len(wu_updates)} driver update(s) available",
            box=box.ROUNDED,
            header_style="bold yellow",
            show_lines=False,
        )
        wu_table.add_column("#", style="dim", width=4, justify="right")
        wu_table.add_column("Update Title", min_width=40)
        wu_table.add_column("New Version", min_width=14)
        wu_table.add_column("Date", min_width=12)
        wu_table.add_column("Size", min_width=8, justify="right")

        installed_lower = {d.device_name.lower(): d for d in installed}

        for i, u in enumerate(wu_updates, 1):
            new_ver = u.driver_version or "[dim]—[/dim]"
            size_str = _fmt_size(u.size_bytes)
            wu_table.add_row(
                str(i),
                u.title,
                f"[green]{new_ver}[/green]",
                u.driver_date or "—",
                size_str,
            )

        console.print(wu_table)
        console.print()
    else:
        console.print(
            Panel(
                "[bold green]Windows Update: no pending driver updates.[/bold green]",
                box=box.ROUNDED,
                style="green",
            )
        )
        console.print()

    # ── Detected GPU / manufacturer info ───────────────────────────────────
    if mfr_info:
        gpu_table = Table(
            title="Detected GPU Drivers",
            box=box.ROUNDED,
            header_style="bold magenta",
            show_lines=False,
        )
        gpu_table.add_column("GPU / Device", min_width=30)
        gpu_table.add_column("Installed Version", min_width=16)
        gpu_table.add_column("Manufacturer", min_width=10)
        gpu_table.add_column("Note", min_width=30)

        for u in mfr_info:
            gpu_table.add_row(
                u.device_name,
                u.current_version,
                f"[magenta]{u.manufacturer}[/magenta]",
                f"[dim]{u.note}[/dim]",
            )

        console.print(gpu_table)
        console.print()


def _fmt_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "—"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"
