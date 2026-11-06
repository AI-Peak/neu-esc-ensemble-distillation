"""Isolate even the production module's import-time default application.

Individual tests supply tmp_path runtimes, but importing services.api.main also
constructs its module-level app. Set this before test collection imports it so
collection cannot migrate, recover or clean a user's running workspace.
"""
import os
from pathlib import Path
import tempfile

import pytest


_previous_runtime = os.environ.get("FEEDBACK_RUNTIME")
_default_runtime = tempfile.TemporaryDirectory(prefix="feedback-pytest-default-")
_runtime_path = Path(_default_runtime.name).resolve()
assert _runtime_path.is_relative_to(Path(tempfile.gettempdir()).resolve())
os.environ["FEEDBACK_RUNTIME"] = str(_runtime_path)


@pytest.fixture(scope="session")
def isolated_default_runtime():
    return _runtime_path


def pytest_unconfigure(config):
    if _previous_runtime is None:
        os.environ.pop("FEEDBACK_RUNTIME", None)
    else:
        os.environ["FEEDBACK_RUNTIME"] = _previous_runtime
    _default_runtime.cleanup()
