"""Tests for the CLI."""

from pathlib import Path
from textwrap import dedent

import pytest

from pytest_discovery.cli import collect_tests


@pytest.fixture
def test_folder(tmp_path: Path):
    test_folder = tmp_path / "tests"
    test_folder.mkdir()
    test_file_1 = test_folder / "test_1.py"

    test_file_1.write_text(
        dedent("""\
        def test_one():...

        def test_two():...
        """)
    )
    return test_folder


def test_watch_folders():
    pass


def test_collect_tests(test_folder):

    collected = collect_tests(test_folder)

    assert collected == ["test_1.py::test_one", "test_1.py::test_two"]


def test_one_more_test(): ...
