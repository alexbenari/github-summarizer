import json
import importlib.util
import os
import socket
import subprocess
import sys
import time
from collections.abc import Generator
from urllib import error, request

import pytest


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(base_url: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.time() + timeout_seconds
    target_urls = [f"{base_url}/openapi.json", f"{base_url}/docs"]

    while time.time() < deadline:
        for target_url in target_urls:
            try:
                with request.urlopen(target_url, timeout=1.0) as response:
                    if response.status == 200:
                        return
            except error.HTTPError as exc:
                if 100 <= exc.code <= 599:
                    return
            except (error.URLError, TimeoutError, OSError):
                continue
        time.sleep(0.1)

    raise TimeoutError(f"Timed out waiting for service readiness at {target_urls[0]} or {target_urls[1]}")


@pytest.fixture(scope="session")
def live_server() -> Generator[str, None, None]:
    if importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn is not installed. Run `pip install -r requirements.txt`.")

    port = _get_free_port()
    base_url = f"http://127.0.0.1:{port}"
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "NEBIUS_API_KEY": os.environ.get("NEBIUS_API_KEY", "test-key")},
    )

    try:
        _wait_until_ready(base_url=base_url, timeout_seconds=10.0)
        yield base_url
    except Exception:
        output = ""
        process.terminate()
        try:
            captured_stdout, _ = process.communicate(timeout=3)
            output = captured_stdout or ""
        except Exception:
            try:
                process.kill()
                captured_stdout, _ = process.communicate(timeout=3)
                output = captured_stdout or ""
            except Exception:
                output = ""
        message = "Uvicorn failed to start."
        if output:
            message = f"{message}\n\nCaptured output:\n{output}"
        raise RuntimeError(message) from None
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture
def post_json():
    def _post_json(url: str, payload: dict[str, str]) -> tuple[int, dict]:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=5.0) as response:
                body = response.read().decode("utf-8")
                return response.status, json.loads(body)
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            return exc.code, json.loads(body)

    return _post_json
