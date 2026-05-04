from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import cast

from cisco_conf_helper.backup import backup_running_config
from cisco_conf_helper.config import load_config
from cisco_conf_helper.models import AppConfig, CliConfig
from cisco_conf_helper.vcs import auto_commit

DEFAULT_CONFIG_PATH = Path("cisco-conf-helper.toml")


class CliArgs(argparse.Namespace):
    config: Path
    device_type: str | None
    password: str | None
    secret: str | None
    port: str | None
    baudrate: int | None
    bytesize: int | None
    parity: str | None
    stopbits: int | None
    output_dir: Path | None
    command: str | None
    fallback_hostname: str | None
    min_expected_bytes: int | None
    retry_on_low_bytes: bool | None
    git_enabled: bool | None
    git_auto_commit: bool | None
    git_commit_message: str | None
    git_commit_body: str | None
    jj_enabled: bool | None
    jj_auto_commit: bool | None
    jj_commit_message: str | None
    jj_commit_body: str | None
    loop: bool | None
    count: int | None
    stop_on_error: bool | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Back up Cisco configs over a serial connection.")
    _ = parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)

    _ = parser.add_argument("--device-type")
    _ = parser.add_argument("--password")
    _ = parser.add_argument("--secret")

    _ = parser.add_argument("--port")
    _ = parser.add_argument("--baudrate", type=int)
    _ = parser.add_argument("--bytesize", type=int)
    _ = parser.add_argument("--parity")
    _ = parser.add_argument("--stopbits", type=int)

    _ = parser.add_argument("--output-dir", type=Path)
    _ = parser.add_argument("--command")
    _ = parser.add_argument("--fallback-hostname")
    _ = parser.add_argument("--min-expected-bytes", type=int)
    _ = parser.add_argument("--retry-on-low-bytes", action="store_true", default=None)
    _ = parser.add_argument(
        "--no-retry-on-low-bytes", action="store_false", dest="retry_on_low_bytes"
    )

    _ = parser.add_argument("--git-enabled", action="store_true", default=None)
    _ = parser.add_argument("--no-git-enabled", action="store_false", dest="git_enabled")
    _ = parser.add_argument("--git-auto-commit", action="store_true", default=None)
    _ = parser.add_argument("--no-git-auto-commit", action="store_false", dest="git_auto_commit")
    _ = parser.add_argument("--git-commit-message")
    _ = parser.add_argument("--git-commit-body")

    _ = parser.add_argument("--jj-enabled", action="store_true", default=None)
    _ = parser.add_argument("--no-jj-enabled", action="store_false", dest="jj_enabled")
    _ = parser.add_argument("--jj-auto-commit", action="store_true", default=None)
    _ = parser.add_argument("--no-jj-auto-commit", action="store_false", dest="jj_auto_commit")
    _ = parser.add_argument("--jj-commit-message")
    _ = parser.add_argument("--jj-commit-body")

    _ = parser.add_argument("--loop", action="store_true", default=None)
    _ = parser.add_argument("--no-loop", action="store_false", dest="loop")
    _ = parser.add_argument("--count", type=int)
    _ = parser.add_argument("--stop-on-error", action="store_true", default=None)
    _ = parser.add_argument("--continue-on-error", action="store_false", dest="stop_on_error")

    return parser


def apply_overrides(config: AppConfig, args: argparse.Namespace) -> AppConfig:
    serial = replace(
        config.device.serial,
        port=args.port if args.port is not None else config.device.serial.port,
        baudrate=args.baudrate if args.baudrate is not None else config.device.serial.baudrate,
        bytesize=args.bytesize if args.bytesize is not None else config.device.serial.bytesize,
        parity=args.parity if args.parity is not None else config.device.serial.parity,
        stopbits=args.stopbits if args.stopbits is not None else config.device.serial.stopbits,
    )

    device = replace(
        config.device,
        device_type=args.device_type if args.device_type is not None else config.device.device_type,
        password=args.password if args.password is not None else config.device.password,
        secret=args.secret if args.secret is not None else config.device.secret,
        serial=serial,
    )

    backup = replace(
        config.backup,
        output_dir=args.output_dir if args.output_dir is not None else config.backup.output_dir,
        command=args.command if args.command is not None else config.backup.command,
        fallback_hostname=(
            args.fallback_hostname
            if args.fallback_hostname is not None
            else config.backup.fallback_hostname
        ),
        min_expected_bytes=(
            args.min_expected_bytes
            if args.min_expected_bytes is not None
            else config.backup.min_expected_bytes
        ),
        retry_on_low_bytes=(
            args.retry_on_low_bytes
            if args.retry_on_low_bytes is not None
            else config.backup.retry_on_low_bytes
        ),
    )

    git = replace(
        config.git,
        enabled=args.git_enabled if args.git_enabled is not None else config.git.enabled,
        auto_commit=(
            args.git_auto_commit if args.git_auto_commit is not None else config.git.auto_commit
        ),
        commit_message=(
            args.git_commit_message
            if args.git_commit_message is not None
            else config.git.commit_message
        ),
        commit_body=(
            args.git_commit_body if args.git_commit_body is not None else config.git.commit_body
        ),
    )

    jj = replace(
        config.jj,
        enabled=args.jj_enabled if args.jj_enabled is not None else config.jj.enabled,
        auto_commit=(
            args.jj_auto_commit if args.jj_auto_commit is not None else config.jj.auto_commit
        ),
        commit_message=(
            args.jj_commit_message
            if args.jj_commit_message is not None
            else config.jj.commit_message
        ),
        commit_body=(
            args.jj_commit_body if args.jj_commit_body is not None else config.jj.commit_body
        ),
    )

    cli = replace(
        config.cli,
        loop=args.loop if args.loop is not None else config.cli.loop,
        count=args.count if args.count is not None else config.cli.count,
        stop_on_error=(
            args.stop_on_error if args.stop_on_error is not None else config.cli.stop_on_error
        ),
    )

    return replace(config, device=device, backup=backup, git=git, jj=jj, cli=cli)


def run_once(config: AppConfig) -> bool:
    result = backup_running_config(config.device, config.backup)

    if result.ok and result.value is not None:
        print(f"Saved {result.value.bytes_written} bytes to {result.value.path}")

        commit_result = auto_commit(config, result.value)
        if not commit_result.ok:
            print(commit_result.error or "Auto-commit failed")
            return False

        for message in commit_result.value or []:
            print(message)
        return True

    print(result.error or "Unknown failure")
    return False


def should_continue(device_number: int, cli: CliConfig) -> bool:
    if cli.count > 0 and device_number >= cli.count:
        return False

    try:
        answer = input(
            "Plug in the next device, then press Enter to continue or type 'q' to quit: "
        )
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    return answer.strip().lower() not in {"q", "quit", "exit"}


def run_loop(config: AppConfig) -> None:
    device_number = 1

    while True:
        print(f"Starting backup for device #{device_number}...")
        ok = run_once(config)

        if not ok and config.cli.stop_on_error:
            print("Stopping because stop_on_error is enabled.")
            break

        if not should_continue(device_number, config.cli):
            break

        device_number += 1


def main() -> None:
    try:
        args = cast(CliArgs, build_parser().parse_args(namespace=CliArgs()))

        if args.config.exists():
            config = apply_overrides(load_config(args.config), args)
        elif args.config == DEFAULT_CONFIG_PATH:
            print(
                f"Hint: no config file found at {args.config}; using built-in defaults. "
                "Create one with --config or copy cisco-conf-helper.toml.",
                file=sys.stderr,
            )
            config = apply_overrides(AppConfig(), args)
        else:
            raise SystemExit(f"Config file not found: {args.config}")

        if config.cli.loop:
            run_loop(config)
            return

        _ = run_once(config)
    except KeyboardInterrupt:
        print("\nInterrupted, exiting gracefully.", file=sys.stderr)
