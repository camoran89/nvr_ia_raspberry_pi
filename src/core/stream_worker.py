import threading
import time
from typing import Callable, Any, Optional
import cv2


class StreamWorker(threading.Thread):
    def __init__(self, camera_ip: str, rtsp_url: str, on_frame: Callable[[str, Any], None], stop_event: threading.Event) -> None:
        super().__init__(daemon=True)
        self.camera_ip = camera_ip
        self.rtsp_url = rtsp_url
        self.on_frame = on_frame
        self.stop_event = stop_event
        self.cap: Optional[cv2.VideoCapture] = None

    def run(self) -> None:
        self.cap = cv2.VideoCapture(self.rtsp_url)
        if not self.cap.isOpened():
            return
        while not self.stop_event.is_set():
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.2)
                continue
            h, w = frame.shape[:2]
            if max(h, w) > 960:
                frame = cv2.resize(frame, (w // 2, h // 2))
            try:
                self.on_frame(self.camera_ip, frame)
            except Exception:
                # Avoid breaking the thread on callback errors
                pass
        if self.cap is not None:
            self.cap.release()

    def stop(self) -> None:
        self.stop_event.set()
