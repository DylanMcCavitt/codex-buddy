# Codex Buddy Firmware Notes

This firmware is a Codex Buddy port of Anthropic's Claude Desktop Buddy
reference firmware. Keep `LICENSE`, `README.md`, `REFERENCE.md`, and bundled
character asset attribution in place when changing the port.

## Identity

- BLE advertisement name: `Codex-XXXX`, where `XXXX` is derived from the last
  two Bluetooth MAC bytes.
- Nordic UART Service UUIDs are unchanged for protocol compatibility.
- The desktop bridge should continue scanning for both `Codex-*` and
  `Claude-*` during the transition.

## Expected On-Device Copy

Normal firmware screens should use Codex-facing copy:

- Idle disconnected state: `No Codex connected`
- About page: `I watch Codex` / `work sessions.`
- Session stats page header: `CODEX`
- Bluetooth pairing page: `Run codex-buddy` / `bridge BLE mode` / `or USB serial`

Upstream attribution remains visible on the credits page.

## Build, Flash, And Erase

Install PlatformIO Core first:

```bash
python3 -m pip install platformio
```

Build from this firmware directory:

```bash
pio run
```

If the `pio` executable is not on your shell `PATH`, use the module entrypoint:

```bash
python3 -m platformio run
```

Flash an attached M5StickC Plus:

```bash
pio run -t upload
```

Erase before flashing a previously used device:

```bash
pio run -t erase && pio run -t upload
```

After flashing, confirm the device advertises as `Codex-*` and verify the
serial bridge still updates the display:

```bash
cd ../..
make bridge-serial
```
