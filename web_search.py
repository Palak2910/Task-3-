"""
web_search.py

Reverse image search using SerpApi's Google Lens engine.

SCOPE: this module ONLY finds candidate URLs where a visually similar or
identical image already appears on the public web. It does NOT perform
face recognition and does NOT claim that any candidate shows the same
person as the input image. That verification step is a separate job for
face_recognizer.py (SFace embeddings + compare_faces), run later against
the images this module downloads.

FLOW:
    1. Upload the local image to SerpApi's /image endpoint (multipart
       upload, max 500KB) -> get back an image_id.
    2. Query the google_lens engine with that image_id -> get back
       visual_matches: real page URLs and image URLs SerpApi found.

WHY RESULTS CAN BE EMPTY: Google Lens matches images that Google has
already crawled and indexed - the same photo (or a near-duplicate/crop of
it) has to already exist somewhere public. A brand-new photo that has
never been posted anywhere will correctly return zero results. That is
expected behavior, not a bug.

CREDENTIALS:
    Set SERPAPI_API_KEY, either in your shell environment or in a .env
    file (see .env.example) - python-dotenv loads that automatically.
    Get a free key (250 searches/month, no credit card) at
    https://serpapi.com/manage-api-key

DEPENDENCIES:
    pip install requests python-dotenv
"""

import os
import sys
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv
import requests

load_dotenv()

# ---------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------

SERPAPI_UPLOAD_URL = "https://serpapi.com/image"
SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"
SERPAPI_UPLOAD_MAX_BYTES = 500 * 1024  # SerpApi's own upload limit
REQUEST_TIMEOUT_SECONDS = 20

DOWNLOAD_TIMEOUT_SECONDS = 10
MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024  # 15 MB safety cap per candidate
DOWNLOAD_CHUNK_SIZE = 64 * 1024
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
}


# ---------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------

class WebSearchError(Exception):
    """Base class for all web_search.py errors."""


class CredentialsError(WebSearchError):
    """SERPAPI_API_KEY is missing or SerpApi rejected it."""


class UploadError(WebSearchError):
    """The image upload to SerpApi's /image endpoint failed."""


class VisionAPIError(WebSearchError):
    """The google_lens search request itself failed."""


# ---------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------

@dataclass
class Candidate:
    """
    One raw candidate from Google Lens. This is NOT a confirmed face
    match - it only means SerpApi found visually-matching web content.
    """
    source_url: Optional[str]   # page that contains the image
    image_url: Optional[str]    # image / thumbnail URL to download
    match_type: str             # "visual_match"
    position: Optional[int] = None
    title: Optional[str] = None
    used_thumbnail_fallback: bool = False

    def to_dict(self) -> dict:
        return {
            "source_url": self.source_url,
            "image_url": self.image_url,
            "match_type": self.match_type,
            "position": self.position,
            "title": self.title,
            "used_thumbnail_fallback": self.used_thumbnail_fallback,
        }


# ---------------------------------------------------------------------
# Credential check
# ---------------------------------------------------------------------

def _get_api_key() -> str:
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        raise CredentialsError(
            "SERPAPI_API_KEY is not set. Get a free key (no credit card, "
            "250 searches/month) at https://serpapi.com/manage-api-key and "
            "add it to your .env file. See .env.example."
        )
    return api_key


# ---------------------------------------------------------------------
# Step 1: upload the local image
# ---------------------------------------------------------------------

def _upload_image(image_path: str, api_key: str) -> str:
    """
    Upload a local image to SerpApi's /image endpoint.

    Returns:
        image_id (str)

    Raises:
        FileNotFoundError: image_path does not exist.
        UploadError: file too large, request failed, or SerpApi
            returned an unexpected response.
        CredentialsError: SerpApi rejected the API key.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    file_size = os.path.getsize(image_path)
    if file_size > SERPAPI_UPLOAD_MAX_BYTES:
        raise UploadError(
            f"'{image_path}' is {file_size} bytes, which exceeds SerpApi's "
            f"{SERPAPI_UPLOAD_MAX_BYTES}-byte upload limit for the /image "
            "endpoint. Downscale or re-compress the image and try again."
        )

    try:
        with open(image_path, "rb") as f:
            response = requests.post(
                SERPAPI_UPLOAD_URL,
                files={"image": f},
                data={"api_key": api_key},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
    except requests.exceptions.RequestException as exc:
        raise UploadError(f"Image upload request failed: {exc}") from exc

    if response.status_code == 401:
        raise CredentialsError(
            "SerpApi rejected the API key during upload (HTTP 401). "
            "Check SERPAPI_API_KEY is correct and active."
        )

    if response.status_code != 200:
        raise UploadError(
            f"Image upload failed: HTTP {response.status_code} - "
            f"{response.text[:300]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise UploadError(
            f"Image upload returned a non-JSON response: {response.text[:300]}"
        ) from exc

    image_id = payload.get("image_id")
    if not image_id:
        raise UploadError(
            f"Image upload succeeded but no image_id was returned. "
            f"Response: {payload}"
        )

    return image_id


# ---------------------------------------------------------------------
# Step 2: search with the image_id
# ---------------------------------------------------------------------

def _search_by_image_id(image_id: str, api_key: str) -> list:
    """
    Query the google_lens engine using an uploaded image's image_id.

    Returns:
        The raw 'visual_matches' list from SerpApi (possibly empty).

    Raises:
        CredentialsError: SerpApi rejected the API key.
        VisionAPIError: the search request itself failed.
    """
    params = {
        "engine": "google_lens",
        "image_id": image_id,
        "api_key": api_key,
    }

    try:
        response = requests.get(
            SERPAPI_SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.exceptions.RequestException as exc:
        raise VisionAPIError(f"Google Lens search request failed: {exc}") from exc

    if response.status_code == 401:
        raise CredentialsError(
            "SerpApi rejected the API key during search (HTTP 401). "
            "Check SERPAPI_API_KEY is correct and active."
        )

    if response.status_code != 200:
        raise VisionAPIError(
            f"Google Lens search failed: HTTP {response.status_code} - "
            f"{response.text[:300]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise VisionAPIError(
            f"Google Lens search returned a non-JSON response: "
            f"{response.text[:300]}"
        ) from exc

    if "error" in payload:
        raise VisionAPIError(f"SerpApi returned an error: {payload['error']}")

    return payload.get("visual_matches", [])


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------

def search_by_image(image_path: str) -> List[Candidate]:
    """
    Run the full reverse-image search flow: upload the local image to
    SerpApi, then query Google Lens using the returned image_id.

    Args:
        image_path: path to a local image file (must be <= 500KB for
            SerpApi's upload endpoint).

    Returns:
        List[Candidate]. An empty list means the search succeeded but
        found no matching web content - a normal, expected outcome for
        images that are not already publicly indexed.

    Raises:
        FileNotFoundError: image_path does not exist.
        CredentialsError: SERPAPI_API_KEY is missing or invalid.
        UploadError: the image upload step failed.
        VisionAPIError: the google_lens search step failed.
    """
    api_key = _get_api_key()
    image_id = _upload_image(image_path, api_key)
    raw_matches = _search_by_image_id(image_id, api_key)

    candidates: List[Candidate] = []
    for match in raw_matches:
        image_url = match.get("image")
        used_fallback = False
        if not image_url:
            image_url = match.get("thumbnail")
            used_fallback = True

        candidates.append(Candidate(
            source_url=match.get("link"),
            image_url=image_url,
            match_type="visual_match",
            position=match.get("position"),
            title=match.get("title"),
            used_thumbnail_fallback=used_fallback,
        ))

    return candidates


# ---------------------------------------------------------------------
# Safe candidate download (UNCHANGED)
# ---------------------------------------------------------------------

def download_candidate(url: str, dest_path: str) -> Optional[str]:
    """
    Attempt to safely download a candidate image to dest_path.

    This never raises for ordinary download failures (timeout, bad
    content-type, oversized file, connection error, non-200 status).
    Callers should treat a None return as "skip this candidate and
    move on" - one bad candidate should never crash the pipeline.

    Returns:
        dest_path on success, None on any graceful failure.
    """
    try:
        response = requests.get(
            url, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS
        )
    except requests.exceptions.RequestException as exc:
        print(f"[web_search] Download failed ({url}): {exc}")
        return None

    if response.status_code != 200:
        print(f"[web_search] Download failed ({url}): HTTP {response.status_code}")
        return None

    content_type = (
        response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    )
    if content_type not in ALLOWED_CONTENT_TYPES:
        print(
            f"[web_search] Skipped ({url}): unsupported or missing "
            f"Content-Type '{content_type}'"
        )
        return None

    declared_length = response.headers.get("Content-Length")
    if declared_length and declared_length.isdigit():
        if int(declared_length) > MAX_DOWNLOAD_BYTES:
            print(
                f"[web_search] Skipped ({url}): declared size "
                f"{declared_length} bytes exceeds the {MAX_DOWNLOAD_BYTES} "
                "byte limit"
            )
            return None

    total_bytes = 0
    try:
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > MAX_DOWNLOAD_BYTES:
                    f.close()
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    print(
                        f"[web_search] Skipped ({url}): exceeded "
                        f"{MAX_DOWNLOAD_BYTES} bytes while streaming"
                    )
                    return None
                f.write(chunk)
    except (OSError, requests.exceptions.RequestException) as exc:
        print(f"[web_search] Download failed while writing ({url}): {exc}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return None

    return dest_path


# ---------------------------------------------------------------------
# CLI entry point for manual testing
# ---------------------------------------------------------------------

def _main():
    if len(sys.argv) != 2:
        print("Usage: python web_search.py <path_to_image>")
        sys.exit(1)

    image_path = sys.argv[1]

    try:
        results = search_by_image(image_path)
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

    if not results:
        print("No web matches found for this image.")
        print(
            "This is expected if the image has never been posted "
            "publicly, or is not yet indexed by Google. Try a photo you "
            "know already exists online (e.g. an existing public profile "
            "photo) to confirm the pipeline itself is working."
        )
        sys.exit(0)

    print(
        f"Found {len(results)} candidate(s). These are NOT confirmed "
        "face matches yet - only visually-matching web content. Run "
        "them through face_recognizer.compare_faces() to verify.\n"
    )

    for c in results:
        print(f"[{c.position}] {c.title or '(no title)'}")
        if c.source_url:
            print(f"    source_url: {c.source_url}")
        if c.image_url:
            fallback_note = " (thumbnail fallback)" if c.used_thumbnail_fallback else ""
            print(f"    image_url:  {c.image_url}{fallback_note}")
        print()


if __name__ == "__main__":
    _main()