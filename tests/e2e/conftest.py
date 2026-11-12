from pathlib import Path
import socket
import os
import subprocess
import sys
import time

import httpx
import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


class TestServer:
    __test__ = False

    def __init__(self, runtime, without_model=False, varying_predictions=False, demo_profile=False, uit_available=False, fail_first_quick=False):
        self.runtime = runtime
        self.without_model = without_model
        self.varying_predictions = varying_predictions
        self.demo_profile = demo_profile
        self.uit_available = uit_available
        self.fail_first_quick = fail_first_quick
        self.control_dir = runtime.parent / (runtime.name + '-controls')
        self.control_dir.mkdir(parents=True, exist_ok=True)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.process = None
        self.log_path = self.runtime.parent / f"{self.runtime.name}-server.log"

    def start(self):
        args = [sys.executable, str(ROOT / "tests/e2e/serve_test_app.py"),
                "--runtime", str(self.runtime), "--port", str(self.port)]
        if self.without_model:
            args.append("--without-model")
        if self.varying_predictions:
            args.append("--varying-predictions")
        if self.demo_profile:
            args.append("--demo-profile")
            args.extend(["--quick-control", str(self.control_dir)])
        if self.uit_available:
            args.append("--uit-available")
        if self.fail_first_quick:
            args.append("--fail-first-quick")
        with self.log_path.open("ab") as log:
            self.process = subprocess.Popen(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        for _ in range(200):
            if self.process.poll() is not None:
                raise RuntimeError("E2E API exited before readiness: " +
                                   self.log_path.read_text(encoding="utf-8", errors="replace")[-4000:])
            try:
                if httpx.get(self.url + "/api/v1/health", timeout=0.5).is_success:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        self.stop()
        raise TimeoutError("E2E API did not become ready")

    def stop(self):
        if self.process is not None:
            if os.name == "nt" and self.process.poll() is None:
                subprocess.run(["taskkill.exe", "/PID", str(self.process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            elif self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None

    def restart(self):
        self.stop()
        self.start()


@pytest.fixture(scope="session")
def browser():
    if not (ROOT / "apps/web/dist/index.html").is_file():
        pytest.skip("Build frontend with npm ci && npm run build before E2E")
    with sync_playwright() as engine:
        instance = engine.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture
def app_server(tmp_path):
    server = TestServer(tmp_path / "e2e-runtime").start()
    yield server
    server.stop()


@pytest.fixture
def missing_server(tmp_path):
    server = TestServer(tmp_path / "missing-runtime", without_model=True).start()
    yield server
    server.stop()


@pytest.fixture
def varying_server(tmp_path):
    server = TestServer(tmp_path / "varying-runtime", varying_predictions=True).start()
    yield server
    server.stop()


@pytest.fixture
def demo_server(tmp_path):
    server = TestServer(tmp_path / "demo-runtime", demo_profile=True).start()
    yield server
    server.stop()


@pytest.fixture
def screenshot_dir(tmp_path):
    path = Path(os.environ.get("SENTENCE_DEMO_SCREENSHOT_DIR", str(tmp_path / "screenshots")))
    path.mkdir(parents=True, exist_ok=True)
    return path
