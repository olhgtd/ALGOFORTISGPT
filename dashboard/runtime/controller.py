"""Owned local lifecycle: OS locks, authenticated readiness, graceful shutdown.

The persistent control secret is protected by the per-user data-root ACL. It
is never a user session, never passed in a URL, and never sent to the frontend.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from uuid import UUID, uuid4

from .paths import RuntimePaths, RuntimeMode, atomic_json


@contextmanager
def file_lock(path: Path):
    with path.open("a+b") as stream:
        stream.seek(0)
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("AlgoFortis runtime is already starting or running") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


class RuntimeController:
    def __init__(self, paths: RuntimePaths, timeout: float = 30):
        self.paths, self.timeout = paths, timeout

    def _record(self):
        try:
            record = json.loads((self.paths.state / "backend.json").read_text(encoding="utf-8"))
            # Never follow an arbitrary URL from a state file.
            port = record["port"]
            if type(port) is not int or not 1 <= port <= 65535 or record["mode"] != self.paths.mode.value:
                return None
            if str(self.paths.root) != record["data_root"]:
                return None
            UUID(record["instance_id"])
            return record
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _call(self, record, action="status"):
        request = Request(f"http://127.0.0.1:{record['port']}/api/v1/runtime/control/{action}",
                          headers={
                              "X-AlgoFortis-Runtime": record["control_secret"],
                              "X-SentinelX-Runtime": record["control_secret"],
                              "Host": f"localhost:{record['port']}",
                          },
                          method="POST" if action == "stop" else "GET")
        with build_opener(ProxyHandler({})).open(request, timeout=1) as response:
            result = json.load(response)
        if result.get("instance_id") != record["instance_id"]:
            raise RuntimeError("Runtime instance identity mismatch")
        return result

    def status(self):
        record = self._record()
        if record:
            try:
                result = self._call(record)
                if result.get("state") == "READY":
                    return {"state": "READY", "url": f"http://localhost:{record['port']}/",
                            "pid": record["pid"], "instance_id": record["instance_id"]}
            except (OSError, ValueError, KeyError, RuntimeError):
                pass
        return {"state": "UNAVAILABLE"}

    def start(self):
        self.paths.prepare()
        with file_lock(self.paths.state / "controller.lock"):
            existing = self.status()
            if existing["state"] == "READY":
                return existing
            # A busy lifetime lock means a live server we must not replace.
            with file_lock(self.paths.state / "backend.lock"):
                pass
            command = [sys.executable, "-m", "dashboard.runtime.controller", "serve", "--mode", self.paths.mode.value,
                       "--data-root", str(self.paths.root), "--install-root", str(self.paths.install)]
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(("UPSTOX_", "SENTINELX_UPSTOX", "SENTINELX_TEST", "SENTINELX_AUTO_SEED", "ALGOFORTIS_TEST", "ALGOFORTIS_AUTO_SEED"))}
            env.update(
                ALGOFORTIS_APP_MODE=self.paths.mode.value,
                SENTINELX_APP_MODE=self.paths.mode.value,
                ALGOFORTIS_AUTO_SEED="0",
                SENTINELX_AUTO_SEED="0",
                ALGOFORTIS_DATA_ROOT=str(self.paths.imports),
                SENTINELX_DATA_ROOT=str(self.paths.imports),
                PYTHONPATH=str(self.paths.install),
            )
            expected_instance = str(uuid4())
            env["ALGOFORTIS_RUNTIME_INSTANCE"] = expected_instance
            env["SENTINELX_RUNTIME_INSTANCE"] = expected_instance
            with (self.paths.logs / "backend.log").open("ab") as log:
                proc = subprocess.Popen(command, cwd=self.paths.install, env=env, stdin=subprocess.DEVNULL,
                                        stdout=log, stderr=log,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError("Backend startup failed; see the application backend log")
                result = self.status()
                if result["state"] == "READY" and result["instance_id"] == expected_instance:
                    return result
                time.sleep(0.1)
            # This is the child handle created above, never a persisted/unverified PID.
            record = self._record()
            if record and record["instance_id"] == expected_instance:
                try:
                    self._call(record, "stop")
                except (OSError, ValueError, RuntimeError):
                    pass
            proc.terminate()
            proc.wait(timeout=5)
            raise RuntimeError("Backend readiness timed out")

    def stop(self):
        if not self.paths.state.exists():
            return {"state": "UNAVAILABLE"}
        with file_lock(self.paths.state / "controller.lock"):
            record = self._record()
            try:
                if record is None:
                    raise ValueError("No owned runtime record")
                self._call(record, "stop")
            except (OSError, ValueError, KeyError, RuntimeError):
                # Stale records must never authorize killing a process.
                with file_lock(self.paths.state / "backend.lock"):
                    return {"state": "UNAVAILABLE"}
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                try:
                    with file_lock(self.paths.state / "backend.lock"):
                        return {"state": "UNAVAILABLE"}
                except RuntimeError:
                    time.sleep(0.1)
            raise RuntimeError("Owned backend did not complete graceful shutdown")

    def restart(self):
        self.stop()
        return self.start()


def serve(paths):
    import uvicorn
    from fastapi import Request as WebRequest
    from fastapi.responses import JSONResponse
    from .application import create_runtime_app
    paths.prepare()
    with file_lock(paths.state / "backend.lock"):
        # Bind before publishing. The OS chooses a free loopback port atomically.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            network_path = paths.config / "runtime.json"
            configured_port = 0
            if network_path.exists():
                configured_port = json.loads(network_path.read_text(encoding="utf-8"))["port"]
                if type(configured_port) is not int or not 1 <= configured_port <= 65535:
                    raise ValueError("Invalid persisted runtime port")
            # Retain the origin over restarts. A port conflict fails closed;
            # it must never silently change an enrolled WebAuthn origin.
            listener.bind(("127.0.0.1", configured_port))
            listener.listen(128)
            port = listener.getsockname()[1]
            if not configured_port:
                atomic_json(network_path, {"version": 1, "port": port})
            origin = f"http://localhost:{port}"
            instance_id = os.environ.get("ALGOFORTIS_RUNTIME_INSTANCE", os.environ.get("SENTINELX_RUNTIME_INSTANCE", str(uuid4())))
            secret = secrets.token_urlsafe(48)
            app = create_runtime_app(paths, origin, instance_id)
            server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, timeout_graceful_shutdown=5))

            # Middleware precedes the static mount; shutdown cannot be reached
            # with a bearer session or browser-supplied Origin from another site.
            @app.middleware("http")
            async def runtime_control(request: WebRequest, call_next):
                if request.url.path.startswith("/api/v1/runtime/control/"):
                    header_secret = request.headers.get("x-algofortis-runtime") or request.headers.get("x-sentinelx-runtime") or ""
                    if (request.headers.get("origin") not in (None, origin)
                            or request.headers.get("host") != f"localhost:{port}"
                            or not secrets.compare_digest(header_secret, secret)):
                        return JSONResponse({"detail": "Runtime controller authorization required"}, status_code=403)
                    if request.url.path.endswith("/stop") and request.method == "POST":
                        asyncio.get_running_loop().call_soon(setattr, server, "should_exit", True)
                        return JSONResponse({"state": "STOPPING", "instance_id": instance_id})
                    if request.url.path.endswith("/status") and request.method == "GET":
                        try:
                            app.state.security_store._conn.execute("SELECT 1").fetchone()
                            app.state.governance_store._conn.execute("SELECT 1").fetchone()
                            app.state.security_status.public_status(app.state.owner.user_id)
                        except Exception:
                            return JSONResponse({"state": "UNAVAILABLE", "instance_id": instance_id}, status_code=503)
                        return JSONResponse({"state": "READY", "instance_id": instance_id})
                    return JSONResponse({"detail": "Unknown runtime control operation"}, status_code=404)
                return await call_next(request)

            record_path = paths.state / "backend.json"
            atomic_json(record_path, {"pid": os.getpid(), "port": port, "mode": paths.mode.value,
                                     "data_root": str(paths.root), "instance_id": instance_id, "control_secret": secret})
            try:
                server.run(sockets=[listener])
            finally:
                record_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="AlgoFortis local runtime controller")
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "serve"])
    parser.add_argument("--mode", choices=[mode.value for mode in RuntimeMode], default="PRODUCTION")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--install-root", type=Path)
    args = parser.parse_args()
    paths = RuntimePaths.resolve(args.mode, install_root=args.install_root, data_root=args.data_root)
    if args.action == "serve":
        serve(paths)
    else:
        print(json.dumps(getattr(RuntimeController(paths), args.action)()))


if __name__ == "__main__":
    main()
