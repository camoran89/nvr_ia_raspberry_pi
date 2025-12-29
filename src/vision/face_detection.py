import cv2


class FaceDetector:
    """Detector de rostros usando Haar Cascade."""
    
    def __init__(self, min_size: int = 60) -> None:
        self.min_size = min_size
        self.classifier = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    
    def detect(self, frame):
        """Detecta rostros en un frame. Retorna lista de (x, y, w, h)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.classifier.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(self.min_size, self.min_size))
        return faces
