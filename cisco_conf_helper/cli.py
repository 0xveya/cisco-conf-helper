from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import cast

from cisco_conf_helper.apply import apply_config_to_device, load_selected_configs
from cisco_conf_helper.backup import backup_running_config, config_has_vlans, wipe_device
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
    print_saved_config: bool | None
    wipe_after_backup: bool | None
    wipe_delete_vlan_dat: bool | None
    git_enabled: bool | None
    git_auto_commit: bool | None
    git_commit_message: str | None
    git_commit_body: str | None
    jj_enabled: bool | None
    jj_auto_commit: bool | None
    jj_commit_message: str | None
    jj_commit_body: str | None
    mode: str | None
    loop: bool | None
    count: int | None
    stop_on_error: bool | None
    apply_source_dir: Path | None
    apply_save_command: str | None
    apply_save_after: bool | None
    select: str | None
    from_commit: str | None
    from_jj_rev: str | None
    dry_run: bool | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Back up or apply Cisco configs over a serial connection."
    )
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
    _ = parser.add_argument("--print-saved-config", action="store_true", default=None)
    _ = parser.add_argument(
        "--no-print-saved-config", action="store_false", dest="print_saved_config"
    )
    _ = parser.add_argument("--wipe-after-backup", action="store_true", default=None)
    _ = parser.add_argument(
        "--no-wipe-after-backup", action="store_false", dest="wipe_after_backup"
    )
    _ = parser.add_argument("--wipe-delete-vlan-dat", action="store_true", default=None)
    _ = parser.add_argument(
        "--no-wipe-delete-vlan-dat", action="store_false", dest="wipe_delete_vlan_dat"
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

    _ = parser.add_argument("--mode", choices=["backup", "apply"])
    _ = parser.add_argument("--loop", action="store_true", default=None)
    _ = parser.add_argument("--no-loop", action="store_false", dest="loop")
    _ = parser.add_argument("--count", type=int)
    _ = parser.add_argument("--stop-on-error", action="store_true", default=None)
    _ = parser.add_argument("--continue-on-error", action="store_false", dest="stop_on_error")

    _ = parser.add_argument("--apply-source-dir", type=Path)
    _ = parser.add_argument("--apply-save-command")
    _ = parser.add_argument("--apply-save-after", action="store_true", default=None)
    _ = parser.add_argument("--no-apply-save-after", action="store_false", dest="apply_save_after")
    _ = parser.add_argument("--select")
    _ = parser.add_argument("--from-commit")
    _ = parser.add_argument("--from-jj-rev")
    _ = parser.add_argument("--dry-run", action="store_true", default=None)
    _ = parser.add_argument("--no-dry-run", action="store_false", dest="dry_run")

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
        print_saved_config=(
            args.print_saved_config
            if args.print_saved_config is not None
            else config.backup.print_saved_config
        ),
        wipe_after_backup=(
            args.wipe_after_backup
            if args.wipe_after_backup is not None
            else config.backup.wipe_after_backup
        ),
        wipe_delete_vlan_dat=(
            args.wipe_delete_vlan_dat
            if args.wipe_delete_vlan_dat is not None
            else config.backup.wipe_delete_vlan_dat
        ),
    )

    apply = replace(
        config.apply,
        source_dir=(
            args.apply_source_dir if args.apply_source_dir is not None else config.apply.source_dir
        ),
        save_command=(
            args.apply_save_command
            if args.apply_save_command is not None
            else config.apply.save_command
        ),
        save_after_apply=(
            args.apply_save_after
            if args.apply_save_after is not None
            else config.apply.save_after_apply
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
        mode=args.mode if args.mode is not None else config.cli.mode,
        loop=args.loop if args.loop is not None else config.cli.loop,
        count=args.count if args.count is not None else config.cli.count,
        stop_on_error=(
            args.stop_on_error if args.stop_on_error is not None else config.cli.stop_on_error
        ),
        dry_run=args.dry_run if args.dry_run is not None else config.cli.dry_run,
    )

    return replace(config, device=device, backup=backup, apply=apply, git=git, jj=jj, cli=cli)


def print_saved_config(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Could not read saved config {path}: {exc}")
        return False

    print(f"--- begin saved config: {path} ---")
    print(text, end="" if text.endswith("\n") else "\n")
    print(f"--- end saved config: {path} ---")
    return True


def run_once(config: AppConfig) -> bool:
    result = backup_running_config(config.device, config.backup)

    if not result.ok or result.value is None:
        print(result.error or "Unknown failure")
        return False

    print(f"Saved {result.value.bytes_written} bytes to {result.value.path}")

    ok = True

    if config.backup.print_saved_config and not print_saved_config(result.value.path):
        ok = False

    commit_result = auto_commit(config, result.value)
    if not commit_result.ok:
        print(commit_result.error or "Auto-commit failed")
        ok = False
    else:
        for message in commit_result.value or []:
            print(message)

    if config.backup.wipe_after_backup:
        delete_vlan_dat = (
            config.backup.wipe_delete_vlan_dat and config_has_vlans(result.value.config_text)
        )
        try:
            from cisco_conf_helper.backup import connect_device

            with connect_device(config.device) as conn:
                _ = conn.enable()
                wipe_result = wipe_device(
                    conn,
                    config.backup,
                    delete_vlan_dat=delete_vlan_dat,
                )
        except Exception as exc:
            print(f"Wipe failed: {exc}")
            ok = False
        else:
            if wipe_result.ok:
                print("Issued lab wipe commands: write erase, reload")
                if config.backup.wipe_delete_vlan_dat:
                    if delete_vlan_dat:
                        print("Detected VLAN config and deleted flash:vlan.dat")
                    else:
                        print("No VLAN config detected; skipped flash:vlan.dat deletion")
            else:
                print(wipe_result.error or "Wipe failed")
                ok = False

    return ok


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


def prompt_for_wipe_choice(default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    try:
        answer = input(f"Wipe each device after backup (write erase + reload)? [{suffix}]: ")
    except (EOFError, KeyboardInterrupt):
        print()
        return default

    cleaned = answer.strip().lower()
    if not cleaned:
        return default
    return cleaned in {"y", "yes"}


def run_backup_loop(config: AppConfig, prompt_for_wipe: bool) -> None:
    if prompt_for_wipe:
        config = replace(
            config,
            backup=replace(
                config.backup,
                wipe_after_backup=prompt_for_wipe_choice(config.backup.wipe_after_backup),
            ),
        )

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


def run_apply(
    config: AppConfig,
    selection: str | None,
    commit: str | None,
    jj_revision: str | None,
) -> bool:
    selected_result = load_selected_configs(
        config.apply.source_dir,
        selection,
        commit,
        jj_revision,
    )
    if not selected_result.ok or selected_result.value is None:
        print(selected_result.error or "Could not load configs")
        return False

    artifacts = selected_result.value
    total = len(artifacts)

    if config.cli.dry_run:
        print("Dry run: these configs would be applied in this order:")
        for index, artifact in enumerate(artifacts, start=1):
            print(f"  {index}. {artifact.name} ({artifact.source})")
        if config.apply.save_after_apply:
            print(f"Would also save to startup-config using: {config.apply.save_command}")
        return True

    for index, artifact in enumerate(artifacts, start=1):
        if index == 1:
            prompt = (
                f"Ready to apply {artifact.name} ({index}/{total}). "
                "Plug in the device and press Enter to continue: "
            )
        else:
            prompt = (
                f"Next config: {artifact.name} ({index}/{total}). "
                "Plug in that device and press Enter to continue: "
            )

        if config.cli.loop:
            try:
                answer = input(prompt)
            except (EOFError, KeyboardInterrupt):
                print()
                return False
            if answer.strip().lower() in {"q", "quit", "exit"}:
                return False
        else:
            print(f"Applying {artifact.name} ({index}/{total})...")

        result = apply_config_to_device(config.device, config.apply, artifact)
        if result.ok and result.value is not None:
            print(result.value)
        else:
            print(result.error or f"Failed to apply {artifact.name}")
            if config.cli.stop_on_error:
                print("Stopping because stop_on_error is enabled.")
                return False

        if config.cli.count > 0 and index >= config.cli.count:
            break

    return True


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

        if config.cli.mode == "apply":
            _ = run_apply(config, args.select, args.from_commit, args.from_jj_rev)
            return

        if config.cli.loop:
            run_backup_loop(config, prompt_for_wipe=args.wipe_after_backup is None)
            return

        _ = run_once(config)
    except KeyboardInterrupt:
        print("\nInterrupted, exiting gracefully.", file=sys.stderr)
