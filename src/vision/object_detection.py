from typing import List, Tuple, Dict
import os
import cv2
import numpy as np


class ObjectDetector:
    """
    MobileNet-SSD (Caffe) object detector via OpenCV DNN.
    Detects: person, car, bus, motorbike, bicycle, train, dog, cat.
    Provide paths to prototxt and caffemodel.
    """

    LABELS = [
        "background", "aeroplane", "bicycle", "bird", "boat", "bottle", "bus",
        "car", "cat", "chair", "cow", "diningtable", "dog", "horse",
        "motorbike", "person", "pottedplant", "sheep", "sofa", "train", "tvmonitor"
    ]

    VEHICLE_CLASSES = {"car", "bus", "motorbike", "bicycle", "train"}
    PET_CLASSES = {"dog", "cat"}

    def __init__(self, prototxt: str, model: str, conf_thresh: float = 0.5) -> None:
        self.available = os.path.exists(prototxt) and os.path.exists(model)
        self.conf_thresh = conf_thresh
        if self.available:
            self.net = cv2.dnn.readNetFromCaffe(prototxt, model)
        else:
            self.net = None

    def detect(self, frame) -> List[Tuple[str, float, Tuple[int, int, int, int]]]:
        results: List[Tuple[str, float, Tuple[int, int, int, int]]] = []
        if not self.available or self.net is None:
            return results
        (h, w) = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5)
        self.net.setInput(blob)
        detections = self.net.forward()
        for i in range(0, detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence < self.conf_thresh:
                continue
            idx = int(detections[0, 0, i, 1])
            label = self.LABELS[idx] if 0 <= idx < len(self.LABELS) else "unknown"
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            (startX, startY, endX, endY) = box.astype("int")
            x, y = max(0, startX), max(0, startY)
            bw, bh = max(0, endX - startX), max(0, endY - startY)
            results.append((label, float(confidence), (x, y, bw, bh)))
        return results

    @staticmethod
    def classify_group(label: str) -> str | None:
        if label in ObjectDetector.VEHICLE_CLASSES:
            return "vehicle"
        if label in ObjectDetector.PET_CLASSES:
            return "pet"
        if label == "person":
            return "person"
        return None
