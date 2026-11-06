from pathlib import Path
import sqlite3
import zipfile

import pytest

from scripts.backup_local import backup, restore
from services.storage.db import Store


def test_backup_sanitizes_quick_uploads_and_restores_snapshot(tmp_path: Path):
    runtime = tmp_path / "source"
    store = Store(runtime)
    with store.tx() as connection:
        base = ("2026-11-06T00:00:00Z",) * 2
        connection.execute("INSERT INTO datasets VALUES(?,?,?,?,?,?,?,?)", ("saved", "Có dấu", "neu", "neu-v1", *base, 0, None))
        connection.execute("INSERT INTO datasets VALUES(?,?,?,?,?,?,?,?)", ("quick", "Tạm", "neu", "neu-v1", *base, 1, 1e12))
        connection.execute("INSERT INTO previews VALUES(?,?,?)", ("upload", "secret preview text", 1e12))
    archive = tmp_path / "backup.zip"
    result = backup(runtime, archive)
    assert result["quick_data_excluded"]
    assert not result["models_included"]
    restored = tmp_path / "restored"
    restore(archive, restored)
    connection = sqlite3.connect(restored / "workspace.sqlite3")
    try:
        assert connection.execute("SELECT name FROM datasets").fetchall() == [("Có dấu",)]
        assert connection.execute("SELECT count(*) FROM previews").fetchone()[0] == 0
    finally:
        connection.close()
    with pytest.raises(ValueError, match="mới"):
        restore(archive, restored)
    with pytest.raises(ValueError, match="tồn tại"):
        backup(runtime, archive)
    assert store.datasets()[0]["id"] == "saved"


def test_restore_rejects_archive_paths(tmp_path):
    archive = tmp_path / "malformed.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("../outside", "bad")
        stream.writestr("manifest.json", "{}")
    with pytest.raises(ValueError, match="format"):
        restore(archive, tmp_path / "target")
    assert not (tmp_path / "outside").exists()
