"""
verify_candidates.py

Face-verifies web_search.py's reverse-image-search candidates against a
source image, using the EXISTING face_recognizer.py (SFace) implementation
exactly as-is. This module does not reimplement or alter face recognition,
fingerprinting, or web search - it only orchestrates the existing public
functions in a strict verify-before-trust order.

CORE RULE: a Google Lens ranking is never treated as proof of identity.
Every single candidate is independently downloaded and face-compared
against the source image before it can be considered a match. Candidates
that fail any check are rejected and recorded in the audit trail, not
silently dropped.

Uses (unmodified):
    face_recognizer.get_face_embedding()  - presence check only
    face_recognizer.compare_faces()       - identity check (uses the
                                             existing SFACE_COSINE_MATCH_THRESHOLD)
    web_search.download_candidate()       - safe candidate download
    image_fingerprint.generate_fingerprint() - fingerprint of the WINNER only
"""

import os
import tempfile
import uuid
from typing import List, Optional

from face_recognizer import get_face_embedding, compare_faces
from web_search import download_candidate, Candidate
from image_fingerprint import generate_fingerprint


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _temp_path_for(url: str) -> str:
    """Pick a temp file path with a best-guess extension from the URL."""
    ext = ".jpg"
    lower_url = url.lower().split("?")[0]
    for candidate_ext in (".png", ".jpeg", ".jpg", ".webp", ".gif", ".bmp"):
        if lower_url.endswith(candidate_ext):
            ext = ".jpg" if candidate_ext == ".jpeg" else candidate_ext
            break
    return os.path.join(tempfile.gettempdir(), f"candidate_{uuid.uuid4().hex}{ext}")


def _safe_remove(path: Optional[str]) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _new_record(candidate: Candidate) -> dict:
    return {
        "source_url": candidate.source_url,
        "image_url": candidate.image_url,
        "match_type": candidate.match_type,
        "face_detected": False,
        "face_similarity": None,
        "is_face_match": False,
        "rejection_reason": None,
    }


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------

def verify_web_candidates(source_image_path: str, candidates: List[Candidate]) -> dict:
    """
    Verify each web-search candidate's face against the source image.

    Args:
        source_image_path: local path to the original source photo.
        candidates: list of web_search.Candidate objects to check.

    Returns:
        {
            "matched": bool,
            "source_url": str | None,
            "image_url": str | None,
            "similarity": float | None,
            "fingerprint": dict | None,
            "candidates": [ per-candidate audit records ... ],
        }

    Raises:
        FileNotFoundError: source_image_path does not exist.
        ValueError: the source image itself has no detectable face -
            verification cannot proceed without one.
    """
    if not os.path.exists(source_image_path):
        raise FileNotFoundError(f"Source image not found: {source_image_path}")

    # Fail fast and clearly if the source itself has no usable face,
    # rather than silently rejecting every candidate downstream.
    try:
        get_face_embedding(source_image_path)
    except ValueError as exc:
        raise ValueError(
            f"Source image has no detectable face, cannot verify "
            f"candidates against it: {exc}"
        ) from exc

    audit_trail: List[dict] = []
    best: Optional[dict] = None  # {source_url, image_url, similarity, temp_path}

    if not candidates:
        return {
            "matched": False,
            "source_url": None,
            "image_url": None,
            "similarity": None,
            "fingerprint": None,
            "candidates": audit_trail,
        }

    for candidate in candidates:
        record = _new_record(candidate)

        if not candidate.image_url:
            record["rejection_reason"] = "no_image_url"
            audit_trail.append(record)
            continue

        temp_path = _temp_path_for(candidate.image_url)
        downloaded = download_candidate(candidate.image_url, temp_path)

        if not downloaded:
            record["rejection_reason"] = "download_failed"
            audit_trail.append(record)
            continue

        try:
            get_face_embedding(downloaded)
        except (ValueError, IndexError):
            record["rejection_reason"] = "no_face_detected"
            audit_trail.append(record)
            _safe_remove(downloaded)
            continue

        record["face_detected"] = True

        try:
            comparison = compare_faces(source_image_path, downloaded)
        except Exception as exc:
            record["rejection_reason"] = f"comparison_failed: {exc}"
            audit_trail.append(record)
            _safe_remove(downloaded)
            continue

        similarity = comparison["cosine_score"]
        is_match = comparison["same_person"]
        record["face_similarity"] = similarity
        record["is_face_match"] = is_match

        if not is_match:
            record["rejection_reason"] = "below_similarity_threshold"
            audit_trail.append(record)
            _safe_remove(downloaded)
            continue

        # Passed SFace verification - a genuine candidate.
        audit_trail.append(record)

        if best is None or similarity > best["similarity"]:
            _safe_remove(best["temp_path"] if best else None)
            best = {
                "source_url": candidate.source_url,
                "image_url": candidate.image_url,
                "similarity": similarity,
                "temp_path": downloaded,
            }
        else:
            _safe_remove(downloaded)

    if best is None:
        return {
            "matched": False,
            "source_url": None,
            "image_url": None,
            "similarity": None,
            "fingerprint": None,
            "candidates": audit_trail,
        }

    fingerprint = generate_fingerprint(best["temp_path"])
    _safe_remove(best["temp_path"])

    return {
        "matched": True,
        "source_url": best["source_url"],
        "image_url": best["image_url"],
        "similarity": best["similarity"],
        "fingerprint": fingerprint,
        "candidates": audit_trail,
    }


# ---------------------------------------------------------------------
# CLI entry point for manual testing
# ---------------------------------------------------------------------

def _main():
    import sys
    from web_search import (
        search_by_image, CredentialsError, UploadError, VisionAPIError, WebSearchError
    )

    if len(sys.argv) != 2:
        print("Usage: python verify_candidates.py <path_to_source_image>")
        sys.exit(1)

    source_path = sys.argv[1]

    try:
        candidates = search_by_image(source_path)
    except CredentialsError as exc:
        print(f"[CREDENTIALS ERROR] {exc}")
        sys.exit(1)
    except UploadError as exc:
        print(f"[UPLOAD ERROR] {exc}")
        sys.exit(1)
    except VisionAPIError as exc:
        print(f"[SEARCH ERROR] {exc}")
        sys.exit(1)
    except FileNotFoundError as exc:
        print(f"[FILE ERROR] {exc}")
        sys.exit(1)
    except WebSearchError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    print(f"Got {len(candidates)} candidate(s) from web search. Verifying faces...\n")

    try:
        result = verify_web_candidates(source_path, candidates)
    except ValueError as exc:
        print(f"[SOURCE IMAGE ERROR] {exc}")
        sys.exit(1)

    reasons = {}
    verified_count = 0
    for c in result["candidates"]:
        if c["is_face_match"]:
            verified_count += 1
        reason = c["rejection_reason"]
        if reason:
            key = reason.split(":")[0]
            reasons[key] = reasons.get(key, 0) + 1

    print("=== SUMMARY ===")
    print(f"Total candidates:      {len(result['candidates'])}")
    print(f"Missing image URL:     {reasons.get('no_image_url', 0)}")
    print(f"Download failed:       {reasons.get('download_failed', 0)}")
    print(f"No face detected:      {reasons.get('no_face_detected', 0)}")
    print(f"Below SFace threshold: {reasons.get('below_similarity_threshold', 0)}")
    print(f"Comparison errors:     {reasons.get('comparison_failed', 0)}")
    print(f"Verified matches:      {verified_count}")
    print()

    if result["matched"]:
        print("VERIFIED FACE MATCH FOUND")
        print(f"  source_url: {result['source_url']}")
        print(f"  image_url:  {result['image_url']}")
        print(f"  similarity: {result['similarity']:.4f}")
        print(f"  fingerprint sha256: {result['fingerprint']['sha256']}")
        print(f"  fingerprint phash:  {result['fingerprint']['phash']}")
    else:
        print("NO VERIFIED FACE MATCH FOUND")


if __name__ == "__main__":
    _main()