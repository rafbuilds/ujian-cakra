// frontend/components/auth.js
const Auth = (() => {
  // Ambil base path dari config (untuk GitHub Pages subdirectory)
  const getBase = () =>
    typeof CONFIG !== "undefined" && CONFIG.BASE_PATH ? CONFIG.BASE_PATH : "";

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
    window.location.href = "/";
  };

  const requireRole = (allowedRoles) => {
    const token = getToken();
    if (!token) {
      // Deteksi base path

      window.location.href = "/";
      return false;
    }
    const user = getUser();
    if (!user) {
      fetchAndStoreUser().then((u) => {
        if (!u) {
          const _p = window.location.pathname.split("/");
          let _b = "";
          for (let i = 0; i < _p.length; i++) {
            if (
              ["admin", "guru", "siswa", "index", ""].includes(_p[i]) &&
              i > 0
            ) {
              _b = _p.slice(0, i).join("/");
              break;
            }
          }
          window.location.href = "/";
          return;
        }
        if (!allowedRoles.includes(u.role)) redirectByRole(u.role);
        else window.location.reload();
      });
      return false;
    }
    if (!allowedRoles.includes(user.role)) {
      // Cache lokal bisa basi (mis. role user baru saja diubah di server
      // tapi belum login ulang) — verifikasi ke server dulu sebelum
      // memutuskan redirect, supaya tidak pingpong antar halaman berdasarkan
      // role yang sudah tidak akurat.
      fetchAndStoreUser().then((u) => {
        if (u && allowedRoles.includes(u.role)) {
          window.location.reload();
        } else {
          redirectByRole(u ? u.role : user.role);
        }
      });
      return false;
    }
    // Set nama di sidebar
    const el = document.getElementById("sb-user-name");
    const av = document.getElementById("sb-avatar");
    if (el) el.textContent = user.name || "";
    if (av) av.textContent = (user.name || "?")[0];
    // Nama sekolah di bawah logo CAKRA — beda-beda per sekolah (multi-tenant),
    // bukan teks statis lagi. super_admin tidak punya sekolah (school_name
    // null) jadi dibiarkan apa adanya kalau halaman itu sudah set teks sendiri.
    const sub = document.getElementById("sb-logo-sub");
    if (sub && user.school_name) sub.textContent = user.school_name;
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
    const map = {
      super_admin: "/super-admin/dashboard",
      admin: "/admin/dashboard",
      guru: "/guru/dashboard",
      siswa: "/siswa/siswa-ujian",
      guru_pending: "/guru/pending",
    };
    window.location.href = map[role] || "/";
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
