from typing import Any, Dict
import time

try:
    import tinytuya
except Exception:
    tinytuya = None

from .base import ActionEngine


class TuyaActionEngine(ActionEngine):
    """
    Control local Tuya devices via TinyTuya.
    Config expects a dict mapping logical names to device credentials.
    Example:
    devices:
      light:
        device_id: "..."
        ip: "192.168.1.50"
        local_key: "..."
        dps: 1
      alarm:
        device_id: "..."
        ip: "192.168.1.51"
        local_key: "..."
        dps: 1
    """

    def __init__(self, devices: Dict[str, Dict[str, Any]], default_on_seconds: int = 10) -> None:
        self.default_on_seconds = int(default_on_seconds)
        self.devices: Dict[str, Any] = {}
        if tinytuya is None:
            return
        for name, cfg in devices.items():
            dev = tinytuya.OutletDevice(cfg.get("device_id"), cfg.get("ip"), cfg.get("local_key"))
            dev.set_version(float(cfg.get("version", 3.3)))
            dev.set_socketTimeout(2.0)
            # DPS channel index, commonly 1
            dev._dps_index = int(cfg.get("dps", 1))
            self.devices[name] = dev

    def emit(self, event_type: str, payload: Any) -> None:
        # Map event types to actions using 'mapping' in payload or default
        # Default rule: unknown events trigger 'light' ON for N seconds
        target = payload.get("target") or payload.get("device") or "light"
        action = payload.get("action") or "pulse"
        seconds = int(payload.get("seconds", self.default_on_seconds))
        dev = self.devices.get(target)
        if dev is None:
            return
        try:
            if action == "on":
                dev.set_status(True, dev._dps_index)
            elif action == "off":
                dev.set_status(False, dev._dps_index)
            elif action == "pulse":
                dev.set_status(True, dev._dps_index)
                time.sleep(seconds)
                dev.set_status(False, dev._dps_index)
        except Exception:
            # Ignore errors to keep pipeline running
            pass
