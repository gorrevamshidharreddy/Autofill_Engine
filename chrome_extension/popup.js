// popup.js
"use strict";

// ── DOM shortcuts ──────────────────────────────────────────────
const $ = id => document.getElementById(id);

const statusEl    = $("status");
const headerSub   = $("header-sub");
const toggleRow   = $("toggle-row");
const autoToggle  = $("auto-toggle");

const viewUpload  = $("view-upload");
const viewProfile = $("view-profile");
const fieldsCont  = $("fields-container");
const statsBar    = $("stats-bar");

const uploadZone  = $("upload-zone");
const fileInput   = $("file-input");
const fileNameEl  = $("file-name");
const extractBtn  = $("extract-btn");

const uploadZone2 = $("upload-zone2");
const fileInput2  = $("file-input2");
const fileNameEl2 = $("file-name2");
const extractBtn2 = $("extract-btn2");

const fillBtn  = $("fill-btn");
const saveBtn  = $("save-btn");
const clearBtn = $("clear-btn");

// ── State ──────────────────────────────────────────────────────
let currentPayload = null;   // { selectorKey: { label, value, confidence, key } }
let selectedFile   = null;
let selectedFile2  = null;

// ── Status helper ──────────────────────────────────────────────
function setStatus(html, type = "info", autoClear = 0) {
  statusEl.innerHTML = html;
  statusEl.className = type;
  statusEl.style.display = html ? "block" : "none";
  if (autoClear > 0) setTimeout(() => setStatus(""), autoClear);
}

function loading(msg) {
  setStatus(`<span class="spin"></span>${msg}`, "loading");
}

// ── Confidence badge ───────────────────────────────────────────
function confBadge(c) {
  const cls  = c >= 0.88 ? "conf-h" : c >= 0.65 ? "conf-m" : "conf-l";
  const lbl  = c >= 0.88 ? "high"   : c >= 0.65 ? "mid"    : "low";
  return `<span class="conf ${cls}">${lbl}</span>`;
}

function formatFieldValue(value) {
  if (value && typeof value === "object") {
    return value["dd-mm-yyyy"] || value.raw || "";
  }
  return value || "";
}

// ── Render field list ──────────────────────────────────────────
function renderFields(payload) {
  fieldsCont.innerHTML = "";
  const entries = Object.entries(payload);

  let total = 0, filled = 0, empty = 0;

  entries.forEach(([selector, info]) => {
    if (!info || !info.label) return;
    total++;
    if (info.value) filled++; else empty++;

    const row = document.createElement("div");
    row.className = "field-row";
    row.dataset.selector = selector;

    const lbl = document.createElement("span");
    lbl.className   = "field-lbl";
    lbl.title       = info.label;
    lbl.textContent = info.label;

    const inp = document.createElement("input");
    inp.className   = "field-inp";
    inp.type        = "text";
    inp.value       = formatFieldValue(info.value);
    inp.placeholder = "—";
    inp.dataset.key = info.key || "";

    const badge = document.createElement("span");
    badge.innerHTML = confBadge(info.confidence || 0);

    row.appendChild(lbl);
    row.appendChild(inp);
    row.appendChild(badge.firstChild);
    fieldsCont.appendChild(row);
  });

  $("s-total").textContent  = total;
  $("s-filled").textContent = filled;
  $("s-empty").textContent  = empty;
  statsBar.style.display    = "flex";
}

// ── Collect edited values ──────────────────────────────────────
function collectEdits() {
  const updated = JSON.parse(JSON.stringify(currentPayload));
  fieldsCont.querySelectorAll(".field-row").forEach(row => {
    const sel = row.dataset.selector;
    const val = row.querySelector("input").value.trim();
    if (updated[sel]) updated[sel] = { ...updated[sel], value: val };
  });
  return updated;
}

// ── Show profile view ──────────────────────────────────────────
function showProfile() {
  viewUpload.style.display  = "none";
  viewProfile.style.display = "block";
  toggleRow.style.display   = "flex";
  switchTab("fields");
}

function showUpload() {
  viewUpload.style.display  = "block";
  viewProfile.style.display = "none";
  toggleRow.style.display   = "none";
  statsBar.style.display    = "none";
}

// ── Tab switching ──────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.tab === name)
  );
  $("tab-fields").style.display  = name === "fields"  ? "block" : "none";
  $("tab-replace").style.display = name === "replace" ? "block" : "none";
}

// ── Extract PDF ────────────────────────────────────────────────
async function doExtract(file) {
  if (!file) return;
  loading("Uploading & extracting…");
  extractBtn.disabled  = true;
  extractBtn2.disabled = true;

  const buf = await file.arrayBuffer();

  chrome.runtime.sendMessage(
    {
      type: "UPLOAD_PDF",
      fileBytes: Array.from(new Uint8Array(buf)),
      fileName: file.name,
    },
    resp => {
      extractBtn.disabled  = false;
      extractBtn2.disabled = false;

      if (!resp || !resp.ok) {
        setStatus("❌ " + (resp?.error || "Unknown error"), "error");
        return;
      }

      currentPayload = resp.payload;
      const count    = Object.keys(currentPayload).length;
      headerSub.textContent = `${count} fields saved`;
      autoToggle.checked = false;
      setStatus(`✓ Extracted ${count} fields. Auto-fill is off by default. Click ⚡ to fill this page.`, "success", 4000);
      showProfile();
      renderFields(currentPayload);
    }
  );
}

// ── File input wiring ──────────────────────────────────────────
function wireFileInput(zone, input, nameEl, extractButton, slot) {
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag"); });
  zone.addEventListener("dragleave", ()  => zone.classList.remove("drag"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag");
    const f = e.dataTransfer.files[0];
    if (f?.type === "application/pdf") {
      if (slot === 1) selectedFile  = f;
      else            selectedFile2 = f;
      nameEl.textContent = f.name;
      zone.classList.add("ready");
      extractButton.disabled = false;
    }
  });
  input.addEventListener("change", () => {
    const f = input.files[0];
    if (f) {
      if (slot === 1) selectedFile  = f;
      else            selectedFile2 = f;
      nameEl.textContent = f.name;
      zone.classList.add("ready");
      extractButton.disabled = false;
    }
  });
}

wireFileInput(uploadZone,  fileInput,  fileNameEl,  extractBtn,  1);
wireFileInput(uploadZone2, fileInput2, fileNameEl2, extractBtn2, 2);

extractBtn.addEventListener( "click", () => doExtract(selectedFile));
extractBtn2.addEventListener("click", () => doExtract(selectedFile2));

// ── Tab clicks ────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach(tab =>
  tab.addEventListener("click", () => switchTab(tab.dataset.tab))
);

// ── Autofill button ───────────────────────────────────────────
fillBtn.addEventListener("click", () => {
  loading("Filling form…");
  chrome.runtime.sendMessage({ type: "TRIGGER_AUTOFILL" }, resp => {
    if (!resp || !resp.ok) {
      setStatus("❌ " + (resp?.error || "Could not fill. Open a form page first."), "error");
    } else {
      setStatus(
        `✓ Filled <strong>${resp.filled}</strong> field${resp.filled !== 1 ? "s" : ""} on this page`,
        "success",
        4000
      );
    }
  });
});

// ── Save edits ────────────────────────────────────────────────
saveBtn.addEventListener("click", () => {
  const updated = collectEdits();
  chrome.runtime.sendMessage({ type: "SAVE_PROFILE", payload: updated }, resp => {
    if (resp?.ok) {
      currentPayload = updated;
      setStatus("✓ Changes saved", "success", 2500);
    } else {
      setStatus("❌ Could not save", "error");
    }
  });
});

// ── Clear ─────────────────────────────────────────────────────
clearBtn.addEventListener("click", () => {
  if (!confirm("Delete saved profile? You will need to re-upload your PDF.")) return;
  chrome.runtime.sendMessage({ type: "CLEAR_DATA" }, () => {
    currentPayload         = null;
    autoToggle.checked     = false;
    headerSub.textContent  = "No profile saved";
    selectedFile  = null;
    selectedFile2 = null;
    fileNameEl.textContent  = "";
    fileNameEl2.textContent = "";
    uploadZone.classList.remove("ready");
    showUpload();
    setStatus("Profile cleared.", "info", 2500);
  });
});

// ── Auto-fill toggle ──────────────────────────────────────────
autoToggle.addEventListener("change", () => {
  chrome.runtime.sendMessage({
    type: "SET_AUTO_ENABLED",
    enabled: autoToggle.checked,
  });
});

// ── Init: load saved state ────────────────────────────────────
chrome.runtime.sendMessage({ type: "GET_STATE" }, res => {
  if (!res) return;

  autoToggle.checked = !!res.enabled;

  if (res.payload && Object.keys(res.payload).length) {
    currentPayload = res.payload;
    const count    = Object.keys(currentPayload).length;
    headerSub.textContent = `${count} fields saved`;
    showProfile();
    renderFields(currentPayload);
    setStatus("Profile loaded. Click ⚡ Autofill to fill this page.", "info", 4000);
  }
});