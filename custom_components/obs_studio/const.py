"""Constants for the OBS Studio integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "obs_studio"
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Config keys
CONF_DISABLE_OFFLINE_REPAIRS = "disable_offline_repairs"
CONF_WS_PORT = "ws_port"
CONF_WS_PASSWORD = "ws_password"
CONF_SSH_ENABLED = "ssh_enabled"
CONF_SSH_HOST = "ssh_host"
CONF_SSH_PORT = "ssh_port"
CONF_SSH_USERNAME = "ssh_username"
CONF_SSH_KEY_PATH = "ssh_key_path"
CONF_SSH_KEY_CONTENT = "ssh_key_content"   # inline private key (alternative to path)
CONF_SSH_KNOWN_HOSTS = "ssh_known_hosts"   # known_hosts entry; blank = skip host key check
CONF_OBS_REMOTE_HOST = "obs_remote_host"

# Defaults
DEFAULT_WS_PORT = 4455
DEFAULT_OBS_REMOTE_HOST = "localhost"
DEFAULT_SSH_ENABLED = False
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USERNAME = "root"
DEFAULT_SSH_KEY_PATH = "/config/.ssh/id_ed25519"
DEFAULT_SCAN_INTERVAL = 10
MIN_SCAN_INTERVAL = 5
DEFAULT_REQUEST_TIMEOUT = 15
DEFAULT_DISABLE_OFFLINE_REPAIRS = False

# Services
SERVICE_SET_SCENE = "set_scene"
SERVICE_START_STREAM = "start_stream"
SERVICE_STOP_STREAM = "stop_stream"
SERVICE_TOGGLE_STREAM = "toggle_stream"
SERVICE_START_RECORD = "start_record"
SERVICE_STOP_RECORD = "stop_record"
SERVICE_TOGGLE_RECORD = "toggle_record"
SERVICE_PAUSE_RECORD = "pause_record"
SERVICE_RESUME_RECORD = "resume_record"
SERVICE_START_VIRTUAL_CAM = "start_virtual_cam"
SERVICE_STOP_VIRTUAL_CAM = "stop_virtual_cam"
SERVICE_START_REPLAY_BUFFER = "start_replay_buffer"
SERVICE_STOP_REPLAY_BUFFER = "stop_replay_buffer"
SERVICE_SAVE_REPLAY_BUFFER = "save_replay_buffer"
SERVICE_TRIGGER_HOTKEY = "trigger_hotkey"
SERVICE_RENDER_TEMPLATES = "render_templates"

# Template overlay rendering
CONF_TEMPLATES = "templates"
CONF_TEMPLATE_NAME = "name"
CONF_TEMPLATE_CONTENT = "content"
CONF_TEMPLATE_FROM_FILE = "from_file"
CONF_TEMPLATE_FILE_PATH = "file_path"
CONF_TEMPLATE_OUTPUT_DIR = "output_dir"
DEFAULT_TEMPLATE_OUTPUT_DIR = "/config/www/obs-studio"
DEFAULT_TEMPLATE_SOURCE_DIR = "/config/obs_studio/templates"

# Attributes
ATTR_SCENE_NAME = "scene_name"
ATTR_HOTKEY_NAME = "hotkey_name"

# Repair issue IDs
REPAIR_CANNOT_CONNECT = "cannot_connect"
REPAIR_AUTH_FAILED = "auth_failed"
REPAIR_SSH_FAILED = "ssh_failed"
