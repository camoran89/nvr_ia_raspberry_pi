import os
import logging
from typing import Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException


class WhatsAppBot:
    """
    Bot de WhatsApp usando Twilio para gestionar elementos desconocidos.
    Envía notificaciones con imágenes y permite comandos para mover a conocidos.
    """

    def __init__(self, account_sid: str, auth_token: str, from_number: str, to_number: str) -> None:
        self.from_number = from_number  # formato: whatsapp:+14155238886
        self.to_number = to_number      # formato: whatsapp:+573001234567
        self.client = Client(account_sid, auth_token) if account_sid and auth_token else None
        self.enabled = self.client is not None

    def send_notification(self, category: str, image_path: str, camera_ip: str, metadata: dict = None) -> bool:
        """
        Envía notificación de elemento desconocido con imagen y menú de opciones.
        
        Args:
            category: 'faces', 'vehicles', 'pets'
            image_path: ruta local a la imagen guardada (o None para solo texto)
            camera_ip: IP de la cámara que detectó
            metadata: dict con info adicional (placa, características, etc)
        """
        if not self.enabled:
            return False
        
        category_emoji = {"faces": "👤", "vehicles": "🚗", "pets": "🐾"}
        emoji = category_emoji.get(category, "❓")
        
        # Construir mensaje
        category_name = {"faces": "Rostro", "vehicles": "Vehículo", "pets": "Mascota"}
        msg_parts = [
            f"{emoji} *{category_name.get(category, 'Elemento')} Desconocido Detectado*",
            f"📷 Cámara: {camera_ip}",
        ]
        
        if metadata:
            if category == "vehicles" and metadata.get("plate"):
                msg_parts.append(f"🚙 Placa detectada: {metadata['plate']}")
            if "features" in metadata:
                features = metadata["features"]
                if "dominant_hue" in features:
                    msg_parts.append(f"🎨 Color HSV: {features['dominant_hue']}, {features['dominant_saturation']}, {features['dominant_value']}")
        
        if image_path and os.path.exists(image_path):
            filename = os.path.basename(image_path)
            msg_parts.append(f"\n_Archivo: {filename}_")
        
        msg_parts.append("\n❓ *¿Es conocido o desconocido?*")
        msg_parts.append("Responde:")
        msg_parts.append("*1* - Conocido (agregar)")
        msg_parts.append("*2* - Desconocido (activar alarma)")
        
        message_body = "\n".join(msg_parts)
        
        try:
            # Enviar con o sin imagen según disponibilidad
            if image_path and os.path.exists(image_path):
                # Nota: file:// no funciona con Twilio
                # En producción, subir a servidor/S3 y usar URL pública
                # Por ahora, enviar solo texto
                message = self.client.messages.create(
                    from_=self.from_number,
                    to=self.to_number,
                    body=message_body + "\n\n⚠️ Imagen guardada localmente (requiere URL pública para envío)"
                )
            else:
                message = self.client.messages.create(
                    from_=self.from_number,
                    to=self.to_number,
                    body=message_body
                )
            logging.info(f"WhatsApp notification sent: {message.sid}")
            return True
        except TwilioRestException as e:
            logging.error(f"WhatsApp send failed: {e}")
            return False

    def send_confirmation(self, entity_type: str, details: dict) -> bool:
        """Envía confirmación personalizada según el tipo de entidad guardada."""
        if not self.enabled:
            return False
        
        try:
            if entity_type == "person":
                msg = f"✅ La persona *{details['name']}* de género *{details['gender']}* ha sido guardada satisfactoriamente en la lista de reconocidos."
            elif entity_type == "vehicle":
                if details.get('plate'):
                    msg = f"✅ Su vehículo (*{details['vehicle_type']}*) de placas *{details['plate']}* fue guardado satisfactoriamente en la lista de reconocidos."
                else:
                    msg = f"✅ Su vehículo (*{details['vehicle_type']}*) de {details['owner']} fue guardado satisfactoriamente en la lista de reconocidos."
            elif entity_type == "pet":
                msg = f"✅ Su mascota *{details['name']}* (*{details['pet_type']}*) ha sido guardada satisfactoriamente en la lista de reconocidos."
            else:
                msg = "✅ Elemento guardado satisfactoriamente."
            
            self.client.messages.create(
                from_=self.from_number,
                to=self.to_number,
                body=msg
            )
            return True
        except TwilioRestException as e:
            logging.error(f"WhatsApp confirmation failed: {e}")
            return False
    
    def send_menu(self, title: str, options: list) -> bool:
        """Envía un menú con opciones numeradas."""
        if not self.enabled:
            return False
        try:
            msg_parts = [f"*{title}*", ""]
            for i, option in enumerate(options, 1):
                msg_parts.append(f"*{i}* - {option}")
            self.client.messages.create(
                from_=self.from_number,
                to=self.to_number,
                body="\n".join(msg_parts)
            )
            return True
        except TwilioRestException as e:
            logging.error(f"WhatsApp menu send failed: {e}")
            return False
    
    def send_text(self, text: str) -> bool:
        """Envía un mensaje de texto simple."""
        if not self.enabled:
            return False
        try:
            self.client.messages.create(
                from_=self.from_number,
                to=self.to_number,
                body=text
            )
            return True
        except TwilioRestException as e:
            logging.error(f"WhatsApp text send failed: {e}")
            return False

    @staticmethod
    def parse_command(message_body: str, category: str) -> Optional[str]:
        """
        Parsea comando de respuesta de WhatsApp.
        Retorna el nombre/ID a asignar o None si no es válido.
        
        Formatos aceptados:
        - "Juan"
        - "/add Juan"
        - "ABC123"
        """
        if not message_body:
            return None
        
        text = message_body.strip()
        
        # Remover prefijo /add si existe
        if text.lower().startswith("/add "):
            text = text[5:].strip()
        
        # Validar que no esté vacío y tenga longitud razonable
        if 1 <= len(text) <= 50:
            return text
        
        return None
