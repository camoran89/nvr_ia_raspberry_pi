#!/bin/bash
#
# Script de instalación automática para NVR-IA en Raspberry Pi
# Ejecutar con: bash setup_raspberry.sh
#

set -e  # Detener en caso de error

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variables
PROJECT_DIR="$HOME/nvr_ia_raspberry_pi"
VENV_DIR="$PROJECT_DIR/.venv"
USER=$(whoami)

# Funciones auxiliares
print_step() {
    echo -e "${BLUE}==>${NC} ${GREEN}$1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ Error: $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Banner
clear
echo -e "${GREEN}"
cat << "EOF"
╔═══════════════════════════════════════════════════╗
║   NVR-IA Raspberry Pi Installer                  ║
║   Sistema de Vigilancia Inteligente              ║
╚═══════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Verificar que estamos en Raspberry Pi
if [ ! -f /proc/device-tree/model ] || ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    print_warning "Este script está diseñado para Raspberry Pi"
    read -p "¿Continuar de todas formas? (s/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        exit 1
    fi
fi

# Verificar que el proyecto existe
if [ ! -d "$PROJECT_DIR" ]; then
    print_error "Directorio del proyecto no encontrado: $PROJECT_DIR"
    echo "Primero clona el repositorio con:"
    echo "git clone https://github.com/camoran89/nvr_ia_raspberry_pi.git ~/nvr_ia_raspberry_pi"
    exit 1
fi

cd "$PROJECT_DIR"
print_success "Directorio del proyecto encontrado"

# Paso 1: Actualizar sistema
print_step "Paso 1/10: Actualizando el sistema..."
sudo apt update
sudo apt upgrade -y
print_success "Sistema actualizado"

# Paso 2: Instalar dependencias del sistema
print_step "Paso 2/10: Instalando dependencias del sistema..."
sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    libopencv-dev \
    python3-opencv \
    libatlas-base-dev \
    libjasper-dev \
    libqt4-test \
    libqtgui4 \
    libhdf5-dev \
    libharfbuzz-dev \
    libwebp-dev \
    libjpeg-dev \
    libtiff-dev \
    git \
    curl
print_success "Dependencias instaladas"

# Paso 3: Aumentar swap si es necesario
print_step "Paso 3/10: Configurando swap..."
CURRENT_SWAP=$(free -m | awk '/^Swap:/ {print $2}')
if [ "$CURRENT_SWAP" -lt 2048 ]; then
    print_warning "Aumentando swap a 2GB (recomendado para instalar OpenCV)"
    sudo dphys-swapfile swapoff
    sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
    sudo dphys-swapfile setup
    sudo dphys-swapfile swapon
    print_success "Swap configurado a 2GB"
else
    print_success "Swap ya está configurado adecuadamente"
fi

# Paso 4: Crear entorno virtual
print_step "Paso 4/10: Creando entorno virtual Python..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    print_success "Entorno virtual creado"
else
    print_success "Entorno virtual ya existe"
fi

# Activar entorno virtual
source "$VENV_DIR/bin/activate"

# Paso 5: Instalar dependencias Python
print_step "Paso 5/10: Instalando dependencias Python (esto puede tardar 20-30 min)..."
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
print_success "Dependencias Python instaladas"

# Paso 6: Descargar modelos
print_step "Paso 6/10: Descargando modelos de detección..."
python scripts/download_models.py
print_success "Modelos descargados"

# Paso 7: Crear estructura de directorios
print_step "Paso 7/10: Creando estructura de directorios..."
python scripts/setup_directories.py
print_success "Estructura de directorios creada"

# Paso 8: Configurar secrets.yaml
print_step "Paso 8/10: Configurando secrets.yaml..."
if [ ! -f "config/secrets.yaml" ]; then
    print_warning "Archivo secrets.yaml no encontrado"
    echo "Se creará una plantilla. Deberás editarlo manualmente con tus credenciales."
    
    cat > config/secrets.yaml << 'EOFYAML'
cameras:
  username: "admin"
  password: "CAMBIAR_PASSWORD"

whatsapp:
  account_sid: "ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
  auth_token: "CAMBIAR_AUTH_TOKEN"
  from_number: "whatsapp:+14155238886"
  to_number: "whatsapp:+57XXXXXXXXXX"

tuya:
  devices:
    - device_id: "CAMBIAR_DEVICE_ID"
      ip: "192.168.1.50"
      local_key: "CAMBIAR_LOCAL_KEY"
      name: "Alarma Principal"
      type: "siren"

actions:
  unknown_alarm_delay_sec: 30
EOFYAML
    
    print_warning "IMPORTANTE: Edita config/secrets.yaml con tus credenciales reales"
    echo "nano config/secrets.yaml"
else
    print_success "secrets.yaml ya existe"
fi

# Paso 9: Instalar y configurar ngrok
print_step "Paso 9/10: Instalando ngrok..."
if ! command -v ngrok &> /dev/null; then
    print_warning "Descargando ngrok..."
    ARCH=$(uname -m)
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
        wget -q https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm64.tgz -O /tmp/ngrok.tgz
    else
        wget -q https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.tgz -O /tmp/ngrok.tgz
    fi
    tar -xzf /tmp/ngrok.tgz -C /tmp/
    sudo mv /tmp/ngrok /usr/local/bin/
    rm /tmp/ngrok.tgz
    print_success "ngrok instalado"
    
    print_warning "Configura tu token de ngrok con:"
    echo "ngrok config add-authtoken TU_TOKEN"
    echo "Obtén tu token en: https://dashboard.ngrok.com/get-started/your-authtoken"
else
    print_success "ngrok ya está instalado"
fi

# Paso 10: Configurar servicios systemd
print_step "Paso 10/10: Configurando servicios systemd..."

# Servicio ngrok
print_warning "Creando servicio ngrok..."
sudo tee /etc/systemd/system/ngrok.service > /dev/null << EOFSERVICE
[Unit]
Description=ngrok secure tunnel
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME
ExecStart=/usr/local/bin/ngrok http 5000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOFSERVICE

# Servicio webhook
print_warning "Creando servicio nvr-webhook..."
sudo tee /etc/systemd/system/nvr-webhook.service > /dev/null << EOFSERVICE
[Unit]
Description=NVR IA WhatsApp Webhook Server
After=network.target ngrok.service
Requires=ngrok.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python scripts/webhook_whatsapp.py
Restart=always
RestartSec=10
StandardOutput=append:$PROJECT_DIR/webhook.log
StandardError=append:$PROJECT_DIR/webhook.log

[Install]
WantedBy=multi-user.target
EOFSERVICE

# Servicio principal
print_warning "Creando servicio nvr-ia..."
sudo tee /etc/systemd/system/nvr-ia.service > /dev/null << EOFSERVICE
[Unit]
Description=NVR IA Surveillance System
After=network.target nvr-webhook.service
Requires=nvr-webhook.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=append:$PROJECT_DIR/nvr_ia.log
StandardError=append:$PROJECT_DIR/nvr_ia.log

[Install]
WantedBy=multi-user.target
EOFSERVICE

# Recargar systemd
sudo systemctl daemon-reload
print_success "Servicios systemd configurados"

# Habilitar servicios (no los iniciamos aún)
sudo systemctl enable ngrok.service
sudo systemctl enable nvr-webhook.service
sudo systemctl enable nvr-ia.service
print_success "Servicios habilitados para inicio automático"

# Configurar logrotate para logs
print_warning "Configurando rotación de logs..."
sudo tee /etc/logrotate.d/nvr-ia > /dev/null << EOFLOGROTATE
$PROJECT_DIR/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    copytruncate
}
EOFLOGROTATE
print_success "Rotación de logs configurada"

# Configurar permisos de secrets.yaml
chmod 600 config/secrets.yaml 2>/dev/null || true

# Banner final
echo ""
echo -e "${GREEN}"
cat << "EOF"
╔═══════════════════════════════════════════════════╗
║   ✓ Instalación Completada                       ║
╚═══════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo ""
echo -e "${YELLOW}PASOS FINALES ANTES DE INICIAR:${NC}"
echo ""
echo "1. Edita tus credenciales:"
echo -e "   ${BLUE}nano ~/nvr_ia_raspberry_pi/config/secrets.yaml${NC}"
echo ""
echo "2. Configura tu token de ngrok:"
echo -e "   ${BLUE}ngrok config add-authtoken TU_TOKEN${NC}"
echo "   Obtén el token en: https://dashboard.ngrok.com/get-started/your-authtoken"
echo ""
echo "3. Inicia los servicios:"
echo -e "   ${BLUE}sudo systemctl start ngrok.service${NC}"
echo -e "   ${BLUE}sudo systemctl start nvr-webhook.service${NC}"
echo -e "   ${BLUE}sudo systemctl start nvr-ia.service${NC}"
echo ""
echo "4. Obtén la URL pública de ngrok:"
echo -e "   ${BLUE}curl http://localhost:4040/api/tunnels${NC}"
echo ""
echo "5. Configura el webhook en Twilio:"
echo "   - URL: https://tu-url-ngrok.app/whatsapp"
echo "   - Método: POST"
echo "   - https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox"
echo ""
echo -e "${YELLOW}COMANDOS ÚTILES:${NC}"
echo ""
echo "Ver estado de servicios:"
echo -e "   ${BLUE}sudo systemctl status nvr-ia.service${NC}"
echo -e "   ${BLUE}sudo systemctl status nvr-webhook.service${NC}"
echo ""
echo "Ver logs en tiempo real:"
echo -e "   ${BLUE}tail -f ~/nvr_ia_raspberry_pi/nvr_ia.log${NC}"
echo -e "   ${BLUE}tail -f ~/nvr_ia_raspberry_pi/webhook.log${NC}"
echo ""
echo "Reiniciar servicios:"
echo -e "   ${BLUE}sudo systemctl restart nvr-ia.service${NC}"
echo ""
echo -e "${GREEN}¡Sistema listo para producción!${NC}"
echo ""
