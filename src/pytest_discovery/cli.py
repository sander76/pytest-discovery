"""CLI for pytest-discovery."""

import argparse
import multiprocessing
import signal
import subprocess
import sys
from pathlib import Path

from watchfiles import watch, PythonFilter


OUTPUT_DIR_NAME = ".pytest_discoveries"


def run_pytest_collect(folder: Path, output_file: Path) -> None:
    """Run pytest --collect-only on the folder and write output to file."""
    try:
        result = subprocess.run(
            ["uv", "run", "pytest", str(folder), "--collect-only", "-q"],
            capture_output=True,
            text=True,
        )
        output_file.write_text(result.stdout + result.stderr)
    except Exception as e:
        output_file.write_text(f"Error running pytest: {e}\n")


def watch_folder(folder: str, output_dir: str) -> None:
    """Watch a folder for changes and run pytest collect on each change.

    This function is meant to run in a separate process.
    """
    folder_path = Path(folder).resolve()
    output_dir_path = Path(output_dir)
    output_file = output_dir_path / f"{folder_path.name}.txt"

    # Run initial pytest collect
    print(f"[{folder_path.name}] Running initial pytest collect...")
    run_pytest_collect(folder_path, output_file)
    print(f"[{folder_path.name}] Output written to {output_file}")

    # Watch for changes
    print(f"[{folder_path.name}] Watching for changes...")
    for changes in watch(folder_path, watch_filter=PythonFilter()):
        changed_files = [str(change[1]) for change in changes]
        print(f"[{folder_path.name}] Detected changes: {changed_files}")
        run_pytest_collect(folder_path, output_file)
        print(f"[{folder_path.name}] Output updated in {output_file}")


def watch_command(folders: list[str]) -> int:
    """Execute the watch command.

    Args:
        folders: List of folder paths to watch.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    # Validate that all folders exist
    resolved_folders: list[Path] = []
    for folder in folders:
        folder_path = Path(folder).resolve()
        if not folder_path.exists():
            print(f"Error: Folder does not exist: {folder}", file=sys.stderr)
            return 1
        if not folder_path.is_dir():
            print(f"Error: Not a directory: {folder}", file=sys.stderr)
            return 1
        resolved_folders.append(folder_path)

    # Check for duplicate folder names (could cause output file collisions)
    folder_names = [f.name for f in resolved_folders]
    if len(folder_names) != len(set(folder_names)):
        print(
            "Warning: Duplicate folder names detected. Output files may be overwritten.",
            file=sys.stderr,
        )

    # Create output directory
    output_dir = Path.cwd() / OUTPUT_DIR_NAME
    output_dir.mkdir(exist_ok=True)
    print(f"Output directory: {output_dir}")

    # Start a watcher process for each folder
    processes: list[multiprocessing.Process] = []
    for folder_path in resolved_folders:
        process = multiprocessing.Process(
            target=watch_folder,
            args=(str(folder_path), str(output_dir)),
            name=f"{Path.cwd().name}-watcher-{folder_path.name}",
            daemon=True,
        )
        process.start()
        processes.append(process)
        print(f"Started watcher for: {folder_path}")

    # Set up signal handlers for graceful shutdown
    def signal_handler(signum: int, frame: object) -> None:
        print("\nShutting down watchers...")
        for proc in processes:
            proc.terminate()
        for proc in processes:
            proc.join(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Wait for all processes (they run indefinitely until interrupted)
    print("\nWatching for changes. Press Ctrl+C to stop.\n")
    try:
        for process in processes:
            process.join()
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
    sys.exit(main())
