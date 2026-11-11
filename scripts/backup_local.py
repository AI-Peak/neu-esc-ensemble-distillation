"""Consistent, local-only backup/restore. Does not overwrite existing runtime data."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import zipfile


def backup(runtime: Path, output: Path) -> dict:
    runtime, output = runtime.resolve(), output.resolve()
    database = runtime / "workspace.sqlite3"
    if not database.is_file():
        raise ValueError(f"Không có database: {database}")
    if output.exists():
        raise ValueError("File backup đã tồn tại; chọn tên mới.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="feedback-backup-") as temp:
        copy_path = Path(temp) / "workspace.sqlite3"
        source = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
        target = sqlite3.connect(copy_path)
        try:
            source.backup(target)
            target.execute("PRAGMA foreign_keys=ON")
            # Upload previews and temporary quick-analysis never become backup history.
            target.execute("DELETE FROM datasets WHERE temporary=1")
            target.execute("DELETE FROM previews")
            target.execute("DELETE FROM worker_status")
            target.execute("DELETE FROM idempotency WHERE result_id NOT IN "
                           "(SELECT id FROM datasets UNION SELECT id FROM runs)")
            if target.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sensitivity_rate_limits'"
            ).fetchone():
                target.execute("DELETE FROM sensitivity_rate_limits")
            target.commit()
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Database backup integrity check failed")
            if target.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("Database backup foreign key check failed")
            target.execute("VACUUM")
            target.execute("PRAGMA journal_mode=DELETE")
        finally:
            source.close()
            target.close()
        manifest = {"format_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                    "database_sha256": hashlib.sha256(copy_path.read_bytes()).hexdigest(),
                    "quick_data_excluded": True, "models_included": False,
                    "exports_included": "SQLite immutable BLOB snapshots"}
        # Exclusive create prevents accidentally replacing a previous backup.
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(copy_path, "workspace.sqlite3")
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def restore(archive_path: Path, runtime: Path) -> dict:
    runtime = runtime.resolve()
    if runtime.exists():
        raise ValueError("Restore chỉ vào thư mục mới; không ghi đè runtime hiện có.")
    with zipfile.ZipFile(archive_path) as archive:
        if len(archive.namelist()) != 2 or set(archive.namelist()) != {"workspace.sqlite3", "manifest.json"}:
            raise ValueError("Backup format không hợp lệ")
        if archive.getinfo("manifest.json").file_size > 65536:
            raise ValueError("Manifest quá lớn")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format_version") != 1:
            raise ValueError("Backup version không hỗ trợ")
        # Stream only fixed known names. Never extract a user-controlled path.
        runtime.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="feedback-restore-", dir=runtime.parent) as temp:
            target = Path(temp) / "workspace.sqlite3"
            with archive.open("workspace.sqlite3") as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            if hashlib.sha256(target.read_bytes()).hexdigest() != manifest.get("database_sha256"):
                raise ValueError("Backup hash mismatch")
            connection = sqlite3.connect(target)
            try:
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup database bị lỗi")
                if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise ValueError("Backup foreign keys bị lỗi")
            finally:
                connection.close()
            # mkdir is exclusive; race cannot replace another runtime.
            runtime.mkdir()
            target.replace(runtime / "workspace.sqlite3")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    save = commands.add_parser("backup")
    save.add_argument("--runtime", type=Path, default=Path("runtime"))
    save.add_argument("--output", type=Path, required=True)
    load = commands.add_parser("restore")
    load.add_argument("--archive", type=Path, required=True)
    load.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = backup(args.runtime, args.output) if args.command == "backup" else restore(args.archive, args.runtime)
    except (ValueError, OSError, sqlite3.DatabaseError, zipfile.BadZipFile) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
