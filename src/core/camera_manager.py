import threading
import time
from typing import Dict, Set, List, Optional
import cv2

from .camera_discovery import CameraDiscovery
from .stream_worker import StreamWorker


class CameraManager:
    def __init__(self, discovery: CameraDiscovery, rtsp_paths: List[str], credentials: Dict[str, str], on_frame) -> None:
        self.discovery = discovery
        self.rtsp_paths = rtsp_paths
        self.credentials = credentials
        self.on_frame = on_frame
        self.workers: Dict[str, StreamWorker] = {}
        self.stop_event = threading.Event()

    def _build_candidates(self, ip: str) -> List[str]:
        user = self.credentials.get("username", "") or ""
        pw = self.credentials.get("password", "") or ""
        candidates: List[str] = []
        for pattern in self.rtsp_paths:
            candidates.append(pattern.format(**{"user": user, "pass": pw, "ip": ip}))
        if not candidates:
            candidates.append(f"rtsp://{ip}:554")
        return candidates

    def _probe_rtsp(self, url: str, timeout: float = 2.0) -> bool:
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            cap.release()
            return False
        # Try read one frame quickly
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        try:
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout * 1000)
        except Exception:
            pass
        ret, _ = cap.read()
        cap.release()
        return bool(ret)

    def _select_rtsp(self, ip: str) -> Optional[str]:
        for url in self._build_candidates(ip):
            if self._probe_rtsp(url):
                return url
        return None

    def start(self, interval_sec: int = 20) -> None:
        threading.Thread(target=self._discovery_loop, args=(interval_sec,), daemon=True).start()

    def _discovery_loop(self, interval_sec: int) -> None:
        while not self.stop_event.is_set():
            self._sync_workers()
            time.sleep(interval_sec)

    def _sync_workers(self) -> None:
        ips: Set[str] = self.discovery.discover_ips()
        # Stop workers for removed cameras
        for ip in list(self.workers.keys()):
            if ip not in ips:
                w = self.workers.pop(ip)
                w.stop()
        # Start workers for new cameras
        for ip in ips:
            if ip not in self.workers:
                rtsp = self._select_rtsp(ip)
                if not rtsp:
                    continue
                worker = StreamWorker(ip, rtsp, self.on_frame, threading.Event())
                self.workers[ip] = worker
                worker.start()

    def stop(self) -> None:
        self.stop_event.set()
        for w in list(self.workers.values()):
            w.stop()
