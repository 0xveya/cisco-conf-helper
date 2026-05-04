from __future__ import annotations

import re
from pathlib import Path
from types import TracebackType
from typing import Protocol, cast

from netmiko import ConnectHandler  # pyright: ignore[reportMissingTypeStubs]

from cisco_conf_helper.models import BackupConfig, BackupResult, CommandResult, DeviceConfig, Result


class Connection(Protocol):
    def __enter__(self) -> Connection: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def enable(self) -> str: ...

    def send_command(
        self,
        command_string: str,
        *args: object,
        **kwargs: object,
    ) -> str | list[object] | dict[str, object]: ...


def connect_device(config: DeviceConfig) -> Connection:
    params: dict[str, object] = {
        "device_type": config.device_type,
        "serial_settings": {
            "port": config.serial.port,
            "baudrate": config.serial.baudrate,
            "bytesize": config.serial.bytesize,
            "parity": config.serial.parity,
            "stopbits": config.serial.stopbits,
        },
        "password": config.password,
        "secret": config.secret,
    }
    return cast(Connection, cast(object, ConnectHandler(**params)))


def run_command(conn: Connection, command: str) -> Result[CommandResult]:
    try:
        output = conn.send_command(command)
        if not isinstance(output, str):
            return Result(
                ok=False,
                error=(
                    f"Command {command!r} returned unexpected output type: {type(output).__name__}"
                ),
            )
        return Result(ok=True, value=CommandResult(command=command, output=output))
    except Exception as exc:
        return Result(ok=False, error=f"Command failed: {command!r}: {exc}")


def extract_hostname(config_text: str, fallback: str) -> str:
    match = re.search(r"^hostname\s+(\S+)", config_text, re.MULTILINE)
    return match.group(1) if match else fallback


def sanitize_config_output(text: str) -> str:
    lines = text.splitlines()
    start = 0

    while start < len(lines):
        line = lines[start].strip()
        if (
            not line
            or line == "Building configuration..."
            or line.startswith("Current configuration :")
        ):
            start += 1
            continue
        break

    end = len(lines)
    last_end_index = -1
    for index, raw_line in enumerate(lines[start:], start=start):
        if raw_line.strip() == "end":
            last_end_index = index

    if last_end_index >= 0:
        end = last_end_index + 1
    else:
        while end > start and not lines[end - 1].strip():
            end -= 1

    cleaned = "\n".join(lines[start:end]).strip()
    return f"{cleaned}\n" if cleaned else ""


def save_text(path: Path, text: str) -> Result[Path]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(text, encoding="utf-8")
        return Result(ok=True, value=path)
    except OSError as exc:
        return Result(ok=False, error=f"Could not write {path}: {exc}")


def prompt_retry(byte_count: int, min_expected_bytes: int) -> bool:
    prompt = f"Only read {byte_count} bytes; expected at least {min_expected_bytes}. Retry? [y/N]: "
    try:
        answer = input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip().lower() in {"y", "yes"}


def backup_running_config(
    device_config: DeviceConfig,
    backup_config: BackupConfig,
) -> Result[BackupResult]:
    try:
        with connect_device(device_config) as conn:
            _ = conn.enable()

            while True:
                command_result = run_command(conn, backup_config.command)
                if not command_result.ok or command_result.value is None:
                    return Result(ok=False, error=command_result.error)

                output = sanitize_config_output(command_result.value.output)
                byte_count = len(output.encode("utf-8"))

                should_accept_output = (
                    byte_count >= backup_config.min_expected_bytes
                    or not backup_config.retry_on_low_bytes
                )
                if should_accept_output:
                    break

                if not prompt_retry(byte_count, backup_config.min_expected_bytes):
                    return Result(
                        ok=False,
                        error=f"Aborted: suspiciously small output ({byte_count} bytes).",
                    )

            hostname = extract_hostname(output, backup_config.fallback_hostname)
            output_path = backup_config.output_dir / f"{hostname}.txt"

            save_result = save_text(output_path, output)
            if not save_result.ok or save_result.value is None:
                return Result(ok=False, error=save_result.error)

            return Result(
                ok=True,
                value=BackupResult(
                    hostname=hostname,
                    path=save_result.value,
                    command=command_result.value.command,
                    bytes_written=byte_count,
                ),
            )
    except KeyboardInterrupt:
        return Result(ok=False, error="Backup interrupted by user.")
    except Exception as exc:
        return Result(ok=False, error=f"Backup failed: {exc}")
