// background.js — Service Worker
// Handles: PDF upload, storage, tab messaging, multi-page auto-fill

const API_BASE = "http://localhost:8000";

// ─────────────────────────────────────────────────────────────
// Upload PDF to backend
// ─────────────────────────────────────────────────────────────
async function uploadPDF(fileBytes, fileName) {
  const formData = new FormData();
  const blob = new Blob([new Uint8Array(fileBytes)], { type: "application/pdf" });
  formData.append("file", blob, fileName);

  const resp = await fetch(`${API_BASE}/autofill`, {
    method: "POST",
    body: formData,
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Server ${resp.status}: ${text.slice(0, 200)}`);
  }
  return await resp.json();
}

// ─────────────────────────────────────────────────────────────
// Inject content script if not already present, then send message
// ─────────────────────────────────────────────────────────────
async function ensureContentScript(tabId) {
  try {
    // Ping first — if content script is alive it responds
    await chrome.tabs.sendMessage(tabId, { type: "PING" });
  } catch (_) {
    // Not injected yet — inject now
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"],
    });
    // Small wait for script to initialise
    await new Promise(r => setTimeout(r, 150));
  }
}

// ─────────────────────────────────────────────────────────────
// Fill active tab (inject if needed, then send payload)
// ─────────────────────────────────────────────────────────────
async function fillActiveTab(sendResponse) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) {
    sendResponse({ ok: false, error: "No active tab found." });
    return;
  }

  const { autofill_payload } = await chrome.storage.local.get("autofill_payload");
  if (!autofill_payload || !Object.keys(autofill_payload).length) {
    sendResponse({ ok: false, error: "No profile saved. Upload a PDF first." });
    return;
  }

  try {
    await ensureContentScript(tab.id);
    const resp = await chrome.tabs.sendMessage(tab.id, {
      type: "DO_AUTOFILL",
      payload: autofill_payload,
    });
    sendResponse(resp || { ok: false, error: "No response from content script." });
  } catch (err) {
    sendResponse({ ok: false, error: err.message });
  }
}

// ─────────────────────────────────────────────────────────────
// Message router
// ─────────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {

  // ── Upload PDF ───────────────────────────────────────────
  if (msg.type === "UPLOAD_PDF") {
    uploadPDF(msg.fileBytes, msg.fileName)
      .then(data => {
        if (data.status !== "success") {
          sendResponse({ ok: false, error: data.error || "Extraction failed" });
          return;
        }
        // Save payload
        chrome.storage.local.set({
          autofill_payload: data.payload
        }, () => sendResponse({ ok: true, payload: data.payload, report: data.report }));
      })
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  // ── Trigger autofill on active tab ──────────────────────
  if (msg.type === "TRIGGER_AUTOFILL") {
    fillActiveTab(sendResponse);
    return true;
  }

  // ── Save edited profile ──────────────────────────────────
  if (msg.type === "SAVE_PROFILE") {
    chrome.storage.local.set({ autofill_payload: msg.payload }, () => {
      sendResponse({ ok: true });
    });
    return true;
  }

  // ── Toggle auto-fill on page load ───────────────────────
  if (msg.type === "SET_AUTO_ENABLED") {
    chrome.storage.local.set({ autofill_enabled: msg.enabled }, () => {
      sendResponse({ ok: true });
    });
    return true;
  }

  // ── Get current state (for popup init) ──────────────────
  if (msg.type === "GET_STATE") {
    chrome.storage.local.get(["autofill_payload"], res => {
      sendResponse({
        ok: true,
        payload: res.autofill_payload || null,
        enabled: true, // We don't use this state anymore, UI toggle can be effectively ignored
      });
    });
    return true;
  }

  // ── Clear data ───────────────────────────────────────────
  if (msg.type === "CLEAR_DATA") {
    chrome.storage.local.remove(["autofill_payload"], () => {
      sendResponse({ ok: true });
    });
    return true;
  }
});