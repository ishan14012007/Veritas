// Main UI Application Logic for Argus
lucide.createIcons();

let currentLastReport = null;
let currentPayPalOrderId = null;
let paypalConfig = null;

// Tab Switching
function switchTab(tabName) {
  const tabs = ['simulator', 'registry', 'audit', 'appeals'];
  tabs.forEach(t => {
    const btn = document.getElementById(`tabBtn-${t}`);
    const content = document.getElementById(`tabContent-${t}`);
    if (t === tabName) {
      btn.className = "px-3 py-1.5 rounded-lg transition-all text-white bg-blue-600 shadow-md";
      content.classList.remove('hidden');
    } else {
      btn.className = "px-3 py-1.5 rounded-lg transition-all text-slate-400 hover:text-white";
      content.classList.add('hidden');
    }
  });

  if (tabName === 'registry') {
    loadRegistryGrid();
    setTimeout(() => { if (registryGridApi) registryGridApi.sizeColumnsToFit(); }, 50);
  }
  if (tabName === 'audit') {
    loadAuditGrid();
    setTimeout(() => { if (auditGridApi) auditGridApi.sizeColumnsToFit(); }, 50);
  }
  if (tabName === 'appeals') {
    loadAppealsGrid();
    setTimeout(() => { if (appealsGridApi) appealsGridApi.sizeColumnsToFit(); }, 50);
  }
}

// -------------------------------------------------------------
// Dynamic Checkout Intent Presets Manager
// -------------------------------------------------------------
const defaultPresets = [
  {
    id: "nike",
    name: "Nike Store",
    brand: "Nike",
    url: "https://www.nike.com/in/t/air-jordan-1-retro-high-og",
    product: "Air Jordan 1 Retro",
    price: 180.00,
    lastScore: 94,
    lastStatus: "PASSED"
  },
  {
    id: "boat",
    name: "boAt Lifestyle",
    brand: "boAt Lifestyle",
    url: "https://www.boat-lifestyle.com/products/rockerz-450",
    product: "boAt Rockerz 450",
    price: 24.99,
    lastScore: 92,
    lastStatus: "PASSED"
  },
  {
    id: "apple_store",
    name: "Apple Store (Official)",
    brand: "Apple",
    url: "https://apple.com/buy/iphone16",
    product: "iPhone 16 Pro Max",
    price: 1199.00,
    lastScore: 75,
    lastStatus: "PASSED"
  },
  {
    id: "amazon_phish",
    name: "Amazon Phishing Trap",
    brand: "Amazon India",
    url: "https://amaz0n-mega-deals.xyz/buy/airpods",
    product: "Apple AirPods Pro 2",
    price: 14.99,
    lastScore: 11,
    lastStatus: "VOIDED"
  },
  {
    id: "apple_scam",
    name: "Apple Clearance Scam",
    brand: "Apple",
    url: "https://apple-clearance-fest.shop/buy/iphone16",
    product: "iPhone 16 Pro Max",
    price: 49.99,
    lastScore: 11,
    lastStatus: "VOIDED"
  },
  {
    id: "my_sandbox_seller",
    name: "Verified Merchant (2252PMF2CJ7Q2)",
    brand: "Sandbox Verified Store",
    url: "https://sandbox-store.paypal.com/item/demo",
    product: "Verified Merchant Demo Item",
    price: 39.99,
    lastScore: 98,
    lastStatus: "PASSED"
  }
];

let presetsList = [];
let selectedPresetId = "apple_store";

function cleanHost(urlStr) {
  try {
    const parsed = new URL(urlStr);
    return parsed.hostname.replace(/^www\./, '');
  } catch (e) {
    if (!urlStr) return 'unknown';
    const parts = urlStr.replace(/^https?:\/\//, '').split('/');
    return parts[0].replace(/^www\./, '');
  }
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function initPresets() {
  presetsList = [];
  try {
    const saved = localStorage.getItem("argus_checkout_presets_v5");
    if (saved) {
      presetsList = JSON.parse(saved);
    }
  } catch(e) {
    presetsList = [];
  }

  // Fallback to default presets if storage was empty, corrupted, or cleared
  if (!Array.isArray(presetsList) || presetsList.length === 0) {
    presetsList = JSON.parse(JSON.stringify(defaultPresets));
    savePresetsToStorage();
  }

  renderPresets();
  if (presetsList.length > 0) {
    const initial = presetsList.find(p => p.id === "apple_store") || presetsList[0];
    selectPreset(initial.id);
  }
}

function savePresetsToStorage() {
  try {
    localStorage.setItem("argus_checkout_presets_v5", JSON.stringify(presetsList));
  } catch(e) {
    console.warn("Could not save to localStorage:", e);
  }
}

function renderPresets() {
  const container = document.getElementById("presetsContainer");
  if (!container) return;

  if (!presetsList || presetsList.length === 0) {
    container.innerHTML = `
      <div class="col-span-2 text-center py-4 bg-slate-900/60 rounded-xl border border-dashed border-slate-800">
        <p class="text-[11px] text-slate-400 mb-1.5">No intent presets available.</p>
        <button type="button" onclick="resetDefaultPresets()" class="px-2.5 py-1 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-[10px] font-bold shadow">
          Load Default Presets
        </button>
      </div>
    `;
    return;
  }

  container.innerHTML = presetsList.map(p => {
    const isSelected = p.id === selectedPresetId;
    let cardStyle = "border-slate-800 bg-slate-900/60 hover:border-slate-700 text-slate-300";
    let statusIcon = "⚪";
    let titleClass = "text-slate-200";
    let badgeClass = "text-slate-400 bg-slate-950/80 border-slate-800";
    let badgeText = "Untested";

    if (p.lastStatus === "PASSED") {
      cardStyle = "border-emerald-500/40 bg-emerald-950/20 hover:border-emerald-400";
      statusIcon = "🟢";
      titleClass = "text-emerald-300";
      badgeClass = "text-emerald-400 bg-emerald-500/10 border-emerald-500/30";
      badgeText = `${p.lastScore}/100`;
    } else if (p.lastStatus === "WARNED") {
      cardStyle = "border-amber-500/40 bg-amber-950/20 hover:border-amber-400";
      statusIcon = "🟡";
      titleClass = "text-amber-300";
      badgeClass = "text-amber-400 bg-amber-500/10 border-amber-500/30";
      badgeText = `${p.lastScore}/100`;
    } else if (p.lastStatus === "VOIDED") {
      cardStyle = "border-rose-900/40 bg-rose-950/20 hover:border-rose-500";
      statusIcon = "🚨";
      titleClass = "text-rose-300";
      badgeClass = "text-rose-400 bg-rose-500/10 border-rose-500/30";
      badgeText = `${p.lastScore}/100`;
    }

    const ringStyle = isSelected ? "ring-2 ring-cyan-500 shadow-md shadow-cyan-500/20" : "";

    return `
      <div onclick="selectPreset('${p.id}')"
        class="group relative text-left p-2.5 rounded-xl border ${cardStyle} ${ringStyle} transition-all text-xs cursor-pointer flex flex-col justify-between">
        <div class="flex items-start justify-between gap-1">
          <span class="font-bold ${titleClass} block truncate text-[11px] flex items-center gap-1">
            <span>${statusIcon}</span>
            <span class="truncate">${escapeHtml(p.name)}</span>
          </span>
          <button type="button" onclick="deletePreset('${p.id}', event)" title="Remove this preset"
            class="opacity-0 group-hover:opacity-100 p-0.5 rounded text-slate-500 hover:text-rose-400 hover:bg-slate-800 transition-all">
            ✕
          </button>
        </div>
        <div class="flex items-center justify-between text-[10px] text-slate-400 font-mono mt-1.5">
          <span class="truncate max-w-[110px] text-slate-400">${cleanHost(p.url)}</span>
          <span class="font-semibold px-1.5 py-0.5 rounded border ${badgeClass} text-[9px]">${badgeText}</span>
        </div>
      </div>
    `;
  }).join("");

  lucide.createIcons();
}

function selectPreset(id) {
  selectedPresetId = id;
  const p = presetsList.find(x => x.id === id);
  if (!p) return;

  document.getElementById("brandInput").value = p.brand;
  document.getElementById("urlInput").value = p.url;
  document.getElementById("productInput").value = p.product;
  document.getElementById("priceInput").value = p.price;

  updateActiveIntentBanner(p);
  renderPresets();
}

// Backward compatibility for any direct call
function loadPreset(key) {
  selectPreset(key);
}

function updateActiveIntentBanner(p) {
  const banner = document.getElementById("activeIntentBanner");
  const dot = document.getElementById("activeIntentDot");
  const label = document.getElementById("activeIntentLabel");
  const score = document.getElementById("activeIntentScore");
  if (!banner || !dot || !label || !score) return;

  label.innerText = `${p.brand} (${cleanHost(p.url)})`;

  if (p.lastStatus === "PASSED") {
    dot.className = "w-2 h-2 rounded-full bg-emerald-400 inline-block";
    score.className = "font-mono text-[10px] font-bold text-emerald-400";
    score.innerText = `Verified • ${p.lastScore}/100`;
  } else if (p.lastStatus === "WARNED") {
    dot.className = "w-2 h-2 rounded-full bg-amber-400 inline-block";
    score.className = "font-mono text-[10px] font-bold text-amber-400";
    score.innerText = `Step-Up Required • ${p.lastScore}/100`;
  } else if (p.lastStatus === "VOIDED") {
    dot.className = "w-2 h-2 rounded-full bg-rose-400 animate-pulse inline-block";
    score.className = "font-mono text-[10px] font-bold text-rose-400";
    score.innerText = `Phishing / Sealed • ${p.lastScore}/100`;
  } else {
    dot.className = "w-2 h-2 rounded-full bg-slate-500 inline-block";
    score.className = "font-mono text-[10px] font-bold text-slate-400";
    score.innerText = `Untested`;
  }
}

function updatePresetWithReport(report, payload) {
  const urlHost = cleanHost(payload.merchant_url);

  // Find by selectedPresetId or match URL
  let targetPreset = presetsList.find(p => p.id === selectedPresetId);
  if (!targetPreset) {
    targetPreset = presetsList.find(p => cleanHost(p.url) === urlHost);
  }

  const newStatus = report.action_taken === "APPROVED_FOR_CAPTURE"
    ? "PASSED"
    : (report.action_taken === "WARNED_REQUIRE_CONFIRMATION" ? "WARNED" : "VOIDED");

  if (targetPreset) {
    targetPreset.brand = payload.brand_name;
    targetPreset.url = payload.merchant_url;
    targetPreset.product = payload.product_name;
    targetPreset.price = payload.price;
    targetPreset.lastScore = report.trust_score;
    targetPreset.lastStatus = newStatus;

    // Adapt name if it was previously labeled a scam and now passed as genuine!
    if (newStatus === "PASSED" && /scam|phish|clearance/i.test(targetPreset.name)) {
      targetPreset.name = `${payload.brand_name} Store (${urlHost})`;
    } else if (newStatus === "VOIDED" && !/scam|phish/i.test(targetPreset.name)) {
      targetPreset.name = `${payload.brand_name} (Suspicious)`;
    }

    updateActiveIntentBanner(targetPreset);
  } else {
    // Brand new custom intent evaluated -> add it to presets list
    const newId = "intent_" + Date.now();
    targetPreset = {
      id: newId,
      name: `${payload.brand_name} (${urlHost})`,
      brand: payload.brand_name,
      url: payload.merchant_url,
      product: payload.product_name,
      price: payload.price,
      lastScore: report.trust_score,
      lastStatus: newStatus
    };
    presetsList.push(targetPreset);
    selectedPresetId = newId;
    updateActiveIntentBanner(targetPreset);
  }

  savePresetsToStorage();
  renderPresets();
}

// Modal Handlers for Intent Manager
function openAddIntentModal() {
  document.getElementById("newIntentName").value = "";
  document.getElementById("newIntentBrand").value = "";
  document.getElementById("newIntentUrl").value = "";
  document.getElementById("newIntentProduct").value = "";
  document.getElementById("newIntentPrice").value = "";
  document.getElementById("addIntentModal").classList.remove("hidden");
}

function closeAddIntentModal() {
  document.getElementById("addIntentModal").classList.add("hidden");
}

function submitNewIntent() {
  const nameInput = document.getElementById("newIntentName");
  const brandInput = document.getElementById("newIntentBrand");
  const urlInput = document.getElementById("newIntentUrl");
  const productInput = document.getElementById("newIntentProduct");
  const priceInput = document.getElementById("newIntentPrice");

  const name = nameInput ? nameInput.value.trim() : "";
  const brand = brandInput ? brandInput.value.trim() : "";
  let url = urlInput ? urlInput.value.trim() : "";
  const product = productInput ? productInput.value.trim() : "";
  const price = priceInput ? parseFloat(priceInput.value) || 0 : 0;

  if (!brand || !url) {
    alert("Please provide Brand Name and Store URL.");
    return;
  }

  if (!url.startsWith("http://") && !url.startsWith("https://")) {
    url = "https://" + url;
  }

  const host = cleanHost(url);
  const newId = "intent_" + Date.now();
  const newPreset = {
    id: newId,
    name: name || `${brand} Store (${host})`,
    brand: brand,
    url: url,
    product: product || "Standard Product",
    price: price,
    lastScore: null,
    lastStatus: "UNTESTED"
  };

  presetsList.unshift(newPreset);
  savePresetsToStorage();
  closeAddIntentModal();
  selectPreset(newId);
  alert(`✓ New intent preset "${newPreset.name}" created and loaded into checkout simulator!`);
}

function saveCurrentFormAsPreset() {
  const brand = document.getElementById("brandInput").value.trim();
  let url = document.getElementById("urlInput").value.trim();
  const product = document.getElementById("productInput").value.trim();
  const price = parseFloat(document.getElementById("priceInput").value) || 0;

  if (!brand || !url) {
    alert("Please enter both Brand Name and Store URL in the checkout simulator form first.");
    return;
  }

  if (!url.startsWith("http://") && !url.startsWith("https://")) {
    url = "https://" + url;
    document.getElementById("urlInput").value = url;
  }

  const host = cleanHost(url);
  const name = `${brand} (${host})`;

  const newId = "intent_" + Date.now();
  const newPreset = {
    id: newId,
    name: name,
    brand: brand,
    url: url,
    product: product || "Product",
    price: price,
    lastScore: currentLastReport ? currentLastReport.trust_score : null,
    lastStatus: currentLastReport
      ? (currentLastReport.action_taken === "APPROVED_FOR_CAPTURE" ? "PASSED" : (currentLastReport.action_taken === "WARNED_REQUIRE_CONFIRMATION" ? "WARNED" : "VOIDED"))
      : "UNTESTED"
  };

  // Add to top of list
  presetsList.unshift(newPreset);
  savePresetsToStorage();
  selectPreset(newId);
  alert(`✓ Current checkout intent saved as preset: "${name}"!\nYou can click it anytime to load and re-verify.`);
}

function deletePreset(id, evt) {
  if (evt) evt.stopPropagation();
  const p = presetsList.find(x => x.id === id);
  const confirmMsg = p ? `Remove preset "${p.name}"?` : "Remove this preset?";
  if (!confirm(confirmMsg)) return;

  presetsList = presetsList.filter(x => x.id !== id);
  if (presetsList.length === 0) {
    presetsList = JSON.parse(JSON.stringify(defaultPresets));
  }

  if (selectedPresetId === id) {
    selectedPresetId = presetsList[0].id;
    selectPreset(selectedPresetId);
  } else {
    savePresetsToStorage();
    renderPresets();
  }
}

function resetDefaultPresets() {
  if (!confirm("Reset all presets to default evaluation set?")) return;
  presetsList = JSON.parse(JSON.stringify(defaultPresets));
  savePresetsToStorage();
  selectPreset(presetsList[0].id);
  alert("Default presets restored successfully!");
}

// -------------------------------------------------------------
// Core Verification Execution & PayPal Lifecycle Stepper
// -------------------------------------------------------------
function updatePPStep(stepNum, status, title, detail, isSuccess) {
  const badge = document.getElementById(`ppStep${stepNum}Badge`);
  const titleEl = document.getElementById(`ppStep${stepNum}Title`);
  const detailEl = document.getElementById(`ppStep${stepNum}Detail`);
  const card = document.getElementById(`ppStep${stepNum}`);

  if (badge) {
    badge.innerText = status;
    if (isSuccess === true) {
      badge.className = "text-emerald-400 font-bold";
    } else if (status === "VOIDED" || status === "BLOCKED") {
      badge.className = "text-rose-400 font-bold";
    } else if (status === "ACTIVE" || status === "HELD" || status === "DONE") {
      badge.className = "text-cyan-400 font-bold";
    } else {
      badge.className = "text-amber-400 font-bold";
    }
  }
  if (titleEl) titleEl.innerText = title;
  if (detailEl) detailEl.innerText = detail;
  if (card) {
    if (isSuccess === true) {
      card.className = "p-2.5 rounded-xl bg-emerald-950/30 border border-emerald-500/40 space-y-1 transition-all";
    } else if (status === "VOIDED" || status === "BLOCKED") {
      card.className = "p-2.5 rounded-xl bg-rose-950/30 border border-rose-500/40 space-y-1 transition-all";
    } else {
      card.className = "p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 space-y-1 transition-all";
    }
  }
}

async function executeVerification() {
  const btn = document.getElementById("payButton");
  btn.disabled = true;
  btn.innerHTML = `<span class="animate-spin inline-block mr-2">⚡</span> Authorizing & Intercepting...`;

  const payload = {
    brand_name: document.getElementById("brandInput").value,
    merchant_url: document.getElementById("urlInput").value,
    product_name: document.getElementById("productInput").value,
    price: parseFloat(document.getElementById("priceInput").value),
    currency: "USD"
  };

  try {
    updatePPStep(1, "CREATING", "Pre-Hold Order...", "intent: AUTHORIZE", null);
    updatePPStep(2, "SCANNING", "Running AI...", "Forensic Workers active", null);
    updatePPStep(3, "PENDING", "Awaiting Decision", "Pre-settlement buffer", null);

    const verifyPromise = fetch("/api/v1/checkout/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(r => r.json());

    const orderPromise = fetch("/api/v1/paypal/create-order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        amount: payload.price,
        currency: payload.currency,
        brand_name: payload.brand_name
      })
    }).then(r => r.json());

    const [report, orderData] = await Promise.all([verifyPromise, orderPromise]);
    currentLastReport = report;
    currentPayPalOrderId = orderData.order_id;

    renderReport(report);
    updatePresetWithReport(report, payload);

    const shortId = (orderData.order_id || "PAYID-SIM").slice(0, 16);
    updatePPStep(1, "HELD", `Hold: ${shortId}...`, "Funds Reserved (intent: AUTHORIZE)", true);
    updatePPStep(2, "DONE", `Score: ${report.trust_score}/100`, `${report.total_latency_ms} ms Latency`, report.trust_score >= 70);

    if (report.action_taken === "APPROVED_FOR_CAPTURE") {
      const capRes = await fetch("/api/v1/paypal/capture-order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ order_id: currentPayPalOrderId })
      }).then(r => r.json());

      const capId = (capRes.capture_id || "CAP-SETTLED").slice(0, 14);
      updatePPStep(3, "CAPTURED", `Settled: ${capId}...`, "Funds released to 2252PMF2CJ7Q2", true);
    } else if (report.action_taken === "TRANSACTION_VOIDED_AND_ACCOUNT_SEALED") {
      await fetch("/api/v1/paypal/void-order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          order_id: currentPayPalOrderId,
          merchant_id: `MCH-${report.root_domain.replace(/\./g, '').toUpperCase().slice(0, 8)}`,
          reason: report.evidence.join("; ")
        })
      });

      updatePPStep(3, "VOIDED", "Authorization Voided", "0 chargeback fees! Scammer blocked", false);
    } else {
      updatePPStep(3, "WARNED", "Step-Up Required", "Hold active until user confirms", null);
    }

    loadAuditGrid();
    loadRegistryGrid();
  } catch (err) {
    alert("Verification failed: " + err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span class="italic font-black text-blue-900">Pay</span><span class="italic font-black text-sky-600">Pal</span> <span class="text-xs font-bold ml-1 text-slate-800">1-Click Fast Interceptor Test</span>`;
  }
}

function renderReport(r) {
  const card = document.getElementById("verdictCard");
  const iconCont = document.getElementById("verdictIconContainer");
  const badge = document.getElementById("verdictBadge");
  const title = document.getElementById("verdictTitle");
  const sub = document.getElementById("verdictSubtitle");
  const score = document.getElementById("scoreDisplay");
  const evBox = document.getElementById("evidenceBox");
  const evList = document.getElementById("evidenceList");
  const quickAppealBtn = document.getElementById("quickAppealBtn");

  score.innerText = r.trust_score + "/100";
  
  const cacheNotice = r.cache_hit ? ` (7-Day Cache Hit: ${r.cache_age_days}d old)` : " (Deep Scan)";
  document.getElementById("latencyBadge").innerText = `Latency: ${r.total_latency_ms} ms${cacheNotice}`;

  if (r.action_taken === "APPROVED_FOR_CAPTURE") {
    card.className = "glass rounded-2xl p-5 border border-emerald-500/40 bg-gradient-to-br from-emerald-950/20 to-slate-900";
    iconCont.className = "p-3 rounded-2xl bg-emerald-500/20 text-emerald-400";
    badge.className = "text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 uppercase";
    badge.innerText = "PASSED • APPROVED FOR CAPTURE";
    title.innerText = "🟢 Transaction Approved & Settled";
    title.className = "text-lg font-extrabold text-emerald-300 mt-0.5";
    sub.innerText = r.ai_verdict_summary;
    score.className = "text-2xl font-black font-mono text-emerald-400 mt-0.5";
    evBox.classList.add("hidden");
  } else if (r.action_taken === "WARNED_REQUIRE_CONFIRMATION") {
    card.className = "glass rounded-2xl p-5 border border-amber-500/40 bg-gradient-to-br from-amber-950/20 to-slate-900";
    iconCont.className = "p-3 rounded-2xl bg-amber-500/20 text-amber-400";
    badge.className = "text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 uppercase";
    badge.innerText = "MODERATE RISK • STEP-UP CONFIRMATION";
    title.innerText = "🟡 Step-Up Verification Required";
    title.className = "text-lg font-extrabold text-amber-300 mt-0.5";
    sub.innerText = r.ai_verdict_summary;
    score.className = "text-2xl font-black font-mono text-amber-400 mt-0.5";
    evBox.classList.remove("hidden");
    quickAppealBtn.classList.remove("hidden");
    evList.innerHTML = r.evidence.map(e => `<li class="flex items-start gap-1.5"><span class="text-amber-400 font-bold">!</span> <span>${e}</span></li>`).join("");
  } else {
    card.className = "glass rounded-2xl p-5 border border-rose-500/60 bg-gradient-to-br from-rose-950/40 to-slate-900 siren-active";
    iconCont.className = "p-3 rounded-2xl bg-rose-500/20 text-rose-400";
    badge.className = "text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 uppercase";
    badge.innerText = "BLOCKED • ACCOUNT SEALED";
    title.innerText = "🚨 PHISHING INTERCEPTED: MERCHANT QUARANTINED";
    title.className = "text-lg font-extrabold text-rose-300 mt-0.5";
    sub.innerText = r.ai_verdict_summary;
    score.className = "text-2xl font-black font-mono text-rose-400 mt-0.5";
    evBox.classList.remove("hidden");
    quickAppealBtn.classList.remove("hidden");
    evList.innerHTML = r.evidence.map(e => `<li class="flex items-start gap-1.5"><span class="text-rose-400 font-bold">✕</span> <span>${e}</span></li>`).join("");
  }

  // Update workers
  if (r.workers && r.workers.length >= 3) {
    updateWorker(1, r.workers[0]);
    updateWorker(2, r.workers[1]);
    updateWorker(3, r.workers[2]);
  } else if (r.cache_hit) {
    setWorkerCached(1);
    setWorkerCached(2);
    setWorkerCached(3);
  }
  
  // Worker 4
  const w4Status = document.getElementById("w4Status");
  w4Status.innerText = r.risk_level;
  w4Status.className = "font-mono font-bold text-[10px] " + (r.risk_level === "LOW" ? "text-emerald-400" : (r.risk_level === "MEDIUM" ? "text-amber-400" : "text-rose-400"));
  document.getElementById("w4Score").innerText = `Score: ${r.trust_score}/100`;
  document.getElementById("w4Time").innerText = `Action: ${r.action_taken.split('_')[0]}`;

  lucide.createIcons();
}

function updateWorker(num, w) {
  const status = document.getElementById(`w${num}Status`);
  status.innerText = w.status;
  status.className = "font-mono font-bold text-[10px] " + (w.status === "PASS" ? "text-emerald-400" : (w.status === "WARN" ? "text-amber-400" : "text-rose-400"));
  document.getElementById(`w${num}Score`).innerText = `Score: ${w.score}/100`;
  document.getElementById(`w${num}Time`).innerText = `Time: ${w.latency_ms} ms`;
}

function setWorkerCached(num) {
  const status = document.getElementById(`w${num}Status`);
  status.innerText = "CACHED";
  status.className = "font-mono font-bold text-[10px] text-cyan-400";
  document.getElementById(`w${num}Score`).innerText = `Score: Cached`;
  document.getElementById(`w${num}Time`).innerText = `Time: < 1ms`;
}

// -------------------------------------------------------------
// Merchant Appeals Modal & Submission
// -------------------------------------------------------------
function openAppealModalFromIncident() {
  if (!currentLastReport) return;
  document.getElementById("modalIncidentId").value = currentLastReport.incident_reference_id || `INC-${Date.now()}`;
  document.getElementById("appealModal").classList.remove("hidden");
}

function closeAppealModal() {
  document.getElementById("appealModal").classList.add("hidden");
}

async function submitAppealForm() {
  const incidentId = document.getElementById("modalIncidentId").value;
  const category = document.getElementById("modalCategory").value;
  const statement = document.getElementById("modalStatement").value;
  const submitBtn = document.querySelector("#appealModal button[type='submit']");

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerText = "Submitting...";
  }

  // Derive merchant ID consistently from incident or domain
  let merchantId = "MCH-MANUAL";
  if (currentLastReport && currentLastReport.root_domain) {
    merchantId = `MCH-${currentLastReport.root_domain.replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(0, 10)}`;
  } else if (incidentId) {
    merchantId = `MCH-${incidentId.replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(-8)}`;
  }

  try {
    const res = await fetch("/api/v1/appeals/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        merchant_id: merchantId,
        incident_reference_id: incidentId,
        reason_category: category,
        statement: statement,
        submitted_documents: ["https://merchant-docs.example.com/certificate-of-incorporation.pdf"]
      })
    });
    if (res.ok) {
      alert("Appeal ticket submitted successfully! Transitioned to 'OPEN' status in the Appeals Center.");
      closeAppealModal();
      switchTab('appeals');
      if (typeof loadAppealsGrid === 'function') loadAppealsGrid();
      if (typeof loadRegistryGrid === 'function') loadRegistryGrid();
    } else {
      const err = await res.json().catch(() => ({}));
      alert("Failed to submit appeal: " + (err.detail || res.statusText || "Server error"));
    }
  } catch (e) {
    alert("Error submitting appeal: " + e);
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerText = "Submit Appeal";
    }
  }
}

// -------------------------------------------------------------
// Official PayPal JavaScript SDK Integration
// -------------------------------------------------------------
async function initPayPalSDK() {
  const loadingEl = document.getElementById("paypal-sdk-loading");

  try {
    const res = await fetch("/api/v1/paypal/config");
    paypalConfig = await res.json();

    if (!paypalConfig.client_id) {
      if (loadingEl) loadingEl.innerText = "PayPal credentials missing in .env";
      return;
    }

    // Load official PayPal SDK script dynamically
    // disable-funding=card,credit prevents PayPal Sandbox unbranded card authorization crashes
    const script = document.createElement("script");
    script.src = `https://www.paypal.com/sdk/js?client-id=${paypalConfig.client_id}&intent=authorize&currency=USD&components=buttons`;
    script.onload = () => {
      if (loadingEl) loadingEl.style.display = "none";
      renderPayPalButtons();
    };
    script.onerror = () => {
      if (loadingEl) loadingEl.innerText = "Failed to load PayPal JS SDK from CDN.";
    };
    document.head.appendChild(script);
  } catch (err) {
    if (loadingEl) loadingEl.innerText = "PayPal configuration unreachable.";
  }
}

function renderPayPalButtons() {
  if (typeof paypal === "undefined" || !paypal.Buttons) {
    console.error("PayPal SDK not loaded");
    return;
  }

  paypal.Buttons({
    style: {
      layout: 'vertical',
      color: 'gold',
      shape: 'rect',
      label: 'paypal',
      height: 40
    },

    // Step 1: Create Order in PayPal Sandbox & trigger parallel Argus verification
    createOrder: async function(data, actions) {
      const payload = {
        brand_name: document.getElementById("brandInput").value,
        merchant_url: document.getElementById("urlInput").value,
        product_name: document.getElementById("productInput").value,
        price: parseFloat(document.getElementById("priceInput").value),
        currency: "USD"
      };

      // 1. Kick off parallel verification in background
      const verifyPromise = fetch("/api/v1/checkout/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).then(r => r.json());

      // 2. Call backend PayPal Gateway to create the authorization order in PayPal Sandbox
      const orderPromise = fetch("/api/v1/paypal/create-order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          amount: payload.price,
          currency: payload.currency,
          brand_name: payload.brand_name
        })
      }).then(r => r.json());

      const [report, orderData] = await Promise.all([verifyPromise, orderPromise]);
      currentLastReport = report;
      currentPayPalOrderId = orderData.order_id;

      // Update UI & Stepper
      const shortId = (orderData.order_id || "PAYID-SIM").slice(0, 16);
      updatePPStep(1, "HELD", `Hold: ${shortId}...`, "Funds Reserved (intent: AUTHORIZE)", true);
      updatePPStep(2, "DONE", `Score: ${report.trust_score}/100`, `${report.total_latency_ms} ms Latency`, report.trust_score >= 70);
      updatePPStep(3, "PENDING", "Buyer Authorizing...", "Waiting in PayPal Popup", null);

      renderReport(report);
      updatePresetWithReport(report, payload);
      loadAuditGrid();
      loadRegistryGrid();

      return orderData.order_id;
    },

    // Step 2: On buyer approval in PayPal popup
    onApprove: async function(data, actions) {
      const orderId = data.orderID || currentPayPalOrderId;

      if (!currentLastReport) {
        alert("Verification report pending...");
        return;
      }

      if (currentLastReport.action_taken === "APPROVED_FOR_CAPTURE") {
        // Merchant is genuine! Settle authorized funds
        const res = await fetch("/api/v1/paypal/capture-order", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ order_id: orderId })
        });
        const cap = await res.json();
        const capId = (cap.capture_id || "CAP-SETTLED").slice(0, 14);
        updatePPStep(3, "CAPTURED", `Settled: ${capId}...`, "Funds released to 2252PMF2CJ7Q2", true);
        alert(`PayPal Authorized Hold Captured Successfully!\nOrder ID: ${orderId}\nCapture ID: ${cap.capture_id}\nStatus: Settled to verified merchant (2252PMF2CJ7Q2).`);
      } else if (currentLastReport.action_taken === "TRANSACTION_VOIDED_AND_ACCOUNT_SEALED") {
        // High Risk / Phishing: Void authorization immediately & seal account
        const res = await fetch("/api/v1/paypal/void-order", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            order_id: orderId,
            merchant_id: `MCH-${currentLastReport.root_domain.replace(/\./g, '').toUpperCase().slice(0, 8)}`,
            reason: currentLastReport.evidence.join("; ")
          })
        });
        const voidRes = await res.json();
        alert(`🚨 ARGUS PRE-SETTLEMENT INTERCEPTION!\nPayPal Authorization Hold VOIDED.\nNo funds transferred to scammer!\nIncident: ${currentLastReport.incident_reference_id}\nMerchant credentials quarantined.`);
      } else {
        // Warned
        const confirmed = confirm(`Argus Warning: Moderate risk detected (${currentLastReport.trust_score}/100).\nEvidence: ${currentLastReport.evidence.join(', ')}\nDo you want to proceed with capture?`);
        if (confirmed) {
          await fetch("/api/v1/paypal/capture-order", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ order_id: orderId })
          });
          alert("Transaction captured upon customer override.");
        } else {
          await fetch("/api/v1/paypal/void-order", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              order_id: orderId,
              merchant_id: `MCH-${currentLastReport.root_domain.replace(/\./g, '').toUpperCase().slice(0, 8)}`,
              reason: "Customer cancelled after Argus risk warning"
            })
          });
        }
      }
      loadAuditGrid();
    },

    onError: function(err) {
      console.warn("PayPal Smart Button notice:", err);
      alert("PayPal Sandbox Notice: The popup window was closed or blocked by browser shields. You can also click the yellow 'Pay Pal 1-Click Fast Interceptor Test' button directly above to test the full lifecycle instantly!");
    }
  }).render("#paypal-button-container");
}

// Initialize on page load
window.addEventListener("DOMContentLoaded", () => {
  initPresets();
  initPayPalSDK();

  // Listen to live input changes to update active target label
  ["brandInput", "urlInput"].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener("input", () => {
        const brand = document.getElementById("brandInput").value.trim();
        const url = document.getElementById("urlInput").value.trim();
        const label = document.getElementById("activeIntentLabel");
        if (label) label.innerText = `${brand || 'Custom'} (${cleanHost(url)})`;
      });
    }
  });
});
