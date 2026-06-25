# homeassistant-obs-studio

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
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

Add `https://github.com/pschmitt/homeassistant-obs-studio` as a custom HACS repository,
install, and restart Home Assistant.

## Configuration

All settings are managed through the UI config flow.  No YAML required.

## Template overlays

The integration can render Jinja2 HTML templates on every OBS poll and write the
output to `/config/www/obs-studio/` (served at `/local/obs-studio/` in HA).  
Add the resulting URL as an OBS **Browser Source** with *"Page is transparent"* enabled
to overlay live data on any scene — no credentials required.

### Available template variables

In addition to all standard HA template functions (`states()`, `state_attr()`,
`now()`, `is_state()`, …), the following OBS state variables are injected:

| Variable | Type | Description |
|---|---|---|
| `obs_scene` | `str \| None` | Name of the current program scene |
| `obs_streaming` | `bool` | True when OBS is live |
| `obs_recording` | `bool` | True when OBS is recording |
| `obs_fps` | `float` | Current output frame rate |
| `obs_cpu` | `float` | OBS process CPU usage (%) |
| `obs_mem` | `float` | OBS process memory usage (MB) |

### Defining templates

#### Option A — File-based (drop a file, zero config)

Place a `<name>.html.j2` file in `/config/www/obs-studio/`.  
The integration auto-discovers all `*.html.j2` files in that directory and renders
each to `<name>.html` on every coordinator update.

```
/config/www/obs-studio/
  obs-overlay.html.j2      → rendered to obs-overlay.html
  streaming-badge.html.j2  → rendered to streaming-badge.html
```

#### Option B — Inline (defined in the options flow)

Go to **Settings → Devices & services → OBS Studio → Configure**.  
In the *Template overlays* dropdown, pick **+ Add template**, enter a name and
paste the template content.  Inline templates are stored in the config entry and
render alongside any file-based ones.  If the same name exists in both, the inline
definition takes precedence.

### Example — room temperature widget

This overlay displays the office temperature from a Home Assistant sensor as a
semi-transparent pill in the bottom-left corner of the scene.

Save as `/config/www/obs-studio/obs-overlay.html.j2` (file-based), or paste the
content into an inline template named `obs-overlay`:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {
      background: transparent;
      margin: 0;
      padding: 0;
      display: inline-flex;
      font-family: 'Segoe UI', system-ui, sans-serif;
    }
    #widget {
      background: rgba(0, 0, 0, 0.55);
      border-radius: 12px;
      padding: 10px 18px;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .icon  { font-size: 1.4rem; }
    .value { font-size: 1.6rem; font-weight: 600; }
    .label { font-size: 0.75rem; opacity: 0.7; }
  </style>
</head>
<body>
  <div id="widget">
    <span class="icon">🌡️</span>
    <div>
      <div class="value">
        {{ states('sensor.office_temperature_filtered') | float | round(1) }} °C
      </div>
      <div class="label">Office</div>
    </div>
  </div>
  <script>
    /* Reload periodically so OBS picks up re-rendered values */
    setTimeout(() => location.reload(), 60000);
  </script>
</body>
</html>
```

**OBS setup:**

1. In your scene (e.g. *Webcam*): **+** → **Browser Source**
2. URL: `http://homeassistant.local:8123/local/obs-studio/obs-overlay.html`
3. Set width/height to fit the widget (e.g. 220 × 70)
4. Check **"Page is transparent"** / **"Allow transparency"**
5. Drag the source to the desired position in the scene

## Logo

The OBS Studio logo used in this integration is © OBS Project contributors and is licensed
under the [GNU General Public License v2.0](https://github.com/obsproject/obs-studio/blob/master/COPYING).
It is included here solely to identify the integrated software.

## License

[GNU General Public License v3.0](LICENSE)
