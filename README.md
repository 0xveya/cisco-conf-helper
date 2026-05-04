# cisco-conf-helper

Back up or apply Cisco configs over a serial connection.

## Install

Run directly with `uvx`:

```bash
uvx cisco-conf-helper --help
```

Package: `cisco-conf-helper` on PyPI (publisher: `veya`).

## Quick start

Create a config file:

```toml
#:schema https://raw.githubusercontent.com/0xveya/cisco-conf-helper/master/cisco-conf-helper.schema.json

[backup]
output_dir = "backups"
command = "show running-config"
min_expected_bytes = 1000
retry_on_low_bytes = true
print_saved_config = false
wipe_after_backup = false
wipe_delete_vlan_dat = false
wipe_extra_commands = []

[apply]
source_dir = "backups"
save_command = "write memory"
save_after_apply = true

[git]
enabled = true
auto_commit = true
commit_message = "Back up config for {hostname}"
commit_body = """
Devices changed:
- {hostname}

Files changed:
- {path}

Bytes written: {bytes_written}
Command: {command}
Device type: {device_type}
Timestamp: {timestamp}
"""

[jj]
enabled = false
auto_commit = false
commit_message = "Back up config for {hostname}"
commit_body = """
Devices changed:
- {hostname}

Files changed:
- {path}

Bytes written: {bytes_written}
Command: {command}
Device type: {device_type}
Timestamp: {timestamp}
"""

[cli]
mode = "backup"
loop = true
count = 0
stop_on_error = true
dry_run = false

[device]
device_type = "cisco_ios_serial"
password = "cisco"
secret = "class"

[serial]
port = "/dev/ttyUSB0"
baudrate = 9600
bytesize = 8
parity = "N"
stopbits = 1
```

## Examples

### Single backup

```bash
uvx cisco-conf-helper --no-loop
```

### Backup loop for a lab

```bash
uvx cisco-conf-helper --loop
```

If `--wipe-after-backup` is not passed, loop mode asks once whether each device should be wiped after backup.

### Force wipe after every backup without asking

```bash
uvx cisco-conf-helper --loop --wipe-after-backup
```

This issues:
- `write erase`
- `reload`

and handles common confirmation prompts automatically.

### Also delete `vlan.dat`

```bash
uvx cisco-conf-helper --loop --wipe-after-backup --wipe-delete-vlan-dat
```

This is useful for school lab switches that should be fully reset at the end of a session.
When enabled, the tool also checks the saved config for VLAN definitions and only deletes `flash:vlan.dat` when VLAN config is detected.

### Print the saved config after each backup

```bash
uvx cisco-conf-helper --loop --print-saved-config
```

This prints the exact saved file after backup so you can verify the config was captured.

### Do both: print config and wipe after backup

```bash
uvx cisco-conf-helper --loop --print-saved-config --wipe-after-backup
```

### Override config defaults from the CLI

```bash
uvx cisco-conf-helper \
  --loop \
  --port /dev/ttyUSB0 \
  --baudrate 9600 \
  --output-dir backups
```

### Use config file defaults for lab cleanup

```toml
[backup]
print_saved_config = true
wipe_after_backup = true
wipe_delete_vlan_dat = true
wipe_extra_commands = []
```

Then run:

```bash
uvx cisco-conf-helper --loop
```

### Add extra wipe commands

Example config:

```toml
[backup]
wipe_after_backup = true
wipe_delete_vlan_dat = true
wipe_extra_commands = [
  "delete flash:multiple-fs",
  "delete flash:private-config.text",
]
```

Then run:

```bash
uvx cisco-conf-helper --loop
```

### Apply saved configs back to devices

```bash
uvx cisco-conf-helper --mode apply
```

### Dry-run apply mode

```bash
uvx cisco-conf-helper --mode apply --dry-run
```

## Notes

- Backups are saved as `backups/<hostname>.txt` by default.
- If the running config looks too small, the tool can ask whether to retry.
- In loop mode, `--wipe-after-backup` overrides the interactive wipe question.
- `--no-wipe-after-backup` forces no wipe and also skips the question.
