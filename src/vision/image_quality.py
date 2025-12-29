import cv2
import numpy as np
import yaml
from pathlib import Path

# Umbrales por defecto (ajustables según necesidad)
DEFAULTS = {
    "min_brightness": 40,   # valor medio en escala de grises
    "max_brightness": 230,  # evita sobreexposición
    "min_sharpness": 120,   # varianza del Laplaciano
    "min_contrast": 20,     # desviación estándar de grises
    "min_size": 48,         # tamaño mínimo del recorte
}


def _load_overrides() -> dict:
    """Carga umbrales desde config/settings.yaml si existen."""
    try:
        cfg_path = Path("config/settings.yaml")
        if not cfg_path.exists():
            return {}
        with cfg_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        quality = data.get("quality", {})
        # Permite override por categoría específica si se desea (face/vehicle/pet)
        return quality if isinstance(quality, dict) else {}
    except Exception:
        return {}


# Aplicar overrides en import
DEFAULTS.update(_load_overrides())


def evaluate(image: np.ndarray, category: str, **kwargs) -> dict:
    """Evalúa la calidad de una imagen recortada.
    Retorna dict con métricas y 'ok': True/False.
    """
    if image is None or image.size == 0:
        return {"ok": False, "reason": "empty"}

    # Parámetros
    params = DEFAULTS.copy()
    params.update(kwargs)

    h, w = image.shape[:2]
    if h < params["min_size"] or w < params["min_size"]:
        return {"ok": False, "reason": "too_small", "h": h, "w": w}

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Brillo y contraste
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))

    # Nitidez (Laplaciano)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    ok = True
    reasons = []

    if brightness < params["min_brightness"]:
        ok = False
        reasons.append("dark")
    if brightness > params["max_brightness"]:
        ok = False
        reasons.append("overexposed")
    if sharpness < params["min_sharpness"]:
        ok = False
        reasons.append("blurry")
    if contrast < params["min_contrast"]:
        ok = False
        reasons.append("low_contrast")

    return {
        "ok": ok,
        "reasons": reasons,
        "brightness": brightness,
        "contrast": contrast,
        "sharpness": sharpness,
        "h": h,
        "w": w,
        "category": category,
    }


def is_good(image: np.ndarray, category: str, **kwargs) -> bool:
    return evaluate(image, category, **kwargs).get("ok", False)
