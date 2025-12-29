from typing import List, Tuple, Optional, Dict
import os
import cv2
import numpy as np
import re


class VehicleRecognizer:
    """
    Reconoce vehículos conocidos por características visuales y placas.
    Almacena descriptores de vehículos conocidos desde data/vehicles/known/
    """

    def __init__(self) -> None:
        self.orb = cv2.ORB_create(nfeatures=500)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        self.vehicle_descriptors: Dict[str, List] = {}
        self.trained = False

    def train_from_dir(self, root_dir: str) -> None:
        """
        Carga imágenes de vehículos conocidos desde subdirectorios.
        Estructura: data/vehicles/known/PLACA_ABC123/foto1.jpg
        """
        if not os.path.exists(root_dir):
            return
        for vehicle_id in sorted(os.listdir(root_dir)):
            vehicle_dir = os.path.join(root_dir, vehicle_id)
            if not os.path.isdir(vehicle_dir):
                continue
            descriptors_list = []
            for fname in os.listdir(vehicle_dir):
                if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue
                path = os.path.join(vehicle_dir, fname)
                img = cv2.imread(path)
                if img is None:
                    continue
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                kp, des = self.orb.detectAndCompute(gray, None)
                if des is not None and len(des) > 0:
                    descriptors_list.append(des)
            if descriptors_list:
                self.vehicle_descriptors[vehicle_id] = descriptors_list
        if self.vehicle_descriptors:
            self.trained = True

    def recognize(self, frame, bbox: Tuple[int, int, int, int], plate_text: Optional[str] = None) -> Tuple[Optional[str], float]:
        """
        Reconoce vehículo por descriptores ORB y/o placa detectada.
        Retorna (vehicle_id, confidence) o (None, 0.0) si desconocido.
        """
        if not self.trained:
            return (None, 0.0)
        
        x, y, w, h = bbox
        vehicle_crop = frame[y:y+h, x:x+w]
        if vehicle_crop.size == 0:
            return (None, 0.0)
        
        gray = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)
        kp, des = self.orb.detectAndCompute(gray, None)
        if des is None or len(des) == 0:
            return (None, 0.0)
        
        best_match = None
        best_score = 0.0
        
        for vehicle_id, desc_list in self.vehicle_descriptors.items():
            # Match por placa si disponible
            if plate_text and plate_text.upper() in vehicle_id.upper():
                return (vehicle_id, 0.95)
            
            # Match por características visuales
            max_matches = 0
            for stored_des in desc_list:
                matches = self.bf.match(des, stored_des)
                if len(matches) > max_matches:
                    max_matches = len(matches)
            
            # Umbral: al menos 30 coincidencias
            if max_matches >= 30:
                score = min(1.0, max_matches / 100.0)
                if score > best_score:
                    best_score = score
                    best_match = vehicle_id
        
        return (best_match, best_score)

    def detect_plate(self, frame, bbox: Tuple[int, int, int, int]) -> Optional[str]:
        """
        Detecta placa de vehículo usando OCR simple (Tesseract no incluido).
        Retorna texto de placa o None.
        Nota: Requiere pytesseract para producción.
        """
        x, y, w, h = bbox
        vehicle_crop = frame[y:y+h, x:x+w]
        if vehicle_crop.size == 0:
            return None
        
        # Preprocesamiento para detectar región de placa
        gray = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)
        # Buscar regiones rectangulares que puedan ser placas
        # Implementación básica sin Tesseract: retorna None
        # Para producción: integrar pytesseract aquí
        return None

    def extract_features(self, frame, bbox: Tuple[int, int, int, int]) -> Dict[str, any]:
        """
        Extrae características básicas del vehículo: color dominante, tamaño relativo.
        """
        x, y, w, h = bbox
        vehicle_crop = frame[y:y+h, x:x+w]
        if vehicle_crop.size == 0:
            return {}
        
        # Color dominante (promedio HSV)
        hsv = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2HSV)
        avg_color = hsv.mean(axis=(0, 1))
        
        return {
            "bbox_size": (w, h),
            "dominant_hue": int(avg_color[0]),
            "dominant_saturation": int(avg_color[1]),
            "dominant_value": int(avg_color[2]),
        }
