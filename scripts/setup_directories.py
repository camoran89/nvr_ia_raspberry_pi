import os
from pathlib import Path


def ensure_directories():
    """Crea la estructura de carpetas necesaria para el proyecto si no existen."""
    base_dirs = [
        "config",
        "data/faces/known",
        "data/faces/unknown",
        "data/vehicles/known",
        "data/vehicles/unknown",
        "data/pets/known",
        "data/pets/unknown",
        "models",
        "scripts",
        "src/core",
        "src/vision",
        "src/actions",
    ]
    
    for dir_path in base_dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    # Create .gitkeep in empty directories to preserve structure
    for dir_path in ["data/faces/known", "data/faces/unknown", 
                      "data/vehicles/known", "data/vehicles/unknown",
                      "data/pets/known", "data/pets/unknown"]:
        gitkeep = Path(dir_path) / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()


if __name__ == "__main__":
    ensure_directories()
    print("✓ Estructura de carpetas creada exitosamente")
