from typing import List, Tuple, Optional, Dict
import os
import cv2
import numpy as np


class PetRecognizer:
    """
    Reconoce mascotas conocidas por características visuales (ORB descriptors).
    Almacena descriptores desde data/pets/known/
    """

    def __init__(self) -> None:
        self.orb = cv2.ORB_create(nfeatures=500)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        self.pet_descriptors: Dict[str, List] = {}
        self.trained = False

    def train_from_dir(self, root_dir: str) -> None:
        """
        Carga imágenes de mascotas conocidas desde subdirectorios.
        Estructura: data/pets/known/Fido/foto1.jpg
        """
        if not os.path.exists(root_dir):
            return
        for pet_name in sorted(os.listdir(root_dir)):
            pet_dir = os.path.join(root_dir, pet_name)
            if not os.path.isdir(pet_dir):
                continue
            descriptors_list = []
            for fname in os.listdir(pet_dir):
                if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue
                path = os.path.join(pet_dir, fname)
                img = cv2.imread(path)
                if img is None:
                    continue
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                kp, des = self.orb.detectAndCompute(gray, None)
                if des is not None and len(des) > 0:
                    descriptors_list.append(des)
            if descriptors_list:
                self.pet_descriptors[pet_name] = descriptors_list
        if self.pet_descriptors:
            self.trained = True

    def recognize(self, frame, bbox: Tuple[int, int, int, int]) -> Tuple[Optional[str], float]:
        """
        Reconoce mascota por descriptores ORB.
        Retorna (pet_name, confidence) o (None, 0.0) si desconocida.
        """
        if not self.trained:
            return (None, 0.0)
        
        x, y, w, h = bbox
        pet_crop = frame[y:y+h, x:x+w]
        if pet_crop.size == 0:
            return (None, 0.0)
        
        gray = cv2.cvtColor(pet_crop, cv2.COLOR_BGR2GRAY)
        kp, des = self.orb.detectAndCompute(gray, None)
        if des is None or len(des) == 0:
            return (None, 0.0)
        
        best_match = None
        best_score = 0.0
        
        for pet_name, desc_list in self.pet_descriptors.items():
            max_matches = 0
            for stored_des in desc_list:
                matches = self.bf.match(des, stored_des)
                if len(matches) > max_matches:
                    max_matches = len(matches)
            
            # Umbral: al menos 25 coincidencias
            if max_matches >= 25:
                score = min(1.0, max_matches / 80.0)
                if score > best_score:
                    best_score = score
                    best_match = pet_name
        
        return (best_match, best_score)

    def extract_features(self, frame, bbox: Tuple[int, int, int, int]) -> Dict[str, any]:
        """
        Extrae características básicas: color dominante, tamaño relativo.
        """
        x, y, w, h = bbox
        pet_crop = frame[y:y+h, x:x+w]
        if pet_crop.size == 0:
            return {}
        
        # Color dominante (promedio HSV)
        hsv = cv2.cvtColor(pet_crop, cv2.COLOR_BGR2HSV)
        avg_color = hsv.mean(axis=(0, 1))
        
        return {
            "bbox_size": (w, h),
            "dominant_hue": int(avg_color[0]),
            "dominant_saturation": int(avg_color[1]),
            "dominant_value": int(avg_color[2]),
        }
