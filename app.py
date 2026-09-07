import os

from face_detector import analyze_face
from face_recognizer import get_face_embedding
from image_fingerprint import generate_fingerprint
from web_search import (
    search_by_image,
    CredentialsError,
    UploadError,
    VisionAPIError,
    WebSearchError,
)
from verify_candidates import verify_web_candidates
from blockchain import (
    register_fingerprint,
    retrieve_fingerprint,
    TransactionError,
    FingerprintNotFoundError,
)
from config import ConfigError


def print_section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def summarize_candidate_audit(candidate_records):
    """
    Aggregate verify_web_candidates()'s per-candidate audit trail into the
    counts app.py needs to display (total / download failures / no face /
    rejected by SFace / verified matches).

    This mirrors the aggregation verify_candidates.py's own CLI (_main)
    already does, rewritten here rather than imported, since _main is a
    private entry point and verify_candidates.py is not to be modified.
    """
    reason_counts = {}
    verified_count = 0

    for record in candidate_records:
        if record["is_face_match"]:
            verified_count += 1
        reason = record["rejection_reason"]
        if reason:
            key = reason.split(":")[0]
            reason_counts[key] = reason_counts.get(key, 0) + 1

    return {
        "total": len(candidate_records),
        "download_failed": reason_counts.get("download_failed", 0),
        "no_face_detected": reason_counts.get("no_face_detected", 0),
        "below_similarity_threshold": reason_counts.get(
            "below_similarity_threshold", 0
        ),
        "verified_count": verified_count,
    }


def print_summary(summary):
    print_section("PIPELINE COMPLETE")

    print(f"Face detected          : {'YES' if summary['face_detected'] else 'NO'}")
    print(f"Face embedding         : {'GENERATED' if summary['embedding_generated'] else 'N/A'}")
    print(f"Input fingerprint      : {'GENERATED' if summary['fingerprint_generated'] else 'N/A'}")
    print(f"Web candidates         : {summary['web_candidates']}")
    print(f"Verified face matches  : {summary['verified_matches']}")

    if summary["best_similarity"] is not None:
        print(f"Best match similarity  : {summary['best_similarity']:.4f}")
    if summary["source_url"]:
        print(f"Source URL             : {summary['source_url']}")
    if summary["tx_hash"]:
        print("Blockchain             : Ethereum Sepolia")
        print(f"Transaction            : {summary['tx_hash']}")
    if summary["blockchain_match"] is not None:
        print(f"Blockchain fingerprint : {'MATCH' if summary['blockchain_match'] else 'MISMATCH'}")

    print(f"FINAL RESULT            : {summary['final_result']}")
    print("=" * 60)
    print(
        "NOTE: 'VERIFIED' means (1) a web candidate passed the configured "
        "SFace similarity threshold, and (2) its fingerprint was recorded "
        "and successfully retrieved from the blockchain. It does NOT mean "
        "the person's real-world identity has been confirmed - only that "
        "this specific image content matched within the tool's threshold "
        "and is now tamper-evidently timestamped on-chain."
    )


def main():

    image_path = input("Enter path to input image: ").strip()

    if not os.path.exists(image_path):
        print("Image does not exist.")
        return

    summary = {
        "face_detected": False,
        "embedding_generated": False,
        "fingerprint_generated": False,
        "web_candidates": 0,
        "verified_matches": 0,
        "best_similarity": None,
        "source_url": None,
        "tx_hash": None,
        "blockchain_match": None,
        "final_result": "NOT VERIFIED",
    }

    # -------------------------------------------------
    # STEP 1 — FACE DETECTION
    # -------------------------------------------------

    print_section("STEP 1: FACE DETECTION")

    try:
        face_result = analyze_face(image_path)
    except FileNotFoundError as exc:
        print(f"Could not read image: {exc}")
        return

    print("Face detected:", face_result["face_detected"])
    print("Number of faces:", face_result["face_count"])

    if not face_result["face_detected"]:
        print("No face detected. Stopping pipeline.")
        return

    summary["face_detected"] = True

    for face in face_result["faces"]:
        print(
            f"Face location: "
            f"x={face['x']} "
            f"y={face['y']} "
            f"w={face['width']} "
            f"h={face['height']}"
        )

    # -------------------------------------------------
    # STEP 1B — SFACE EMBEDDING
    # -------------------------------------------------

    print_section("STEP 1B: FACE EMBEDDING")

    try:
        embedding = get_face_embedding(image_path)
    except FileNotFoundError as exc:
        print(f"Could not read image: {exc}")
        return
    except (ValueError, IndexError) as exc:
        # get_face_embedding() uses face_recognizer.py's own YuNet detector,
        # which is a different detector from the Haar cascade used in STEP 1.
        # They can occasionally disagree on borderline images even though
        # STEP 1 already found a face.
        print(f"Could not generate face embedding: {exc}")
        return

    embedding_dim = embedding.shape[-1] if hasattr(embedding, "shape") else len(embedding)
    print(f"Face embedding generated: {embedding_dim}-dimensional vector.")
    summary["embedding_generated"] = True

    # -------------------------------------------------
    # STEP 2 — INPUT IMAGE FINGERPRINT
    # -------------------------------------------------

    print_section("STEP 2: IMAGE FINGERPRINT")

    input_fingerprint = generate_fingerprint(image_path)

    print("SHA-256:", input_fingerprint["sha256"])
    print("Perceptual hash:", input_fingerprint["phash"])
    summary["fingerprint_generated"] = True

    # -------------------------------------------------
    # STEP 3 — WEB SEARCH
    # -------------------------------------------------

    print_section("STEP 3: WEB SEARCH")

    try:
        candidates = search_by_image(image_path)
    except CredentialsError as exc:
        print(f"[CREDENTIALS ERROR] {exc}")
        return
    except UploadError as exc:
        print(f"[UPLOAD ERROR] {exc}")
        return
    except VisionAPIError as exc:
        print(f"[SEARCH ERROR] {exc}")
        return
    except FileNotFoundError as exc:
        print(f"[FILE ERROR] {exc}")
        return
    except WebSearchError as exc:
        print(f"[ERROR] {exc}")
        return

    print(f"Web candidates found: {len(candidates)}")
    summary["web_candidates"] = len(candidates)

    # -------------------------------------------------
    # STEP 3B — VERIFY CANDIDATES
    # -------------------------------------------------

    print_section("STEP 3B: CANDIDATE VERIFICATION")

    # verify_web_candidates() handles an empty candidate list gracefully on
    # its own (returns matched=False with an empty audit trail), so it is
    # always safe to call here rather than branching on len(candidates).
    try:
        verification = verify_web_candidates(image_path, candidates)
    except FileNotFoundError as exc:
        print(f"[FILE ERROR] {exc}")
        return
    except ValueError as exc:
        # Raised if the SOURCE image has no face detectable by
        # face_recognizer's own detector - see the STEP 1B note above.
        print(f"[SOURCE IMAGE ERROR] {exc}")
        return

    audit = summarize_candidate_audit(verification["candidates"])

    print(f"Total candidates:            {audit['total']}")
    print(f"Download failures:           {audit['download_failed']}")
    print(f"No face detected:            {audit['no_face_detected']}")
    print(f"Rejected by SFace threshold: {audit['below_similarity_threshold']}")
    print(f"Verified matches:            {audit['verified_count']}")
    summary["verified_matches"] = audit["verified_count"]

    if not verification["matched"]:
        print_section("RESULT")
        print("No verified web face match found.")
        print("Blockchain registration skipped: nothing verified to register.")
        summary["final_result"] = "NOT VERIFIED"
        print_summary(summary)
        return

    print(f"Source URL:  {verification['source_url']}")
    print(f"Image URL:   {verification['image_url']}")
    print(f"Similarity:  {verification['similarity']:.4f}")
    print(f"Fingerprint: sha256={verification['fingerprint']['sha256']}")
    print(f"             phash ={verification['fingerprint']['phash']}")

    summary["best_similarity"] = verification["similarity"]
    summary["source_url"] = verification["source_url"]

    # -------------------------------------------------
    # STEP 4 — WINNING CANDIDATE FINGERPRINT
    # -------------------------------------------------

    print_section("STEP 4: WINNING CANDIDATE FINGERPRINT")

    # verify_web_candidates() already called generate_fingerprint() on the
    # winning candidate internally, then deleted its temp file. There is no
    # local copy left here to re-fingerprint, and re-downloading image_url a
    # second time could produce a DIFFERENT fingerprint if the remote file
    # changed between downloads - which would silently break the guarantee
    # that the registered hash matches the exact bytes that were verified.
    # So this step reuses the fingerprint already produced during
    # verification instead of recomputing it.
    winner_fingerprint = verification["fingerprint"]

    print("SHA-256:", winner_fingerprint["sha256"])
    print("Perceptual hash:", winner_fingerprint["phash"])

    # -------------------------------------------------
    # STEP 5 — BLOCKCHAIN REGISTRATION
    # -------------------------------------------------

    print_section("STEP 5: BLOCKCHAIN REGISTRATION")

    try:
        registration = register_fingerprint(winner_fingerprint["sha256"])
    except ConfigError as exc:
        print(f"[CONFIG ERROR] {exc}")
        print_summary(summary)
        return
    except TransactionError as exc:
        print(f"[TRANSACTION ERROR] {exc}")
        print_summary(summary)
        return

    block_number_display = (
        registration["block_number"]
        if registration["block_number"] is not None
        else "pending (not yet confirmed)"
    )
    print("Transaction hash:", registration["tx_hash"])
    print("Status:", registration["status"])
    print("Block number:", block_number_display)
    summary["tx_hash"] = registration["tx_hash"]

    # -------------------------------------------------
    # STEP 6 — BLOCKCHAIN VERIFICATION
    # -------------------------------------------------

    print_section("STEP 6: BLOCKCHAIN VERIFICATION")

    try:
        retrieved = retrieve_fingerprint(registration["tx_hash"])
    except ConfigError as exc:
        print(f"[CONFIG ERROR] {exc}")
        print_summary(summary)
        return
    except FingerprintNotFoundError as exc:
        print(f"[NOT FOUND] {exc}")
        print_summary(summary)
        return
    except TransactionError as exc:
        print(f"[TRANSACTION ERROR] {exc}")
        print_summary(summary)
        return

    blockchain_match = (
        retrieved["sha256_hash"].lower() == winner_fingerprint["sha256"].lower()
    )

    print("Retrieved SHA-256:", retrieved["sha256_hash"])
    print("Confirmed on-chain:", retrieved["confirmed"])
    print("Blockchain fingerprint match:", "MATCH" if blockchain_match else "MISMATCH")

    summary["blockchain_match"] = blockchain_match
    summary["final_result"] = "VERIFIED" if blockchain_match else "NOT VERIFIED"

    print_summary(summary)


if __name__ == "__main__":
    main()