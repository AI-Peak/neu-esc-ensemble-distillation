"""Collection must never initialize the live workspace as an import side effect."""
import os

from services.api.main import app
from services.storage.db import ROOT


def test_module_level_app_uses_session_temporary_runtime(isolated_default_runtime):
    assert app.state.store.runtime == isolated_default_runtime
    assert app.state.store.runtime != (ROOT / "runtime").resolve()
    assert os.environ["FEEDBACK_RUNTIME"] == str(isolated_default_runtime)
    assert app.state.store.path.is_file()
