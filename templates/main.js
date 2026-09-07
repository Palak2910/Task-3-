/* ==========================================================================
   Image Provenance & Verification — frontend logic.

   This file contains NO pipeline logic of its own. It uploads the chosen
   image to POST /api/verify (api.py, which calls app.py's run_pipeline())
   and renders whatever JSON comes back. Every status shown in the UI is
   derived directly from fields already present in that response — nothing
   here re-implements face detection, search, verification, or blockchain
   logic, and nothing here fabricates a result.
   ========================================================================== */

(function () {
  "use strict";

  const STEP_DEFS = [
    { id: "face_detection", title: "Face Detection", desc: "Locate faces in the uploaded image." },
    { id: "face_embedding", title: "Face Embedding", desc: "Convert the detected face into a numerical representation." },
    { id: "fingerprint", title: "Image Fingerprint", desc: "Generate SHA-256 and perceptual hashes." },
    { id: "web_search", title: "Web Search", desc: "Find visually similar indexed images." },
    { id: "face_verification", title: "Candidate Verification", desc: "Compare candidate faces using SFace." },
    { id: "blockchain_registration", title: "Blockchain Registration", desc: "Record the winning fingerprint on Ethereum Sepolia." },
    { id: "blockchain_verification", title: "Blockchain Verification", desc: "Retrieve and confirm the recorded fingerprint." },
  ];

  const $ = (id) => document.getElementById(id);

  const dropzone = $("dropzone");
  const fileInput = $("fileInput");
  const filePreview = $("filePreview");
  const previewImg = $("previewImg");
  const previewName = $("previewName");
  const previewSize = $("previewSize");
  const removeFileBtn = $("removeFile");
  const verifyBtn = $("verifyBtn");
  const errorBanner = $("errorBanner");
  const errorText = $("errorText");
  const infoBanner = $("infoBanner");
  const infoText = $("infoText");
  const pipelineEl = $("pipeline");
  const timelineEl = $("timeline");
  const resultCard = $("resultCard");
  const matchCard = $("matchCard");
  const chainCard = $("chainCard");

  let selectedFile = null;
  let uploadedObjectUrl = null;

  // ---------------------------------------------------------------------
  // File selection
  // ---------------------------------------------------------------------

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(2) + " MB";
  }

  function selectFile(file) {
    if (!file) return;
    const okTypes = ["image/jpeg", "image/png", "image/webp", "image/bmp", "image/gif"];
    if (!okTypes.includes(file.type)) {
      showError("Unsupported file type. Please choose a JPG, PNG, WEBP, BMP, or GIF image.");
      return;
    }
    hideError();
    selectedFile = file;
    if (uploadedObjectUrl) URL.revokeObjectURL(uploadedObjectUrl);
    uploadedObjectUrl = URL.createObjectURL(file);

    previewImg.src = uploadedObjectUrl;
    previewName.textContent = file.name;
    previewSize.textContent = formatBytes(file.size);

    dropzone.classList.add("hidden");
    filePreview.classList.remove("hidden");
    verifyBtn.disabled = false;

    resetResults();
  }

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) selectFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) selectFile(e.target.files[0]);
  });

  removeFileBtn.addEventListener("click", () => {
    selectedFile = null;
    fileInput.value = "";
    if (uploadedObjectUrl) { URL.revokeObjectURL(uploadedObjectUrl); uploadedObjectUrl = null; }
    filePreview.classList.add("hidden");
    dropzone.classList.remove("hidden");
    verifyBtn.disabled = true;
    resetResults();
  });

  function showError(msg) {
    errorText.textContent = msg;
    errorBanner.classList.add("show");
  }
  function hideError() {
    errorBanner.classList.remove("show");
  }
  function showInfo(msg) {
    infoText.textContent = msg;
    infoBanner.classList.add("show");
  }
  function hideInfo() {
    infoBanner.classList.remove("show");
  }

  function resetResults() {
    pipelineEl.classList.remove("show");
    resultCard.classList.remove("show");
    matchCard.classList.remove("show");
    chainCard.classList.remove("show");
    hideError();
    hideInfo();
  }

  // ---------------------------------------------------------------------
  // Timeline rendering
  // ---------------------------------------------------------------------

  function renderTimelineSkeleton() {
    timelineEl.innerHTML = "";
    STEP_DEFS.forEach((step, i) => {
      const el = document.createElement("div");
      el.className = "step";
      el.dataset.status = i === 0 ? "processing" : "not-reached";
      el.dataset.stepId = step.id;
      el.innerHTML = `
        <div class="step-node">${String(i + 1).padStart(2, "0")}</div>
        <div class="step-body">
          <div class="step-top">
            <div>
              <div class="step-title">${step.title}</div>
              <div class="step-desc">${step.desc}</div>
            </div>
            <span class="status-pill"><span class="dot"></span><span class="status-label">${i === 0 ? "Processing" : "Not reached"}</span></span>
          </div>
          <div class="step-note"></div>
        </div>`;
      timelineEl.appendChild(el);
    });
  }

  const STATUS_LABELS = {
    completed: "Completed",
    processing: "Processing",
    pending: "Pending",
    failed: "Failed",
    "not-reached": "Not reached",
  };

  function setStepStatus(id, status, note) {
    const el = timelineEl.querySelector(`[data-step-id="${id}"]`);
    if (!el) return;
    el.dataset.status = status;
    el.querySelector(".status-label").textContent = STATUS_LABELS[status] || status;
    const noteEl = el.querySelector(".step-note");
    if (note) { noteEl.textContent = note; noteEl.style.display = "block"; }
  }

  // Derive each step's displayed status purely from run_pipeline()'s
  // returned fields. Nothing here re-computes the pipeline itself.
  function applyResultToTimeline(result) {
    const errStage = result.error_stage;

    // 1. Face detection
    if (errStage === "input" || errStage === "face_detection") {
      setStepStatus("face_detection", "failed", result.error);
    } else if (result.face_detected) {
      setStepStatus("face_detection", "completed", `${result.face_count} face(s) detected.`);
    } else {
      setStepStatus("face_detection", "not-reached");
    }

    // 2. Face embedding
    if (errStage === "face_embedding") {
      setStepStatus("face_embedding", "failed", result.error);
    } else if (result.embedding_generated) {
      setStepStatus("face_embedding", "completed", `${result.embedding_dim}-dimensional vector.`);
    } else {
      setStepStatus("face_embedding", "not-reached");
    }

    // 3. Image fingerprint (input image)
    if (result.input_fingerprint) {
      setStepStatus("fingerprint", "completed", `SHA-256 ${result.input_fingerprint.sha256.slice(0, 12)}…`);
    } else {
      setStepStatus("fingerprint", "not-reached");
    }

    // 4. Web search
    if (errStage === "web_search") {
      setStepStatus("web_search", "failed", result.error);
    } else if (result.input_fingerprint && !errStage) {
      setStepStatus("web_search", "completed", `${result.web_candidates} candidate(s) found.`);
    } else if (result.input_fingerprint && errStage && !["input", "face_detection", "face_embedding"].includes(errStage)) {
      setStepStatus("web_search", "completed", `${result.web_candidates} candidate(s) found.`);
    } else {
      setStepStatus("web_search", "not-reached");
    }

    // 5. Candidate / face verification
    if (errStage === "candidate_verification") {
      setStepStatus("face_verification", "failed", result.error);
    } else if (result.candidate_audit) {
      const a = result.candidate_audit;
      setStepStatus(
        "face_verification",
        "completed",
        `${a.verified_count} verified of ${a.total} candidate(s) — ${a.download_failed} download failed, ${a.no_face_detected} no face, ${a.invalid_image} invalid, ${a.below_similarity_threshold} below threshold.`
      );
    } else {
      setStepStatus("face_verification", "not-reached");
    }

    // 6. Blockchain registration
    if (errStage === "blockchain_registration") {
      setStepStatus("blockchain_registration", "failed", result.error);
    } else if (result.registration) {
      setStepStatus(
        "blockchain_registration",
        "completed",
        `Tx status: ${result.registration.status}.`
      );
    } else if (result.candidate_audit && result.verified_matches === 0) {
      setStepStatus("blockchain_registration", "not-reached", "Skipped — no verified match to register.");
    } else {
      setStepStatus("blockchain_registration", "not-reached");
    }

    // 7. Blockchain verification
    if (errStage === "blockchain_retrieval") {
      setStepStatus("blockchain_verification", "failed", result.error);
    } else if (result.retrieved) {
      setStepStatus(
        "blockchain_verification",
        result.retrieved.confirmed ? "completed" : "pending",
        result.retrieved.confirmed ? "Confirmed on-chain." : "Transaction not yet confirmed on-chain."
      );
    } else {
      setStepStatus("blockchain_verification", "not-reached");
    }
  }

  // ---------------------------------------------------------------------
  // Final result
  // ---------------------------------------------------------------------

  function renderFinalResult(result) {
    resultCard.classList.remove("verified", "not-verified");
    resultCard.classList.add("show");

    const badge = $("resultBadge");
    const headline = $("resultHeadline");
    const explain = $("resultExplain");
    const stats = $("resultStats");
    stats.innerHTML = "";

    if (result.error) {
      resultCard.classList.add("not-verified");
      badge.className = "result-badge not-verified";
      badge.textContent = "NOT VERIFIED";
      headline.textContent = "Pipeline stopped early";
      explain.textContent = result.error;
      return;
    }

    const isVerified = result.final_result === "VERIFIED";
    resultCard.classList.add(isVerified ? "verified" : "not-verified");
    badge.className = "result-badge " + (isVerified ? "verified" : "not-verified");
    badge.textContent = isVerified ? "✓ VERIFIED" : "NOT VERIFIED";

    if (isVerified) {
      headline.textContent = "Verified web match with confirmed blockchain provenance";
      explain.textContent = "A web candidate passed the configured SFace similarity threshold, and its fingerprint was recorded and confirmed on the Ethereum Sepolia blockchain.";
    } else {
      headline.textContent = "No verified provenance established";
      if (result.verified_matches === 0) {
        explain.textContent = "No sufficiently similar web face match was found.";
      } else if (result.registration && result.blockchain_match === false) {
        explain.textContent = "The fingerprint did not match the recorded blockchain fingerprint.";
      } else if (result.registration && result.blockchain_match && result.retrieved && !result.retrieved.confirmed) {
        explain.textContent = "A candidate matched the face threshold, but the blockchain transaction is not yet confirmed.";
      } else {
        explain.textContent = "The verification chain could not be completed for this image.";
      }
    }

    const addStat = (label, value) => {
      if (value === null || value === undefined || value === "") return;
      const d = document.createElement("div");
      d.className = "result-stat";
      d.innerHTML = `<div class="label">${label}</div><div class="value">${value}</div>`;
      stats.appendChild(d);
    };
    addStat("Web candidates", result.web_candidates);
    addStat("Verified matches", result.verified_matches);
    if (result.best_similarity !== null && result.best_similarity !== undefined) {
      addStat("Best similarity", result.best_similarity.toFixed(4));
    }
  }

  // ---------------------------------------------------------------------
  // Match details
  // ---------------------------------------------------------------------

  function truncateMiddle(str, head = 28, tail = 10) {
    if (!str || str.length <= head + tail + 3) return str || "";
    return str.slice(0, head) + "…" + str.slice(-tail);
  }

  function copyRow(container, fullText) {
    container.innerHTML = "";
    const link = document.createElement(fullText.startsWith("http") ? "a" : "span");
    link.textContent = truncateMiddle(fullText);
    link.title = fullText;
    if (fullText.startsWith("http")) { link.href = fullText; link.target = "_blank"; link.rel = "noopener"; }
    const btn = document.createElement("button");
    btn.className = "copy-btn";
    btn.textContent = "Copy";
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      navigator.clipboard.writeText(fullText).then(() => {
        btn.textContent = "Copied";
        setTimeout(() => (btn.textContent = "Copy"), 1200);
      });
    });
    container.appendChild(link);
    container.appendChild(btn);
  }

  function renderMatchDetails(result) {
    if (!result.source_url && !result.image_url) {
      matchCard.classList.remove("show");
      return;
    }
    matchCard.classList.add("show");

    $("uploadedImg").src = uploadedObjectUrl || "";

    const matchedImg = $("matchedImg");
    const matchedFrame = $("matchedFrame");
    matchedImg.onerror = () => {
      matchedFrame.innerHTML = `<div class="broken">Image could not be loaded from source (hotlink or availability restriction). <a href="${result.image_url}" target="_blank" rel="noopener">Open original</a></div>`;
    };
    matchedImg.src = result.image_url || "";

    const similarity = result.best_similarity || 0;
    $("similarityScore").textContent = (similarity * 100).toFixed(1) + "%";
    $("similarityFill").style.width = Math.min(100, similarity * 100) + "%";

    copyRow($("sourceUrlRow"), result.source_url || "—");
    copyRow($("imageUrlRow"), result.image_url || "—");

    const fp = result.winner_fingerprint || {};
    copyRow($("sha256Row"), fp.sha256 || "—");
    copyRow($("phashRow"), fp.phash || "—");
  }

  // ---------------------------------------------------------------------
  // Blockchain provenance
  // ---------------------------------------------------------------------

  function renderChainCard(result) {
    if (!result.registration) {
      chainCard.classList.remove("show");
      return;
    }
    chainCard.classList.add("show");

    copyRow($("txRow"), result.registration.tx_hash || "—");

    const statusEl = $("statusRow");
    const confirmed = result.registration.status === "confirmed";
    statusEl.innerHTML = `<span class="status-tag ${confirmed ? "ok" : "warn"}">${confirmed ? "Confirmed" : "Pending"}</span>`;

    const blockNumber = result.registration.block_number ?? (result.retrieved && result.retrieved.block_number);
    $("blockRow").textContent = blockNumber != null ? blockNumber : "Pending";

    const fpMatchEl = $("fpMatchRow");
    if (result.blockchain_match === null || result.blockchain_match === undefined) {
      fpMatchEl.innerHTML = `<span class="status-tag warn">Not yet checked</span>`;
    } else {
      fpMatchEl.innerHTML = `<span class="status-tag ${result.blockchain_match ? "ok" : "bad"}">${result.blockchain_match ? "MATCH" : "NO MATCH"}</span>`;
    }

    const confirmEl = $("confirmRow");
    const onchainConfirmed = result.retrieved && result.retrieved.confirmed;
    confirmEl.innerHTML = `<span class="status-tag ${onchainConfirmed ? "ok" : "warn"}">${onchainConfirmed ? "Confirmed" : "Pending"}</span>`;
  }

  // ---------------------------------------------------------------------
  // Verify action
  // ---------------------------------------------------------------------

  async function runVerification() {
    if (!selectedFile) return;

    resetResults();
    pipelineEl.classList.add("show");
    renderTimelineSkeleton();
    verifyBtn.disabled = true;
    verifyBtn.textContent = "Verifying…";

    const formData = new FormData();
    formData.append("image", selectedFile);

    try {
      const response = await fetch("/api/verify", { method: "POST", body: formData });
      const data = await response.json();

      if (!response.ok) {
        showError(data.error || "Verification request failed.");
        pipelineEl.classList.remove("show");
        return;
      }

      applyResultToTimeline(data);
      renderFinalResult(data);
      renderMatchDetails(data);
      renderChainCard(data);
      resultCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (err) {
      showError("Could not reach the server. Is `python api.py` running?");
      pipelineEl.classList.remove("show");
    } finally {
      verifyBtn.disabled = false;
      verifyBtn.textContent = "Verify Image";
    }
  }

  verifyBtn.addEventListener("click", runVerification);

  // ---------------------------------------------------------------------
  // Demo cases — these run the real pipeline on a judge-selected image,
  // never a fabricated result. They just scroll to the uploader and
  // prime the file picker with a short contextual hint.
  // ---------------------------------------------------------------------

  function primeDemo(hint) {
    resetResults();
    document.getElementById("verify").scrollIntoView({ behavior: "smooth" });
    showInfo(hint);
    setTimeout(() => fileInput.click(), 500);
  }

  $("demoPositive").addEventListener("click", () => {
    primeDemo("Positive case: choose an image with a known public web presence, then click Verify.");
  });
  $("demoNegative").addEventListener("click", () => {
    primeDemo("Negative case: choose an image with no public web presence, then click Verify.");
  });
})();