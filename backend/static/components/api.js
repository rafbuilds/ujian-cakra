// frontend/components/api.js
const API = (() => {
  const base = () => {
    // Cek CONFIG.API_BASE — bisa string kosong "" (valid untuk same-domain)
    if (typeof CONFIG !== "undefined" && CONFIG.API_BASE !== undefined)
      return CONFIG.API_BASE;
    if (typeof Config !== "undefined" && Config.apiBase) return Config.apiBase;
    return ""; // default: same domain
  };

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
    fetch(base() + path, { method: "DELETE", headers: headers() }).then(handle);

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

  const download = async (path, filename) => {
    const token = localStorage.getItem("ujian_token");
    const h = token ? { Authorization: `Bearer ${token}` } : {};
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
