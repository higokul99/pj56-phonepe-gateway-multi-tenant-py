/**
 * PhonePe Payment Gateway — API Client & Toast Utilities
 */

const API = {
  getAdminKey() {
    return sessionStorage.getItem("pg_admin_key") || "";
  },

  setAdminKey(key) {
    sessionStorage.setItem("pg_admin_key", key);
  },

  clearAdminKey() {
    sessionStorage.removeItem("pg_admin_key");
  },

  isAuthenticated() {
    return !!this.getAdminKey();
  },

  async request(endpoint, options = {}) {
    const adminKey = this.getAdminKey();
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };

    if (adminKey) {
      headers["X-Admin-API-Key"] = adminKey;
    }

    try {
      const response = await fetch(endpoint, {
        ...options,
        headers,
      });

      if (response.status === 401 && !endpoint.includes("/admin/auth/verify")) {
        this.clearAdminKey();
        window.location.reload();
        throw new Error("Session expired. Please log in again.");
      }

      const data = await response.json().catch(() => ({}));

      if (!response.ok || data.success === false) {
        const errorMsg = data.error?.message || data.detail || `Request failed (${response.status})`;
        throw new Error(errorMsg);
      }

      return data.data !== undefined ? data.data : data;
    } catch (err) {
      console.error(`API Error [${endpoint}]:`, err);
      throw err;
    }
  },

  // Auth
  async verifyAdminKey(key) {
    return this.request("/admin/auth/verify", {
      method: "POST",
      body: JSON.stringify({ admin_api_key: key }),
    });
  },

  // Stats
  async getStats() {
    return this.request("/admin/stats");
  },

  // Tenants
  async getTenants() {
    return this.request("/admin/tenants");
  },

  async getTenant(id) {
    return this.request(`/admin/tenants/${id}`);
  },

  async createTenant(payload) {
    return this.request("/admin/tenants", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async updateTenant(id, payload) {
    return this.request(`/admin/tenants/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  // API Keys
  async getTenantKeys(tenantId) {
    return this.request(`/admin/tenants/${tenantId}/keys`);
  },

  async createApiKey(tenantId, environment = "live") {
    return this.request(`/admin/tenants/${tenantId}/keys`, {
      method: "POST",
      body: JSON.stringify({ environment }),
    });
  },

  async revokeApiKey(keyId) {
    return this.request(`/admin/keys/${keyId}/revoke`, {
      method: "POST",
    });
  },

  // Orders
  async getOrders(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/admin/orders${query ? `?${query}` : ""}`);
  },

  async triggerRefund(merchantOrderId, tenantId, amount, reason) {
    return this.request(`/admin/orders/${merchantOrderId}/refund?tenant_id=${tenantId}`, {
      method: "POST",
      body: JSON.stringify({ amount, reason }),
    });
  },

  // Webhooks
  async getWebhooks(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/admin/webhooks${query ? `?${query}` : ""}`);
  },
};

// Toast notification helper
function showToast(message, type = "success") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${message}</span>`;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    toast.style.transition = "all 0.2s ease";
    setTimeout(() => toast.remove(), 200);
  }, 3500);
}
