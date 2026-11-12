// AG Grid Setup for Registry, Audit Ledger, and Appeals Center

let registryGridApi = null;
let auditGridApi = null;
let appealsGridApi = null;

// 1. REGISTRY GRID CONFIG
const registryGridOptions = {
  columnDefs: [
    { field: "paypal_merchant_id", headerName: "Merchant ID", minWidth: 140, flex: 1, font: "mono" },
    { field: "legal_business_name", headerName: "Legal Entity", minWidth: 180, flex: 1.5 },
    { field: "brand_name_claimed", headerName: "Brand", minWidth: 120, flex: 1 },
    { field: "root_domain", headerName: "Root Domain", minWidth: 150, flex: 1.2 },
    { field: "identity_status", headerName: "Identity Status", minWidth: 130, flex: 1, cellRenderer: p => {
      const isVer = p.value === "VERIFIED";
      const color = isVer ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-amber-500/10 text-amber-400 border-amber-500/20";
      return `<span class="px-2 py-0.5 rounded text-[11px] border ${color}">${p.value}</span>`;
    }},
    { field: "association_status", headerName: "Domain Auth", minWidth: 130, flex: 1, cellRenderer: p => {
      const isAuth = p.value === "AUTHORIZED";
      const isRev = p.value === "REVOKED";
      const color = isAuth ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : (isRev ? "bg-rose-500/10 text-rose-400 border-rose-500/20" : "bg-slate-800 text-slate-400");
      return `<span class="px-2 py-0.5 rounded text-[11px] font-bold border ${color}">${p.value}</span>`;
    }},
    { field: "trust_score", headerName: "Trust Score", minWidth: 110, flex: 0.9, cellRenderer: p => {
      const color = p.value >= 70 ? 'text-emerald-400' : 'text-rose-400';
      return `<span class="font-mono font-bold ${color}">${p.value}/100</span>`;
    }},
    { field: "expires_at", headerName: "7-Day Cache Expires", minWidth: 150, flex: 1, valueFormatter: p => p.value ? p.value.split("T")[0] : "No Cache" },
    { headerName: "Action", minWidth: 120, flex: 0.8, cellRenderer: p => {
      return `<button onclick="invalidateCacheAction('${p.data.merchant_id}', '${p.data.website_id}')" class="px-2.5 py-1 bg-slate-800 hover:bg-rose-950/40 text-slate-300 hover:text-rose-300 text-[11px] rounded border border-slate-700 transition-all">Invalidate</button>`;
    }}
  ],
  defaultColDef: {
    flex: 1,
    minWidth: 100,
    sortable: true,
    filter: true,
    resizable: true
  },
  autoSizeStrategy: { type: 'fitGridWidth' },
  rowData: []
};

// 2. AUDIT GRID CONFIG
const auditGridOptions = {
  columnDefs: [
    { field: "transaction_id", headerName: "Order ID", minWidth: 130, flex: 1, font: "mono" },
    { field: "timestamp", headerName: "Time", minWidth: 120, flex: 0.9 },
    { field: "brand_name", headerName: "Brand", minWidth: 120, flex: 1 },
    { field: "product_name", headerName: "Product", minWidth: 160, flex: 1.3 },
    { field: "amount", headerName: "Amount", minWidth: 90, flex: 0.8, valueFormatter: p => `$${p.value}` },
    { field: "trust_score", headerName: "Score", minWidth: 90, flex: 0.8, cellRenderer: p => {
      const color = p.value >= 70 ? 'text-emerald-400' : (p.value >= 45 ? 'text-amber-400' : 'text-rose-400');
      return `<span class="font-mono font-bold ${color}">${p.value}/100</span>`;
    }},
    { field: "verdict", headerName: "Mitigation Verdict", minWidth: 190, flex: 1.5, cellRenderer: p => {
      const isApp = p.value === "APPROVED_FOR_CAPTURE";
      const isWarn = p.value === "WARNED_REQUIRE_CONFIRMATION";
      const bg = isApp ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : (isWarn ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' : 'bg-rose-500/10 text-rose-400 border-rose-500/20');
      return `<span class="px-2 py-0.5 rounded text-[10px] border ${bg}">${p.value}</span>`;
    }},
    { field: "latency_ms", headerName: "Latency", minWidth: 90, flex: 0.8, valueFormatter: p => p.value + " ms" },
    { field: "target_url", headerName: "Destination URL", minWidth: 220, flex: 2 }
  ],
  defaultColDef: {
    flex: 1,
    minWidth: 90,
    sortable: true,
    filter: true,
    resizable: true
  },
  autoSizeStrategy: { type: 'fitGridWidth' },
  rowData: []
};

// 3. APPEALS GRID CONFIG
const appealsGridOptions = {
  columnDefs: [
    { field: "id", headerName: "Ticket ID", minWidth: 110, flex: 0.8, font: "mono" },
    { field: "merchant_name", headerName: "Merchant", minWidth: 160, flex: 1.2 },
    { field: "incident_reference_id", headerName: "Incident Ref", minWidth: 130, flex: 1, font: "mono" },
    { field: "reason_category", headerName: "Dispute Reason", minWidth: 150, flex: 1 },
    { field: "status", headerName: "Ticket Status", minWidth: 120, flex: 0.9, cellRenderer: p => {
      const isRes = p.value === "RESOLVED";
      const isOpen = p.value === "OPEN";
      const color = isRes ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : (isOpen ? "bg-amber-500/10 text-amber-400 border-amber-500/20" : "bg-rose-500/10 text-rose-400 border-rose-500/20");
      return `<span class="px-2 py-0.5 rounded text-[11px] font-bold border ${color}">${p.value}</span>`;
    }},
    { field: "statement", headerName: "Merchant Statement", minWidth: 260, flex: 2.5 },
    { headerName: "Admin Action", minWidth: 130, flex: 1, cellRenderer: p => {
      if (p.data.status === "OPEN" || p.data.status === "UNDER_REVIEW") {
        return `<button onclick="resolveAppealDirect('${p.data.id}')" class="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-bold rounded shadow transition-all">Approve Appeal</button>`;
      }
      return `<span class="text-xs text-slate-500">Resolved</span>`;
    }}
  ],
  defaultColDef: {
    flex: 1,
    minWidth: 100,
    sortable: true,
    filter: true,
    resizable: true
  },
  autoSizeStrategy: { type: 'fitGridWidth' },
  rowData: []
};

document.addEventListener("DOMContentLoaded", () => {
  // Init Grids
  const regDiv = document.querySelector("#registryGrid");
  if (regDiv) registryGridApi = agGrid.createGrid(regDiv, registryGridOptions);

  const audDiv = document.querySelector("#auditGrid");
  if (audDiv) auditGridApi = agGrid.createGrid(audDiv, auditGridOptions);

  const appDiv = document.querySelector("#appealsGrid");
  if (appDiv) appealsGridApi = agGrid.createGrid(appDiv, appealsGridOptions);

  loadRegistryGrid();
  loadAuditGrid();
  loadAppealsGrid();

  // Resize listener to keep columns filled across viewport
  window.addEventListener("resize", () => {
    if (registryGridApi) registryGridApi.sizeColumnsToFit();
    if (auditGridApi) auditGridApi.sizeColumnsToFit();
    if (appealsGridApi) appealsGridApi.sizeColumnsToFit();
  });
});

async function loadRegistryGrid() {
  try {
    const res = await fetch("/api/v1/registry");
    const data = await res.json();
    if (registryGridApi) {
      registryGridApi.setGridOption('rowData', data);
      setTimeout(() => registryGridApi.sizeColumnsToFit(), 30);
    }
  } catch (e) { console.error("Error loading registry", e); }
}

async function loadAuditGrid() {
  try {
    const res = await fetch("/api/v1/audit-log");
    const data = await res.json();
    if (auditGridApi) {
      auditGridApi.setGridOption('rowData', data);
      setTimeout(() => auditGridApi.sizeColumnsToFit(), 30);
    }
  } catch (e) { console.error("Error loading audit log", e); }
}

async function loadAppealsGrid() {
  try {
    const res = await fetch("/api/v1/appeals");
    const data = await res.json();
    if (appealsGridApi) {
      appealsGridApi.setGridOption('rowData', data);
      setTimeout(() => appealsGridApi.sizeColumnsToFit(), 30);
    }
    
    // Update badge count
    const openCount = data.filter(d => d.status === "OPEN" || d.status === "UNDER_REVIEW").length;
    const badge = document.getElementById("appealsBadge");
    if (badge) badge.innerText = openCount;
  } catch (e) { console.error("Error loading appeals", e); }
}

function onRegistryFilterChanged() {
  registryGridApi.setGridOption('quickFilterText', document.getElementById('registryFilter').value);
}

function onAuditFilterChanged() {
  auditGridApi.setGridOption('quickFilterText', document.getElementById('auditFilter').value);
}

function onAppealsFilterChanged() {
  appealsGridApi.setGridOption('quickFilterText', document.getElementById('appealsFilter').value);
}

async function resolveAppealDirect(ticketId) {
  if (!confirm(`Approve appeal ticket ${ticketId} and restore merchant access with fresh 7-day cache?`)) return;
  try {
    const res = await fetch("/api/v1/appeals/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticket_id: ticketId,
        action: "APPROVE",
        resolution_notes: "Identity documents verified by Argus Compliance Officer. Domain authorization approved."
      })
    });
    if (res.ok) {
      alert("Appeal approved! Merchant status restored to VERIFIED.");
      loadAppealsGrid();
      loadRegistryGrid();
      loadAuditGrid();
    }
  } catch (err) { alert("Error resolving appeal: " + err); }
}

async function invalidateCacheAction(merchantId, websiteId) {
  try {
    await fetch("/api/v1/cache/invalidate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ merchant_id: merchantId, website_id: websiteId, reason: "ADMIN_SIMULATED_CHANGE" })
    });
    alert("7-day cache invalidated! Next checkout for this merchant will trigger full deep re-verification.");
    loadRegistryGrid();
  } catch (e) { console.error(e); }
}
