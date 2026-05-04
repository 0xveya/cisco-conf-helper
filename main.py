from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Protocol, cast

from netmiko import ConnectHandler  # pyright: ignore[reportMissingTypeStubs]


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


@dataclass(frozen=True)
class Result[T]:
    ok: bool
    value: T | None = None
    error: str | None = None


@dataclass(frozen=True)
class SerialSettings:
    port: str = "/dev/ttyUSB0"
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "N"
    stopbits: int = 1


@dataclass(frozen=True)
class DeviceConfig:
    device_type: str = "cisco_ios_serial"
    password: str = "cisco"
    secret: str = "class"
    serial: SerialSettings = SerialSettings()


@dataclass(frozen=True)
class BackupConfig:
    output_dir: Path = Path(".")
    command: str = "show running-config"
    fallback_hostname: str = "unknown-device"
    min_expected_bytes: int = 1_000
    retry_on_low_bytes: bool = True


@dataclass(frozen=True)
class CommandResult:
    command: str
    output: str


@dataclass(frozen=True)
class BackupResult:
    hostname: str
    path: Path
    command: str
    bytes_written: int


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


def save_text(path: Path, text: str) -> Result[Path]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(text, encoding="utf-8")
        return Result(ok=True, value=path)
    except OSError as exc:
        return Result(ok=False, error=f"Could not write {path}: {exc}")


def prompt_retry(byte_count: int, min_expected_bytes: int) -> bool:
    prompt = f"Only read {byte_count} bytes; expected at least {min_expected_bytes}. Retry? [y/N]: "
    answer = input(prompt)
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

                output = command_result.value.output
                byte_count = len(output.encode("utf-8"))

                should_accept_output = (
                    byte_count >= backup_config.min_expected_bytes
                    or not backup_config.retry_on_low_bytes
                )

                if should_accept_output:
                    break

                if not prompt_retry(byte_count, backup_config.min_expected_bytes):
                    error = f"Aborted: suspiciously small output ({byte_count} bytes)."
                    return Result(ok=False, error=error)

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

    except Exception as exc:
        return Result(ok=False, error=f"Backup failed: {exc}")


def main() -> None:
    device_config = DeviceConfig(
        serial=SerialSettings(port="/dev/ttyUSB0"),
        password="cisco",
        secret="class",
    )

    backup_config = BackupConfig(output_dir=Path("backups"))

    result = backup_running_config(device_config, backup_config)

    if result.ok and result.value is not None:
        print(f"Saved {result.value.bytes_written} bytes to {result.value.path}")
    else:
        print(result.error or "Unknown failure")


if __name__ == "__main__":
    main()
