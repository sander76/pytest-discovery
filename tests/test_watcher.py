import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

import tests
from pytest_discovery.argus import WATCH_TASKS, argus


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    source_folder = Path(tests.__file__).parent / "project"
    shutil.copytree(src=source_folder, dst=tmp_path)

    return tmp_path / "project"


def make_task(tasks_folder: Path, folder_to_watch: Path, pytest_folder: Path) -> Path:
    """Create a file with a task definition.

    To be picked up by Argus, which creates an async watchfiles task watching the 'watch' folder and
    running pytest collection on the 'action' folder on change.
    """
    dct = [
        {
            "watch": str(folder_to_watch),
            "action": str(pytest_folder),
        }
    ]
    task_file_name = tasks_folder / f"{folder_to_watch.name}.task"

    with open(task_file_name, "w") as fl:
        fl.write(json.dumps(dct))

    return task_file_name


@pytest.fixture(autouse=True)
def reset_watch_tasks():
    """Reset global watcher state before each test."""
    WATCH_TASKS.clear()
    _TASK_FILE_WATCHES.clear()
    yield
    WATCH_TASKS.clear()
    _TASK_FILE_WATCHES.clear()


@pytest.fixture
def tasks_folder(tmp_path: Path) -> Path:
    """Folder to watch for incoming watch tasks."""
    watch_folder = tmp_path / "tasks"
    watch_folder.mkdir()
    return watch_folder


@pytest.mark.asyncio
async def test_nothing_watching(tasks_folder: Path):
    watcher = asyncio.create_task(argus(tasks_folder))

    await asyncio.sleep(0.2)
    assert WATCH_TASKS == {}

    watcher.cancel()
    try:
        await watcher
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_add_watch_task(tasks_folder: Path, project_root: Path):
    watcher = asyncio.create_task(argus(tasks_folder))
    await asyncio.sleep(0.2)

    make_task(
        folder_to_watch=project_root / "project" / "mod_1",
        pytest_folder=project_root / "tests" / "mod_1",
        tasks_folder=tasks_folder,
    )

    await asyncio.sleep(0.2)

    watcher.cancel()

    try:
        await watcher
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_remove_task(
    task_watch_folder: Path, folder_to_watch: Path, tmp_path: Path
):
    watcher = asyncio.create_task(argus(task_watch_folder))
    await asyncio.sleep(0.2)

    task_file = make_task(
        folder_to_watch=folder_to_watch,
        target_folder=tmp_path,
        tasks_folder=task_watch_folder,
    )
    await asyncio.sleep(0.2)
    assert len(WATCH_TASKS) == 1

    os.remove(path=task_file)

    await asyncio.sleep(0.2)
    assert len(WATCH_TASKS) == 0

    watcher.cancel()
    try:
        await watcher
    except asyncio.CancelledError:
        pass
