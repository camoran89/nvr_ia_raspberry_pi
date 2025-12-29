import os
import yaml
from typing import Any, Dict


class Config:
    def __init__(self, settings_path: str = "config/settings.yaml", credentials_path: str = "config/secrets.yaml") -> None:
        if not os.path.exists(settings_path):
            raise FileNotFoundError(f"Config not found: {settings_path}")
        with open(settings_path, "r", encoding="utf-8") as f:
            self._cfg: Dict[str, Any] = yaml.safe_load(f) or {}
        # Overlay credentials if present
        # Try secrets.yaml first, fallback to legacy credentials.yaml
        cred_path = credentials_path if os.path.exists(credentials_path) else "config/credentials.yaml"
        if os.path.exists(cred_path):
            with open(cred_path, "r", encoding="utf-8") as f:
                creds = yaml.safe_load(f) or {}

            # Cameras credentials
            camera_cfg = self._cfg.get("camera", {})
            camera_creds = creds.get("cameras", {})
            if "username" in camera_creds:
                camera_cfg["username"] = camera_creds.get("username")
            if "password" in camera_creds:
                camera_cfg["password"] = camera_creds.get("password")
            self._cfg["camera"] = camera_cfg

            # WhatsApp credentials
            if "whatsapp" in creds:
                actions_cfg = self._cfg.get("actions", {})
                actions_cfg["whatsapp"] = creds["whatsapp"]
                self._cfg["actions"] = actions_cfg

            # Safety / delayed alarm configs
            actions_cfg = self._cfg.get("actions", {})
            secrets_actions = creds.get("actions", {})
            if "unknown_alarm_delay_sec" in secrets_actions:
                actions_cfg["unknown_alarm_delay_sec"] = secrets_actions.get("unknown_alarm_delay_sec")
            self._cfg["actions"] = actions_cfg

    def get(self, key: str, default: Any = None) -> Any:
        return self._cfg.get(key, default)

    @property
    def network(self) -> Dict[str, Any]:
        return self._cfg.get("network", {})

    @property
    def camera(self) -> Dict[str, Any]:
        return self._cfg.get("camera", {})

    @property
    def recognition(self) -> Dict[str, Any]:
        return self._cfg.get("recognition", {})

    @property
    def actions(self) -> Dict[str, Any]:
        return self._cfg.get("actions", {})

    @property
    def object_detection(self) -> Dict[str, Any]:
        return self._cfg.get("object_detection", {})

    @property
    def logging(self) -> Dict[str, Any]:
        return self._cfg.get("logging", {})
