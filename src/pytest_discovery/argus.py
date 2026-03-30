import asyncio
import json
from asyncio.tasks import Task
from pathlib import Path

from watchfiles import Change, awatch

from pytest_discovery.cli import OUTPUT_DIR_NAME, run_pytest_collect

test_folder = Path
watch_folder = Path
WATCH_TASKS: dict[tuple[test_folder, watch_folder], asyncio.Task] = {}


async def _run_watcher(
    watch_folder: Path, test_folder: Path, repo_root: Path
) -> None:
    """Watch a folder and run pytest collection on any change.

    Runs an initial pytest collection immediately, then re-runs on every
    detected filesystem change in watch_folder.

    Args:
        watch_folder: Directory to watch for filesystem changes.
        target_folder: Test folder to collect from on each change.
        repo_root: Root folder of the repository
    """
    output_dir = repo_root / OUTPUT_DIR_NAME
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{test_folder.name}.txt"

    run_pytest_collect(test_folder, output_file)

    async for _ in awatch(watch_folder):
        run_pytest_collect(test_folder, output_file)


async def argus(watch_folder: Path) -> None:
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
    async for changes in awatch(watch_folder):
        # load all json file and process them all.

        _new_watch_tasks={}
        for fl in watch_folder.glob("*.task"):
            defs = json.loads(fl.read_text())

            for task in defs:
                watch_folder = Path(task["watch"])
                test_folder = Path(task["action"])
                discovery_folder=Path(task[OUTPUT_DIR_NAME])
                _new_watch_tasks[test_folder,watch_folder]=create_or_get_task(watch_folder=watch_folder,test_folder=test_folder,root_folder=)
        # todo: replace WATCH_TASKS with _new_watch_tasks and cancel all tasks that only exist in the old WATCH_TASKS folder

def create_or_get_task(watch_folder: Path, test_folder: Path, root_folder) -> Task:
    if (test_folder, watch_folder) in WATCH_TASKS:
        return WATCH_TASKS[(test_folder, watch_folder)]
    return asyncio.create_task(
        _run_watcher(
            watch_folder=watch_folder, test_folder=test_folder, repo_root=root_folder
        )
    )
