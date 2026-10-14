"""Run one foreground development server per Git worktree."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
from datetime import datetime, timezone

from dotenv import load_dotenv
from werkzeug.serving import make_server


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".dev"
STATE_FILE = STATE_DIR / "session.json"
LOCK_FILE = STATE_DIR / "run.lock"
SESSION_ID = hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
SOCKET_FILE = Path(f"/tmp/recipe-dev-{os.getuid()}-{SESSION_ID}.sock")
TAILSCALE_RANGE = ipaddress.ip_network("100.64.0.0/10")


def bind_host() -> str:
    requested = os.environ.get("DEV_HOST", "").strip()
    if requested:
        host = requested
    else:
        try:
            result = subprocess.run(
                ["tailscale", "ip", "-4"],
                capture_output=True,
                text=True,
                check=True,
                timeout=3,
            )
            host = result.stdout.strip().splitlines()[0]
        except (FileNotFoundError, IndexError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            host = "127.0.0.1"

    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise SystemExit(f"DEV_HOST must be a loopback or Tailscale IPv4 address: {host}") from exc
    if address.version != 4 or not (address.is_loopback or address in TAILSCALE_RANGE):
        raise SystemExit(f"Refusing to bind outside loopback or Tailscale: {host}")
    return host


def prepare_state() -> None:
    STATE_DIR.mkdir(mode=0o700, exist_ok=True)
    STATE_DIR.chmod(0o700)


def active_session(command: str) -> dict[str, object] | None:
    if not SOCKET_FILE.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(SOCKET_FILE))
            client.sendall(command.encode() + b"\n")
            reply = client.recv(65536)
    except (ConnectionError, OSError, TimeoutError):
        return None
    try:
        return json.loads(reply)
    except json.JSONDecodeError:
        return None


def remove_stale_state() -> None:
    for path in (SOCKET_FILE, STATE_FILE):
        if path.exists():
            if path.stat().st_uid != os.getuid():
                raise SystemExit(f"Refusing to remove a file owned by another user: {path}")
            path.unlink()


def run_server() -> int:
    prepare_state()
    with LOCK_FILE.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            session = active_session("status")
            location = session.get("url", "this worktree") if session else "this worktree"
            raise SystemExit(f"Development server already running at {location}")

        remove_stale_state()
        os.chdir(ROOT)
        sys.path.insert(0, str(ROOT))
        load_dotenv(ROOT / ".env", override=False)
        os.environ["FLASK_ENV"] = "development"
        os.environ["DATABASE_PATH"] = str(STATE_DIR / "recipes.db")
        os.environ.setdefault("AUTH_ENABLED", "false")

        from app import create_app

        host = bind_host()
        server = make_server(host, 0, create_app(), threaded=True)
        port = server.socket.getsockname()[1]
        session: dict[str, object] = {
            "worktree": str(ROOT),
            "pid": os.getpid(),
            "host": host,
            "port": port,
            "url": f"http://{host}:{port}",
            "database": str(STATE_DIR / "recipes.db"),
            "playwright_session": f"recipe-{SESSION_ID}",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as control:
            control.bind(str(SOCKET_FILE))
            SOCKET_FILE.chmod(0o600)
            control.listen(2)
            control.settimeout(1)
            STATE_FILE.write_text(json.dumps(session, indent=2) + "\n")
            STATE_FILE.chmod(0o600)

            worker = threading.Thread(target=server.serve_forever, name="dev-http")
            worker.start()

            def interrupted(_signum: int, _frame: object) -> None:
                raise KeyboardInterrupt

            signal.signal(signal.SIGTERM, interrupted)
            print(f"Dev URL: {session['url']}", flush=True)
            print(f"SQLite: {session['database']}", flush=True)
            print(f"Playwright session: {session['playwright_session']}", flush=True)
            print("Stop with: make dev-stop", flush=True)

            try:
                while worker.is_alive():
                    try:
                        connection, _ = control.accept()
                    except socket.timeout:
                        continue
                    with connection:
                        connection.settimeout(2)
                        command = connection.recv(128).strip()
                        if command == b"status":
                            connection.sendall(json.dumps(session).encode())
                        elif command == b"stop":
                            connection.sendall(json.dumps({"stopping": session["url"]}).encode())
                            break
            except KeyboardInterrupt:
                pass
            finally:
                server.shutdown()
                worker.join(timeout=5)
                server.server_close()
                remove_stale_state()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "status", "stop", "prune", "clean"))
    command = parser.parse_args().command
    if command == "start":
        return run_server()

    if command in {"prune", "clean"}:
        prepare_state()
        with LOCK_FILE.open("a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit("A development server still owns this worktree")
            remove_stale_state()
            if command == "clean":
                for suffix in ("", "-wal", "-shm", "-journal"):
                    database_file = STATE_DIR / f"recipes.db{suffix}"
                    if database_file.exists():
                        database_file.unlink()
        if command == "clean":
            print("Removed this worktree's development SQLite data and stale run metadata")
        else:
            print("Removed stale run metadata; SQLite data was retained")
        return 0

    session = active_session("status" if command == "status" else "stop")
    if session is not None:
        if command == "stop":
            print(f"Stopping {session['stopping']}")
        else:
            print(json.dumps(session, indent=2))
        return 0

    print("No running development server for this worktree")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
