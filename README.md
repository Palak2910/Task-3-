# Task-3: Face-Based Image Provenance & Verification

A face-based image verification pipeline that combines **face detection, face recognition, reverse image search, cryptographic fingerprinting, and blockchain-based provenance**.

The system takes an input image, searches for visually related content on the web, verifies candidate images using face embeddings, generates a cryptographic fingerprint for the verified image, and records that fingerprint on the Ethereum Sepolia testnet.

> **Important:** This system does not establish or confirm a person's real-world identity. Face recognition is used only to measure similarity between faces in images. Blockchain provides tamper-evident timestamping of an image fingerprint; it does not prove that the face match is correct.

---

## Features

- Face detection using OpenCV Haar Cascade
- Face embedding generation using YuNet + SFace
- 128-dimensional face embeddings
- Reverse image search using SerpApi Google Lens
- Candidate image downloading and validation
- Face-based candidate verification using SFace cosine similarity
- SHA-256 cryptographic fingerprinting
- Perceptual hashing (pHash)
- Ethereum Sepolia blockchain registration
- Retrieval and verification of blockchain-stored fingerprints
- Graceful handling of unavailable web images and failed downloads
- Detailed candidate verification audit trail

---

## System Architecture

```text
                    INPUT IMAGE
                         |
                         v
                +------------------+
                | Face Detection   |
                |  Haar Cascade    |
                +------------------+
                         |
                         v
                +------------------+
                | Face Embedding   |
                | YuNet + SFace    |
                | 128-D Vector     |
                +------------------+
                         |
                         +----------------------+
                         |                      |
                         v                      v
                +------------------+    +------------------+
                | Image            |    | Reverse Image   |
                | Fingerprinting   |    | Search          |
                | SHA-256 + pHash  |    | SerpApi + Lens  |
                +------------------+    +------------------+
                                               |
                                               v
                                      +------------------+
                                      | Web Candidates   |
                                      +------------------+
                                               |
                                               v
                                      +------------------+
                                      | Candidate Face   |
                                      | Verification     |
                                      | SFace Comparison |
                                      +------------------+
                                               |
                                     +---------+---------+
                                     |                   |
                                  NO MATCH            MATCH
                                     |                   |
                                     v                   v
                              NOT VERIFIED        Fingerprint
                                                       |
                                                       v
                                              Ethereum Sepolia
                                                       |
                                                       v
                                            Blockchain Transaction
                                                       |
                                                       v
                                             Retrieve & Verify
                                                       |
                                                       v
                                                   VERIFIED
```

## Pipeline

### Step 1 — Face Detection

The input image is first analyzed using an OpenCV Haar Cascade classifier.

The system checks:

- Whether a face is present
- Number of detected faces
- Location of each detected face

Example:

```
Face detected: True
Number of faces: 2
Face location: x=364 y=161 w=90 h=90
```

### Step 1B — Face Embedding

The detected face is separately processed by `face_recognizer.py`'s YuNet detector and SFace recognizer.

The system generates a 128-dimensional face embedding representing the facial features of the detected face.

Example:

```
Face embedding generated: 128-dimensional vector.
```

Face embeddings allow the system to compare two images using cosine similarity.

> **Note:** Step 1 (Haar Cascade) and Step 1B (YuNet) are two independent detectors. They will usually agree, but on borderline images it is possible for Step 1 to find a face while Step 1B does not. If this happens, the pipeline stops with a clear error rather than proceeding on an assumption.

### Step 2 — Image Fingerprinting

The input image is fingerprinted using two complementary methods.

**SHA-256**

SHA-256 produces a cryptographic hash representing the exact file contents.

Example:

```
SHA-256: b87fe1e185a839f339ff7bc7a0ee21c0a1d1473242ab20d715c48c3bd5d439ba
```

Even a small change to the file can produce a completely different SHA-256 hash.

**Perceptual Hash**

A perceptual hash (pHash) is also generated.

Unlike SHA-256, pHash is designed to remain relatively similar when an image is resized or recompressed.

Example:

```
Perceptual hash: a6b3590d99fc4c8c
```

### Step 3 — Reverse Image Search

The input image is uploaded to SerpApi, which performs a Google Lens visual search.

The search returns visually related web content.

The system extracts information such as:

- Source page URL
- Image URL
- Match position
- Match type
- Title
- Thumbnail information

For example:

```
Web candidates found: 60
```

A visual search result is not automatically considered a face match.

### Step 3B — Candidate Face Verification

Every downloadable candidate is independently checked.

The process is:

```
Web Candidate
     |
     v
Download Image
     |
     v
Face Detection
     |
     +---- No Face ----> Reject
     |
     v
SFace Comparison
     |
     +---- Below Threshold ----> Reject
     |
     v
Potential Face Match
```

The configured SFace cosine similarity threshold is:

```
0.363
```

The candidate with the highest similarity among candidates passing the configured threshold is selected.

The system maintains an audit trail containing information such as:

- Source URL
- Image URL
- Match type
- Whether a face was detected
- Face similarity score
- Whether the candidate passed the threshold
- Reason for rejection

### Step 4 — Winning Candidate Fingerprint

`verify_web_candidates()` already fingerprints the winning candidate internally as part of verification, then deletes its temporary local copy. `app.py` reuses that fingerprint directly rather than re-downloading and re-fingerprinting the candidate — recomputing from a second download could silently pick up different bytes if the remote content changed in between, which would break the link between "what was verified" and "what gets registered on-chain."

Example:

```
SHA-256: b87fe1e185a839f339ff7bc7a0ee21c0a1d1473242ab20d715c48c3bd5d439ba
Perceptual hash: a6b3590d99fc4c8c
```

### Step 5 — Blockchain Registration

Only a successfully verified web candidate proceeds to blockchain registration.

The selected candidate's SHA-256 fingerprint (from Step 4) is stored in an Ethereum Sepolia transaction.

The current implementation does not require a smart contract.

Instead, the SHA-256 hash is stored in the transaction data field of a zero-value self-transaction.

The transaction produces a blockchain transaction hash that can later be used to retrieve the stored fingerprint.

### Step 6 — Blockchain Verification

The system retrieves the transaction from Ethereum Sepolia and extracts the stored fingerprint.

The retrieved fingerprint is compared with the fingerprint from Step 4.

Example:

```
Original SHA-256:  b87fe1e185a839f339ff7bc7a0ee21c0a1d1473242ab20d715c48c3bd5d439ba
Retrieved SHA-256:  b87fe1e185a839f339ff7bc7a0ee21c0a1d1473242ab20d715c48c3bd5d439ba

Result: MATCH
```

This provides a tamper-evident record that the fingerprint was registered on-chain.

---

## Project Structure

```
Task-3-/
│
├── app.py
├── config.py
├── blockchain.py
├── face_detector.py
├── face_recognizer.py
├── image_fingerprint.py
├── verify_candidates.py
├── web_search.py
├── verifier.py
│
├── models/
│   ├── face_detection_yunet_2023mar.onnx
│   └── face_recognition_sface_2021dec.onnx
│
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

`verifier.py` (`verify_local_hash()`) and `image_fingerprint.py`'s `verify_fingerprint()` are not currently called by `app.py` — the running pipeline does a direct string comparison of the two SHA-256 hashes in Step 6 instead. They're kept in the repo as reusable building blocks (e.g. for verifying a locally-held file against a previously stored hash outside the main pipeline) rather than wired into the main flow.

The ONNX model files are required locally but are not committed to Git (see `.gitignore`) — they're large binaries. Follow the model download instructions below to obtain them.

---

## Requirements

- Python 3.10+
- OpenCV
- YuNet face detection model
- SFace face recognition model
- SerpApi account and API key
- Ethereum Sepolia RPC endpoint
- Sepolia test ETH
- A dedicated/throwaway Ethereum wallet for testing

## Installation

Clone the repository:

```
git clone <repository-url>
cd Task-3-
```

Create a virtual environment:

**Windows**
```
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux**
```
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```
pip install -r requirements.txt
```

## Model Files

The face recognition pipeline requires two ONNX model files:

```
models/
├── face_detection_yunet_2023mar.onnx
└── face_recognition_sface_2021dec.onnx
```

Place both files inside the `models/` directory.

The application validates that the required model files are real model files rather than Git LFS pointer files.

## Environment Configuration

Create a local `.env` file based on `.env.example`.

```
Copy-Item .env.example .env
```

(or `cp .env.example .env` on macOS/Linux)

Configure the following values:

```
SERPAPI_API_KEY="your_serpapi_api_key"

SEPOLIA_RPC_URL="https://ethereum-sepolia-rpc.publicnode.com"

WALLET_PRIVATE_KEY="your_throwaway_wallet_private_key"
```

## Security

Never commit `.env` to Git.

Never expose:

- API keys
- Ethereum private keys
- Service account credentials
- Other authentication secrets

Use a dedicated test wallet for Sepolia development.

## Running the Application

Run:

```
python app.py
```

The application will request an input image:

```
Enter path to input image:
```

For example:

```
test.jpg
```

### Example Output — No Verified Match

```
============================================================
STEP 1: FACE DETECTION
============================================================
Face detected: True
Number of faces: 2

============================================================
STEP 1B: FACE EMBEDDING
============================================================
Face embedding generated: 128-dimensional vector.

============================================================
STEP 2: IMAGE FINGERPRINT
============================================================
SHA-256: ...
Perceptual hash: ...

============================================================
STEP 3: WEB SEARCH
============================================================
Web candidates found: 60

============================================================
STEP 3B: CANDIDATE VERIFICATION
============================================================
Total candidates: 60
Download failures: 12
No face detected: 15
Rejected by SFace threshold: 33
Verified matches: 0

============================================================
RESULT
============================================================
No verified web face match found.
Blockchain registration skipped: nothing verified to register.
```

This is a valid result, not an error. The system intentionally prevents an unverified web result from being registered on the blockchain. This exact scenario has been run and confirmed against `test.jpg`.

### Expected Flow — Verified Match

Each stage below (detection, embedding, search, candidate verification, Sepolia registration, Sepolia retrieval) has been independently tested and confirmed working. When a candidate passes face verification, the full run is expected to proceed as:

```
Input Image
     |
     v
Face Detection
     |
     v
Face Embedding
     |
     v
Reverse Image Search
     |
     v
Candidate Images
     |
     v
SFace Face Verification
     |
     v
Verified Candidate
     |
     v
SHA-256 Fingerprint
     |
     v
Ethereum Sepolia
     |
     v
Transaction Confirmed
     |
     v
Fingerprint Retrieved
     |
     v
Fingerprint Match
     |
     v
VERIFIED
```

### Blockchain Example

A successful Sepolia registration returns information similar to:

```
Registration:
{
    'tx_hash': '0x...',
    'status': 'confirmed',
    'block_number': 11651763
}
```

The fingerprint can then be retrieved from the transaction:

```
Retrieved:
{
    'sha256_hash': '...',
    'confirmed': True,
    'block_number': 11651763
}
```

---

## Important Design Decisions

### Face similarity is not identity proof

A face similarity score only indicates that two detected faces are sufficiently similar according to the configured recognition model.

It does not prove:

- Legal identity
- Ownership of an account
- Authenticity of a social-media profile
- That two images depict the same real-world person with certainty

The system should therefore be described as face similarity verification, not identity verification.

### Reverse image search is index-dependent

SerpApi/Google Lens can only return useful results when visually related content is available in its searchable/indexed sources.

A newly captured private image may return:

```
No web matches found
```

This does not mean that the image is fake. It means that the search engine did not find suitable indexed visual matches.

### Visual similarity is not face similarity

Google Lens may return visually similar images based on:

- Clothing
- Colors
- Background
- Pose
- Composition
- Objects

Therefore, search results are treated only as candidates. The SFace verification stage is responsible for determining whether a candidate contains a sufficiently similar face.

### Blockchain does not validate the face match

Blockchain provides:

- Tamper-evident storage
- Timestamped transaction history
- Independent verification of the stored fingerprint

Blockchain does not determine whether the face recognition result was correct.

The trust model is therefore:

```
Face Recognition
       +
Image Fingerprinting
       +
Blockchain Provenance
```

rather than blockchain replacing face recognition.

---

## Privacy Considerations

This project processes facial images and may send images to a third-party reverse image search service.

For demonstrations and testing:

- Use images of consenting subjects.
- Avoid uploading sensitive or private photographs.
- Do not commit personal photographs to the repository.
- Do not expose API credentials or private keys.
- Use a dedicated test wallet for blockchain operations.

The test images used during development of this project (`test.jpg`, `test2.jpg`, `test_resaved.jpg`, `person2.jpg`) are from consenting subjects and are excluded from version control via `.gitignore` — they exist only in local development copies of this repo, not in the committed history.

---

## Limitations

- Reverse image search depends on publicly indexed web content.
- Visually similar search results can contain false positives.
- Websites may block automated image downloads.
- Some candidate URLs may return HTTP errors such as 403 or 406.
- Social media CDN URLs may return HTML instead of image data.
- Face recognition similarity scores are not absolute proof of identity.
- Blockchain registration requires Sepolia test ETH for transaction fees.
- The current implementation uses two detection stages: Haar Cascade for initial detection and YuNet internally for SFace recognition — see the note under Step 1B.
- Multiple candidate comparisons can increase processing time and network usage; `verify_web_candidates()` currently checks every returned candidate with no cap.
- Sepolia is a test network and should not be treated as production infrastructure.

---

## Testing Strategy

The project should be tested using both positive and negative cases.

### Negative Case

Use an image that does not have a sufficiently similar indexed web image.

Expected result:

```
Web candidates found
        ↓
Candidates filtered
        ↓
No SFace match
        ↓
Blockchain skipped
        ↓
NOT VERIFIED
```

### Positive Case

Use a consenting test image for which the same or a near-duplicate image is publicly indexed.

Expected result:

```
Web candidates found
        ↓
Candidate face detected
        ↓
SFace similarity passes threshold
        ↓
Fingerprint generated
        ↓
Fingerprint registered on Sepolia
        ↓
Fingerprint retrieved
        ↓
VERIFIED
```

---

## Future Improvements

Potential future improvements include:

- Confidence tiers instead of a strict binary face-match result
- Candidate ranking and smarter pre-filtering
- Caching of source face embeddings
- Limiting the number of candidate downloads
- Better handling of social-media image URLs
- Persistent off-chain provenance records
- Smart-contract-based fingerprint lookup
- Multiple-face selection and tracking
- A web-based user interface
- Automated audit reports
- Support for additional reverse image search providers

---

## Conclusion

This project demonstrates an end-to-end approach to image provenance and face-based web-content verification.

The system combines:

```
Computer Vision
       +
Face Recognition
       +
Reverse Image Search
       +
Cryptographic Fingerprinting
       +
Blockchain Provenance
```

The key design principle is that each layer has a separate responsibility:

- Computer vision finds faces.
- Face recognition measures similarity.
- Reverse image search discovers candidate web content.
- SHA-256 and pHash fingerprint image content.
- Blockchain provides a tamper-evident record of the fingerprint.

Together, these components provide a practical prototype for investigating the provenance and online presence of image content while keeping the distinction between similarity, verification, and identity explicit.