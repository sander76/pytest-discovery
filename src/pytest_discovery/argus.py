import asyncio
import json
import logging
from asyncio.tasks import Task
from pathlib import Path

from watchfiles import awatch

from pytest_discovery._collector import CanCollect, PytestCollector

test_folder = Path
watch_folder = Path
WATCH_TASKS: dict[tuple[test_folder, watch_folder], asyncio.Task] = {}

_logger = logging.getLogger(__name__)

DISCOVERY_FOLDER = ".pytest_discoveries"


async def _run_watcher(
    watch_folder: Path, test_folder: Path, repo_root: Path, collector: CanCollect
) -> None:
    """Watch a folder and run pytest collection on any change.

    Runs an initial pytest collection immediately, then re-runs on every
    detected filesystem change in watch_folder.

    Args:
        watch_folder: Directory to watch for filesystem changes.
        test_folder: Test folder to collect from on each change.
        repo_root: Root folder of the repository.
    """
    try:
        output_dir = repo_root / DISCOVERY_FOLDER
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f"{test_folder.name}.txt"

        _logger.debug(f"First test collect of {test_folder}")
        collector.collect(
            test_folder=test_folder, output_file=output_file, repo_root=repo_root
        )
        stop_event = asyncio.Event()

        async for _ in awatch(watch_folder, stop_event=stop_event):
            collector.collect(
                test_folder=test_folder, output_file=output_file, repo_root=repo_root
            )
    except asyncio.CancelledError:
        stop_event.set()


async def argus(watch_folder: Path, collector: CanCollect | None = None) -> None:
    """Watch a folder for incoming task files.

    Monitors watch_folder for .task files. Each task file contains a JSON
    list of watch definitions:

    ```json
    [
        {"watch": "<folder to watch>", "action": "<test folder to collect from>"}
    ]
    ```

    When a task file is **added**: runs an initial pytest collection on the
    target folder, then creates an async watcher (via watchfiles.awatch) that
    re-runs collection on every change. The asyncio.Task is stored in
    WATCH_TASKS, keyed by the watch folder path.

    When a task file is **deleted or modified**: cancels and removes the
    corresponding watcher tasks from WATCH_TASKS. On modification, new watchers
    are created from the updated file contents.

    Args:
        watch_folder: Directory to monitor for incoming .task files.
    """
    _logger.debug("Starting Argus")

    if collector is None:
        collector = PytestCollector()

    async for changes in awatch(watch_folder):
        _new_watch_tasks = {}
        for fl in watch_folder.glob("*.task"):
            _logger.debug("Change occurred in tasks folder. reloading them all")
            defs = json.loads(fl.read_text())
            _logger.debug(f"Tasks defined: {defs=!r}, {fl.name}")
            for task in defs:
                _logger.debug(f"processing task. {task=!r}")
                task_watch_folder = Path(task["watch"])
                task_test_folder = Path(task["action"])
                task_repo_root = Path(task["repo_root"])
                _new_watch_tasks[task_test_folder, task_watch_folder] = (
                    create_or_get_task(
                        watch_folder=task_watch_folder,
                        test_folder=task_test_folder,
                        root_folder=task_repo_root,
                        collector=collector,
                    )
                )
        update_tasks_collection(_new_watch_tasks)


def update_tasks_collection(
    new_watch_tasks: dict[tuple[Path, Path], Task[None]],
) -> None:
    for old_task in WATCH_TASKS:
        if old_task not in new_watch_tasks:
            to_be_cancelled = WATCH_TASKS.pop(old_task)
            to_be_cancelled.cancel()

    WATCH_TASKS.update(new_watch_tasks)


def create_or_get_task(
    watch_folder: Path, test_folder: Path, root_folder: Path, collector: CanCollect
) -> Task[None]:
    if (test_folder, watch_folder) in WATCH_TASKS:
        # _logger.debug("Task already exists. Returning existing one")
        return WATCH_TASKS[(test_folder, watch_folder)]

    _logger.debug(f"Creating a new watcher task. {watch_folder=!r}, {test_folder=!r}")
    return asyncio.create_task(
        _run_watcher(
            watch_folder=watch_folder,
            test_folder=test_folder,
            repo_root=root_folder,
            collector=collector,
        )
    )
