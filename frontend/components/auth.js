// ============================================================
// auth.js — Authentication & Session Management
// ============================================================

const Auth = (() => {
  const TOKEN_KEY = "ujian_token";
  const USER_KEY = "ujian_user";

  // ── Token ──────────────────────────────────────────────
  const getToken = () => localStorage.getItem(TOKEN_KEY);
  const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
  const clearToken = () => localStorage.removeItem(TOKEN_KEY);

  // ── User ───────────────────────────────────────────────
  const getUser = () => JSON.parse(localStorage.getItem(USER_KEY) || "null");
  const setUser = (u) => localStorage.setItem(USER_KEY, JSON.stringify(u));
  const clearUser = () => localStorage.removeItem(USER_KEY);

  // ── Logout ─────────────────────────────────────────────
  const logout = () => {
    clearToken();
    clearUser();
    window.location.href = "/index.html";
  };

  // ── Role guard ─────────────────────────────────────────────
  const requireRole = (allowedRoles) => {
    const token = getToken();
    if (!token) {
      window.location.href = "/index.html";
      return false;
    }
    const user = getUser();
    if (!user) {
      // User belum di-fetch — fetch dulu lalu reload
      fetchAndStoreUser().then((u) => {
        if (!u) {
          window.location.href = "/index.html";
          return;
        }
        if (!allowedRoles.includes(u.role)) {
          redirectByRole(u.role);
        } else {
          window.location.reload();
        }
      });
      return false;
    }
    if (!allowedRoles.includes(user.role)) {
      UI.toast(
        `Akses ditolak. Halaman ini untuk ${allowedRoles.join("/")}`,
        "error",
      );
      setTimeout(() => redirectByRole(user.role), 1200);
      return false;
    }
    return true;
  };

  // ── Init dari URL token (setelah OAuth redirect) ───────
  const initFromUrl = () => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const err = params.get("error");

    if (token) {
      setToken(token);
      window.history.replaceState({}, "", window.location.pathname);
    }
    if (err) {
      UI.toast(decodeURIComponent(err), "error");
    }
    return !!token;
  };

  // ── Fetch user dari server & simpan ───────────────────
  const fetchAndStoreUser = async () => {
    try {
      const user = await API.get("/api/auth/me");
      setUser(user);
      return user;
    } catch {
      clearToken();
      clearUser();
      return null;
    }
  };

  // ── Redirect ke halaman sesuai role ───────────────────
  const redirectByRole = (role) => {
    const map = {
      admin: "/pages/admin-dashboard.html",
      guru: "/pages/guru-dashboard.html",
      siswa: "/pages/siswa-ujian.html",
    };
    // Guru baru (belum diapprove)
    if (role === "guru_pending") {
      window.location.href = "/pages/guru-pending.html";
      return;
    }
    window.location.href = map[role] || "/index.html";
  };

  return {
    getToken,
    setToken,
    clearToken,
    getUser,
    setUser,
    clearUser,
    logout,
    requireRole,
    initFromUrl,
    fetchAndStoreUser,
    redirectByRole,
  };
})();
