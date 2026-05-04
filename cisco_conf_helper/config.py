from __future__ import annotations

import tomllib
from pathlib import Path

from dacite import Config, DaciteError, from_dict

from cisco_conf_helper.models import AppConfig


def load_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as file_handle:
        return tomllib.load(file_handle)


def get_table(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def merge_legacy_serial_table(data: dict[str, object]) -> dict[str, object]:
    merged = dict(data)
    device = dict(get_table(merged, "device"))

    if "serial" not in device:
        serial = get_table(merged, "serial")
        if serial:
            device["serial"] = serial

    if device:
        merged["device"] = device

    return merged


def load_config(path: Path) -> AppConfig:
    raw = load_toml(path)
    prepared = merge_legacy_serial_table(raw)

    try:
        return from_dict(
            data_class=AppConfig,
            data=prepared,
            config=Config(type_hooks={Path: Path}),
        )
    except DaciteError as exc:
        raise ValueError(f"Invalid config in {path}: {exc}") from exc
