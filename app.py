import os

from face_detector import analyze_face
from image_fingerprint import generate_fingerprint


def print_section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main():

    image_path = input(
        "Enter path to input image: "
    ).strip()

    if not os.path.exists(image_path):
        print("Image does not exist.")
        return

    # -------------------------------------------------
    # STEP 1 — FACE DETECTION
    # -------------------------------------------------

    print_section("STEP 1: FACE DETECTION")

    face_result = analyze_face(image_path)

    print(
        "Face detected:",
        face_result["face_detected"]
    )

    print(
        "Number of faces:",
        face_result["face_count"]
    )

    if not face_result["face_detected"]:
        print("No face detected.")
        return

    for face in face_result["faces"]:
        print(
            f"Face location: "
            f"x={face['x']} "
            f"y={face['y']} "
            f"w={face['width']} "
            f"h={face['height']}"
        )

    # -------------------------------------------------
    # STEP 2 — FINGERPRINT
    # -------------------------------------------------

    print_section("STEP 2: IMAGE FINGERPRINT")

    fingerprint = generate_fingerprint(
        image_path
    )

    print(
        "SHA-256:",
        fingerprint["sha256"]
    )

    print(
        "Perceptual hash:",
        fingerprint["phash"]
    )

    # -------------------------------------------------
    # STEP 3 — SEARCH
    # -------------------------------------------------

    print_section("STEP 3: WEB SEARCH")

    print(
        "Search stage ready."
    )

    print(
        "Use an authorized image/content search "
        "source here to locate the corresponding "
        "permitted public post."
    )

    # -------------------------------------------------
    # STEP 4 — BLOCKCHAIN
    # -------------------------------------------------

    print_section("STEP 4: BLOCKCHAIN")

    print(
        "Blockchain registration module ready."
    )

    print(
        "The discovered content should be hashed "
        "and that hash registered on the testnet."
    )

    # -------------------------------------------------
    # STEP 5 — VERIFICATION
    # -------------------------------------------------

    print_section("STEP 5: VERIFICATION")

    print(
        "Recalculate the content hash and compare "
        "it with the on-chain hash."
    )

    print_section("PIPELINE COMPLETE")

    print("Face detected        : YES")
    print("Fingerprint generated: YES")
    print("Search stage         : READY")
    print("Blockchain stage     : READY")
    print("Verification stage   : READY")


if __name__ == "__main__":
    main()