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

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.actions.whatsapp_bot import WhatsAppBot

app = Flask(__name__)

# Estado conversacional (en producción usar Redis/DB)
# Estructura: {phone_number: {step, category, filename, camera_ip, data}}
conversation_state = {}

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
        
        # Guardar persona
        camera_ip = state.get("camera_ip", "unknown")
        new_filename = f"{state['name'].lower().replace(' ', '_')}_{state['gender'].lower()}_{camera_ip.replace('.', '_')}.png"
        
        # Obtener archivo original más reciente
        base_dir = Path(__file__).parent.parent / "data" / "faces" / "unknown"
        unknowns = sorted(base_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
        if unknowns:
            success = move_and_rename("faces", unknowns[0].name, new_filename)
            if success:
                whatsapp_bot.send_confirmation("person", {
                    "name": state['name'],
                    "gender": state['gender']
                })
            else:
                msg.body("❌ Error al guardar. Archivo no encontrado.")
        
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
        
        # Guardar vehículo
        base_dir = Path(__file__).parent.parent / "data" / "vehicles" / "unknown"
        unknowns = sorted(base_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
        if unknowns:
            success = move_and_rename("vehicles", unknowns[0].name, new_filename)
            if success:
                whatsapp_bot.send_confirmation("vehicle", {
                    "vehicle_type": state['vehicle_type'],
                    "plate": state.get('plate'),
                    "owner": state.get('owner')
                })
            else:
                msg.body("❌ Error al guardar. Archivo no encontrado.")
        
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
                
                # Guardar mascota
                camera_ip = state.get("camera_ip", "unknown")
                new_filename = f"{state['name'].lower().replace(' ', '_')}_{state['pet_type'].lower()}_{camera_ip.replace('.', '_')}.png"
                
                base_dir = Path(__file__).parent.parent / "data" / "pets" / "unknown"
                unknowns = sorted(base_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
                if unknowns:
                    success = move_and_rename("pets", unknowns[0].name, new_filename)
                    if success:
                        whatsapp_bot.send_confirmation("pet", {
                            "name": state['name'],
                            "pet_type": state['pet_type']
                        })
                    else:
                        msg.body("❌ Error al guardar. Archivo no encontrado.")
                
                conversation_state.pop(from_number, None)
                return str(resp)
        else:
            msg.body("❓ Opción inválida. Responde *1*, *2*, *3*, *4*, *5* o *6*.")
            return str(resp)
    
    elif state.get("step") == "ask_pet_other_type":
        state["pet_type"] = incoming_msg
        
        # Guardar mascota
        camera_ip = state.get("camera_ip", "unknown")
        new_filename = f"{state['name'].lower().replace(' ', '_')}_{state['pet_type'].lower()}_{camera_ip.replace('.', '_')}.png"
        
        base_dir = Path(__file__).parent.parent / "data" / "pets" / "unknown"
        unknowns = sorted(base_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
        if unknowns:
            success = move_and_rename("pets", unknowns[0].name, new_filename)
            if success:
                whatsapp_bot.send_confirmation("pet", {
                    "name": state['name'],
                    "pet_type": state['pet_type']
                })
            else:
                msg.body("❌ Error al guardar. Archivo no encontrado.")
        
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
