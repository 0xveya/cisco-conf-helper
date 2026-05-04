from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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
    serial: SerialSettings = field(default_factory=SerialSettings)


@dataclass(frozen=True)
class BackupConfig:
    output_dir: Path = Path("backups")
    command: str = "show running-config"
    fallback_hostname: str = "unknown-device"
    min_expected_bytes: int = 1_000
    retry_on_low_bytes: bool = True
    print_saved_config: bool = False
    wipe_after_backup: bool = False
    wipe_delete_vlan_dat: bool = False
    wipe_extra_commands: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ApplyConfig:
    source_dir: Path = Path("backups")
    save_command: str = "write memory"
    save_after_apply: bool = True


@dataclass(frozen=True)
class GitConfig:
    enabled: bool = False
    auto_commit: bool = False
    commit_message: str = "Back up config for {hostname}"
    commit_body: str = (
        "Devices changed:\n"
        "- {hostname}\n\n"
        "Files changed:\n"
        "- {path}\n\n"
        "Bytes written: {bytes_written}\n"
        "Command: {command}\n"
        "Device type: {device_type}\n"
        "Timestamp: {timestamp}"
    )


@dataclass(frozen=True)
class JjConfig:
    enabled: bool = False
    auto_commit: bool = False
    commit_message: str = "Back up config for {hostname}"
    commit_body: str = (
        "Devices changed:\n"
        "- {hostname}\n\n"
        "Files changed:\n"
        "- {path}\n\n"
        "Bytes written: {bytes_written}\n"
        "Command: {command}\n"
        "Device type: {device_type}\n"
        "Timestamp: {timestamp}"
    )


@dataclass(frozen=True)
class CliConfig:
    mode: str = "backup"
    loop: bool = True
    count: int = 0
    stop_on_error: bool = True
    dry_run: bool = False


@dataclass(frozen=True)
class AppConfig:
    device: DeviceConfig = field(default_factory=DeviceConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    apply: ApplyConfig = field(default_factory=ApplyConfig)
    git: GitConfig = field(default_factory=GitConfig)
    jj: JjConfig = field(default_factory=JjConfig)
    cli: CliConfig = field(default_factory=CliConfig)


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
    config_text: str
