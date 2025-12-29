# Modelos de detección (MobileNet-SSD)

Para detección de vehículos y mascotas se usa MobileNet-SSD (Caffe):

- `MobileNetSSD_deploy.prototxt`
- `MobileNetSSD_deploy.caffemodel`

Descarga desde repositorios públicos (por ejemplo, del proyecto original):

- Prototxt: https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/MobileNetSSD_deploy.prototxt
- Caffemodel: https://storage.googleapis.com/caffe-models/MobileNetSSD_deploy.caffemodel

Coloca ambos archivos en esta carpeta `models/`.

Nota: Alternativamente puedes usar otros modelos ONNX con OpenCV DNN, actualizando rutas en `config/settings.yaml`.
