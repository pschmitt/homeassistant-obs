# homeassistant-obs

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

A Home Assistant custom integration for **OBS Studio** via the OBS WebSocket v5 protocol.

## Features

### Entities

| Type | Entity | Description |
|---|---|---|
| Sensor | Current scene | Name of the active program scene |
| Sensor | CPU usage | OBS process CPU utilisation (%) |
| Sensor | Memory usage | OBS process memory (MB) |
| Sensor | Available disk space | Free disk space on the recording drive (MB) |
| Sensor | Active FPS | Current output frame rate |
| Sensor | Render skipped frames | Accumulated skipped render frames |
| Sensor | Output skipped frames | Accumulated skipped output frames |
| Sensor | Stream duration | Live stream timecode (when streaming) |
| Sensor | Record duration | Recording timecode (when recording) |
| Sensor | OBS version | Installed OBS Studio version |
| Sensor | Platform | Host OS platform string |
| Binary sensor | Streaming | On when OBS is live |
| Binary sensor | Recording | On when OBS is recording |
| Binary sensor | Recording paused | On when recording is paused |
| Binary sensor | Virtual camera | On when virtual camera is active |
| Binary sensor | Studio mode | On when studio mode is enabled |
| Binary sensor | Replay buffer | On when replay buffer is active |
| Select | Scene | Switch the current scene |
| Switch | Virtual camera | Toggle virtual camera |
| Switch | Studio mode | Toggle studio mode |

### Services

| Service | Description |
|---|---|
| `obs.set_scene` | Switch to a named scene |
| `obs.start_stream` / `obs.stop_stream` / `obs.toggle_stream` | Control live streaming |
| `obs.start_record` / `obs.stop_record` / `obs.toggle_record` | Control recording |
| `obs.pause_record` / `obs.resume_record` | Pause / resume recording |
| `obs.start_virtual_cam` / `obs.stop_virtual_cam` | Control virtual camera |
| `obs.start_replay_buffer` / `obs.stop_replay_buffer` / `obs.save_replay_buffer` | Control replay buffer |
| `obs.trigger_hotkey` | Trigger any OBS hotkey by name |

## Prerequisites

- OBS Studio 28+ with **WebSocket Server** enabled  
  *(OBS → Tools → WebSocket Server Settings → Enable)*
- Python package `obsws-python >= 1.7.0` (installed automatically by HA)

## Connection modes

### Direct WebSocket

Connect straight to `ws://<host>:<port>` — suitable when OBS is reachable on the network.

### SSH tunnel

When OBS only listens on `localhost` (the default), enable the **SSH tunnel** option.  
Home Assistant will forward the OBS WebSocket port over an SSH connection using a key
stored at the configured path (default: `/config/.ssh/id_ed25519`).

The SSH key must be pre-authorised on the remote host (`~/.ssh/authorized_keys`).

## Installation

### Manual

1. Copy or symlink `custom_components/obs` into your HA `custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **OBS Studio**.

### HACS (custom repo)

Add `https://github.com/pschmitt/homeassistant-obs` as a custom HACS repository,
install, and restart Home Assistant.

## Configuration

All settings are managed through the UI config flow.  No YAML required.

## License

[GNU General Public License v3.0](LICENSE)
