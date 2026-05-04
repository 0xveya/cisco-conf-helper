from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cisco_conf_helper.models import AppConfig, BackupResult, GitConfig, JjConfig, Result


@dataclass(frozen=True)
class CommitContext:
    hostname: str
    path: Path
    bytes_written: int
    command: str
    device_type: str
    timestamp: str

    def as_template_values(self) -> dict[str, str | int]:
        return {
            "hostname": self.hostname,
            "path": str(self.path),
            "path_name": self.path.name,
            "bytes_written": self.bytes_written,
            "command": self.command,
            "device_type": self.device_type,
            "timestamp": self.timestamp,
            "changed_devices": self.hostname,
            "changed_paths": str(self.path),
        }


def make_commit_context(config: AppConfig, result: BackupResult) -> CommitContext:
    try:
        display_path = result.path.relative_to(Path.cwd())
    except ValueError:
        display_path = result.path

    return CommitContext(
        hostname=result.hostname,
        path=display_path,
        bytes_written=result.bytes_written,
        command=result.command,
        device_type=config.device.device_type,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def render_template(template: str, context: CommitContext) -> Result[str]:
    try:
        return Result(ok=True, value=template.format_map(context.as_template_values()))
    except KeyError as exc:
        return Result(ok=False, error=f"Unknown commit template field: {exc.args[0]}")


def run_command(command: list[str]) -> Result[subprocess.CompletedProcess[str]]:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        return Result(ok=False, error=f"Could not run {' '.join(command)!r}: {exc}")

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        details = stderr or stdout or f"exit code {completed.returncode}"
        return Result(ok=False, error=f"Command failed: {' '.join(command)!r}: {details}")

    return Result(ok=True, value=completed)


def build_message(
    subject_template: str, body_template: str, context: CommitContext
) -> Result[tuple[str, str]]:
    subject_result = render_template(subject_template, context)
    if not subject_result.ok or subject_result.value is None:
        return Result(ok=False, error=subject_result.error)

    body_result = render_template(body_template, context)
    if not body_result.ok or body_result.value is None:
        return Result(ok=False, error=body_result.error)

    return Result(ok=True, value=(subject_result.value.strip(), body_result.value.strip()))


def git_has_changes(path: Path) -> Result[bool]:
    add_result = run_command(["git", "add", "--", str(path)])
    if not add_result.ok:
        return Result(ok=False, error=add_result.error)

    diff_result = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    return Result(ok=True, value=diff_result.returncode == 1)


def maybe_git_commit(config: GitConfig, context: CommitContext) -> Result[str]:
    message_result = build_message(config.commit_message, config.commit_body, context)
    if not message_result.ok or message_result.value is None:
        return Result(ok=False, error=message_result.error)

    subject, body = message_result.value
    changes_result = git_has_changes(context.path)
    if not changes_result.ok or changes_result.value is None:
        return Result(ok=False, error=changes_result.error)
    if not changes_result.value:
        return Result(ok=True, value="Git: no changes to commit")

    command = ["git", "commit", "-m", subject]
    if body:
        command += ["-m", body]
    command += ["--", str(context.path)]

    commit_result = run_command(command)
    if not commit_result.ok:
        return Result(ok=False, error=commit_result.error)

    return Result(ok=True, value=f"Git: committed {context.path}")


def jj_has_changes(path: Path) -> Result[bool]:
    diff_result = run_command(["jj", "diff", "--summary", "--", str(path)])
    if not diff_result.ok or diff_result.value is None:
        return Result(ok=False, error=diff_result.error)
    return Result(ok=True, value=bool(diff_result.value.stdout.strip()))


def maybe_jj_commit(config: JjConfig, context: CommitContext) -> Result[str]:
    message_result = build_message(config.commit_message, config.commit_body, context)
    if not message_result.ok or message_result.value is None:
        return Result(ok=False, error=message_result.error)

    subject, body = message_result.value
    changes_result = jj_has_changes(context.path)
    if not changes_result.ok or changes_result.value is None:
        return Result(ok=False, error=changes_result.error)
    if not changes_result.value:
        return Result(ok=True, value="JJ: no changes to commit")

    full_message = subject if not body else f"{subject}\n\n{body}"
    commit_result = run_command(["jj", "commit", "-m", full_message, "--", str(context.path)])
    if not commit_result.ok:
        return Result(ok=False, error=commit_result.error)

    return Result(ok=True, value=f"JJ: committed {context.path}")


def auto_commit(config: AppConfig, result: BackupResult) -> Result[list[str]]:
    context = make_commit_context(config, result)
    messages: list[str] = []

    if config.git.enabled and config.git.auto_commit:
        git_result = maybe_git_commit(config.git, context)
        if not git_result.ok or git_result.value is None:
            return Result(ok=False, error=git_result.error)
        messages.append(git_result.value)

    if config.jj.enabled and config.jj.auto_commit:
        jj_result = maybe_jj_commit(config.jj, context)
        if not jj_result.ok or jj_result.value is None:
            return Result(ok=False, error=jj_result.error)
        messages.append(jj_result.value)

    return Result(ok=True, value=messages)
