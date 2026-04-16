// content.js
// Injected into every page (all_frames: true).
// Finds form fields, matches them to the saved profile, fills them accurately.
// Works on multi-page forms, SPAs, React, Vue, Angular.

(function () {
  "use strict";

  // Prevent double-injection
  if (window.__autofillInjected) return;
  window.__autofillInjected = true;

  // ─────────────────────────────────────────────────────────
  // SYNONYM MAP
  // key   = canonical field key (matches payload keys from backend)
  // value = array of label strings that map to this field
  // ORDER MATTERS — more specific entries first
  // ─────────────────────────────────────────────────────────
  const SYNONYM_MAP = {
    // ── Name ──────────────────────────────────────────────
    full_name:    ["full name","full name *","student name","candidate name","applicant name","name"],
    first_name:   ["first name","given name","firstname","first"],
    middle_name:  ["middle name","middlename","middle"],
    last_name:    ["last name","surname","family name","lastname","last"],

    // ── Personal ──────────────────────────────────────────
    gender:         ["gender","sex"],
    blood_group:    ["blood group","blood type","bg","blood"],
    dob:            ["date of birth","dob","birth date","d.o.b","birthdate","date of birth (dd-mm-yyyy)","date of birth dd-mm-yyyy"],
    age:            ["age","age (auto-calculated)","age auto calculated","age in years"],
    nationality:    ["nationality","citizenship"],
    mother_tongue:  ["mother tongue","native language","first language","language","home language","regional language","spoken language"],
    email:          ["email","e-mail","email address","mail","email id","email-id","e mail"],
    religion:       ["religion","faith"],
    marital_status: ["marital status","marital","married","relationship status"],
    aadhar:         ["aadhaar number","aadhar number","aadhaar","aadhar","aadhar no","uid","12-digit aadhaar","aadhaar no","uidai"],
    caste_category: ["caste category","caste","category","sub-caste","social category"],

    // ── Contact ───────────────────────────────────────────
    phone:           ["mobile number","phone number","mobile","phone","contact number","cell","telephone","10-digit mobile","primary mobile"],
    alternate_phone: ["alternate mobile","alternate phone","secondary phone","other mobile","alternative mobile","alt mobile","alternate number","alternative number"],

    // ── Parent / Guardian ─────────────────────────────────
    // NOTE: father/mother specific keys must be checked BEFORE generic "phone"
    father_name:       ["father / guardian name","father name","father guardian name","father's name","father"],
    father_mobile:     ["father mobile","father phone","father contact","father's mobile","father mobile number","father's phone"],
    father_occupation: ["father occupation","father's occupation","father profession"],
    mother_name:       ["mother / guardian name","mother name","mother guardian name","mother's name","mother"],
    mother_mobile:     ["mother mobile","mother phone","mother contact","mother's mobile","mother mobile number","mother's phone"],
    mother_occupation: ["mother occupation","mother's occupation","mother profession"],
    guardian_email:    ["parent / guardian email","parent email","guardian email","family email","parent guardian email","parents email"],

    // ── Emergency Contact ─────────────────────────────────
    emergency_contact_name:   ["emergency contact name","emergency contact","emergency name","contact name","contact person name"],
    emergency_contact_number: ["emergency contact number","emergency number","emergency phone","emergency mobile","contact number"],
    relationship:             ["relationship","relation","relation with student","relationship to student","relation with patient"],

    // ── Address ───────────────────────────────────────────
    address:   ["address","residential address","current address","permanent address","mailing address","full address"],
    house_no:  ["house no","house no.","house number","flat no","flat number","door no","h.no","plot no","house","flat","door number"],
    street:    ["street / locality","street","street address","locality","road","lane","area","street or locality"],
    city:      ["village / town / city","city / town","city/town","city","town","village","city or village","city or town","village town city"],
    mandal:    ["mandal / taluk","mandal","taluk","tehsil","mandal or taluk","mandal/taluk","taluka"],
    district:  ["district"],
    state:     ["state","province"],
    country:   ["country","nation","country of residence","country of birth"],
    pincode:   ["pincode","pin code","pin","zip","zip code","postal code","post code","6-digit pin code"],

    // ── Branch / Institution ──────────────────────────────
    branch_id: ["branch id","branch code","branch","branch number"],

    // ── Academic ──────────────────────────────────────────
    class_:           ["class","grade","standard","std"],
    section:          ["section","division"],
    admission_number: ["admission number","admission no","adm no","roll number","roll no","admission"],
    // academic_year intentionally NOT including bare "year" to avoid DOB year clash
    academic_year:    ["academic year","academic session","school year","academic year *"],
    // medium intentionally NOT including language/tongue words
    medium:           ["medium of instruction","medium","instruction medium","teaching medium","language of instruction"],
    date_of_admission:["date of admission","admission date","joining date","date of joining"],
    previous_school:  ["previous school name","previous school","last school","school name","school"],
    tc_number:        ["transfer certificate","tc number","tc no"],

    // ── Health / Emergency / Transport ────────────────────
    allergies:          ["allergies details","allergies","allergy","any allergies","allergy details"],
    medical_conditions: ["medical conditions","medical condition","any medical conditions","health conditions","medical history"],
    nearest_hospital:   ["nearest hospital / doctor","nearest hospital","hospital","doctor name","hospital or doctor name"],
    transport_mode:     ["mode of transport","transport mode","transport","conveyance","mode of conveyance"],
    bus_route:          ["bus route / vehicle number","bus route","vehicle number","route number","bus route or vehicle no"],
    hostel:             ["hostel / day scholar","hostel","day scholar","boarding","hostel or day scholar","day scholar or hostel"],

    // ── Professional / Universal ──────────────────────────
    website:          ["website","personal website","portfolio url","blog","web address","portfolio"],
    linkedin:         ["linkedin","linkedin profile","linkedin url"],
    pan_number:       ["pan number","pan no","pan card","permanent account number","pan"],
    passport_number:  ["passport number","passport no","passport"],
    voter_id:         ["voter id","voter id number","epic number","voter card"],
    driving_license:  ["driving license","driving licence","dl number","license number","licence number"],
    employee_id:      ["employee id","emp id","staff id","employee number","employee code"],
    department:       ["department","dept"],
    designation:      ["designation","job title","position","role","post","title"],
    annual_income:    ["annual income","yearly income","income","family income","annual salary"],
    bank_account:     ["bank account number","account number","bank account no","account no"],
    ifsc_code:        ["ifsc code","ifsc","bank ifsc","ifsc number"],
  };

  // Build reverse lookup: normalised_synonym → canonical_key
  // Longer synonyms take priority (sorted descending by length)
  const REVERSE_MAP = new Map();
  for (const [key, synonyms] of Object.entries(SYNONYM_MAP)) {
    const sorted = [...synonyms].sort((a, b) => b.length - a.length);
    for (const syn of sorted) {
      const n = normStr(syn);
      if (!REVERSE_MAP.has(n)) REVERSE_MAP.set(n, key);
    }
  }

  // ─────────────────────────────────────────────────────────
  // String helpers
  // ─────────────────────────────────────────────────────────

  function normStr(s) {
    return (s || "")
      .toLowerCase()
      .replace(/[*†‡✱•]/g, "")          // required-field markers
      .replace(/\s+/g, " ")
      .replace(/^(enter|type|select|choose|e\.g\.?|eg\.?)\s+/i, "")
      .replace(/\s+(here|below)$/i, "")
      .trim();
  }

  // Levenshtein distance (capped for performance)
  function levenshtein(a, b) {
    if (Math.abs(a.length - b.length) > 20) return 999;
    const m = a.length, n = b.length;
    const dp = [];
    for (let i = 0; i <= m; i++) dp[i] = [i];
    for (let j = 0; j <= n; j++) dp[0][j] = j;
    for (let i = 1; i <= m; i++)
      for (let j = 1; j <= n; j++)
        dp[i][j] = a[i-1] === b[j-1]
          ? dp[i-1][j-1]
          : 1 + Math.min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1]);
    return dp[m][n];
  }

  // Similarity 0→1 combining exact, substring, token-overlap, and edit distance
  function similarity(query, candidate) {
    const q = normStr(query);
    const c = normStr(candidate);
    if (!q || !c) return 0;
    if (q === c) return 1.0;
    if (q.includes(c) || c.includes(q)) return 0.92;

    // Token overlap score
    const qt = new Set(q.split(" "));
    const ct = new Set(c.split(" "));
    const inter = [...qt].filter(t => ct.has(t)).length;
    const tokenScore = inter > 0 ? (2 * inter) / (qt.size + ct.size) : 0;

    // Edit distance score
    const dist  = levenshtein(q, c);
    const editScore = 1 - dist / Math.max(q.length, c.length);

    return Math.max(tokenScore, editScore);
  }

  // ─────────────────────────────────────────────────────────
  // Label extraction — 6 strategies in priority order
  // ─────────────────────────────────────────────────────────

  function getFieldLabel(el) {
    const candidates = [];

    // 1. <label for="id">
    if (el.id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lbl) candidates.push({ text: lbl.innerText || lbl.textContent, score: 1.0 });
    }

    // 2. aria-label / aria-labelledby
    const ariaLabel = el.getAttribute("aria-label");
    if (ariaLabel) candidates.push({ text: ariaLabel, score: 0.95 });
    const ariaId = el.getAttribute("aria-labelledby");
    if (ariaId) {
      const ref = document.getElementById(ariaId);
      if (ref) candidates.push({ text: ref.innerText || ref.textContent, score: 0.95 });
    }

    // 3. Wrapping <label> element
    let p = el.parentElement;
    let depth = 0;
    while (p && depth < 5) {
      if (p.tagName === "LABEL") {
        const clone = p.cloneNode(true);
        // Remove input/select/textarea text from clone
        clone.querySelectorAll("input,select,textarea").forEach(c => c.remove());
        const t = (clone.innerText || clone.textContent || "").trim();
        if (t) candidates.push({ text: t, score: 0.9 - depth * 0.05 });
        break;
      }
      p = p.parentElement;
      depth++;
    }

    // 4. Sibling / nearby <label> or <span> / <div> with label-like class
    const parent = el.parentElement;
    if (parent) {
      const sibs = Array.from(parent.children);
      const idx  = sibs.indexOf(el);
      for (let i = idx - 1; i >= Math.max(0, idx - 3); i--) {
        const sib = sibs[i];
        const tag = sib.tagName;
        if (["LABEL","SPAN","DIV","P","LI","TD","TH","DT","LEGEND"].includes(tag)) {
          const t = (sib.innerText || sib.textContent || "").trim();
          if (t && t.length < 100) {
            candidates.push({ text: t, score: 0.85 - (idx - i) * 0.05 });
          }
        }
      }
    }

    // 5. name / id attribute (camelCase → words)
    const nameAttr = el.name || el.id || "";
    if (nameAttr) {
      const readable = nameAttr
        .replace(/([a-z])([A-Z])/g, "$1 $2")
        .replace(/[_\-]/g, " ");
      candidates.push({ text: readable, score: 0.6 });
    }

    // 6. placeholder
    if (el.placeholder) candidates.push({ text: el.placeholder, score: 0.5 });

    // Pick highest-confidence non-empty candidate
    candidates.sort((a, b) => b.score - a.score);
    for (const c of candidates) {
      const t = (c.text || "").trim().replace(/\s+/g, " ");
      if (t && t.length > 1 && t.length < 120) return t;
    }
    return "";
  }

  // ─────────────────────────────────────────────────────────
  // Field → payload key matching
  // ─────────────────────────────────────────────────────────

  function matchFieldToKey(el, payload) {
    const labelRaw = getFieldLabel(el);
    if (!labelRaw) return null;

    const labelNorm = normStr(labelRaw);

    // Combine all hints: label + name attr + id attr
    const nameHint = normStr(el.name || "");
    const idHint   = normStr(el.id   || "");

    // ── Strategy 1: Exact match in reverse map ─────────────
    if (REVERSE_MAP.has(labelNorm)) {
      const key = REVERSE_MAP.get(labelNorm);
      if (payload[key] !== undefined) return { key, score: 1.0 };
    }

    // Exact label matching only. Fuzzy match removed to prevent errors.
    return null;
  }

  // ─────────────────────────────────────────────────────────
  // Value formatting
  // ─────────────────────────────────────────────────────────

  function formatValue(el, key, rawValue) {
    if (!rawValue) return "";
    const v = String(rawValue);

    // DOB: detect format from placeholder or input type
    if (key === "dob" && typeof rawValue === "object") {
      if (el.type === "date") {
        return rawValue["yyyy-mm-dd"] || rawValue["yyyy_mm_dd"] || "";
      }
      const ph = normStr(el.placeholder || "");
      if (ph.includes("yyyy") && ph.includes("mm") && ph.startsWith("yyyy"))
        return rawValue["yyyy-mm-dd"] || rawValue["yyyy_mm_dd"] || "";
      if (ph.includes("mm") && ph.includes("dd") && ph.startsWith("mm"))
        return rawValue["mm/dd/yyyy"] || rawValue["mm_slash"] || "";
      return rawValue["dd-mm-yyyy"] || rawValue["dd_mm_yyyy"] || "";
    }

    // Aadhaar: the payload stores 12 raw digits; check if form wants spaces
    if (key === "aadhar") {
      const digits = v.replace(/\D/g, "");
      if (digits.length === 12) {
        const ph = el.placeholder || "";
        // If placeholder shows "XXXX XXXX XXXX" format use spaces
        if (/\d{4}\s\d{4}/.test(ph)) {
          return `${digits.slice(0,4)} ${digits.slice(4,8)} ${digits.slice(8)}`;
        }
        return digits;
      }
    }

    return v;
  }

  // ─────────────────────────────────────────────────────────
  // Native-event fill (works with React / Vue / Angular)
  // ─────────────────────────────────────────────────────────

  function nativeFill(el, value) {
    if (!value) return false;

    el.focus();

    if (el.tagName === "SELECT") {
      const normValue = normStr(value);
      let matched = false;
      for (const opt of el.options) {
        if (normStr(opt.text) === normValue || normStr(opt.value) === normValue) {
          el.value = opt.value;
          matched = true;
          break;
        }
      }
      // Fuzzy match if exact failed
      if (!matched) {
        let bestOpt = null, bestScore = 0;
        for (const opt of el.options) {
          const s = similarity(normValue, normStr(opt.text));
          if (s > bestScore) { bestScore = s; bestOpt = opt; }
        }
        if (bestScore >= 0.65 && bestOpt) {
          el.value = bestOpt.value;
          matched  = true;
        }
      }
      if (!matched) return false;
    } else {
      // React-compatible setter
      const proto = el.tagName === "TEXTAREA"
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      if (setter) {
        try {
          setter.call(el, value);
        } catch (e) {
          el.value = value;
        }
      } else {
        el.value = value;
      }
    }

    // Fire all events React/Vue/Angular might listen to
    ["input","change","blur","keyup"].forEach(evt => {
      el.dispatchEvent(new Event(evt, { bubbles: true, cancelable: true }));
    });

    return true;
  }

  // ─────────────────────────────────────────────────────────
  // Build a flat value map from the payload
  // payload = { selectorKey: { label, value, confidence, key } }
  // We need: canonicalKey → display_value
  // ─────────────────────────────────────────────────────────

  function buildValueMap(payload) {
    const map = {};
    for (const info of Object.values(payload)) {
      if (info && info.key && info.value !== undefined && info.value !== "") {
        map[info.key] = info.value;
      }
    }
    return map;
  }

  // ─────────────────────────────────────────────────────────
  // Main autofill routine
  // ─────────────────────────────────────────────────────────

  function doAutofill(payload) {
    if (!payload || !Object.keys(payload).length) return { filled: 0, total: 0 };

    const valueMap = buildValueMap(payload);

    // Collect fillable inputs
    const inputs = Array.from(
      document.querySelectorAll("input, select, textarea")
    ).filter(el => {
      const type = (el.type || "text").toLowerCase();
      return !["hidden","submit","button","reset","file",
               "image","checkbox","radio"].includes(type)
          && !el.disabled && !el.readOnly;
    });

    let filled = 0;

    for (const el of inputs) {
      const match = matchFieldToKey(el, valueMap);
      if (!match) continue;

      const rawVal = valueMap[match.key];
      if (rawVal === undefined || rawVal === null || rawVal === "") continue;

      const formattedVal = formatValue(el, match.key, rawVal);
      if (!formattedVal) continue;

      const success = nativeFill(el, formattedVal);
      if (success) {
        filled++;
        // Green flash to confirm fill
        const prev = el.style.outline;
        el.style.outline = "2px solid #22c55e";
        el.style.transition = "outline 0.5s";
        setTimeout(() => { el.style.outline = prev; }, 1800);
      }
    }

    return { filled, total: inputs.length };
  }

  // ─────────────────────────────────────────────────────────
  // Message listener
  // ─────────────────────────────────────────────────────────

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {

    if (msg.type === "PING") {
      sendResponse({ ok: true });
      return false;
    }

    if (msg.type === "DO_AUTOFILL") {
      const payload = msg.payload;
      if (!payload) {
        sendResponse({ ok: false, error: "No payload provided." });
        return false;
      }
      const result = doAutofill(payload);
      sendResponse({ ok: true, filled: result.filled, total: result.total });
      return false;
    }
  });

})();