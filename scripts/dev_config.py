"""Private, project-scoped native-development configuration; stdlib only.

No shell evaluation, global exports, production loading, or secret-value output.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

PROJECT = "recipe-manager"
ALLOWED_KEYS = frozenset(["ANTHROPIC_API_KEY","AUTH_ENABLED","AUTH_USERNAME","AUTH_PASSWORD","SECRET_KEY","HONEYCOMB_API_KEY","OTEL_SERVICE_NAME","DEV_HOST","MCP_ENABLED"])


class ConfigError(ValueError):
    """Invalid config, with an error message that never includes values."""


def read_config() -> tuple[Path | None, dict[str, str]]:
    if os.environ.get("DEV_CONFIG_DISABLED") == "1":
        return None, {}
    explicit = os.environ.get("DEV_CONFIG_FILE")
    config_root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    path = Path(explicit).expanduser() if explicit else config_root / "project-dev" / f"{PROJECT}.json"
    if not path.is_absolute():
        raise ConfigError("DEV_CONFIG_FILE and XDG_CONFIG_HOME must be absolute paths")
    if path.is_symlink() or path.parent.is_symlink():
        raise ConfigError("Development config must not be symlinked")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if explicit:
            raise ConfigError("Explicit development config file is missing") from None
        return path, {}
    except OSError:
        raise ConfigError("Cannot open development config file") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ConfigError("Development config must be a regular, owner-only file (chmod 600)")
        parent = path.parent.stat()
        if parent.st_uid != os.getuid() or parent.st_mode & 0o077:
            raise ConfigError("Development config directory must be owner-only (chmod 700)")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            fd = -1
            raw = handle.read(65537)
        if len(raw) > 65536:
            raise ConfigError("Development config is too large")
        try:
            values = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ConfigError("Development config must contain valid JSON") from None
        if not isinstance(values, dict) or any(
            key not in ALLOWED_KEYS or not isinstance(value, str) or "\0" in value
            for key, value in values.items()
        ):
            raise ConfigError("Development config must map supported variable names to strings")
        return path, values
    except UnicodeError:
        raise ConfigError("Development config must be UTF-8 JSON") from None
    finally:
        if fd >= 0:
            os.close(fd)


def load_config() -> tuple[Path | None, list[str]]:
    path, values = read_config()
    # Validate the whole file before changing any environment variables.
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return path, sorted(values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "run"), nargs="?", default="check")
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        path, keys = load_config()
        if args.command == "check":
            print(f"Project: {PROJECT}")
            print(f"Config: {path if path else 'disabled'}")
            print("Configured names: " + (", ".join(keys) or "(none)"))
            print("Supported names: " + ", ".join(sorted(ALLOWED_KEYS)))
        else:
            command = args.args[1:] if args.args[:1] == ["--"] else args.args
            if not command:
                raise ConfigError("run requires a command after --")
            os.execvpe(command[0], command, os.environ)
        return 0
    except (ConfigError, OSError) as exc:
        # OS command errors may include arbitrary paths, never config values.
        print(f"Development config refused: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
