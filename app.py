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
    counts the pipeline needs to display (total / download failures /
    no face / invalid image / rejected by SFace / verified matches).

    This mirrors the aggregation verify_candidates.py's own CLI (_main)
    already does, rewritten here rather than imported, since _main is a
    private entry point and verify_candidates.py is not to be modified
    beyond the two fixes applied to it directly.
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
        "invalid_image": reason_counts.get("invalid_image", 0),
        "below_similarity_threshold": reason_counts.get(
            "below_similarity_threshold", 0
        ),
        "verified_count": verified_count,
    }


def _new_result():
    """Baseline result dict returned by run_pipeline() from every exit
    point, so callers (CLI or future API) always get a consistent shape."""
    return {
        "error": None,
        "error_stage": None,
        "face_detected": False,
        "face_count": 0,
        "embedding_generated": False,
        "embedding_dim": None,
        "input_fingerprint": None,
        "web_candidates": 0,
        "candidate_audit": None,
        "verified_matches": 0,
        "best_similarity": None,
        "source_url": None,
        "image_url": None,
        "winner_fingerprint": None,
        "registration": None,
        "retrieved": None,
        "blockchain_match": None,
        "final_result": "NOT VERIFIED",
    }


def print_summary(result):
    print_section("PIPELINE COMPLETE")

    print(f"Face detected          : {'YES' if result['face_detected'] else 'NO'}")
    print(f"Face embedding         : {'GENERATED' if result['embedding_generated'] else 'N/A'}")
    print(f"Input fingerprint      : {'GENERATED' if result['input_fingerprint'] else 'N/A'}")
    print(f"Web candidates         : {result['web_candidates']}")
    print(f"Verified face matches  : {result['verified_matches']}")

    if result["best_similarity"] is not None:
        print(f"Best match similarity  : {result['best_similarity']:.4f}")
    if result["source_url"]:
        print(f"Source URL             : {result['source_url']}")
    if result["registration"]:
        print("Blockchain             : Ethereum Sepolia")
        print(f"Transaction            : {result['registration']['tx_hash']}")
    if result["blockchain_match"] is not None:
        print(f"Blockchain fingerprint : {'MATCH' if result['blockchain_match'] else 'MISMATCH'}")

    print(f"FINAL RESULT            : {result['final_result']}")
    print("=" * 60)
    print(
        "NOTE: 'VERIFIED' means (1) a web candidate passed the configured "
        "SFace similarity threshold, and (2) its fingerprint was recorded "
        "and successfully retrieved from a CONFIRMED blockchain transaction. "
        "It does NOT mean the person's real-world identity has been "
        "confirmed - only that this specific image content matched within "
        "the tool's threshold and is now tamper-evidently timestamped "
        "on-chain."
    )


def run_pipeline(image_path):
    """
    Runs the full detection -> embedding -> fingerprint -> search ->
    verification -> blockchain pipeline for a single image and returns a
    result dict (see _new_result() for the shape). Never raises for
    expected failure modes - each stage's known exceptions are caught and
    turned into result["error"] / result["error_stage"] instead, so this
    function is safe for a non-interactive caller (e.g. a future Flask
    endpoint) as well as the CLI below.

    This still contains all of main()'s original print() calls, so running
    it from the CLI produces identical output to before. A caller that
    doesn't want console output (e.g. a web server) can redirect stdout,
    but the RETURN VALUE is the actual data contract.
    """

    result = _new_result()

    if not os.path.exists(image_path):
        print("Image does not exist.")
        result["error"] = "Image does not exist."
        result["error_stage"] = "input"
        return result

    # -------------------------------------------------
    # STEP 1 — FACE DETECTION
    # -------------------------------------------------

    print_section("STEP 1: FACE DETECTION")

    try:
        face_result = analyze_face(image_path)
    except FileNotFoundError as exc:
        print(f"Could not read image: {exc}")
        result["error"] = str(exc)
        result["error_stage"] = "face_detection"
        return result

    print("Face detected:", face_result["face_detected"])
    print("Number of faces:", face_result["face_count"])

    result["face_count"] = face_result["face_count"]

    if not face_result["face_detected"]:
        print("No face detected. Stopping pipeline.")
        result["error"] = "No face detected."
        result["error_stage"] = "face_detection"
        return result

    result["face_detected"] = True

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
        result["error"] = str(exc)
        result["error_stage"] = "face_embedding"
        return result
    except (ValueError, IndexError) as exc:
        # get_face_embedding() uses face_recognizer.py's own YuNet detector,
        # a different detector from the Haar cascade used in STEP 1. They
        # can occasionally disagree on borderline images even though STEP 1
        # already found a face.
        print(f"Could not generate face embedding: {exc}")
        result["error"] = str(exc)
        result["error_stage"] = "face_embedding"
        return result

    embedding_dim = embedding.shape[-1] if hasattr(embedding, "shape") else len(embedding)
    print(f"Face embedding generated: {embedding_dim}-dimensional vector.")
    result["embedding_generated"] = True
    result["embedding_dim"] = int(embedding_dim)

    # -------------------------------------------------
    # STEP 2 — INPUT IMAGE FINGERPRINT
    # -------------------------------------------------

    print_section("STEP 2: IMAGE FINGERPRINT")

    input_fingerprint = generate_fingerprint(image_path)

    print("SHA-256:", input_fingerprint["sha256"])
    print("Perceptual hash:", input_fingerprint["phash"])
    result["input_fingerprint"] = input_fingerprint

    # -------------------------------------------------
    # STEP 3 — WEB SEARCH
    # -------------------------------------------------

    print_section("STEP 3: WEB SEARCH")

    try:
        candidates = search_by_image(image_path)
    except CredentialsError as exc:
        print(f"[CREDENTIALS ERROR] {exc}")
        result["error"] = str(exc)
        result["error_stage"] = "web_search"
        return result
    except UploadError as exc:
        print(f"[UPLOAD ERROR] {exc}")
        result["error"] = str(exc)
        result["error_stage"] = "web_search"
        return result
    except VisionAPIError as exc:
        print(f"[SEARCH ERROR] {exc}")
        result["error"] = str(exc)
        result["error_stage"] = "web_search"
        return result
    except FileNotFoundError as exc:
        print(f"[FILE ERROR] {exc}")
        result["error"] = str(exc)
        result["error_stage"] = "web_search"
        return result
    except WebSearchError as exc:
        print(f"[ERROR] {exc}")
        result["error"] = str(exc)
        result["error_stage"] = "web_search"
        return result

    print(f"Web candidates found: {len(candidates)}")
    result["web_candidates"] = len(candidates)

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
        result["error"] = str(exc)
        result["error_stage"] = "candidate_verification"
        return result
    except ValueError as exc:
        # Raised if the SOURCE image has no face detectable by
        # face_recognizer's own detector - see the STEP 1B note above.
        print(f"[SOURCE IMAGE ERROR] {exc}")
        result["error"] = str(exc)
        result["error_stage"] = "candidate_verification"
        return result

    audit = summarize_candidate_audit(verification["candidates"])
    result["candidate_audit"] = audit

    print(f"Total candidates:            {audit['total']}")
    print(f"Download failures:           {audit['download_failed']}")
    print(f"No face detected:            {audit['no_face_detected']}")
    print(f"Invalid/corrupt images:      {audit['invalid_image']}")
    print(f"Rejected by SFace threshold: {audit['below_similarity_threshold']}")
    print(f"Verified matches:            {audit['verified_count']}")
    result["verified_matches"] = audit["verified_count"]

    if not verification["matched"]:
        print_section("RESULT")
        print("No verified web face match found.")
        print("Blockchain registration skipped: nothing verified to register.")
        result["final_result"] = "NOT VERIFIED"
        print_summary(result)
        return result

    print(f"Source URL:  {verification['source_url']}")
    print(f"Image URL:   {verification['image_url']}")
    print(f"Similarity:  {verification['similarity']:.4f}")
    print(f"Fingerprint: sha256={verification['fingerprint']['sha256']}")
    print(f"             phash ={verification['fingerprint']['phash']}")

    result["best_similarity"] = verification["similarity"]
    result["source_url"] = verification["source_url"]
    result["image_url"] = verification["image_url"]

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
    result["winner_fingerprint"] = winner_fingerprint

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
        result["error"] = str(exc)
        result["error_stage"] = "blockchain_registration"
        print_summary(result)
        return result
    except TransactionError as exc:
        print(f"[TRANSACTION ERROR] {exc}")
        result["error"] = str(exc)
        result["error_stage"] = "blockchain_registration"
        print_summary(result)
        return result

    block_number_display = (
        registration["block_number"]
        if registration["block_number"] is not None
        else "pending (not yet confirmed)"
    )
    print("Transaction hash:", registration["tx_hash"])
    print("Status:", registration["status"])
    print("Block number:", block_number_display)
    result["registration"] = registration

    # -------------------------------------------------
    # STEP 6 — BLOCKCHAIN VERIFICATION
    # -------------------------------------------------

    print_section("STEP 6: BLOCKCHAIN VERIFICATION")

    try:
        retrieved = retrieve_fingerprint(registration["tx_hash"])
    except ConfigError as exc:
        print(f"[CONFIG ERROR] {exc}")
        result["error"] = str(exc)
        result["error_stage"] = "blockchain_retrieval"
        print_summary(result)
        return result
    except FingerprintNotFoundError as exc:
        print(f"[NOT FOUND] {exc}")
        result["error"] = str(exc)
        result["error_stage"] = "blockchain_retrieval"
        print_summary(result)
        return result
    except TransactionError as exc:
        print(f"[TRANSACTION ERROR] {exc}")
        result["error"] = str(exc)
        result["error_stage"] = "blockchain_retrieval"
        print_summary(result)
        return result

    result["retrieved"] = retrieved

    blockchain_match = (
        retrieved["sha256_hash"].lower() == winner_fingerprint["sha256"].lower()
    )

    print("Retrieved SHA-256:", retrieved["sha256_hash"])
    print("Confirmed on-chain:", retrieved["confirmed"])
    print("Blockchain fingerprint match:", "MATCH" if blockchain_match else "MISMATCH")

    if blockchain_match and not retrieved["confirmed"]:
        print(
            "Hash matches, but the transaction is not yet confirmed on-chain "
            "- not treated as VERIFIED until it is."
        )

    result["blockchain_match"] = blockchain_match

    # FINAL RESULT requires BOTH a matching hash AND on-chain confirmation.
    # A matching hash from a pending/unconfirmed transaction is not durable
    # proof - the transaction could still be dropped or replaced - so it
    # must not be reported as VERIFIED.
    result["final_result"] = (
        "VERIFIED" if (blockchain_match and retrieved["confirmed"]) else "NOT VERIFIED"
    )

    print_summary(result)
    return result


def main():
    image_path = input("Enter path to input image: ").strip()
    run_pipeline(image_path)


if __name__ == "__main__":
    main()