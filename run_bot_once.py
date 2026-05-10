from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
ENTRYPOINTS = ("start.py", "main.py")
SCRIPT_NAME = Path(__file__).name
LOG_DIR = REPO_ROOT / "logs"
CLI_LOG_PATH = LOG_DIR / "cli.log"
FOLLOW_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.25


def process_rows() -> list[tuple[int, str]]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        check=True,
        capture_output=True,
        text=True,
    )

    rows: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        if not command:
            continue
        try:
            rows.append((int(pid_text), command.strip()))
        except ValueError:
            continue
    return rows


def process_cwd(pid: int) -> Path | None:
    proc_cwd = Path(f"/proc/{pid}/cwd")
    if proc_cwd.exists():
        try:
            return proc_cwd.resolve()
        except OSError:
            return None

    try:
        result = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None

    for line in result.stdout.splitlines():
        if line.startswith("n"):
            return Path(line[1:]).resolve()
    return None


def command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def references_this_bot(pid: int, command: str) -> bool:
    tokens = command_tokens(command)
    token_names = {Path(token).name for token in tokens}
    ignored_scripts = {SCRIPT_NAME, "status.py", "stop.py"}
    if token_names & ignored_scripts:
        return False

    script_paths = {str((REPO_ROOT / entrypoint).resolve()) for entrypoint in ENTRYPOINTS}
    if any(token in script_paths for token in tokens):
        return True

    if not any(token_name in ENTRYPOINTS for token_name in token_names):
        return False

    cwd = process_cwd(pid)
    if cwd is None:
        return False

    return cwd == REPO_ROOT


def find_bot_processes() -> list[tuple[int, str]]:
    current_pid = os.getpid()
    return [
        (pid, command)
        for pid, command in process_rows()
        if pid != current_pid and references_this_bot(pid, command)
    ]


def start_bot_detached() -> int:
    LOG_DIR.mkdir(exist_ok=True)

    with Path(os.devnull).open("r") as stdin, Path(os.devnull).open("a") as devnull:
        process = subprocess.Popen(
            [sys.executable, str(REPO_ROOT / "start.py")],
            cwd=REPO_ROOT,
            stdin=stdin,
            stdout=devnull,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )

    return process.pid


def print_bot_processes(matches: list[tuple[int, str]]) -> None:
    for pid, command in matches:
        print(f"PID: {pid}")
        print(f"Command: {command}")


def follow_cli_log(seconds: float) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    CLI_LOG_PATH.touch(exist_ok=True)

    deadline = time.monotonic() + seconds
    position = CLI_LOG_PATH.stat().st_size
    print(f"\n=== CLI LOG ({CLI_LOG_PATH.relative_to(REPO_ROOT)}) ===")
    print(f"Printing new CLI log output for {seconds:g} seconds.")

    while time.monotonic() < deadline:
        with CLI_LOG_PATH.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(position)
            chunk = handle.read()
            position = handle.tell()

        if chunk:
            print(chunk, end="" if chunk.endswith("\n") else "\n")

        remaining = deadline - time.monotonic()
        time.sleep(min(POLL_INTERVAL_SECONDS, max(remaining, 0)))

    print("\nStopped printing CLI logs. Bot process was not stopped.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the trading bot if needed, print CLI logs briefly, then exit.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=FOLLOW_SECONDS,
        help="Number of seconds to print new CLI log output before exiting.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.seconds < 0:
        print("--seconds must be zero or greater", file=sys.stderr)
        return 2

    matches = find_bot_processes()
    if matches:
        print("Bot is already running. Reusing existing process.")
        print_bot_processes(matches)
    else:
        pid = start_bot_detached()
        print(f"Bot was stopped. Started detached bot process with PID: {pid}")

    follow_cli_log(args.seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
