# Guía de Despliegue en Raspberry Pi

Esta guía describe cómo transferir y configurar el sistema de vigilancia inteligente NVR-IA en un Raspberry Pi para que se ejecute automáticamente al inicio.

## Instalación Rápida (Recomendado)

Si solo quieres instalar y configurar el sistema rápidamente, usa el script automatizado:

```bash
# 1. Clonar el repositorio
cd ~
git clone https://github.com/camoran89/nvr_ia_raspberry_pi.git
cd nvr_ia_raspberry_pi

# 2. Ejecutar el script de instalación automática
bash setup_raspberry.sh
```

El script automatiza:
- ✓ Actualización del sistema
- ✓ Instalación de dependencias (OpenCV, Python, etc.)
- ✓ Configuración de swap (2GB)
- ✓ Creación del entorno virtual Python
- ✓ Instalación de paquetes Python (puede tardar 20-30 min)
- ✓ Descarga de modelos MobileNet-SSD
- ✓ Creación de estructura de directorios
- ✓ Plantilla de secrets.yaml
- ✓ Instalación y configuración de ngrok
- ✓ Configuración de servicios systemd para inicio automático
- ✓ Configuración de rotación de logs

**Después de ejecutar el script:**

1. **Edita tus credenciales:**
   ```bash
   nano ~/nvr_ia_raspberry_pi/config/secrets.yaml
   ```
   Completa con tus datos reales de cámaras, WhatsApp, Tuya y ngrok.

2. **Configura el webhook en Twilio:**
   - Inicia ngrok: `sudo systemctl start ngrok.service`
   - Obtén la URL pública: `curl http://localhost:4040/api/tunnels`
   - Configura en Twilio: https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox
   - URL: `https://tu-url-ngrok.app/whatsapp`
   - Método: `POST`

3. **Inicia los servicios:**
   ```bash
   sudo systemctl start nvr-webhook.service
   sudo systemctl start nvr-ia.service
   ```

4. **Verifica que todo funciona:**
   ```bash
   sudo systemctl status nvr-ia.service
   tail -f ~/nvr_ia_raspberry_pi/nvr_ia.log
   ```

**¡Listo!** El sistema está configurado para arrancar automáticamente cada vez que el Raspberry Pi se encienda.

---

## Entrenar Reconocedores con Imágenes Reales

Una vez instalado el sistema, agrega imágenes de las personas, vehículos y mascotas que deseas reconocer:

### Agregar rostros conocidos

```bash
mkdir -p ~/nvr_ia_raspberry_pi/data/faces/known/Juan
mkdir -p ~/nvr_ia_raspberry_pi/data/faces/known/Maria
```

Copia al menos 5-10 fotos de cada persona en su carpeta correspondiente.

### Agregar vehículos conocidos

```bash
mkdir -p ~/nvr_ia_raspberry_pi/data/vehicles/known/ABC123
```

Copia fotos del vehículo (diferentes ángulos).

### Agregar mascotas conocidas

```bash
mkdir -p ~/nvr_ia_raspberry_pi/data/pets/known/Rex
```

Copia fotos de la mascota.

### Reiniciar para reentrenar

```bash
sudo systemctl restart nvr-ia.service
```

El sistema reentrenará automáticamente con las nuevas imágenes al iniciar.

---

## Calidad de Imagen y Umbrales (Opcional)

El sistema filtra imágenes malas antes de entrenar (muy oscuras, borrosas o con bajo contraste). Puedes ajustar los umbrales en [config/settings.yaml](config/settings.yaml):

```yaml
quality:
   min_brightness: 40   # muy oscuro por debajo
   max_brightness: 230  # sobreexpuesto por encima
   min_contrast: 20     # bajo contraste por debajo
   min_sharpness: 120   # borrosa por debajo
   min_size: 48         # tamaño mínimo del recorte
```

Notas:
- Los umbrales aplican a todas las categorías (persona, vehículo y mascota).
- Si quieres ser más permisivo en exteriores (vehículos), baja `min_sharpness` y/o `min_contrast`.
- Para mejorar rostros, aumenta `min_sharpness` a ~150-200.
- Las imágenes descartadas siguen guardándose en `unknown/` para auditoría, pero no se mueven a `known/`.

## Comandos Útiles

### Reiniciar servicios

```bash
sudo systemctl restart nvr-ia.service
sudo systemctl restart nvr-webhook.service
sudo systemctl restart ngrok.service
```

### Detener servicios

```bash
sudo systemctl stop nvr-ia.service
sudo systemctl stop nvr-webhook.service
```

### Ver logs completos

```bash
cat ~/nvr_ia_raspberry_pi/nvr_ia.log
cat ~/nvr_ia_raspberry_pi/webhook.log
```

### Ejecutar manualmente para debugging

```bash
cd ~/nvr_ia_raspberry_pi
source .venv/bin/activate
python main.py  # Sistema principal
python scripts/webhook_whatsapp.py  # Webhook
```

### Actualizar código

```bash
cd ~/nvr_ia_raspberry_pi
git pull  # Si usas Git
sudo systemctl restart nvr-ia.service
sudo systemctl restart nvr-webhook.service
```

## Solución de Problemas

### Problema: "No se encuentran cámaras"

**Solución**: Verifica la red y credenciales

```bash
# Ping al switch PoE
ping 192.168.1.1

# Verificar credenciales en secrets.yaml
cat config/secrets.yaml
```

### Problema: "OpenCV no se instala"

**Solución**: Usa el paquete precompilado del sistema

```bash
sudo apt install python3-opencv
# En lugar de pip install opencv-contrib-python
```

### Problema: "WhatsApp no responde"

**Solución**: Verifica ngrok y Twilio

```bash
# Ver URL de ngrok
curl http://localhost:4040/api/tunnels | python3 -m json.tool

# Verificar webhook está corriendo
curl http://localhost:5000/health
```

### Problema: "Alta carga de CPU"

**Solución**: Ajusta intervalos de detección

```bash
nano config/settings.yaml
# Aumenta detection_interval_sec de 0.5 a 1 o 2 segundos
```

### Problema: "Alarma no se activa"

**Solución**: Verifica configuración Tuya

```bash
# Prueba manualmente
cd ~/nvr_ia_raspberry_pi
source .venv/bin/activate
python3 -c "
from src.actions.tuya import TuyaActionEngine
from src.core.config import Config
config = Config.from_yaml('config')
tuya = TuyaActionEngine(config)
tuya.emit('unknown_detected', {'detection_type': 'person'})
"
```

## Optimizaciones de Rendimiento

### Reducir uso de CPU

Edita `config/settings.yaml`:

```yaml
detection_interval_sec: 2  # Aumentar de 0.5 a 2 segundos
recognition:
  face:
    confidence_threshold: 70  # Más permisivo = menos procesamiento
```

### Usar solo una cámara inicialmente

Comenta cámaras en `secrets.yaml` para probar con una sola primero.

### Deshabilitar detección de objetos si no es necesaria

Edita `main.py` y comenta las líneas de detección que no uses.

## Mantenimiento Regular

### Backup semanal de imágenes conocidas

```bash
tar -czf ~/backup_known_$(date +%Y%m%d).tar.gz ~/nvr_ia_raspberry_pi/data/*/known/
```

### Limpiar imágenes desconocidas antiguas

```bash
find ~/nvr_ia_raspberry_pi/data/*/unknown/ -type f -mtime +30 -delete
```

### Rotar logs

```bash
sudo nano /etc/logrotate.d/nvr-ia
```

Contenido:

```
/home/pi/nvr_ia_raspberry_pi/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

## Seguridad

1. **Cambiar contraseñas por defecto** de cámaras
2. **Configurar firewall** en el Raspberry Pi:

```bash
sudo apt install ufw
sudo ufw allow 22/tcp  # SSH
sudo ufw allow from 192.168.1.0/24  # Red local
sudo ufw enable
```

3. **Actualizar regularmente**:

```bash
sudo apt update && sudo apt upgrade -y
```

4. **Proteger secrets.yaml**:

```bash
chmod 600 ~/nvr_ia_raspberry_pi/config/secrets.yaml
```

## Próximos Pasos

1. Monitorea los logs durante 24-48 horas para detectar problemas
2. Ajusta umbrales de detección según resultados reales
3. Entrena reconocedores con más imágenes para mejor precisión
4. Configura backup automático de datos importantes
5. Considera agregar más dispositivos Tuya según necesidad

---

**¡Sistema listo para producción!** El Raspberry Pi ahora detectará automáticamente personas, vehículos y mascotas desconocidas, te notificará por WhatsApp con un menú interactivo, y activará acciones automáticas (alarmas, luces) según tu configuración.
