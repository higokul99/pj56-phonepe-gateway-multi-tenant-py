/**
 * PhonePe Payment Gateway — Dashboard View & Interaction Controller
 */

let revenueChart = null;
let statusDonutChart = null;
let currentTenantsCache = [];

document.addEventListener("DOMContentLoaded", () => {
  initAuthFlow();
  setupNavListeners();
});

// --- Auth Flow ---
function initAuthFlow() {
  const loginSection = document.getElementById("login-section");
  const appSection = document.getElementById("app-section");
  const loginForm = document.getElementById("login-form");

  if (API.isAuthenticated()) {
    loginSection.classList.add("hidden");
    appSection.classList.remove("hidden");
    loadOverviewTab();
  } else {
    loginSection.classList.remove("hidden");
    appSection.classList.add("hidden");
  }

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const keyInput = document.getElementById("admin-key-input");
    const key = keyInput.value.trim();

    if (!key) return;

    try {
      await API.verifyAdminKey(key);
      API.setAdminKey(key);
      showToast("Authenticated successfully!", "success");
      loginSection.classList.add("hidden");
      appSection.classList.remove("hidden");
      loadOverviewTab();
    } catch (err) {
      showToast(err.message || "Invalid Admin Key", "error");
    }
  });

  document.getElementById("btn-logout").addEventListener("click", () => {
    API.clearAdminKey();
    window.location.reload();
  });
}

// --- Navigation Controller ---
function setupNavListeners() {
  const navItems = document.querySelectorAll(".nav-item[data-tab]");
  navItems.forEach((item) => {
    item.addEventListener("click", () => {
      navItems.forEach((n) => n.classList.remove("active"));
      item.classList.add("active");

      const targetTab = item.getAttribute("data-tab");
      document.querySelectorAll(".tab-content").forEach((tc) => tc.classList.add("hidden"));
      document.getElementById(`tab-${targetTab}`).classList.remove("hidden");

      document.getElementById("header-title").innerText = item.innerText.trim();

      // Load data for selected tab
      if (targetTab === "overview") loadOverviewTab();
      else if (targetTab === "tenants") loadTenantsTab();
      else if (targetTab === "keys") loadKeysTab();
      else if (targetTab === "orders") loadOrdersTab();
      else if (targetTab === "webhooks") loadWebhooksTab();
    });
  });
}

// --- Tab 1: Overview & Metrics ---
async function loadOverviewTab() {
  try {
    const data = await API.getStats();
    const m = data.metrics;

    document.getElementById("metric-volume").innerText = `₹${m.total_volume_rupees.toLocaleString("en-IN")}`;
    document.getElementById("metric-orders").innerText = m.total_orders;
    document.getElementById("metric-tenants").innerText = `${m.active_tenants} / ${m.total_tenants}`;
    document.getElementById("metric-success-rate").innerText = `${m.success_rate_percentage}%`;

    renderCharts(data.chart_data, m);
    loadRecentOrdersOverview();
  } catch (err) {
    showToast(`Failed to load metrics: ${err.message}`, "error");
  }
}

function renderCharts(chartData, metrics) {
  const labels = chartData.map((d) => d.date);
  const volumes = chartData.map((d) => d.volume_rupees);

  // 1. Revenue Trend Line Chart
  const ctxRevenue = document.getElementById("chart-revenue").getContext("2d");
  if (revenueChart) revenueChart.destroy();

  revenueChart = new Chart(ctxRevenue, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Volume (₹)",
          data: volumes,
          borderColor: "#6366f1",
          backgroundColor: "rgba(99, 102, 241, 0.1)",
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          pointBackgroundColor: "#818cf8",
          pointRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8" } },
        y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8" } },
      },
    },
  });

  // 2. Status Donut Chart
  const ctxStatus = document.getElementById("chart-status").getContext("2d");
  if (statusDonutChart) statusDonutChart.destroy();

  statusDonutChart = new Chart(ctxStatus, {
    type: "doughnut",
    data: {
      labels: ["Completed", "Pending", "Failed"],
      datasets: [
        {
          data: [metrics.completed_orders, metrics.pending_orders, metrics.failed_orders],
          backgroundColor: ["#10b981", "#f59e0b", "#ef4444"],
          borderColor: "#111726",
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { color: "#94a3b8", boxWidth: 12 } },
      },
    },
  });
}

async function loadRecentOrdersOverview() {
  try {
    const orders = await API.getOrders({ limit: 5 });
    const tbody = document.getElementById("overview-recent-orders-tbody");
    if (!orders.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">No transactions recorded yet</td></tr>`;
      return;
    }

    tbody.innerHTML = orders
      .map(
        (o) => `
      <tr>
        <td class="mono-text">${o.merchant_order_id}</td>
        <td>${escapeHtml(o.tenant_name)}</td>
        <td><strong>₹${o.amount_rupees.toLocaleString("en-IN")}</strong></td>
        <td>${getStatusBadge(o.status)}</td>
        <td class="mono-text">${formatDate(o.created_at)}</td>
      </tr>
    `
      )
      .join("");
  } catch (err) {
    console.error(err);
  }
}

// --- Tab 2: Tenants (Merchants) ---
async function loadTenantsTab() {
  const tbody = document.getElementById("tenants-tbody");
  tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Loading merchants...</td></tr>`;

  try {
    const tenants = await API.getTenants();
    currentTenantsCache = tenants;

    if (!tenants.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">No merchants registered yet. Click "Add Tenant" to onboard.</td></tr>`;
      return;
    }

    tbody.innerHTML = tenants
      .map(
        (t) => `
      <tr>
        <td><strong>${escapeHtml(t.name)}</strong></td>
        <td class="mono-text">${t.phonepe_merchant_id}</td>
        <td><span class="badge ${t.phonepe_env === "production" ? "badge-success" : "badge-warning"}">${t.phonepe_env}</span></td>
        <td>${t.is_active ? '<span class="badge badge-success">Active</span>' : '<span class="badge badge-danger">Disabled</span>'}</td>
        <td class="mono-text text-muted" style="max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${t.webhook_url || ""}">
          ${t.webhook_url || '<span class="text-muted">None</span>'}
        </td>
        <td>
          <button class="btn btn-sm btn-secondary" onclick="copyWebhookSecret('${t.webhook_secret}')" title="Copy Webhook Secret">
            Copy Secret
          </button>
        </td>
        <td class="text-right">
          <button class="btn btn-sm btn-primary" onclick="openCreateApiKeyModal('${t.id}', '${escapeHtml(t.name)}')">
            + Key
          </button>
          <button class="btn btn-sm btn-secondary" onclick="openEditTenantModal('${t.id}')">
            Edit
          </button>
        </td>
      </tr>
    `
      )
      .join("");
  } catch (err) {
    showToast(`Failed to load tenants: ${err.message}`, "error");
  }
}

// --- Tab 3: API Keys ---
async function loadKeysTab() {
  const tbody = document.getElementById("keys-tbody");
  tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Loading API keys...</td></tr>`;

  try {
    const tenants = await API.getTenants();
    currentTenantsCache = tenants;

    // Populate tenant select in key creation modal
    const tenantSelect = document.getElementById("new-key-tenant-select");
    tenantSelect.innerHTML = tenants.map((t) => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join("");

    let allKeys = [];
    for (const t of tenants) {
      const keys = await API.getTenantKeys(t.id);
      allKeys.push(...keys.map((k) => ({ ...k, tenant_name: t.name })));
    }

    if (!allKeys.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No API keys issued yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = allKeys
      .map(
        (k) => `
      <tr>
        <td class="mono-text"><strong>${k.key_prefix}***</strong></td>
        <td>${escapeHtml(k.tenant_name)}</td>
        <td>${k.is_active ? '<span class="badge badge-success">Active</span>' : '<span class="badge badge-danger">Revoked</span>'}</td>
        <td class="mono-text">${k.last_used_at ? formatDate(k.last_used_at) : '<span class="text-muted">Never</span>'}</td>
        <td class="mono-text">${formatDate(k.created_at)}</td>
        <td class="text-right">
          ${
            k.is_active
              ? `<button class="btn btn-sm btn-danger" onclick="revokeKey('${k.id}')">Revoke</button>`
              : '<span class="text-muted">Revoked</span>'
          }
        </td>
      </tr>
    `
      )
      .join("");
  } catch (err) {
    showToast(`Failed to load API keys: ${err.message}`, "error");
  }
}

// --- Tab 4: Orders & Transactions ---
async function loadOrdersTab() {
  const tbody = document.getElementById("orders-tbody");
  const search = document.getElementById("orders-search-input")?.value || "";
  const statusFilter = document.getElementById("orders-status-filter")?.value || "";

  tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Loading orders...</td></tr>`;

  try {
    const params = { limit: 50 };
    if (search) params.search = search;
    if (statusFilter) params.status = statusFilter;

    const orders = await API.getOrders(params);

    if (!orders.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">No orders match the criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = orders
      .map(
        (o) => `
      <tr>
        <td class="mono-text"><strong>${escapeHtml(o.merchant_order_id)}</strong></td>
        <td class="mono-text text-muted">${o.phonepe_order_id || "-"}</td>
        <td>${escapeHtml(o.tenant_name)}</td>
        <td><strong>₹${o.amount_rupees.toLocaleString("en-IN")}</strong></td>
        <td>${getStatusBadge(o.status)}</td>
        <td class="mono-text">${formatDate(o.created_at)}</td>
        <td class="text-right">
          ${
            o.status === "COMPLETED"
              ? `<button class="btn btn-sm btn-secondary" onclick="openRefundModal('${o.merchant_order_id}', '${o.tenant_id}', ${o.amount})">Refund</button>`
              : ""
          }
          <button class="btn btn-sm btn-secondary" onclick="viewOrderDetails(${escapeJsonForAttr(o)})">Inspect</button>
        </td>
      </tr>
    `
      )
      .join("");
  } catch (err) {
    showToast(`Failed to load orders: ${err.message}`, "error");
  }
}

// --- Tab 5: Webhook Logs ---
async function loadWebhooksTab() {
  const tbody = document.getElementById("webhooks-tbody");
  tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Loading webhook logs...</td></tr>`;

  try {
    const logs = await API.getWebhooks({ limit: 50 });

    if (!logs.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No webhook activity recorded yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = logs
      .map(
        (l) => `
      <tr>
        <td><span class="badge ${l.source === "PHONEPE" ? "badge-info" : "badge-neutral"}">${l.source}</span></td>
        <td class="mono-text">${escapeHtml(l.event_type || "-")}</td>
        <td>${getStatusBadge(l.status)}</td>
        <td>${l.response_code ? `<span class="badge ${l.response_code < 300 ? "badge-success" : "badge-danger"}">${l.response_code}</span>` : "-"}</td>
        <td class="mono-text">${formatDate(l.created_at)}</td>
        <td class="text-right">
          <button class="btn btn-sm btn-secondary" onclick="viewWebhookPayload(${escapeJsonForAttr(l.payload)})">Payload</button>
        </td>
      </tr>
    `
      )
      .join("");
  } catch (err) {
    showToast(`Failed to load webhook logs: ${err.message}`, "error");
  }
}

// --- Modals & Actions ---

// Add Tenant Modal
function openAddTenantModal() {
  document.getElementById("modal-add-tenant").classList.add("active");
}

async function handleCreateTenantSubmit(e) {
  e.preventDefault();
  const payload = {
    name: document.getElementById("tenant-name").value.trim(),
    phonepe_client_id: document.getElementById("tenant-client-id").value.trim(),
    phonepe_client_secret: document.getElementById("tenant-client-secret").value.trim(),
    phonepe_merchant_id: document.getElementById("tenant-merchant-id").value.trim(),
    phonepe_env: document.getElementById("tenant-env").value,
    webhook_url: document.getElementById("tenant-webhook-url").value.trim() || null,
  };

  try {
    await API.createTenant(payload);
    closeModal("modal-add-tenant");
    document.getElementById("form-add-tenant").reset();
    showToast("Tenant registered successfully!");
    loadTenantsTab();
  } catch (err) {
    showToast(`Failed to create tenant: ${err.message}`, "error");
  }
}

// Edit Tenant Modal
async function openEditTenantModal(tenantId) {
  try {
    const tenant = await API.getTenant(tenantId);
    document.getElementById("edit-tenant-id").value = tenant.id;
    document.getElementById("edit-tenant-name").value = tenant.name;
    document.getElementById("edit-tenant-merchant-id").value = tenant.phonepe_merchant_id;
    document.getElementById("edit-tenant-env").value = tenant.phonepe_env;
    document.getElementById("edit-tenant-webhook-url").value = tenant.webhook_url || "";
    document.getElementById("edit-tenant-active").checked = tenant.is_active;

    document.getElementById("modal-edit-tenant").classList.add("active");
  } catch (err) {
    showToast(`Error fetching tenant: ${err.message}`, "error");
  }
}

async function handleEditTenantSubmit(e) {
  e.preventDefault();
  const tenantId = document.getElementById("edit-tenant-id").value;
  const payload = {
    name: document.getElementById("edit-tenant-name").value.trim(),
    phonepe_merchant_id: document.getElementById("edit-tenant-merchant-id").value.trim(),
    phonepe_env: document.getElementById("edit-tenant-env").value,
    webhook_url: document.getElementById("edit-tenant-webhook-url").value.trim() || null,
    is_active: document.getElementById("edit-tenant-active").checked,
  };

  const newSecret = document.getElementById("edit-tenant-client-secret").value.trim();
  if (newSecret) payload.phonepe_client_secret = newSecret;

  const newClientId = document.getElementById("edit-tenant-client-id").value.trim();
  if (newClientId) payload.phonepe_client_id = newClientId;

  try {
    await API.updateTenant(tenantId, payload);
    closeModal("modal-edit-tenant");
    showToast("Tenant updated successfully!");
    loadTenantsTab();
  } catch (err) {
    showToast(`Failed to update tenant: ${err.message}`, "error");
  }
}

// Create API Key Modal
function openCreateApiKeyModal(tenantId = null, tenantName = null) {
  if (tenantId) {
    document.getElementById("new-key-tenant-select").value = tenantId;
  }
  document.getElementById("key-created-result").classList.add("hidden");
  document.getElementById("form-create-key").classList.remove("hidden");
  document.getElementById("modal-create-key").classList.add("active");
}

async function handleCreateApiKeySubmit(e) {
  e.preventDefault();
  const tenantId = document.getElementById("new-key-tenant-select").value;
  const env = document.getElementById("new-key-env-select").value;

  try {
    const result = await API.createApiKey(tenantId, env);
    document.getElementById("form-create-key").classList.add("hidden");

    const resultBox = document.getElementById("key-created-result");
    resultBox.classList.remove("hidden");
    document.getElementById("displayed-raw-key").innerText = result.raw_api_key;
    document.getElementById("btn-copy-raw-key").onclick = () => {
      navigator.clipboard.writeText(result.raw_api_key);
      showToast("API Key copied to clipboard!");
    };

    showToast("API Key generated successfully!");
    if (!document.getElementById("tab-keys").classList.contains("hidden")) {
      loadKeysTab();
    }
  } catch (err) {
    showToast(`Failed to generate key: ${err.message}`, "error");
  }
}

async function revokeKey(keyId) {
  if (!confirm("Are you sure you want to revoke this API key? This cannot be undone.")) return;
  try {
    await API.revokeApiKey(keyId);
    showToast("API Key revoked successfully!");
    loadKeysTab();
  } catch (err) {
    showToast(`Failed to revoke key: ${err.message}`, "error");
  }
}

// Refund Modal
function openRefundModal(merchantOrderId, tenantId, amountPaise) {
  document.getElementById("refund-order-id").value = merchantOrderId;
  document.getElementById("refund-tenant-id").value = tenantId;
  document.getElementById("refund-amount").value = amountPaise;
  document.getElementById("refund-amount-label").innerText = `Order Amount: ₹${(amountPaise / 100).toFixed(2)}`;
  document.getElementById("modal-refund").classList.add("active");
}

async function handleRefundSubmit(e) {
  e.preventDefault();
  const merchantOrderId = document.getElementById("refund-order-id").value;
  const tenantId = document.getElementById("refund-tenant-id").value;
  const amount = parseInt(document.getElementById("refund-amount").value);
  const reason = document.getElementById("refund-reason").value.trim();

  try {
    await API.triggerRefund(merchantOrderId, tenantId, amount, reason);
    closeModal("modal-refund");
    showToast("Refund initiated successfully!");
    loadOrdersTab();
  } catch (err) {
    showToast(`Refund error: ${err.message}`, "error");
  }
}

// JSON Inspector Modals
function viewOrderDetails(order) {
  document.getElementById("inspector-title").innerText = `Order: ${order.merchant_order_id}`;
  document.getElementById("inspector-code").innerText = JSON.stringify(order, null, 2);
  document.getElementById("modal-inspector").classList.add("active");
}

function viewWebhookPayload(payload) {
  document.getElementById("inspector-title").innerText = "Webhook Payload JSON";
  document.getElementById("inspector-code").innerText = JSON.stringify(payload, null, 2);
  document.getElementById("modal-inspector").classList.add("active");
}

function copyWebhookSecret(secret) {
  navigator.clipboard.writeText(secret);
  showToast("Webhook secret copied to clipboard!");
}

function closeModal(modalId) {
  document.getElementById(modalId).classList.remove("active");
}

// --- Helpers ---
function getStatusBadge(status) {
  const s = (status || "").toUpperCase();
  if (s === "COMPLETED" || s === "SUCCESS" || s === "PROCESSED" || s === "FORWARDED") {
    return `<span class="badge badge-success">${s}</span>`;
  }
  if (s === "PENDING" || s === "CREATED" || s === "INITIATED" || s === "RECEIVED") {
    return `<span class="badge badge-warning">${s}</span>`;
  }
  return `<span class="badge badge-danger">${s || "FAILED"}</span>`;
}

function formatDate(isoStr) {
  if (!isoStr) return "-";
  const d = new Date(isoStr);
  return d.toLocaleDateString("en-IN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeJsonForAttr(obj) {
  return `'${JSON.stringify(obj).replace(/'/g, "&apos;")}'`;
}
