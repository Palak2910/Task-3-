import hashlib


def hash_string(data):
    return hashlib.sha256(
        data.encode("utf-8")
    ).hexdigest()


def verify_local_hash(
    original_hash,
    current_data
):

    current_hash = hash_string(current_data)

    return {
        "original_hash": original_hash,
        "current_hash": current_hash,
        "verified": original_hash == current_hash
    }