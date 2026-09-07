"""
api.py

Minimal Flask wrapper around the existing image-verification pipeline.

This file does NOT contain any pipeline logic of its own. It imports and
calls run_pipeline() from app.py - the same function the CLI (`python
app.py`) uses - and returns its result as JSON. It never calls app.py's
main() (which uses input()/print() and isn't meant to be called from a
web request).

Flow:
    Browser (templates/index.html)
        -> POST /api/verify  (multipart image upload)
        -> api.py saves the upload to a temp file
        -> run_pipeline(temp_path)   [from app.py, unmodified]
        -> temp file deleted
        -> JSON result returned to the browser
"""

import os
import tempfile
import uuid

from flask import Flask, request, jsonify, render_template

from app import run_pipeline

app = Flask(__name__)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "bmp", "gif"}


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/verify", methods=["POST"])
def verify():
    if "image" not in request.files:
        return jsonify({"error": "No image file provided."}), 400

    file = request.files["image"]

    if file.filename == "":
        return jsonify({"error": "No image selected."}), 400

    if not _allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type."}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    temp_path = os.path.join(tempfile.gettempdir(), f"upload_{uuid.uuid4().hex}.{ext}")

    try:
        file.save(temp_path)
        # This is the ENTIRE integration: call the same function the CLI
        # uses, with the uploaded file's path. Nothing else pipeline-related
        # happens in this file.
        result = run_pipeline(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return jsonify(result)


if __name__ == "__main__":
    # Flask's built-in dev server - fine for a hackathon demo, not for
    # production use.
    app.run(debug=True, port=5000)