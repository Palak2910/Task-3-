"""
face_recognizer.py

Face DETECTION (YuNet) + face RECOGNITION/identification (SFace), using
OpenCV's built-in DNN face APIs (cv2.FaceDetectorYN / cv2.FaceRecognizerSF).
This replaces the Haar Cascade detector in face_detector.py, which could only
find bounding boxes and had no concept of "is this the same person".

REQUIRED MODEL FILES (not included here — must be downloaded manually):
    models/face_detection_yunet_2023mar.onnx
    models/face_recognition_sface_2021dec.onnx

Get them from the official OpenCV Model Zoo repo (Apache-2.0 licensed):
    https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
    https://github.com/opencv/opencv_zoo/blob/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx

IMPORTANT: those files are stored via Git LFS. Do NOT curl/wget a raw.githubusercontent.com
URL — that silently returns a small text pointer file, not the real weights, and this
module will refuse to load it (see _assert_real_model_file below). Instead click the
"Download raw file" button on the GitHub page above (it resolves LFS correctly), or
`git lfs install && git clone` the repo if you have git-lfs set up locally.

No extra pip package is needed for the detector/recognizer themselves — both APIs
ship inside opencv-python >= 4.5.4 (already in requirements.txt).
"""

import os
import cv2

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
YUNET_MODEL_PATH = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
SFACE_MODEL_PATH = os.path.join(MODELS_DIR, "face_recognition_sface_2021dec.onnx")

# Cosine-similarity threshold recommended in the OpenCV Zoo SFace docs.
# Two face embeddings scoring at/above this are considered the same person.
SFACE_COSINE_MATCH_THRESHOLD = 0.363

_LFS_POINTER_SIGNATURE = b"version https://git-lfs.github.com"


def _assert_real_model_file(path, friendly_name):
    """Fail loudly and clearly instead of letting OpenCV crash with a cryptic
    error when the model file is missing or is just a Git LFS pointer."""

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{friendly_name} model not found at: {path}\n"
            "Download it from the official OpenCV Model Zoo and place it in "
            "the 'models/' folder next to this file. See the module "
            "docstring at the top of face_recognizer.py for the exact links."
        )

    with open(path, "rb") as f:
        header = f.read(64)

    if header.startswith(_LFS_POINTER_SIGNATURE):
        raise ValueError(
            f"{friendly_name} at {path} is a Git LFS *pointer* file (a few "
            "bytes of text), not the real model. This usually happens when "
            "the file was fetched with curl/wget/raw.githubusercontent.com "
            "instead of a proper LFS-aware download. Re-download using the "
            "'Download raw file' button on the GitHub file page, or "
            "`git lfs pull` if you cloned opencv_zoo with git-lfs installed."
        )

    size_bytes = os.path.getsize(path)
    if size_bytes < 1024:
        raise ValueError(
            f"{friendly_name} at {path} is only {size_bytes} bytes — far too "
            "small to be a real ONNX model. It is likely corrupted or an "
            "incomplete download. Delete it and download it again."
        )


class FaceRecognizer:
    """
    Thin wrapper around OpenCV's YuNet detector and SFace recognizer.

    - detect(image): finds faces + 5 landmarks (eyes, nose, mouth corners)
    - get_embedding(image, raw_face): turns one detected face into a
      128-dim identity vector ("embedding")
    - compare(embedding_a, embedding_b): scores whether two embeddings
      belong to the same person
    """

    def __init__(self, input_size=(320, 320), score_threshold=0.9):
        _assert_real_model_file(YUNET_MODEL_PATH, "YuNet face detection")
        _assert_real_model_file(SFACE_MODEL_PATH, "SFace face recognition")

        self.detector = cv2.FaceDetectorYN_create(
            YUNET_MODEL_PATH,
            "",
            input_size,
            score_threshold=score_threshold,
            nms_threshold=0.3,
            top_k=5000,
        )
        self.recognizer = cv2.FaceRecognizerSF_create(SFACE_MODEL_PATH, "")

    def detect(self, image):
        """
        image: BGR numpy array (e.g. from cv2.imread).
        Returns a list of dicts, one per detected face:
            {x, y, width, height, confidence, landmarks, raw}
        'raw' is YuNet's original 15-value row for that face — required by
        SFace's alignCrop() when extracting an embedding, so keep it around.
        """
        h, w = image.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(image)

        results = []
        if faces is None:
            return results

        for face in faces:
            x, y, bw, bh = face[0:4].astype(int)
            landmarks = face[4:14].reshape(5, 2).astype(int).tolist()
            confidence = float(face[14])
            results.append({
                "x": int(x),
                "y": int(y),
                "width": int(bw),
                "height": int(bh),
                "confidence": confidence,
                "landmarks": landmarks,
                "raw": face,
            })
        return results

    def get_embedding(self, image, raw_face):
        """
        image: BGR numpy array containing the face.
        raw_face: the 'raw' value from a detect() result for that face.
        Returns a 128-dim numpy float embedding.
        """
        aligned = self.recognizer.alignCrop(image, raw_face)
        return self.recognizer.feature(aligned)

    def compare(self, embedding_a, embedding_b):
        """Returns (cosine_score, is_same_person)."""
        score = self.recognizer.match(
            embedding_a, embedding_b, cv2.FaceRecognizerSF_FR_COSINE
        )
        return score, score >= SFACE_COSINE_MATCH_THRESHOLD


_recognizer_singleton = None


def _get_recognizer():
    # Loading the ONNX models is the slow part, so reuse one instance
    # instead of re-loading it on every call.
    global _recognizer_singleton
    if _recognizer_singleton is None:
        _recognizer_singleton = FaceRecognizer()
    return _recognizer_singleton


def analyze_face(image_path):
    """
    Same return shape as face_detector.analyze_face(), so it's a drop-in
    replacement in app.py — plus 'confidence' and 'landmarks' per face:
        {
            "face_detected": bool,
            "face_count": int,
            "faces": [{x, y, width, height, confidence, landmarks}, ...]
        }
    """
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    recognizer = _get_recognizer()
    faces = recognizer.detect(image)

    return {
        "face_detected": len(faces) > 0,
        "face_count": len(faces),
        "faces": [
            {
                "x": f["x"],
                "y": f["y"],
                "width": f["width"],
                "height": f["height"],
                "confidence": f["confidence"],
                "landmarks": f["landmarks"],
            }
            for f in faces
        ],
    }


def get_face_embedding(image_path, face_index=0):
    """
    Detects faces in an image and returns the embedding for one of them
    (default: the first one YuNet returns, generally its most confident).
    Raises ValueError if no face is found, IndexError if face_index is out
    of range.
    """
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    recognizer = _get_recognizer()
    faces = recognizer.detect(image)

    if not faces:
        raise ValueError(f"No face detected in {image_path}")
    if face_index >= len(faces):
        raise IndexError(
            f"Requested face_index={face_index} but only {len(faces)} "
            f"face(s) found in {image_path}"
        )

    return recognizer.get_embedding(image, faces[face_index]["raw"])


def compare_faces(image_path_a, image_path_b):
    """
    High-level identity check: is the (first) face in image A the same
    person as the (first) face in image B?
    Returns {"cosine_score": float, "same_person": bool}
    """
    recognizer = _get_recognizer()
    embedding_a = get_face_embedding(image_path_a)
    embedding_b = get_face_embedding(image_path_b)
    score, same = recognizer.compare(embedding_a, embedding_b)
    return {"cosine_score": float(score), "same_person": bool(same)}
