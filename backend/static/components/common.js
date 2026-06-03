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

  // Init user info di sidebar + mobile responsive
  const initSidebar = () => {
    const user = Auth.getUser();
    if (!user) return;
    const nameEl   = document.getElementById("sb-user-name");
    const roleEl   = document.getElementById("sb-user-role");
    const avatarEl = document.getElementById("sb-avatar");
    if (nameEl) nameEl.textContent = user.name || "—";
    if (roleEl) roleEl.textContent = {
      admin: "Administrator", guru: "Guru Pengampu",
      guru_pending: "Menunggu Approval", siswa: "Siswa",
    }[user.role] || user.role;
    if (avatarEl) avatarEl.textContent = (user.name || "?")[0].toUpperCase();

    // Admin di halaman guru → tombol balik
    if (user.role === "admin" && window.location.pathname.includes("/guru/")) {
      const sbNav = document.querySelector(".sb-nav");
      if (sbNav && !document.getElementById("btn-back-admin")) {
        const b = document.createElement("a");
        b.id = "btn-back-admin"; b.href = "/admin/dashboard.html"; b.className = "sb-item";
        b.style.cssText = "background:rgba(255,255,255,.1);margin:0 .75rem .5rem;border-radius:8px";
        b.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="18" height="18"><path d="M19 12H5M12 5l-7 7 7 7" stroke-linecap="round" stroke-linejoin="round"/></svg> Admin Panel`;
        sbNav.insertBefore(b, sbNav.firstChild);
      }
    }

    // ── MOBILE: Hamburger + Overlay + Bottom Nav ────────────────
    _initMobileNav();
  };

  const _initMobileNav = () => {
    const sidebar = document.querySelector(".sidebar");
    const topbar  = document.querySelector(".topbar");
    if (!sidebar || !topbar) return;

    // Overlay
    let overlay = document.getElementById("_sb_overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "_sb_overlay";
      overlay.className = "sidebar-overlay";
      document.body.appendChild(overlay);
    }

    // Hamburger button di topbar
    if (!document.getElementById("_hamburger")) {
      const btn = document.createElement("button");
      btn.id = "_hamburger"; btn.className = "hamburger"; btn.setAttribute("aria-label","Menu");
      btn.innerHTML = "<span></span><span></span><span></span>";
      topbar.insertBefore(btn, topbar.firstChild);
      btn.addEventListener("click", _toggleSidebar);
    }

    overlay.addEventListener("click", _closeSidebar);

    // Close sidebar on nav item click (mobile)
    sidebar.querySelectorAll(".sb-item,.sb-logout").forEach(el => {
      el.addEventListener("click", () => { if (window.innerWidth <= 768) _closeSidebar(); });
    });

    // ── Bottom Navigation ─────────────────────────────────────
    if (!document.getElementById("_bottom_nav")) {
      const items = [];
      sidebar.querySelectorAll(".sb-item").forEach(el => {
        const label = el.textContent.trim();
        const href  = el.getAttribute("href") || "#";
        const svgEl = el.querySelector("svg");
        const svg   = svgEl ? svgEl.outerHTML : "";
        const active = el.classList.contains("active");
        items.push({ label, href, svg, active });
      });

      const maxItems = Math.min(items.length, 5);
      const visible  = items.slice(0, maxItems);

      const nav = document.createElement("nav");
      nav.id = "_bottom_nav"; nav.className = "bottom-nav";
      nav.innerHTML = `<div class="bottom-nav-inner">
        ${visible.map(it => `
          <a class="bn-item${it.active ? " active" : ""}" href="${it.href}">
            ${it.svg}
            <span>${it.label.substring(0,9)}</span>
          </a>`).join("")}
      </div>`;
      document.body.appendChild(nav);
    }
  };

  const _toggleSidebar = () => {
    const sidebar  = document.querySelector(".sidebar");
    const overlay  = document.getElementById("_sb_overlay");
    const ham      = document.getElementById("_hamburger");
    const isOpen   = sidebar.classList.toggle("open");
    if (overlay) overlay.classList.toggle("show", isOpen);
    if (ham) ham.setAttribute("aria-expanded", isOpen);
    document.body.style.overflow = isOpen ? "hidden" : "";
  };

  const _closeSidebar = () => {
    const sidebar = document.querySelector(".sidebar");
    const overlay = document.getElementById("_sb_overlay");
    const ham     = document.getElementById("_hamburger");
    if (sidebar) sidebar.classList.remove("open");
    if (overlay) overlay.classList.remove("show");
    if (ham) ham.setAttribute("aria-expanded", "false");
    document.body.style.overflow = "";
  };

  // Close on ESC key
  document.addEventListener("keydown", e => { if (e.key === "Escape") _closeSidebar(); });

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
