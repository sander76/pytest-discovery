import logging
import os
from pathlib import Path
from typing import Protocol

import pytest

_logger = logging.getLogger(__name__)


class CanCollect(Protocol):
    def collect(
        self, *, test_folder: Path, output_file: Path, repo_root: Path
    ) -> None: ...


class TestCollectorPlugin:
    """Pytest plugin to capture collected test items."""

    def __init__(self) -> None:
        self.collected: list[pytest.Item] = []

    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
        """Hook called after collection is complete."""
        self.collected = list(items)


class PytestCollector:
    def collect_tests(self, folder: Path, repo_root: Path) -> list[str]:
        collector = TestCollectorPlugin()

        os.chdir(repo_root)

        pytest.main(
            [str(folder), "--collect-only", "-q"],
            plugins=[collector],
        )
        print(f"Pytest collection on {folder}")
        lines = [item.nodeid for item in collector.collected]
        return lines

    def collect(self, *, test_folder: Path, output_file: Path, repo_root: Path) -> None:
        """Run pytest collection on the folder and write output to file.

        Args:
            test_folder: The folder to collect tests from.
            output_file: The file to write collected test node IDs to.
            repo_root: Root folder of the repository.
        """
        _logger.info(f"collecting tests. folder={test_folder}")
        lines = self.collect_tests(folder=test_folder, repo_root=repo_root)
        output_file.write_text("\n".join(lines) + "\n")
