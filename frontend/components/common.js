// ============================================================
// common.js — Shared UI Components & Utilities
// ============================================================

// ── Toast Notification ──────────────────────────────────────
const UI = (() => {
  // Toast
  let toastTimer;
  const toast = (msg, type = "info", duration = 3000) => {
    let el = document.getElementById("_toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "_toast";
      el.style.cssText = `
        position:fixed;top:20px;left:50%;transform:translateX(-50%);
        z-index:9999;padding:12px 24px;border-radius:12px;font-size:14px;
        font-weight:600;font-family:'Plus Jakarta Sans',sans-serif;
        box-shadow:0 8px 30px rgba(0,0,0,.2);transition:opacity .3s;
        max-width:90vw;text-align:center;
      `;
      document.body.appendChild(el);
    }
    const colors = {
      info: { bg: "#e6f1fb", color: "#185fa5", border: "#b3d4f5" },
      success: { bg: "#eaf3de", color: "#3b6d11", border: "#9fe1cb" },
      error: { bg: "#fcebeb", color: "#a32d2d", border: "#f7c1c1" },
      warn: { bg: "#faeeda", color: "#854f0b", border: "#fac775" },
    };
    const c = colors[type] || colors.info;
    el.style.background = c.bg;
    el.style.color = c.color;
    el.style.border = `1px solid ${c.border}`;
    el.style.opacity = "1";
    el.textContent = msg;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.style.opacity = "0";
    }, duration);
  };

  // Loading overlay
  const loading = (show, text = "Memuat...") => {
    let el = document.getElementById("_loading");
    if (show) {
      if (!el) {
        el = document.createElement("div");
        el.id = "_loading";
        el.innerHTML = `
          <div style="text-align:center">
            <div style="width:40px;height:40px;border:3px solid #e2e0d8;border-top-color:#1d9e75;
                        border-radius:50%;animation:spin .7s linear infinite;margin:0 auto 12px"></div>
            <div style="font-size:14px;color:#888780" id="_loading_text">${text}</div>
          </div>
        `;
        el.style.cssText = `
          position:fixed;inset:0;background:rgba(255,255,255,.85);
          display:flex;align-items:center;justify-content:center;z-index:9998;
          backdrop-filter:blur(2px);
        `;
        if (!document.getElementById("_spin_style")) {
          const s = document.createElement("style");
          s.id = "_spin_style";
          s.textContent = "@keyframes spin{to{transform:rotate(360deg)}}";
          document.head.appendChild(s);
        }
        document.body.appendChild(el);
      } else {
        document.getElementById("_loading_text").textContent = text;
        el.style.display = "flex";
      }
    } else {
      if (el) el.style.display = "none";
    }
  };

  // Confirm modal
  const confirm = (title, msg, onConfirm, type = "danger") => {
    let el = document.getElementById("_confirm");
    if (el) el.remove();
    el = document.createElement("div");
    el.id = "_confirm";
    const btnColor = type === "danger" ? "#a32d2d" : "#0f4c35";
    el.innerHTML = `
      <div style="background:#fff;border-radius:20px;padding:2rem;max-width:380px;
                  width:90%;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,.2)">
        <div style="font-size:40px;margin-bottom:.75rem">${type === "danger" ? "🗑️" : "✅"}</div>
        <div style="font-weight:700;font-size:16px;margin-bottom:.5rem">${title}</div>
        <div style="font-size:14px;color:#888780;margin-bottom:1.5rem;line-height:1.6">${msg}</div>
        <div style="display:flex;gap:10px">
          <button id="_confirm_cancel" style="flex:1;padding:11px;background:#f1efe8;border:none;
            border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit">
            Batal
          </button>
          <button id="_confirm_ok" style="flex:1;padding:11px;background:${btnColor};color:#fff;
            border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit">
            Ya, Lanjutkan
          </button>
        </div>
      </div>
    `;
    el.style.cssText = `position:fixed;inset:0;background:rgba(0,0,0,.5);
      display:flex;align-items:center;justify-content:center;z-index:9997;padding:1rem;
      backdrop-filter:blur(4px)`;
    document.body.appendChild(el);
    document.getElementById("_confirm_cancel").onclick = () => el.remove();
    document.getElementById("_confirm_ok").onclick = () => {
      el.remove();
      onConfirm();
    };
  };

  // Format helpers
  const fmtDate = (d) =>
    new Date(d).toLocaleDateString("id-ID", {
      day: "2-digit",
      month: "long",
      year: "numeric",
    });
  const fmtTime = (d) =>
    new Date(d).toLocaleTimeString("id-ID", {
      hour: "2-digit",
      minute: "2-digit",
    });
  const fmtDT = (d) =>
    new Date(d).toLocaleString("id-ID", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  // Badge status ujian
  const examStatusBadge = (status) => {
    const map = {
      draft: { label: "Draft", cls: "badge-gray" },
      published: { label: "Terbuka", cls: "badge-blue" },
      ongoing: { label: "Berlangsung", cls: "badge-green" },
      finished: { label: "Selesai", cls: "badge-yellow" },
    };
    const s = map[status] || { label: status, cls: "badge-gray" };
    return `<span class="badge ${s.cls}">${s.label}</span>`;
  };

  // Role badge
  const roleBadge = (role) => {
    const map = {
      admin: { label: "Admin", cls: "badge-red" },
      guru: { label: "Guru", cls: "badge-blue" },
      guru_pending: { label: "Menunggu", cls: "badge-yellow" },
      siswa: { label: "Siswa", cls: "badge-green" },
    };
    const r = map[role] || { label: role, cls: "badge-gray" };
    return `<span class="badge ${r.cls}">${r.label}</span>`;
  };

  // Render sidebar aktif
  const setActiveSidebar = (id) => {
    document
      .querySelectorAll(".sb-item")
      .forEach((el) => el.classList.remove("active"));
    const el = document.getElementById(id);
    if (el) el.classList.add("active");
  };

  // Init user info di sidebar
  const initSidebar = () => {
    const user = Auth.getUser();
    if (!user) return;
    const nameEl = document.getElementById("sb-user-name");
    const roleEl = document.getElementById("sb-user-role");
    const avatarEl = document.getElementById("sb-avatar");
    if (nameEl) nameEl.textContent = user.name || "—";
    if (roleEl)
      roleEl.textContent =
        {
          admin: "Administrator",
          guru: "Guru Pengampu",
          guru_pending: "Menunggu Approval",
          siswa: "Siswa",
        }[user.role] || user.role;
    if (avatarEl) avatarEl.textContent = (user.name || "?")[0].toUpperCase();

    // Kalau admin masuk halaman guru, tambahkan tombol balik ke admin panel
    if (
      user.role === "admin" &&
      window.location.pathname.includes("/pages/guru-")
    ) {
      const sbNav = document.querySelector(".sb-nav");
      if (sbNav && !document.getElementById("btn-back-admin")) {
        const backBtn = document.createElement("a");
        backBtn.id = "btn-back-admin";
        backBtn.href = "/pages/admin-dashboard.html";
        backBtn.className = "sb-item";
        backBtn.style.cssText =
          "background:rgba(255,255,255,.1);margin:0 .75rem .5rem;border-radius:8px";
        backBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="18" height="18"><path d="M19 12H5M12 5l-7 7 7 7" stroke-linecap="round" stroke-linejoin="round"/></svg> Admin Panel`;
        sbNav.insertBefore(backBtn, sbNav.firstChild);
      }
    }
  };

  return {
    toast,
    loading,
    confirm,
    fmtDate,
    fmtTime,
    fmtDT,
    examStatusBadge,
    roleBadge,
    setActiveSidebar,
    initSidebar,
  };
})();
