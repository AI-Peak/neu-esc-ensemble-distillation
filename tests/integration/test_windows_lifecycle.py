"""Exercise the actual user-facing Windows launcher and child-process cleanup."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell launchers")
def test_windows_start_idempotence_partial_recovery_restart_and_stop(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell or not (ROOT / ".venv/Scripts/python.exe").exists() or not (ROOT / "apps/web/dist/index.html").exists():
        pytest.skip("Run setup-local.ps1 before Windows lifecycle test")
    runtime = tmp_path / "local runtime with spaces"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}/api/v1"

    def script(name, *args):
        # Start-Process may inherit extra pipe handles on Windows. Plain files let
        # subprocess wait for the script itself instead of its background children.
        log_path = tmp_path / f"{name}-script.log"
        with log_path.open("w", encoding="utf-8") as log:
            result = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                     str(ROOT / f"scripts/{name}-local.ps1"), "-RuntimeDirectory", str(runtime), *args],
                                    cwd=ROOT, stdout=log, stderr=log, text=True, timeout=45)
        assert result.returncode == 0, log_path.read_text(encoding="utf-8", errors="replace")
        return result

    try:
        script("start", "-Port", str(port))
        assert httpx.get(url + "/health").json()["worker"]["alive"]
        before = json.loads((runtime / "local-processes.json").read_text(encoding="utf-8-sig"))
        script("start", "-Port", str(port))
        assert json.loads((runtime / "local-processes.json").read_text(encoding="utf-8-sig")) == before
        dataset = httpx.post(url + "/datasets", json={"name": "Lưu qua restart", "profile": "uit",
                                                       "items": [{"text": "Phản hồi qua script Windows."}]}).json()
        # Simulate one managed process dying. The launcher must stop the other before replacing both.
        subprocess.run(["taskkill.exe", "/PID", str(before["api"]["id"]), "/T", "/F"],
                       capture_output=True, check=True)
        script("start", "-Port", str(port))
        after = json.loads((runtime / "local-processes.json").read_text(encoding="utf-8-sig"))
        assert after["api"]["id"] != before["api"]["id"]
        assert after["worker"]["id"] != before["worker"]["id"]
        assert httpx.get(url + f"/datasets/{dataset['id']}").json()["item_count"] == 1
        assert httpx.get(url + "/health").json()["worker"]["alive"]
    finally:
        script("stop")
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0
