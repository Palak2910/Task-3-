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


def verify_fingerprint(
    original_fingerprint: dict,
    file_path: str,
    phash_max_distance: int = 5
) -> dict:
    current_fingerprint = generate_fingerprint(file_path)
    original_sha256 = original_fingerprint.get("sha256")
    original_phash = original_fingerprint.get("phash")
    if not original_sha256 or not original_phash:
        raise ValueError(
            "original_fingerprint must contain 'sha256' and 'phash'."
        )
    try:
        original_hash = imagehash.hex_to_hash(original_phash)
        current_hash = imagehash.hex_to_hash(
            current_fingerprint["phash"]
        )
    except (TypeError, ValueError):
        raise ValueError("Invalid pHash format in original_fingerprint.")
    sha256_match = bool(
        current_fingerprint["sha256"] == original_sha256
    )
    phash_distance = int(original_hash - current_hash)
    phash_match = bool(phash_distance <= phash_max_distance)
    return {
        "sha256_match": sha256_match,
        "phash_distance": phash_distance,
        "phash_match": phash_match,
        "verified": bool(sha256_match and phash_match),
        "current_fingerprint": current_fingerprint,
    }

