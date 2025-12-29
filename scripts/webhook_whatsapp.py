"""
Webhook listener para respuestas de WhatsApp con flujo conversacional.
Maneja clasificación guiada de elementos desconocidos.
"""
import os
import sys
import shutil
from pathlib import Path
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import yaml
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.actions.whatsapp_bot import WhatsAppBot
from src.vision.image_quality import is_good
from src.core.capture_session import start_session

app = Flask(__name__)

# Estado conversacional (en producción usar Redis/DB)
# Estructura: {phone_number: {step, category, filename, camera_ip, data}}
conversation_state = {}

def _parse_camera_ip_from_filename(name: str) -> str:
    # name format: YYYYMMDD_HHMMSS_192_168_1_100.jpg
    parts = name.split("_")
    if len(parts) >= 6:
        ip_parts = parts[-4:]
        last = ip_parts[-1]
        if "." in last:
            ip_parts[-1] = last.split(".")[0]
        return ".".join(ip_parts)
    return "unknown"

# Cargar WhatsApp bot para enviar respuestas
with open('config/secrets.yaml', 'r', encoding='utf-8') as f:
    creds = yaml.safe_load(f)['whatsapp']
whatsapp_bot = WhatsAppBot(
    account_sid=creds['account_sid'],
    auth_token=creds['auth_token'],
    from_number=creds['from_number'],
    to_number=creds['to_number']
)


def move_and_rename(category: str, old_filename: str, new_filename: str) -> bool:
    """Mueve archivo de unknown a known con nuevo nombre."""
    base_dir = Path(__file__).parent.parent / "data" / category
    unknown_file = base_dir / "unknown" / old_filename
    
    if not unknown_file.exists():
        return False
    
    # Crear carpeta en known
    known_dir = base_dir / "known" / new_filename.split('_')[0]
    known_dir.mkdir(parents=True, exist_ok=True)
    
    # Mover archivo
    dest_file = known_dir / new_filename
    shutil.copy2(unknown_file, dest_file)
    unknown_file.unlink()
    
    return True


def move_recent_captures(category: str, base_name: str, time_window_seconds: int = 30, max_images: int = 10) -> int:
    """
    Mueve múltiples capturas recientes de unknown a known para entrenar mejor.
    
    Args:
        category: 'faces', 'vehicles' o 'pets'
        base_name: nombre base para los archivos (ej: 'juan_masculino_192_168_1_100')
        time_window_seconds: ventana de tiempo en segundos para considerar capturas recientes
        max_images: máximo de imágenes a mover
    
    Returns:
        Número de imágenes movidas
    """
    base_dir = Path(__file__).parent.parent / "data" / category
    unknown_dir = base_dir / "unknown"
    
    if not unknown_dir.exists():
        return 0
    
    # Obtener todas las imágenes unknown ordenadas por fecha (más recientes primero)
    unknowns = sorted(unknown_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)

    # Filtrar por IP de cámara derivada del base_name para evitar mezclar cámaras
    # base_name ejemplo: juan_masculino_192_168_1_100.png
    parts = base_name.split("_")
    ip_token = None
    if len(parts) >= 4:
        ip_parts = parts[-4:]
        # El último trae extensión .png
        ip_parts[-1] = ip_parts[-1].split(".")[0]
        ip_token = "_".join(ip_parts)
    if ip_token:
        unknowns = [p for p in unknowns if p.name.endswith(f"{ip_token}.jpg")]
    
    if not unknowns:
        return 0
    
    # Obtener timestamp de la imagen más reciente
    latest_time = unknowns[0].stat().st_mtime
    
    # Filtrar imágenes dentro de la ventana temporal
    recent_images = []
    for img in unknowns:
        if (latest_time - img.stat().st_mtime) <= time_window_seconds:
            recent_images.append(img)
        else:
            break  # Ya que están ordenadas, no hay más recientes
        
        if len(recent_images) >= max_images:
            break
    
    # Crear carpeta en known
    name_prefix = base_name.split('_')[0]
    known_dir = base_dir / "known" / name_prefix
    known_dir.mkdir(parents=True, exist_ok=True)
    
    # Mover todas las imágenes recientes con nombres secuenciales
    moved_count = 0
    for idx, img in enumerate(recent_images, start=1):
        # Agregar índice al nombre para evitar colisiones
        name_parts = base_name.rsplit('.', 1)
        if len(name_parts) == 2:
            new_name = f"{name_parts[0]}_{idx:03d}.{name_parts[1]}"
        else:
            new_name = f"{base_name}_{idx:03d}.png"
        
        dest_file = known_dir / new_name
        
        try:
            # Cargar y filtrar por calidad
            import cv2
            image = cv2.imread(str(img))
            if image is None or not is_good(image, category):
                # descartar sin mover si no cumple calidad
                img.unlink()
                continue
            shutil.copy2(img, dest_file)
            img.unlink()
            moved_count += 1
        except Exception as e:
            print(f"Error moviendo {img}: {e}")
            continue
    
    return moved_count


def trigger_alarm():
    """Activa la alarma inmediatamente para desconocidos."""
    # Importar TuyaActionEngine y disparar alarma
    from src.core.config import Config
    from src.actions.tuya import TuyaActionEngine
    
    cfg = Config()
    tuya_cfg = cfg.actions.get("tuya", {})
    action_engine = TuyaActionEngine(
        devices=tuya_cfg.get("devices", {}),
        default_on_seconds=int(tuya_cfg.get("default_on_seconds", 10))
    )
    
    action_engine.emit("alarm_immediate", {
        "target": "alarm",
        "action": "pulse",
        "seconds": 15
    })


@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """Recibe mensajes de WhatsApp y maneja flujo conversacional."""
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")
    
    resp = MessagingResponse()
    msg = resp.message()
    
    if not incoming_msg:
        msg.body("❓ Mensaje vacío. Por favor responde con una opción.")
        return str(resp)
    
    # Obtener o crear estado de conversación
    state = conversation_state.get(from_number, {})
    
    # PASO 1: Clasificación inicial (Conocido / Desconocido)
    if not state or state.get("step") == "initial":
        if incoming_msg == "1":
            # Conocido - pedir tipo
            whatsapp_bot.send_menu("¿Qué tipo de elemento es?", [
                "Persona",
                "Vehículo",
                "Mascota"
            ])
            state = {"step": "ask_type"}
            conversation_state[from_number] = state
            return str(resp)
        elif incoming_msg == "2":
            # Desconocido - activar alarma
            trigger_alarm()
            msg.body("🚨 *Alarma activada* por elemento desconocido.")
            conversation_state.pop(from_number, None)
            return str(resp)
        else:
            msg.body("❓ Opción inválida. Responde *1* (Conocido) o *2* (Desconocido).")
            return str(resp)
    
    # PASO 2: Tipo de elemento (Persona / Vehículo / Mascota)
    elif state.get("step") == "ask_type":
        if incoming_msg == "1":
            # Persona
            state["category"] = "faces"
            state["step"] = "ask_person_name"
            whatsapp_bot.send_text("👤 *Persona*\n\n📝 Escribe el nombre de la persona:")
            conversation_state[from_number] = state
            return str(resp)
        elif incoming_msg == "2":
            # Vehículo
            state["category"] = "vehicles"
            state["step"] = "ask_vehicle_type"
            whatsapp_bot.send_menu("🚗 *Vehículo*\n\n¿Qué tipo de vehículo es?", [
                "Carro",
                "Bicicleta",
                "Motocicleta",
                "Scooter",
                "Otros"
            ])
            conversation_state[from_number] = state
            return str(resp)
        elif incoming_msg == "3":
            # Mascota
            state["category"] = "pets"
            state["step"] = "ask_pet_name"
            whatsapp_bot.send_text("🐾 *Mascota*\n\n📝 Escribe el nombre de la mascota:")
            conversation_state[from_number] = state
            return str(resp)
        else:
            msg.body("❓ Opción inválida. Responde *1*, *2* o *3*.")
            return str(resp)
    
    # FLUJO PERSONA
    elif state.get("step") == "ask_person_name":
        state["name"] = incoming_msg
        state["step"] = "ask_person_gender"
        whatsapp_bot.send_menu("¿Género?", ["Hombre", "Mujer"])
        conversation_state[from_number] = state
        return str(resp)
    
    elif state.get("step") == "ask_person_gender":
        if incoming_msg == "1":
            state["gender"] = "Masculino"
        elif incoming_msg == "2":
            state["gender"] = "Femenino"
        else:
            msg.body("❓ Opción inválida. Responde *1* (Hombre) o *2* (Mujer).")
            return str(resp)
        
        # Guardar persona con múltiples capturas recientes
        camera_ip = state.get("camera_ip", "unknown")
        base_filename = f"{state['name'].lower().replace(' ', '_')}_{state['gender'].lower()}_{camera_ip.replace('.', '_')}.png"
        
        # Mover múltiples capturas de los últimos 30 segundos (máximo 10 imágenes)
        moved_count = move_recent_captures("faces", base_filename, time_window_seconds=30, max_images=10)

        # Iniciar sesión de captura dinámica mientras la cámara siga viendo al objeto
        # Derivar camera_ip desde la última captura unknown si no está en estado
        if camera_ip == "unknown":
            base_dir = Path(__file__).parent.parent / "data" / "faces" / "unknown"
            unknowns = sorted(base_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
            if unknowns:
                camera_ip = _parse_camera_ip_from_filename(unknowns[0].name)
        start_session("faces", camera_ip, base_filename, ttl_sec=10, max_images=50)
        
        if moved_count > 0:
            whatsapp_bot.send_confirmation("person", {
                "name": state['name'],
                "gender": state['gender']
            })
            whatsapp_bot.send_text(f"✅ Se guardaron {moved_count} imágenes para entrenamiento.")
        else:
            msg.body("❌ Error al guardar. No se encontraron imágenes recientes.")
        
        conversation_state.pop(from_number, None)
        return str(resp)
    
    # FLUJO VEHÍCULO
    elif state.get("step") == "ask_vehicle_type":
        vehicle_types = {
            "1": "Carro",
            "2": "Bicicleta",
            "3": "Motocicleta",
            "4": "Scooter",
            "5": "Otros"
        }
        
        if incoming_msg in vehicle_types:
            if incoming_msg == "5":
                state["step"] = "ask_vehicle_other_type"
                whatsapp_bot.send_text("📝 Escribe el tipo de vehículo:")
                conversation_state[from_number] = state
                return str(resp)
            else:
                state["vehicle_type"] = vehicle_types[incoming_msg]
                state["step"] = "ask_vehicle_plate"
                whatsapp_bot.send_text(f"🚗 {vehicle_types[incoming_msg]}\n\n¿Tiene placa? Si sí, escríbela. Si no, escribe el nombre del propietario:")
                conversation_state[from_number] = state
                return str(resp)
        else:
            msg.body("❓ Opción inválida. Responde *1*, *2*, *3*, *4* o *5*.")
            return str(resp)
    
    elif state.get("step") == "ask_vehicle_other_type":
        state["vehicle_type"] = incoming_msg
        state["step"] = "ask_vehicle_plate"
        whatsapp_bot.send_text("¿Tiene placa? Si sí, escríbela. Si no, escribe el nombre del propietario:")
        conversation_state[from_number] = state
        return str(resp)
    
    elif state.get("step") == "ask_vehicle_plate":
        # Determinar si es placa o propietario
        if incoming_msg.replace("-", "").replace(" ", "").isalnum() and len(incoming_msg) <= 10:
            # Probablemente placa
            state["plate"] = incoming_msg.upper()
            new_filename = f"{state['plate']}_{state['vehicle_type'].lower()}_{state.get('camera_ip', 'unknown').replace('.', '_')}.png"
        else:
            # Probablemente propietario
            state["owner"] = incoming_msg
            new_filename = f"{incoming_msg.lower().replace(' ', '_')}_{state['vehicle_type'].lower()}_{state.get('camera_ip', 'unknown').replace('.', '_')}.png"
        
        # Guardar vehículo con múltiples capturas recientes
        moved_count = move_recent_captures("vehicles", new_filename, time_window_seconds=30, max_images=10)

        # Iniciar sesión de captura dinámica
        camera_ip = state.get("camera_ip", "unknown")
        if camera_ip == "unknown":
            base_dir = Path(__file__).parent.parent / "data" / "vehicles" / "unknown"
            unknowns = sorted(base_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
            if unknowns:
                camera_ip = _parse_camera_ip_from_filename(unknowns[0].name)
        start_session("vehicles", camera_ip, new_filename, ttl_sec=10, max_images=50)
        
        if moved_count > 0:
            whatsapp_bot.send_confirmation("vehicle", {
                "vehicle_type": state['vehicle_type'],
                "plate": state.get('plate'),
                "owner": state.get('owner')
            })
            whatsapp_bot.send_text(f"✅ Se guardaron {moved_count} imágenes para entrenamiento.")
        else:
            msg.body("❌ Error al guardar. No se encontraron imágenes recientes.")
        
        conversation_state.pop(from_number, None)
        return str(resp)
    
    # FLUJO MASCOTA
    elif state.get("step") == "ask_pet_name":
        state["name"] = incoming_msg
        state["step"] = "ask_pet_type"
        whatsapp_bot.send_menu("¿Qué tipo de mascota es?", [
            "Perro",
            "Gato",
            "Gallina",
            "Conejo",
            "Cabra",
            "Otros"
        ])
        conversation_state[from_number] = state
        return str(resp)
    
    elif state.get("step") == "ask_pet_type":
        pet_types = {
            "1": "Perro",
            "2": "Gato",
            "3": "Gallina",
            "4": "Conejo",
            "5": "Cabra",
            "6": "Otros"
        }
        
        if incoming_msg in pet_types:
            if incoming_msg == "6":
                state["step"] = "ask_pet_other_type"
                whatsapp_bot.send_text("📝 Escribe el tipo de mascota:")
                conversation_state[from_number] = state
                return str(resp)
            else:
                state["pet_type"] = pet_types[incoming_msg]
                
                # Guardar mascota con múltiples capturas recientes
                camera_ip = state.get("camera_ip", "unknown")
                new_filename = f"{state['name'].lower().replace(' ', '_')}_{state['pet_type'].lower()}_{camera_ip.replace('.', '_')}.png"
                
                moved_count = move_recent_captures("pets", new_filename, time_window_seconds=30, max_images=10)

                # Iniciar sesión de captura dinámica
                cam_ip = state.get("camera_ip", "unknown")
                if cam_ip == "unknown":
                    base_dir = Path(__file__).parent.parent / "data" / "pets" / "unknown"
                    unknowns = sorted(base_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if unknowns:
                        cam_ip = _parse_camera_ip_from_filename(unknowns[0].name)
                start_session("pets", cam_ip, new_filename, ttl_sec=10, max_images=50)
                
                if moved_count > 0:
                    whatsapp_bot.send_confirmation("pet", {
                        "name": state['name'],
                        "pet_type": state['pet_type']
                    })
                    whatsapp_bot.send_text(f"✅ Se guardaron {moved_count} imágenes para entrenamiento.")
                else:
                    msg.body("❌ Error al guardar. No se encontraron imágenes recientes.")
                
                conversation_state.pop(from_number, None)
                return str(resp)
        else:
            msg.body("❓ Opción inválida. Responde *1*, *2*, *3*, *4*, *5* o *6*.")
            return str(resp)
    
    elif state.get("step") == "ask_pet_other_type":
        state["pet_type"] = incoming_msg
        
        # Guardar mascota con múltiples capturas recientes
        camera_ip = state.get("camera_ip", "unknown")
        new_filename = f"{state['name'].lower().replace(' ', '_')}_{state['pet_type'].lower()}_{camera_ip.replace('.', '_')}.png"
        
        moved_count = move_recent_captures("pets", new_filename, time_window_seconds=30, max_images=10)

        # Iniciar sesión de captura dinámica
        cam_ip = state.get("camera_ip", "unknown")
        if cam_ip == "unknown":
            base_dir = Path(__file__).parent.parent / "data" / "pets" / "unknown"
            unknowns = sorted(base_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
            if unknowns:
                cam_ip = _parse_camera_ip_from_filename(unknowns[0].name)
        start_session("pets", cam_ip, new_filename, ttl_sec=10, max_images=50)
        
        if moved_count > 0:
            whatsapp_bot.send_confirmation("pet", {
                "name": state['name'],
                "pet_type": state['pet_type']
            })
            whatsapp_bot.send_text(f"✅ Se guardaron {moved_count} imágenes para entrenamiento.")
        else:
            msg.body("❌ Error al guardar. No se encontraron imágenes recientes.")
        
        conversation_state.pop(from_number, None)
        return str(resp)
    
    # Estado desconocido
    msg.body("❓ Estado de conversación inválido. Por favor inicia de nuevo.")
    conversation_state.pop(from_number, None)
    return str(resp)


if __name__ == "__main__":
    # Producción: usar gunicorn con HTTPS
    # gunicorn -w 4 -b 0.0.0.0:5000 webhook_whatsapp:app
    app.run(host="0.0.0.0", port=5000, debug=False)
