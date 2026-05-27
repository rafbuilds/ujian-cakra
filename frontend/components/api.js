// ============================================================
// api.js — API Fetch Wrapper
// ============================================================

const API = (() => {
  const base = () =>
    typeof CONFIG !== "undefined" ? CONFIG.API_BASE : "http://localhost:5000";

  const headers = (extra = {}) => {
    const h = { "Content-Type": "application/json", ...extra };
    const token = localStorage.getItem("ujian_token");
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
  };

  const handle = async (res) => {
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw { ...data, status: res.status };
    return data;
  };

  // ── Methods ────────────────────────────────────────────
  const get = (path) =>
    fetch(base() + path, { headers: headers() }).then(handle);

  const post = (path, body) =>
    fetch(base() + path, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    }).then(handle);

  const patch = (path, body) =>
    fetch(base() + path, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    }).then(handle);

  const del = (path) =>
    fetch(base() + path, {
      method: "DELETE",
      headers: headers(),
    }).then(handle);

  // Upload file (FormData)
  const upload = (path, formData) => {
    const h = {};
    const token = localStorage.getItem("ujian_token");
    if (token) h["Authorization"] = `Bearer ${token}`;
    return fetch(base() + path, {
      method: "POST",
      headers: h,
      body: formData,
    }).then(handle);
  };

  // Download file (blob)
  const download = async (path, filename) => {
    const token = localStorage.getItem("ujian_token");
    const h = {};
    if (token) h["Authorization"] = `Bearer ${token}`;
    const res = await fetch(base() + path, { headers: h });
    if (!res.ok) throw new Error("Gagal mengunduh");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return { get, post, patch, del, upload, download };
})();
