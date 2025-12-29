import cv2


class PersonDetector:
    """Detector de personas usando HOG."""
    
    def __init__(self) -> None:
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    
    def detect(self, frame):
        """Detecta personas en un frame. Retorna lista de bounding boxes."""
        boxes, _ = self.hog.detectMultiScale(frame, winStride=(8, 8), padding=(4, 4), scale=1.05)
        return boxes
