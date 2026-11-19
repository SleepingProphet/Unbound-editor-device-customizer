# config.py — load/save button mappings and app settings

import json
import os
import sys
import uuid


def _app_dir() -> str:
    """Return the directory that should hold config.json.
    When running as a PyInstaller bundle sys.frozen is set and sys.executable
    points to the .exe, so we place config.json next to it.
    When running from source, use the script directory as before."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(_app_dir(), 'config.json')

# Action types
ACTION_HOTKEY      = "hotkey"
ACTION_HOLD_KEY    = "hold_key"
ACTION_TOGGLE_HOLD = "toggle_hold"
ACTION_APP_SWITCH  = "app_switch"
ACTION_APP_LAUNCH  = "app_launch"
ACTION_OBS_SCENE   = "obs_scene"
ACTION_OBS_TOGGLE  = "obs_toggle"
ACTION_LAYER_PUSH  = "layer_push"
ACTION_LAYER_POP   = "layer_pop"
ACTION_DIAL_MODE   = "dial_mode"   # sets runtime dial override (sys_vol / app_vol / brightness / normal)
ACTION_NONE        = "none"

OBS_TOGGLE_OPTIONS = ["stream", "record", "mute_mic"]

DEFAULT_LAYER_ID = "default"

DEFAULT_CONFIG = {
    "obs": {
        "host": "localhost",
        "port": 4455,
    },
    "layers": {
        DEFAULT_LAYER_ID: {
            "name": "Default",
            "buttons": {}
        }
    }
}


# ---------------------------------------------------------------------------
# OBS password — kept in the OS keyring, never in config.json
# ---------------------------------------------------------------------------

_KEYRING_SERVICE = "unbound-editor-customizer"
_KEYRING_OBS_USER = "obs-websocket"
_session_obs_password = ""   # fallback when no keyring backend is available


def get_obs_password() -> str:
    """Return the stored OBS password ('' if none)."""
    try:
        import keyring
        pw = keyring.get_password(_KEYRING_SERVICE, _KEYRING_OBS_USER)
        if pw is not None:
            return pw
    except Exception as e:
        print(f'[config] keyring unavailable ({e}); using session-only OBS password')
    return _session_obs_password


def set_obs_password(password: str) -> bool:
    """Store the OBS password in the keyring. Returns False if only kept for this session."""
    global _session_obs_password
    _session_obs_password = password
    try:
        import keyring
        if password:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_OBS_USER, password)
        else:
            try:
                keyring.delete_password(_KEYRING_SERVICE, _KEYRING_OBS_USER)
            except keyring.errors.PasswordDeleteError:
                pass
        return True
    except Exception as e:
        print(f'[config] could not use keyring ({e}); OBS password kept for this session only')
        return False


def load() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return _deep_copy(DEFAULT_CONFIG)
    with open(CONFIG_FILE, 'r') as f:
        data = json.load(f)

    # Migrate old format (top-level "buttons") to layers
    if "buttons" in data and "layers" not in data:
        data["layers"] = {
            DEFAULT_LAYER_ID: {"name": "Default", "buttons": data.pop("buttons")}
        }

    merged = _deep_copy(DEFAULT_CONFIG)
    obs_data = dict(data.get("obs", {}))
    legacy_password = obs_data.pop("password", None)
    merged["obs"].update(obs_data)
    merged["layers"] = data.get("layers", merged["layers"])

    # Migrate: older configs stored the OBS password in plaintext. Move it to the
    # keyring and rewrite the file without it.
    if legacy_password is not None:
        if legacy_password:
            set_obs_password(legacy_password)
        save(merged)
    return merged


def save(config: dict):
    out = dict(config)
    out["obs"] = {k: v for k, v in config.get("obs", {}).items() if k != "password"}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(out, f, indent=2)


def get_button(config: dict, button_name: str, layer_id: str = DEFAULT_LAYER_ID) -> dict:
    return (config["layers"]
            .get(layer_id, {})
            .get("buttons", {})
            .get(button_name, {"action": ACTION_NONE}))


def get_dial_default(config: dict, layer_id: str = DEFAULT_LAYER_ID) -> dict:
    """Return the default dial action for this layer."""
    return (config["layers"]
            .get(layer_id, {})
            .get("dial_default", {"action": "sys_vol", "hw_mode": "Jog", "sensitivity": 100, "app": ""}))


def set_dial_default(config: dict, action: dict, layer_id: str = DEFAULT_LAYER_ID):
    if layer_id not in config["layers"]:
        config["layers"][layer_id] = {"name": layer_id, "buttons": {}}
    config["layers"][layer_id]["dial_default"] = action


def get_dial_sensitivity(config: dict, mode: str, layer_id: str = DEFAULT_LAYER_ID) -> int:
    """Return sensitivity 0-100 for this dial mode (default 100 = max sensitive).
    Migrates old threshold format (1-20) automatically."""
    raw = (config["layers"]
           .get(layer_id, {})
           .get("dial_sensitivity", {})
           .get(mode, None))
    if raw is None:
        return 100
    # Migrate old threshold format (1-20): threshold 1 → 100, threshold 20 → 0
    if raw <= 20:
        return max(0, round(100 - (raw - 1) * 100 / 19))
    return raw  # already 0-100


def set_dial_sensitivity(config: dict, mode: str, threshold: int, layer_id: str = DEFAULT_LAYER_ID):
    if layer_id not in config["layers"]:
        config["layers"][layer_id] = {"name": layer_id, "buttons": {}}
    layer = config["layers"][layer_id]
    layer.setdefault("dial_sensitivity", {})[mode] = threshold


def get_dial_action(config: dict, mode: str, direction: str, layer_id: str = DEFAULT_LAYER_ID) -> dict:
    return (config["layers"]
            .get(layer_id, {})
            .get("dial", {})
            .get(mode, {})
            .get(direction, {"action": ACTION_NONE}))


def set_dial_action(config: dict, mode: str, direction: str, action: dict, layer_id: str = DEFAULT_LAYER_ID):
    if layer_id not in config["layers"]:
        config["layers"][layer_id] = {"name": layer_id, "buttons": {}}
    layer = config["layers"][layer_id]
    if "dial" not in layer:
        layer["dial"] = {}
    if mode not in layer["dial"]:
        layer["dial"][mode] = {}
    layer["dial"][mode][direction] = action


def set_button(config: dict, button_name: str, action: dict, layer_id: str = DEFAULT_LAYER_ID):
    if layer_id not in config["layers"]:
        config["layers"][layer_id] = {"name": layer_id, "buttons": {}}
    config["layers"][layer_id]["buttons"][button_name] = action


def add_layer(config: dict, name: str) -> str:
    layer_id = uuid.uuid4().hex[:8]
    config["layers"][layer_id] = {"name": name, "buttons": {}}
    return layer_id


def delete_layer(config: dict, layer_id: str):
    if layer_id != DEFAULT_LAYER_ID:
        config["layers"].pop(layer_id, None)
        # Remove any layer_push references to the deleted layer
        for lid, layer in config["layers"].items():
            for btn, action in list(layer["buttons"].items()):
                if action.get("action") == ACTION_LAYER_PUSH and action.get("layer") == layer_id:
                    layer["buttons"].pop(btn)


def rename_layer(config: dict, layer_id: str, new_name: str):
    if layer_id in config["layers"]:
        config["layers"][layer_id]["name"] = new_name


def get_layers(config: dict) -> list[tuple[str, str]]:
    """Return [(layer_id, layer_name), ...] sorted with default first."""
    layers = [(k, v["name"]) for k, v in config["layers"].items()]
    layers.sort(key=lambda x: (x[0] != DEFAULT_LAYER_ID, x[1]))
    return layers


# ---------------------------------------------------------------------------
# Per-app layer matching ("match": ["spotify.exe", "com.spotify.client", ...])
# ---------------------------------------------------------------------------

def get_layer_match(config: dict, layer_id: str) -> list:
    return list(config["layers"].get(layer_id, {}).get("match", []))


def set_layer_match(config: dict, layer_id: str, patterns: list):
    layer = config["layers"].get(layer_id)
    if layer is None:
        return
    cleaned = []
    for p in patterns:
        p = str(p).strip()
        if p and p.lower() not in (c.lower() for c in cleaned):
            cleaned.append(p)
    if cleaned and layer_id != DEFAULT_LAYER_ID:
        layer["match"] = cleaned
    else:
        layer.pop("match", None)


def any_layer_has_match(config: dict) -> bool:
    return any(l.get("match") for lid, l in list(config["layers"].items())
               if lid != DEFAULT_LAYER_ID)


def find_layer_for_app(config: dict, app_ids) -> str:
    """First non-default layer whose match list contains one of app_ids, else default.

    Matching is exact but case-insensitive and ignores a trailing .exe / .app.
    """
    from platform_layer.focus import normalize_app_id
    ids = {normalize_app_id(i) for i in app_ids if i}
    if ids:
        for lid, layer in list(config["layers"].items()):
            if lid == DEFAULT_LAYER_ID:
                continue
            for pat in layer.get("match", []):
                if normalize_app_id(pat) in ids:
                    return lid
    return DEFAULT_LAYER_ID


def load_profile_into_working(config: dict, layers: dict):
    """Replace working layers with the given layers dict (deep-copied).
    Ensures the default layer always exists.  Does NOT save to disk."""
    config["layers"] = _deep_copy(layers)
    if DEFAULT_LAYER_ID not in config["layers"]:
        config["layers"][DEFAULT_LAYER_ID] = {"name": "Default", "buttons": {}}


def _deep_copy(d):
    return json.loads(json.dumps(d))
