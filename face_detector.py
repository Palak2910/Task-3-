import cv2


def detect_faces(image_path):
    image = cv2.imread(image_path)

    if image is None:
        raise FileNotFoundError(
            f"Could not read image: {image_path}"
        )

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades +
        "haarcascade_frontalface_default.xml"
    )

    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(50, 50)
    )

    return image, faces


def analyze_face(image_path):
    image, faces = detect_faces(image_path)

    result = {
        "face_detected": len(faces) > 0,
        "face_count": len(faces),
        "faces": []
    }

    for (x, y, w, h) in faces:
        result["faces"].append({
            "x": int(x),
            "y": int(y),
            "width": int(w),
            "height": int(h)
        })

    return result