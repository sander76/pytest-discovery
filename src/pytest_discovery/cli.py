"""CLI for pytest-discovery."""

import argparse
import logging
import signal
import sys
from pathlib import Path
from threading import Event

import pytest
from watchfiles import PythonFilter, watch

OUTPUT_DIR_NAME = ".pytest_discoveries"

_logger = logging.getLogger(__name__)


class TestCollectorPlugin:
    """Pytest plugin to capture collected test items."""

    def __init__(self) -> None:
        self.collected: list[pytest.Item] = []

    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
        """Hook called after collection is complete."""
        self.collected = list(items)


def collect_tests(folder: Path) -> list[str]:
    collector = TestCollectorPlugin()

    pytest.main(
        [str(folder), "--collect-only", "-q"],
        plugins=[collector],
    )
    print(f"Pytest collection on {folder}")
    lines = [item.nodeid for item in collector.collected]
    return lines


def run_pytest_collect(folder: Path, output_file: Path) -> None:
    """Run pytest collection on the folder and write output to file.

    Args:
        folder: The folder to collect tests from.
        output_file: The file to write collected test node IDs to.
        venv_paths: Optional list of paths from local venv to add to sys.path.
    """
    _logger.debug(f"collecting tests. folder={folder}")
    lines = collect_tests(folder)
    output_file.write_text("\n".join(lines) + "\n")


def watch_folders(folders: list[Path], output_dir: Path, stop_event) -> None:
    """Watch a folder for changes and run pytest collect on each change."""

    folder_output_mapping = {fldr: output_dir / f"{fldr.name}.txt" for fldr in folders}

    # Run initial pytest collect
    for folder, output in folder_output_mapping.items():
        print(f"Running initial pytest collect. {folder.name}")
        run_pytest_collect(folder, output)

    _logger.info("Watching for changes...")
    for changes in watch(
        *(folders), stop_event=stop_event, watch_filter=PythonFilter()
    ):
        for change in changes:
            _logger.debug(f"Something changed: {change}")
            for folder in folders:
                if str(folder) in change[1]:
                    run_pytest_collect(folder, folder_output_mapping[folder])
                    break
    _logger.info("Stopped watching.")


class CliError(Exception): ...


def watch_command(folders: list[str]) -> int:
    """Execute the watch command.

    Args:
        folders: List of folder paths to watch.

    Returns:
        Exit code (0 for success, non-zero for error).
    """

    folders_to_watch = [Path(pth) for pth in folders]

    for folder in folders_to_watch:
        if not folder.exists():
            raise CliError(f"Folder does not exist. {folder} ")

    cwd = Path.cwd()

    output_dir = cwd / OUTPUT_DIR_NAME
    output_dir.mkdir(exist_ok=True)
    _logger.info(f"Output directory: {output_dir}")

    stop_evt = Event()

    # Set up signal handlers for graceful shutdown
    def signal_handler(signum: int, frame: object) -> None:
        print("\nShutting down watchers...")
        stop_evt.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("\nWatching for changes. Press Ctrl+C to stop.\n")
    try:
        watch_folders(folders_to_watch, output_dir, stop_evt)

    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)

    return 0


def main() -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="pytest-discovery",
        description="Discover and watch pytest tests.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Watch subcommand
    watch_parser = subparsers.add_parser(
        "watch",
        help="Watch folders for changes and run pytest collect.",
    )
    watch_parser.add_argument(
        "folders",
        nargs="+",
        help="Folders to watch for changes.",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "watch":
        return watch_command(args.folders)

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    sys.exit(main())
