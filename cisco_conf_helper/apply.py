from __future__ import annotations

import subprocess
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Protocol, cast

from netmiko import ConnectHandler  # pyright: ignore[reportMissingTypeStubs]

from cisco_conf_helper.models import ApplyConfig, DeviceConfig, Result


@dataclass(frozen=True)
class ConfigArtifact:
    name: str
    source: str
    text: str


class Connection(Protocol):
    def __enter__(self) -> Connection: ...

    def __exit__(self, exc_type, exc_value, traceback) -> None: ...

    def enable(self) -> str: ...

    def send_command(
        self,
        command_string: str,
        *args: object,
        **kwargs: object,
    ) -> str | list[object] | dict[str, object]: ...

    def send_command_timing(
        self,
        command_string: str,
        *args: object,
        **kwargs: object,
    ) -> str: ...

    def send_config_set(
        self,
        config_commands: list[str],
        *args: object,
        **kwargs: object,
    ) -> str: ...


def make_connection_params(
    config: DeviceConfig,
    password: str,
    secret: str,
) -> dict[str, object]:
    return {
        "device_type": config.device_type,
        "serial_settings": {
            "port": config.serial.port,
            "baudrate": config.serial.baudrate,
            "bytesize": config.serial.bytesize,
            "parity": config.serial.parity,
            "stopbits": config.serial.stopbits,
        },
        "password": password,
        "secret": secret,
    }


def connect_device(config: DeviceConfig, password: str, secret: str) -> Connection:
    params = make_connection_params(config, password, secret)
    return cast(Connection, cast(object, ConnectHandler(**params)))


def auth_candidates(config: DeviceConfig) -> list[tuple[str, str]]:
    candidates = [
        (config.password, config.secret),
        ("", config.secret),
        (config.password, ""),
        ("", ""),
    ]
    return list(dict.fromkeys(candidates))


def bypass_initial_dialog(conn: Connection) -> None:
    output = conn.send_command_timing("\n", strip_prompt=False, strip_command=False)
    lowered = output.lower()

    if "initial configuration dialog" in lowered:
        output = conn.send_command_timing("no", strip_prompt=False, strip_command=False)
        lowered = output.lower()

    if "terminate autoinstall" in lowered:
        output = conn.send_command_timing("yes", strip_prompt=False, strip_command=False)
        lowered = output.lower()

    if "press return to get started" in lowered:
        _ = conn.send_command_timing("\n", strip_prompt=False, strip_command=False)


def prompt_for_credentials() -> tuple[str, str] | None:
    try:
        password = getpass("Login/line password (leave blank if none): ")
        secret = getpass("Enable secret/password (leave blank if none): ")
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return password, secret


def list_local_configs(source_dir: Path) -> Result[list[ConfigArtifact]]:
    if not source_dir.exists():
        return Result(ok=False, error=f"Config directory not found: {source_dir}")

    artifacts: list[ConfigArtifact] = []
    for path in sorted(source_dir.glob("*.txt")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            return Result(ok=False, error=f"Could not read {path}: {exc}")
        artifacts.append(ConfigArtifact(name=path.stem, source=str(path), text=text))

    if not artifacts:
        return Result(ok=False, error=f"No config files found in {source_dir}")

    return Result(ok=True, value=artifacts)


def run_command(command: list[str]) -> Result[subprocess.CompletedProcess[str]]:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        return Result(ok=False, error=f"Could not run {' '.join(command)!r}: {exc}")

    if completed.returncode != 0:
        details = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or f"exit code {completed.returncode}"
        )
        return Result(ok=False, error=f"Command failed: {' '.join(command)!r}: {details}")

    return Result(ok=True, value=completed)


def list_git_configs(source_dir: Path, commit: str) -> Result[list[ConfigArtifact]]:
    tree_result = run_command(
        ["git", "ls-tree", "-r", "--name-only", commit, "--", str(source_dir)]
    )
    if not tree_result.ok or tree_result.value is None:
        return Result(ok=False, error=tree_result.error)

    names = [
        line.strip()
        for line in tree_result.value.stdout.splitlines()
        if line.strip().endswith(".txt")
    ]
    if not names:
        return Result(ok=False, error=f"No config files found in {source_dir} at commit {commit}")

    artifacts: list[ConfigArtifact] = []
    for name in names:
        show_result = run_command(["git", "show", f"{commit}:{name}"])
        if not show_result.ok or show_result.value is None:
            return Result(ok=False, error=show_result.error)
        path = Path(name)
        artifacts.append(
            ConfigArtifact(name=path.stem, source=f"{commit}:{name}", text=show_result.value.stdout)
        )

    return Result(ok=True, value=artifacts)


def list_jj_configs(source_dir: Path, revision: str) -> Result[list[ConfigArtifact]]:
    list_result = run_command(["jj", "file", "list", "-r", revision, str(source_dir)])
    if not list_result.ok or list_result.value is None:
        return Result(ok=False, error=list_result.error)

    names = [
        line.strip()
        for line in list_result.value.stdout.splitlines()
        if line.strip().endswith(".txt")
    ]
    if not names:
        return Result(
            ok=False,
            error=f"No config files found in {source_dir} at jj revision {revision}",
        )

    artifacts: list[ConfigArtifact] = []
    for name in names:
        show_result = run_command(["jj", "file", "show", "-r", revision, name])
        if not show_result.ok or show_result.value is None:
            return Result(ok=False, error=show_result.error)
        path = Path(name)
        artifacts.append(
            ConfigArtifact(
                name=path.stem,
                source=f"jj:{revision}:{name}",
                text=show_result.value.stdout,
            )
        )

    return Result(ok=True, value=artifacts)


def print_choices(artifacts: list[ConfigArtifact]) -> None:
    print("Available configs:")
    for index, artifact in enumerate(artifacts, start=1):
        print(f"  {index}. {artifact.name} ({artifact.source})")


def parse_selection(
    selection: str,
    artifacts: list[ConfigArtifact],
) -> Result[list[ConfigArtifact]]:
    by_name = {artifact.name: artifact for artifact in artifacts}
    chosen: list[ConfigArtifact] = []
    seen: set[str] = set()

    for raw_token in selection.split(","):
        token = raw_token.strip()
        if not token:
            continue

        artifact: ConfigArtifact | None = None
        if token.isdigit():
            index = int(token)
            if 1 <= index <= len(artifacts):
                artifact = artifacts[index - 1]
            else:
                return Result(ok=False, error=f"Selection {token} is out of range")
        else:
            artifact = by_name.get(token)
            if artifact is None:
                return Result(ok=False, error=f"Unknown config selection: {token}")

        if artifact.name not in seen:
            chosen.append(artifact)
            seen.add(artifact.name)

    if not chosen:
        return Result(ok=False, error="No configs selected")

    return Result(ok=True, value=chosen)


def prompt_for_selection(artifacts: list[ConfigArtifact]) -> Result[list[ConfigArtifact]]:
    print_choices(artifacts)
    try:
        selection = input("Select configs to apply (example: 1,2 or sw1,sw2): ")
    except (EOFError, KeyboardInterrupt):
        print()
        return Result(ok=False, error="Selection cancelled")
    return parse_selection(selection, artifacts)


def load_selected_configs(
    source_dir: Path,
    selection: str | None,
    commit: str | None,
    jj_revision: str | None,
) -> Result[list[ConfigArtifact]]:
    if commit and jj_revision:
        return Result(ok=False, error="Use either --from-commit or --from-jj-rev, not both")

    if commit:
        source_result = list_git_configs(source_dir, commit)
    elif jj_revision:
        source_result = list_jj_configs(source_dir, jj_revision)
    else:
        source_result = list_local_configs(source_dir)
    if not source_result.ok or source_result.value is None:
        return Result(ok=False, error=source_result.error)

    artifacts = source_result.value
    if selection is None:
        return prompt_for_selection(artifacts)
    return parse_selection(selection, artifacts)


def prepare_config_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped == "end":
            continue
        lines.append(line)
    return lines


def apply_config_to_device(
    device_config: DeviceConfig,
    apply_config: ApplyConfig,
    artifact: ConfigArtifact,
) -> Result[str]:
    commands = prepare_config_lines(artifact.text)
    if not commands:
        return Result(ok=False, error=f"Config {artifact.name} has no commands to apply")

    errors: list[str] = []

    for password, secret in auth_candidates(device_config):
        try:
            with connect_device(device_config, password, secret) as conn:
                bypass_initial_dialog(conn)
                _ = conn.enable()
                _ = conn.send_config_set(commands)
                if apply_config.save_after_apply:
                    save_output = conn.send_command(apply_config.save_command)
                    if not isinstance(save_output, str):
                        return Result(
                            ok=False,
                            error=(
                                f"Save command returned unexpected output for {artifact.name}"
                            ),
                        )
            return Result(ok=True, value=f"Applied {artifact.name} from {artifact.source}")
        except KeyboardInterrupt:
            return Result(ok=False, error="Apply interrupted by user.")
        except Exception as exc:
            errors.append(str(exc))

    print("Configured password/secret did not work. You can enter them manually.")
    prompted = prompt_for_credentials()
    if prompted is None:
        return Result(ok=False, error="Apply cancelled while prompting for credentials.")

    password, secret = prompted
    try:
        with connect_device(device_config, password, secret) as conn:
            bypass_initial_dialog(conn)
            _ = conn.enable()
            _ = conn.send_config_set(commands)
            if apply_config.save_after_apply:
                save_output = conn.send_command(apply_config.save_command)
                if not isinstance(save_output, str):
                    return Result(
                        ok=False,
                        error=f"Save command returned unexpected output for {artifact.name}",
                    )
        return Result(ok=True, value=f"Applied {artifact.name} from {artifact.source}")
    except KeyboardInterrupt:
        return Result(ok=False, error="Apply interrupted by user.")
    except Exception as exc:
        details = errors[-1] if errors else "no automatic auth attempts succeeded"
        return Result(
            ok=False,
            error=(
                f"Apply failed for {artifact.name}: {exc}. "
                f"Automatic auth attempts also failed: {details}"
            ),
        )
