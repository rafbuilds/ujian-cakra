// frontend/components/auth.js
const Auth = (() => {
  const TOKEN_KEY = "ujian_token";
  const USER_KEY = "ujian_user";

  const getToken = () => localStorage.getItem(TOKEN_KEY);
  const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
  const clearToken = () => localStorage.removeItem(TOKEN_KEY);

  const getUser = () => JSON.parse(localStorage.getItem(USER_KEY) || "null");
  const setUser = (u) => localStorage.setItem(USER_KEY, JSON.stringify(u));
  const clearUser = () => localStorage.removeItem(USER_KEY);

  const logout = () => {
    clearToken();
    clearUser();
    window.location.href = "/index.html";
  };

  const requireRole = (allowedRoles) => {
    const token = getToken();
    if (!token) {
      window.location.href = "/index.html";
      return false;
    }
    const user = getUser();
    if (!user) {
      fetchAndStoreUser().then((u) => {
        if (!u) {
          window.location.href = "/index.html";
          return;
        }
        if (!allowedRoles.includes(u.role)) redirectByRole(u.role);
        else window.location.reload();
      });
      return false;
    }
    if (!allowedRoles.includes(user.role)) {
      setTimeout(() => redirectByRole(user.role), 800);
      return false;
    }
    // Set nama di sidebar
    const el = document.getElementById("sb-user-name");
    const av = document.getElementById("sb-avatar");
    if (el) el.textContent = user.name || "";
    if (av) av.textContent = (user.name || "?")[0];
    return true;
  };

  const initFromUrl = () => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (token) {
      setToken(token);
      window.history.replaceState({}, "", window.location.pathname);
    }
    return !!token;
  };

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

  const redirectByRole = (role) => {
    // Deteksi apakah pakai struktur baru (admin/, guru/) atau lama (pages/)
    const isNewStructure =
      window.location.pathname.includes("/admin/") ||
      window.location.pathname.includes("/guru/") ||
      window.location.pathname.includes("/siswa/") ||
      window.location.pathname === "/" ||
      window.location.pathname === "/index.html";

    const newMap = {
      admin: "/admin/dashboard.html",
      guru: "/guru/dashboard.html",
      siswa: "/siswa/ujian.html",
      guru_pending: "/guru/pending.html",
    };
    const oldMap = {
      admin: "/pages/admin-dashboard.html",
      guru: "/pages/guru-dashboard.html",
      siswa: "/pages/siswa-ujian.html",
      guru_pending: "/pages/guru-pending.html",
    };

    // Cek apakah folder baru ada
    fetch("/admin/dashboard.html", { method: "HEAD" })
      .then((r) => {
        const map = r.ok ? newMap : oldMap;
        window.location.href = map[role] || "/index.html";
      })
      .catch(() => {
        window.location.href = oldMap[role] || "/index.html";
      });
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
