import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(__file__))
MODELS = {
    "MobileNetSSD_deploy.prototxt": "https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/MobileNetSSD_deploy.prototxt",
    "MobileNetSSD_deploy.caffemodel": "https://storage.googleapis.com/caffe-models/MobileNetSSD_deploy.caffemodel",
}


def main():
    models_dir = os.path.join(ROOT, "models")
    os.makedirs(models_dir, exist_ok=True)
    for fname, url in MODELS.items():
        dest = os.path.join(models_dir, fname)
        if os.path.exists(dest):
            print(f"Exists: {dest}")
            continue
        print(f"Downloading {fname}...")
        urllib.request.urlretrieve(url, dest)
        print(f"Saved to {dest}")


if __name__ == "__main__":
    main()
