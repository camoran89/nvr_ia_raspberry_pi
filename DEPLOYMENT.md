# Guía de Despliegue en Raspberry Pi

Esta guía describe cómo transferir y configurar el sistema de vigilancia inteligente NVR-IA en un Raspberry Pi para que se ejecute automáticamente al inicio.

## Requisitos Previos

### Hardware
- Raspberry Pi 4 (4GB RAM mínimo recomendado)
- Tarjeta microSD (32GB mínimo)
- Switch PoE con las cámaras IP conectadas
- Conexión a internet (para Twilio/WhatsApp)
- Dispositivos Tuya configurados en la red local (luces, alarmas)

### Software en Raspberry Pi
- Raspberry Pi OS (Bullseye o superior) 64-bit
- Python 3.10 o superior
- Git (opcional, para clonar el repositorio)

## Paso 1: Preparar el Raspberry Pi

### 1.1 Actualizar el sistema

```bash
sudo apt update && sudo apt upgrade -y
```

### 1.2 Instalar dependencias del sistema

```bash
sudo apt install -y \
    python3-pip \
    python3-venv \
    libopencv-dev \
    python3-opencv \
    libatlas-base-dev \
    libjasper-dev \
    libqt4-test \
    libhdf5-dev \
    libharfbuzz-dev \
    libwebp-dev \
    git
```

### 1.3 Aumentar swap (recomendado para instalación de OpenCV)

```bash
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Cambiar CONF_SWAPSIZE=100 a CONF_SWAPSIZE=2048
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

## Paso 2: Transferir el Proyecto al Raspberry Pi

### Opción A: Usando Git (recomendado)

```bash
cd ~
git clone <URL_DE_TU_REPOSITORIO> nvr_ia_raspberry_pi
cd nvr_ia_raspberry_pi
```

### Opción B: Transferir por SCP desde Windows

En tu PC Windows (PowerShell):

```powershell
# Comprimir el proyecto (excluye .venv y archivos innecesarios)
$source = "C:\Users\camilo_moran\OneDrive - SATRACK\Documentos\School\nvr_ia_raspberry_pi"
cd $source
tar -czf nvr_ia.tar.gz --exclude=".venv" --exclude="__pycache__" --exclude="*.pyc" --exclude="data/*/unknown/*" *

# Transferir al Raspberry Pi (reemplazar con tu IP)
scp nvr_ia.tar.gz pi@192.168.1.100:~/
```

En el Raspberry Pi:

```bash
cd ~
tar -xzf nvr_ia.tar.gz
mv nvr_ia_raspberry_pi nvr_ia_raspberry_pi  # O el nombre que desees
cd nvr_ia_raspberry_pi
```

### Opción C: Transferir por USB

1. Copia la carpeta del proyecto a una memoria USB (excluye `.venv` y `__pycache__`)
2. Conecta la USB al Raspberry Pi
3. Monta y copia:

```bash
sudo mount /dev/sda1 /mnt
cp -r /mnt/nvr_ia_raspberry_pi ~/
cd ~/nvr_ia_raspberry_pi
```

## Paso 3: Configurar el Entorno Python

### 3.1 Crear entorno virtual

```bash
cd ~/nvr_ia_raspberry_pi
python3 -m venv .venv
source .venv/bin/activate
```

### 3.2 Instalar dependencias

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Nota**: La instalación de OpenCV puede tardar 20-30 minutos en Raspberry Pi.

### 3.3 Descargar modelos de detección

```bash
python scripts/download_models.py
```

### 3.4 Crear estructura de directorios

```bash
python scripts/setup_directories.py
```

## Paso 4: Configurar Credenciales

### 4.1 Editar secrets.yaml

```bash
nano config/secrets.yaml
```

Completa con tus credenciales reales:

```yaml
cameras:
  username: "admin"
  password: "tu_password_real"

whatsapp:
  account_sid: "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  auth_token: "tu_token_real"
  from_number: "whatsapp:+14155238886"
  to_number: "whatsapp:+57XXXXXXXXXX"  # Tu número

tuya:
  devices:
    - device_id: "tu_device_id"
      ip: "192.168.1.50"
      local_key: "tu_local_key"
      name: "Alarma Principal"
      type: "siren"

actions:
  unknown_alarm_delay_sec: 30
```

### 4.2 Configurar settings.yaml (opcional)

```bash
nano config/settings.yaml
```

Ajusta parámetros según necesites (intervalos de detección, umbrales, etc.).

## Paso 5: Configurar ngrok para WhatsApp Webhook

### 5.1 Instalar ngrok

```bash
# Descargar ngrok para ARM64
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm64.tgz
tar -xzf ngrok-v3-stable-linux-arm64.tgz
sudo mv ngrok /usr/local/bin/
```

### 5.2 Configurar token de ngrok

```bash
ngrok config add-authtoken TU_TOKEN_DE_NGROK
```

Obtén tu token en: https://dashboard.ngrok.com/get-started/your-authtoken

### 5.3 Crear servicio systemd para ngrok

```bash
sudo nano /etc/systemd/system/ngrok.service
```

Contenido:

```ini
[Unit]
Description=ngrok secure tunnel
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
ExecStart=/usr/local/bin/ngrok http 5000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Activar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ngrok.service
sudo systemctl start ngrok.service
```

### 5.4 Obtener URL pública de ngrok

```bash
curl http://localhost:4040/api/tunnels
```

Anota la URL pública (ej: `https://abc123.ngrok-free.app`).

### 5.5 Configurar webhook en Twilio

1. Ve a: https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox
2. En "WHEN A MESSAGE COMES IN":
   - URL: `https://abc123.ngrok-free.app/whatsapp`
   - Método: `POST`
3. Guarda los cambios

## Paso 6: Configurar Servicios Systemd para Inicio Automático

### 6.1 Crear servicio para el servidor webhook

```bash
sudo nano /etc/systemd/system/nvr-webhook.service
```

Contenido:

```ini
[Unit]
Description=NVR IA WhatsApp Webhook Server
After=network.target ngrok.service
Requires=ngrok.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/nvr_ia_raspberry_pi
Environment="PATH=/home/pi/nvr_ia_raspberry_pi/.venv/bin"
ExecStart=/home/pi/nvr_ia_raspberry_pi/.venv/bin/python scripts/webhook_whatsapp.py
Restart=always
RestartSec=10
StandardOutput=append:/home/pi/nvr_ia_raspberry_pi/webhook.log
StandardError=append:/home/pi/nvr_ia_raspberry_pi/webhook.log

[Install]
WantedBy=multi-user.target
```

### 6.2 Crear servicio para el sistema principal

```bash
sudo nano /etc/systemd/system/nvr-ia.service
```

Contenido:

```ini
[Unit]
Description=NVR IA Surveillance System
After=network.target nvr-webhook.service
Requires=nvr-webhook.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/nvr_ia_raspberry_pi
Environment="PATH=/home/pi/nvr_ia_raspberry_pi/.venv/bin"
ExecStart=/home/pi/nvr_ia_raspberry_pi/.venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=append:/home/pi/nvr_ia_raspberry_pi/nvr_ia.log
StandardError=append:/home/pi/nvr_ia_raspberry_pi/nvr_ia.log

[Install]
WantedBy=multi-user.target
```

### 6.3 Activar y arrancar servicios

```bash
sudo systemctl daemon-reload
sudo systemctl enable nvr-webhook.service
sudo systemctl enable nvr-ia.service
sudo systemctl start nvr-webhook.service
sudo systemctl start nvr-ia.service
```

## Paso 7: Verificación y Monitoreo

### 7.1 Verificar estado de servicios

```bash
sudo systemctl status nvr-ia.service
sudo systemctl status nvr-webhook.service
sudo systemctl status ngrok.service
```

### 7.2 Ver logs en tiempo real

```bash
# Logs del sistema principal
tail -f ~/nvr_ia_raspberry_pi/nvr_ia.log

# Logs del webhook
tail -f ~/nvr_ia_raspberry_pi/webhook.log

# Logs de systemd
sudo journalctl -u nvr-ia.service -f
sudo journalctl -u nvr-webhook.service -f
```

### 7.3 Probar detección

Colócate frente a una cámara y verifica:
1. Recibes notificación en WhatsApp
2. Puedes responder al menú interactivo
3. Los archivos se mueven de `unknown/` a `known/` correctamente

## Paso 8: Entrenar Reconocedores con Imágenes Reales

### 8.1 Agregar rostros conocidos

```bash
mkdir -p ~/nvr_ia_raspberry_pi/data/faces/known/Juan
mkdir -p ~/nvr_ia_raspberry_pi/data/faces/known/Maria
```

Copia al menos 5-10 fotos de cada persona en su carpeta correspondiente.

### 8.2 Agregar vehículos conocidos

```bash
mkdir -p ~/nvr_ia_raspberry_pi/data/vehicles/known/ABC123
```

Copia fotos del vehículo (diferentes ángulos).

### 8.3 Agregar mascotas conocidas

```bash
mkdir -p ~/nvr_ia_raspberry_pi/data/pets/known/Rex
```

Copia fotos de la mascota.

### 8.4 Reiniciar para reentrenar

```bash
sudo systemctl restart nvr-ia.service
```

El sistema reentrenará automáticamente con las nuevas imágenes al iniciar.

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
