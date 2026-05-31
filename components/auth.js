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
    // Deteksi base path
    const pathParts = window.location.pathname.split('/');
    let basePath = '';
    for (let i = 0; i < pathParts.length; i++) {
      if (['admin','guru','siswa','index.html',''].includes(pathParts[i]) && i > 0) {
        basePath = pathParts.slice(0, i).join('/');
        break;
      }
    }
    window.location.href = basePath + '/index.html';
  };

  const requireRole = (allowedRoles) => {
    const token = getToken();
    if (!token) {
      // Deteksi base path
      const _parts = window.location.pathname.split('/');
      let _base = '';
      for (let i = 0; i < _parts.length; i++) {
        if (['admin','guru','siswa','index.html',''].includes(_parts[i]) && i > 0) {
          _base = _parts.slice(0, i).join('/'); break;
        }
      }
      window.location.href = _base + '/index.html';
      return false;
    }
    const user = getUser();
    if (!user) {
      fetchAndStoreUser().then((u) => {
        if (!u) {
          const _p = window.location.pathname.split('/');
          let _b = '';
          for (let i = 0; i < _p.length; i++) {
            if (['admin','guru','siswa','index.html',''].includes(_p[i]) && i > 0) { _b = _p.slice(0,i).join('/'); break; }
          }
          window.location.href = _b + '/index.html';
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
    // Deteksi base path otomatis dari URL saat ini
    // Contoh: https://rafbuilds.github.io/my-smaba/admin/dashboard.html
    // → basePath = /my-smaba
    const pathParts = window.location.pathname.split('/');
    // Cari segmen sebelum admin/guru/siswa/index.html
    let basePath = '';
    for (let i = 0; i < pathParts.length; i++) {
      if (['admin','guru','siswa','index.html',''].includes(pathParts[i]) && i > 0) {
        basePath = pathParts.slice(0, i).join('/');
        break;
      }
    }

    const map = {
      admin:       basePath + '/admin/dashboard.html',
      guru:        basePath + '/guru/dashboard.html',
      siswa:       basePath + '/siswa/ujian.html',
      guru_pending: basePath + '/guru/pending.html',
    };
    window.location.href = map[role] || basePath + '/index.html';
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
