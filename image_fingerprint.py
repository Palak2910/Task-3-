import hashlib
import imagehash
from PIL import Image


def sha256_file(file_path):
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as file:
        while True:
            data = file.read(1024 * 1024)

            if not data:
                break

            sha256.update(data)

    return sha256.hexdigest()


def perceptual_hash(file_path):
    image = Image.open(file_path)
    return str(imagehash.phash(image))


def generate_fingerprint(file_path):
    return {
        "sha256": sha256_file(file_path),
        "phash": perceptual_hash(file_path)
    }