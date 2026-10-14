"""Create, inspect and safely finish explicitly managed development worktrees.

Uses only the Python standard library; run from a checkout that will be retained.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from collections.abc import Iterator
import fcntl
import json
from pathlib import Path
import re
import subprocess
import sys


class Refusal(RuntimeError):
    """An environment needs attention; leave it in place."""


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
    )
    if result.returncode:
        raise Refusal(result.stderr.strip() or result.stdout.strip())
    return result.stdout.rstrip("\n")


class Worktrees:
    def __init__(self, repo: Path):
        self.repo = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
        self.common = Path(git(self.repo, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
        # The first porcelain record is always the main working tree.
        self.main = Path(self.entries()[0]["worktree"]).resolve()
        self.parent = self.main.parent / f"{self.main.name}-worktrees"
        self.registry = self.common / "dev-worktrees"

    def entries(self) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        record: dict[str, str] = {}
        for field in git(self.repo, "worktree", "list", "--porcelain", "-z").split("\0"):
            if not field:
                if record:
                    records.append(record)
                    record = {}
            else:
                key, _, value = field.partition(" ")
                record[key] = value
        return records

    @contextmanager
    def locked(self) -> Iterator[None]:
        self.registry.mkdir(mode=0o700, exist_ok=True)
        with (self.registry / "registry.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def record_file(self, name: str) -> Path:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", name):
            raise Refusal("NAME must be 1–48 lowercase letters, digits or hyphens, starting with a letter/digit")
        return self.registry / f"{name}.json"

    def create(self, name: str, base: str = "HEAD") -> Path:
        record_file = self.record_file(name)
        target = self.parent / name
        if self.parent.is_symlink() or target.exists() or target.is_symlink() or record_file.exists():
            raise Refusal("Environment path or registry entry already exists (or parent is a symlink)")
        if git(self.repo, "status", "--porcelain", "--untracked-files=all"):
            raise Refusal("Source checkout has unfinished work; commit or preserve it before creating an environment")
        commit = git(self.repo, "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}")
        branch = f"codex/{name}"
        self.parent.mkdir(mode=0o700, exist_ok=True)
        git(self.repo, "worktree", "add", "-b", branch, str(target), commit)
        record_file.write_text(json.dumps({
            "name": name, "path": str(target), "branch": branch,
            "common": str(self.common), "created_from": commit,
        }, indent=2) + "\n")
        record_file.chmod(0o600)
        return target

    def target(self, name: str) -> tuple[Path, str]:
        record_file = self.record_file(name)
        if record_file.is_symlink():
            raise Refusal("Registry entry is a symlink")
        try:
            record = json.loads(record_file.read_text())
        except (FileNotFoundError, ValueError) as exc:
            raise Refusal(f"No valid managed environment named {name}") from exc
        target = self.parent / name
        branch = f"codex/{name}"
        if record.get("path") != str(target) or record.get("branch") != branch or record.get("common") != str(self.common):
            raise Refusal("Registry identity does not match this repository and environment")
        if self.parent.is_symlink() or target.is_symlink() or target == self.main or not target.is_dir():
            raise Refusal("Managed worktree path is missing or unsafe")
        entry = next((e for e in self.entries() if e.get("worktree") == str(target)), None)
        if entry is None or entry.get("branch") != f"refs/heads/{branch}" or "locked" in entry:
            raise Refusal("Worktree is unregistered, locked, detached, or on a different branch")
        common = Path(git(target, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
        if common != self.common or Path(git(target, "rev-parse", "--show-toplevel")).resolve() != target:
            raise Refusal("Worktree repository identity has changed")
        return target, branch

    def check_files(self, target: Path) -> None:
        if git(target, "status", "--porcelain", "--untracked-files=all"):
            raise Refusal("Uncommitted or untracked files remain; preserve them before finishing")
        # Git normally removes ignored files too. Only known disposable outputs
        # may be discarded; .env, legacy data/, and unknown ignored files block.
        ignored = git(target, "ls-files", "--others", "--ignored", "--exclude-standard", "-z")
        disposable_dirs = {".venv", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        disposable_state = {"run.lock", "session.json", "server.log", "control.sock",
                            "recipes.db", "recipes.db-wal", "recipes.db-shm", "recipes.db-journal"}
        for item in filter(None, ignored.split("\0")):
            path = Path(item)
            allowed = (path.parts[0] in disposable_dirs or "__pycache__" in path.parts
                       or (len(path.parts) == 2 and path.parts[0] == ".dev" and path.name in disposable_state))
            if not allowed:
                raise Refusal(f"Ignored file is not a disposable development output: {item}")
        for item in (".dev", ".venv"):
            if (target / item).is_symlink():
                raise Refusal(f"Refusing cleanup with symlinked development state: {item}")
        if (target / ".dev").is_dir():
            for path in (target / ".dev").iterdir():
                if path.is_symlink():
                    raise Refusal(f"Refusing cleanup with symlinked development state: {path.name}")

    def check_published(self, target: Path, refresh: bool = True) -> None:
        if refresh:
            # Fetch real branch tips, not a possibly stale local tracking claim.
            git(self.repo, "fetch", "--no-tags", "--prune", "origin",
                "+refs/heads/*:refs/remotes/origin/*")
        head = git(target, "rev-parse", "HEAD")
        refs = git(self.repo, "for-each-ref", "--format=%(refname)",
                   f"--contains={head}", "refs/remotes/origin/")
        if not any(ref != "refs/remotes/origin/HEAD" for ref in refs.splitlines()):
            raise Refusal("HEAD contains commits not preserved on an origin branch; push them before finishing")

    def check(self, name: str) -> tuple[Path, str]:
        target, branch = self.target(name)
        self.check_files(target)
        self.check_published(target)
        return target, branch

    @staticmethod
    def server_running(target: Path) -> bool:
        lock_path = target / ".dev/run.lock"
        if not lock_path.exists():
            return False
        with lock_path.open("a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
        return False

    def finish(self, name: str) -> str:
        target, branch = self.check(name)
        # A controller must survive the removal (including the invoking shell).
        if self.repo == target or Path.cwd().resolve().is_relative_to(target):
            raise Refusal("Run finish from a retained checkout, not inside the worktree being removed")
        if self.server_running(target):
            result = subprocess.run(
                [str(target / ".venv/bin/python"), str(target / "scripts/dev_session.py"), "stop"],
                cwd=target, check=False,
            )
            if result.returncode:
                raise Refusal("Server did not stop; worktree retained. Check permissions and dev-status")
        state_dir = target / ".dev"
        state_dir.mkdir(mode=0o700, exist_ok=True)
        with (state_dir / "run.lock").open("a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Refusal("Server still running; worktree retained") from exc
            # Recheck after shutdown; never use --force, and never delete branches.
            self.target(name)
            self.check_files(target)
            self.check_published(target, refresh=False)
            git(self.repo, "worktree", "remove", str(target))
        self.record_file(name).unlink()
        return branch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("name")
    create.add_argument("--base", default="HEAD")
    commands.add_parser("list")
    for command in ("check", "finish"):
        commands.add_parser(command).add_argument("name")
    args = parser.parse_args()
    try:
        manager = Worktrees(Path(__file__).resolve().parents[1])
        with manager.locked():
            if args.command == "create":
                target = manager.create(args.name, args.base)
                print(f"Created codex/{args.name} at {target}\nNext: cd {target} && make setup && make dev-start")
            elif args.command == "list":
                for record_file in sorted(manager.registry.glob("*.json")):
                    print(record_file.read_text().strip())
            elif args.command == "check":
                target, _ = manager.check(args.name)
                print(f"Safe to finish: {target}\nScratch database, logs, virtualenv and caches will be discarded.")
            else:
                branch = manager.finish(args.name)
                print(f"Removed environment {args.name}, including scratch data/logs/virtualenv. Retained branch {branch}.")
        return 0
    except (Refusal, OSError) as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
