import time
import logging
import os
import threading
from typing import Dict
from pathlib import Path
from datetime import datetime
import cv2

from scripts.setup_directories import ensure_directories
from src.core.config import Config
from src.core.camera_discovery import CameraDiscovery
from src.core.camera_manager import CameraManager
from src.vision.face_detection import FaceDetector
from src.vision.face_recognition import FaceRecognizer
from src.vision.person_detection import PersonDetector
from src.vision.object_detection import ObjectDetector
from src.vision.vehicle_recognition import VehicleRecognizer
from src.vision.pet_recognition import PetRecognizer
from src.actions.tuya import TuyaActionEngine
from src.actions.whatsapp_bot import WhatsAppBot
from src.core.capture_session import is_active, append_image, touch
from src.vision.image_quality import is_good


def setup_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")


def save_unknown(frame, bbox: tuple, camera_ip: str, category: str) -> str:
    """Guarda imagen de elemento desconocido y retorna path."""
    x, y, w, h = bbox
    crop = frame[y:y+h, x:x+w]
    if crop.size == 0:
        return ""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_ip = camera_ip.replace(".", "_")
    filename = f"{timestamp}_{safe_ip}.jpg"
    
    unknown_dir = f"data/{category}/unknown"
    os.makedirs(unknown_dir, exist_ok=True)
    
    filepath = os.path.join(unknown_dir, filename)
    cv2.imwrite(filepath, crop)

    # Dynamic capture: if a session is active for this category+camera,
    # append this frame into known dataset and refresh session activity.
    try:
        if is_active(category, camera_ip):
            # Solo anexar si la imagen cumple criterios de calidad
            if is_good(crop, category):
                append_image(category, camera_ip, Path(filepath))
                touch(category, camera_ip)
    except Exception:
        pass

    return filepath


def build_action_engine(cfg: Dict) -> object:
    tuya_cfg = cfg.get("tuya", {})
    return TuyaActionEngine(devices=tuya_cfg.get("devices", {}), default_on_seconds=int(tuya_cfg.get("default_on_seconds", 10)))


def build_whatsapp_bot(cfg: Dict) -> WhatsAppBot:
    wa_cfg = cfg.get("whatsapp", {})
    return WhatsAppBot(
        account_sid=wa_cfg.get("account_sid", ""),
        auth_token=wa_cfg.get("auth_token", ""),
        from_number=wa_cfg.get("from_number", ""),
        to_number=wa_cfg.get("to_number", "")
    )


def on_frame_factory(face_det: FaceDetector, face_rec: FaceRecognizer, person_det: PersonDetector, obj_det: ObjectDetector | None, vehicle_rec: VehicleRecognizer, pet_rec: PetRecognizer, action_engine, whatsapp_bot: WhatsAppBot, min_conf: float, emit_unknown: bool, unknown_alarm_delay_sec: int):
    def on_frame(camera_ip: str, frame):
        ts = int(time.time() * 1000)

        def schedule_delayed(event_type: str, payload: Dict, delay: int) -> None:
            """Programa la activación de la alarma/luz tras un retraso."""
            def _fire():
                action_engine.emit(event_type, payload)
            t = threading.Timer(delay, _fire)
            t.daemon = True
            t.start()
        # People detection
        people = person_det.detect(frame)
        if people:
            action_engine.emit("person", {"camera_ip": camera_ip, "count": len(people), "ts": ts})
        # Face detection + recognition
        faces = face_det.detect(frame)
        recs = face_rec.recognize(frame, faces)
        for name, conf, (x, y, w, h) in recs:
            if name and conf >= min_conf:
                action_engine.emit("face_known", {"camera_ip": camera_ip, "name": name, "confidence": conf, "bbox": [x, y, w, h], "ts": ts})
            elif emit_unknown:
                saved_path = save_unknown(frame, (x, y, w, h), camera_ip, "faces")
                whatsapp_bot.send_notification("faces", saved_path, camera_ip)
                schedule_delayed(
                    "face_unknown",
                    {"camera_ip": camera_ip, "confidence": conf, "bbox": [x, y, w, h], "ts": ts, "saved_path": saved_path, "target": "alarm", "action": "pulse"},
                    unknown_alarm_delay_sec,
                )
        # Object detection for pets/vehicles with recognition
        if obj_det is not None and obj_det.available:
            objs = obj_det.detect(frame)
            for label, conf, bbox in objs:
                group = obj_det.classify_group(label)
                if group == "vehicle":
                    plate = vehicle_rec.detect_plate(frame, bbox)
                    vehicle_id, rec_conf = vehicle_rec.recognize(frame, bbox, plate)
                    features = vehicle_rec.extract_features(frame, bbox)
                    if vehicle_id and rec_conf >= min_conf:
                        action_engine.emit("vehicle_known", {"camera_ip": camera_ip, "vehicle_id": vehicle_id, "plate": plate, "confidence": rec_conf, "features": features, "bbox": list(bbox), "ts": ts})
                    else:
                        saved_path = save_unknown(frame, bbox, camera_ip, "vehicles")
                        whatsapp_bot.send_notification("vehicles", saved_path, camera_ip, {"plate": plate, "features": features})
                        schedule_delayed(
                            "vehicle_unknown",
                            {"camera_ip": camera_ip, "plate": plate, "features": features, "bbox": list(bbox), "ts": ts, "saved_path": saved_path, "target": "alarm", "action": "pulse", "seconds": 15},
                            unknown_alarm_delay_sec,
                        )
                elif group == "pet":
                    pet_name, rec_conf = pet_rec.recognize(frame, bbox)
                    features = pet_rec.extract_features(frame, bbox)
                    if pet_name and rec_conf >= min_conf:
                        action_engine.emit("pet_known", {"camera_ip": camera_ip, "pet_name": pet_name, "confidence": rec_conf, "features": features, "bbox": list(bbox), "ts": ts})
                    else:
                        saved_path = save_unknown(frame, bbox, camera_ip, "pets")
                        whatsapp_bot.send_notification("pets", saved_path, camera_ip, {"features": features})
                        schedule_delayed(
                            "pet_unknown",
                            {"camera_ip": camera_ip, "features": features, "bbox": list(bbox), "ts": ts, "saved_path": saved_path, "target": "alarm", "action": "pulse"},
                            unknown_alarm_delay_sec,
                        )
    return on_frame


def main() -> None:
    # Ensure directory structure exists
    ensure_directories()
    
    cfg = Config()
    setup_logging(cfg.logging.get("level", "INFO"))

    # Build action engine
    action_engine = build_action_engine(cfg.actions)
    
    # Build WhatsApp bot
    whatsapp_bot = build_whatsapp_bot(cfg.actions)

    # Vision components
    face_det = FaceDetector(min_size=int(cfg.recognition.get("min_face_size", 60)))
    face_rec = FaceRecognizer()
    face_rec.train_from_dir(cfg.recognition.get("face_dir", "data/faces/known"), detector=face_det)
    person_det = PersonDetector()
    # Object detector
    obj_cfg = cfg.get("object_detection", {})
    obj_det = None
    if bool(obj_cfg.get("enabled", True)):
        obj_det = ObjectDetector(
            prototxt=obj_cfg.get("prototxt", "models/MobileNetSSD_deploy.prototxt"),
            model=obj_cfg.get("model", "models/MobileNetSSD_deploy.caffemodel"),
            conf_thresh=float(obj_cfg.get("confidence_threshold", 0.5)),
        )
    # Vehicle recognizer
    vehicle_rec = VehicleRecognizer()
    vehicle_rec.train_from_dir(cfg.recognition.get("vehicle_dir", "data/vehicles/known"))
    # Pet recognizer
    pet_rec = PetRecognizer()
    pet_rec.train_from_dir(cfg.recognition.get("pet_dir", "data/pets/known"))

    # Discovery + manager
    discovery = CameraDiscovery(
        scan_subnets=cfg.network.get("scan_subnets", []),
        ws_enabled=bool(cfg.network.get("ws_discovery_enabled", True)),
        timeout=2.0,
    )
    manager = CameraManager(
        discovery=discovery,
        rtsp_paths=cfg.camera.get("rtsp_paths", []),
        credentials={"username": cfg.camera.get("username", ""), "password": cfg.camera.get("password", "")},
        on_frame=on_frame_factory(
            face_det=face_det,
            face_rec=face_rec,
            person_det=person_det,
            obj_det=obj_det,
            vehicle_rec=vehicle_rec,
            pet_rec=pet_rec,
            action_engine=action_engine,
            whatsapp_bot=whatsapp_bot,
            min_conf=float(cfg.recognition.get("min_confidence", 0.5)),
            emit_unknown=bool(cfg.recognition.get("emit_unknown_face_events", True)),
            unknown_alarm_delay_sec=int(cfg.actions.get("unknown_alarm_delay_sec", 30)),
        ),
    )

    discovery_interval = int(cfg.network.get("discovery_interval_sec", 20))
    manager.start(interval_sec=discovery_interval)

    try:
        logging.info("NVR AI service running. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Stopping...")
        manager.stop()


if __name__ == "__main__":
    main()
