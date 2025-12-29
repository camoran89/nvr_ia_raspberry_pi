import cv2
import os
from pathlib import Path
from typing import List, Tuple, Optional


class FaceRecognizer:
    """Reconocedor de rostros usando LBPH."""
    
    def __init__(self) -> None:
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.labels = {}
        self.trained = False
    
    def train_from_dir(self, face_dir: str, detector=None) -> None:
        """Entrena el reconocedor con rostros de un directorio."""
        face_dir_path = Path(face_dir)
        if not face_dir_path.exists():
            return
        
        faces_data = []
        labels_data = []
        label_id = 0
        
        for person_dir in face_dir_path.iterdir():
            if not person_dir.is_dir():
                continue
            
            person_name = person_dir.name
            self.labels[label_id] = person_name
            
            for img_file in person_dir.glob("*.jpg") + person_dir.glob("*.png"):
                img = cv2.imread(str(img_file), cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    faces_data.append(img)
                    labels_data.append(label_id)
            
            label_id += 1
        
        if faces_data:
            self.recognizer.train(faces_data, cv2.array(labels_data))
            self.trained = True
    
    def recognize(self, frame, faces: List[Tuple[int, int, int, int]]) -> List[Tuple[Optional[str], float, Tuple[int, int, int, int]]]:
        """Reconoce rostros en un frame. Retorna lista de (nombre, confianza, bbox)."""
        if not self.trained:
            return [(None, 0.0, face) for face in faces]
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        results = []
        
        for (x, y, w, h) in faces:
            roi = gray[y:y+h, x:x+w]
            label, confidence = self.recognizer.predict(roi)
            name = self.labels.get(label)
            # LBPH: menor es mejor, invertir para que mayor sea mejor
            conf_score = max(0, 100 - confidence) / 100.0
            results.append((name, conf_score, (x, y, w, h)))
        
        return results
