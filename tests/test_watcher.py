import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from textwrap import dedent
from typing import Generator

import pytest
import pytest_asyncio
from watchfiles import watch

import tests
from pytest_discovery.argus import (
    DISCOVERY_FOLDER,
    WATCH_TASKS,
    argus,
    create_or_get_task,
)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    source_folder = Path(tests.__file__).parent / "project"
    shutil.copytree(src=source_folder, dst=tmp_path / "project")

    return tmp_path / "project"


class SimpleCollector:
    func_name = re.compile(r"def (test_.*)\(")

    def _test_names_from_file(self, test_file: Path) -> Generator[str, None, None]:
        with open(test_file) as fl:
            for ln in fl:
                if ln.startswith("def test_"):
                    mtch = self.func_name.match(ln)
                    if mtch:
                        yield f"{test_file.name}::{mtch.group(1)}"

    def collect(self, *, test_folder: Path, output_file: Path, repo_root: Path) -> None:
        with open(output_file, "w") as out_fl:
            for fl in test_folder.glob("test_*.py"):
                out_fl.write("\n".join(self._test_names_from_file(fl)))
                out_fl.write("\n")


def make_task(
    tasks_folder: Path,
    folder_to_watch: Path,
    pytest_folder: Path,
    repo_root: Path,
) -> Path:
    """Create a file with a task definition.

    To be picked up by Argus, which creates an async watchfiles task watching the 'watch' folder and
    running pytest collection on the 'action' folder on change.
    """
    dct = [
        {
            "watch": str(folder_to_watch),
            "action": str(pytest_folder),
            "repo_root": str(repo_root),
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
    yield
    WATCH_TASKS.clear()


@pytest.fixture
def tasks_folder(tmp_path: Path) -> Path:
    """Folder to watch for incoming watch tasks."""
    tasks_folder = tmp_path / "tasks"
    tasks_folder.mkdir()
    return tasks_folder


@pytest_asyncio.fixture(loop_scope="function")
async def argus_dummy_task(tasks_folder):
    watcher = asyncio.create_task(argus(tasks_folder, collector=SimpleCollector()))

    yield watcher

    watcher.cancel()
    try:
        await watcher
    except asyncio.CancelledError:
        pass


@pytest_asyncio.fixture(loop_scope="function")
async def argus_task(tasks_folder):
    watcher = asyncio.create_task(argus(tasks_folder))

    yield watcher

    watcher.cancel()
    try:
        await watcher
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio(scope="function")
async def test_nothing_watching(argus_dummy_task, tasks_folder: Path):

    await asyncio.sleep(0.2)
    assert WATCH_TASKS == {}


@pytest.mark.asyncio(scope="function")
async def test_add_watch_task(argus_task, tasks_folder: Path, project_root: Path):
    """e2e test including actual pytest collector."""

    make_task(
        folder_to_watch=project_root / "project" / "mod_1",
        pytest_folder=project_root / "tests" / "mod_1",
        tasks_folder=tasks_folder,
        repo_root=project_root,
    )

    await asyncio.sleep(0.5)

    [test_discoveries] = (project_root / DISCOVERY_FOLDER).glob("*.txt")
    discovered_tests = test_discoveries.read_text()
    assert discovered_tests == "tests/mod_1/test_mod_1.py::test_mod_1\n"


@pytest.mark.asyncio(scope="function")
async def test_new_test_added(argus_dummy_task, tasks_folder, project_root: Path):
    await asyncio.sleep(0.2)

    make_task(
        folder_to_watch=project_root / "tests" / "mod_1",
        pytest_folder=project_root / "tests" / "mod_1",
        tasks_folder=tasks_folder,
        repo_root=project_root,
    )
    await asyncio.sleep(0.5)

    [test_discoveries] = (project_root / DISCOVERY_FOLDER).glob("*.txt")
    discovered_tests = test_discoveries.read_text()
    assert discovered_tests == "test_mod_1.py::test_mod_1\n"

    new_test = dedent("""\
        def test_another_mod():...
        """)
    new_test_file = project_root / "tests" / "mod_1" / "test_another_mod.py"
    new_test_file.write_text(new_test)

    await asyncio.sleep(0.5)

    [test_discoveries] = (project_root / DISCOVERY_FOLDER).glob("*.txt")
    discovered_tests = test_discoveries.read_text()
    assert (
        discovered_tests
        == "test_another_mod.py::test_another_mod\ntest_mod_1.py::test_mod_1\n"
    )


@pytest.mark.asyncio
async def test_remove_task(argus_dummy_task, tasks_folder: Path, project_root: Path):

    await asyncio.sleep(0.2)

    tsk = create_or_get_task(
        watch_folder=tasks_folder,
        test_folder=project_root / "tests" / "mod_1",
        root_folder=project_root,
        collector=SimpleCollector(),
    )
    await asyncio.sleep(0.1)

    tsk.cancel()
    await tsk
    assert (
        tsk.done()
    )  # we have not cancelled it. we have used cancel to gracefully stop watching.

    all_tasks = asyncio.all_tasks()
    assert tsk not in all_tasks
