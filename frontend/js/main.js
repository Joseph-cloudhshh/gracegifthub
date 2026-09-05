// Uses window.APP_CONFIG.BACKEND_URL (set in js/config.js) so this works
// whether the frontend and backend are on the same server (leave it blank)
// or split across two domains, e.g. Netlify (frontend) + PythonAnywhere (backend).
const API_BASE = ((window.APP_CONFIG && window.APP_CONFIG.BACKEND_URL) || "") + "/api";

function getToken() {
  return localStorage.getItem("ggh_token");
}

function getUser() {
  const raw = localStorage.getItem("ggh_user");
  return raw ? JSON.parse(raw) : null;
}

function setSession(token, user) {
  localStorage.setItem("ggh_token", token);
  localStorage.setItem("ggh_user", JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem("ggh_token");
  localStorage.removeItem("ggh_user");
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (networkErr) {
    throw new Error(
      `Could not reach the server at ${API_BASE}. Is the backend (python app.py) running?`
    );
  }

  const rawText = await res.text();
  let data = {};
  try {
    data = rawText ? JSON.parse(rawText) : {};
  } catch (parseErr) {
    throw new Error(
      `Server returned an unexpected response (status ${res.status}). ` +
      `Raw response: ${rawText.slice(0, 200)}`
    );
  }

  if (!res.ok) throw new Error(data.error || `Request failed (status ${res.status}).`);
  return data;
}

function formatNaira(amount) {
  return "₦" + Number(amount).toLocaleString("en-NG");
}

// ---------- Delivery countries ----------
const DELIVERY_COUNTRIES = [
  "United States", "Canada", "United Kingdom", "Germany", "Australia",
  "France", "Switzerland", "Spain", "Belgium", "Italy", "Japan",
  "Malaysia", "Mexico", "Netherlands", "Poland", "Sweden", "Brazil",
  "China", "New Zealand", "Norway", "Portugal", "Singapore", "Thailand",
];

// ---------- Address book (stored server-side, one per country per user) ----------
async function getAddressBook() {
  const list = await apiFetch("/addresses");
  const book = {};
  list.forEach(a => { book[a.country] = a; });
  return book;
}

async function saveAddress(country, address) {
  return apiFetch("/addresses", {
    method: "POST",
    body: JSON.stringify({
      country,
      full_name: address.fullName,
      phone: address.phone,
      street: address.street,
      city: address.city,
      state: address.state,
      postal_code: address.postal,
    }),
  });
}

async function deleteAddressById(addressId) {
  return apiFetch(`/addresses/${addressId}`, { method: "DELETE" });
}

// ---------- Contact info (centrally managed by admin) ----------
let _contactInfoCache = null;
async function getContactInfo() {
  if (_contactInfoCache) return _contactInfoCache;
  try {
    _contactInfoCache = await apiFetch("/settings/contact");
  } catch (e) {
    // Safe fallback if the API call fails for any reason.
    _contactInfoCache = {
      support_email: "supportgracegifthub@gmail.com",
      support_phone: "+234 708 837 6847",
      whatsapp_link: "https://wa.link/y9ozfj",
    };
  }
  return _contactInfoCache;
}

function applyContactInfoToPage(info) {
  // Leaf elements: just show the text (and set href if it's a link with no children).
  document.querySelectorAll("[data-contact-email-text]").forEach(el => {
    el.textContent = info.support_email;
    if (el.tagName === "A") el.href = `mailto:${info.support_email}`;
  });
  document.querySelectorAll("[data-contact-phone-text]").forEach(el => {
    el.textContent = info.support_phone;
    if (el.tagName === "A") el.href = `tel:${info.support_phone.replace(/[^\d+]/g, "")}`;
  });
  // Wrapper links (may contain icons/labels) — only set href, never touch content.
  document.querySelectorAll("[data-contact-email-href]").forEach(el => {
    el.href = `mailto:${info.support_email}`;
  });
  document.querySelectorAll("[data-contact-phone-href]").forEach(el => {
    el.href = `tel:${info.support_phone.replace(/[^\d+]/g, "")}`;
  });
  document.querySelectorAll("[data-contact-whatsapp]").forEach(el => {
    if (el.tagName === "A") el.href = info.whatsapp_link;
  });
}

// ---------- WhatsApp product-request popup (reusable, site-wide) ----------
const WHATSAPP_DISMISS_KEY = "ggh_whatsapp_popup_dismissed_at";
const WHATSAPP_DISMISS_MS = 1000 * 60 * 30; // remember dismissal for 30 minutes

function whatsappPopupHtml(info) {
  return `
    <div id="ggh-whatsapp-widget" class="ggh-wa-widget">
      <div id="ggh-wa-card" class="ggh-wa-card hidden">
        <button id="ggh-wa-close" class="ggh-wa-close" aria-label="Close">✕</button>
        <div class="ggh-wa-icon">💬</div>
        <p class="ggh-wa-text">Looking for a particular product and couldn't find it?
          Contact us on WhatsApp and we'll help you find it.</p>
        <a href="${info.whatsapp_link}" target="_blank" rel="noopener" class="ggh-wa-btn">
          Contact Us on WhatsApp
        </a>
      </div>
      <button id="ggh-wa-fab" class="ggh-wa-fab" aria-label="WhatsApp support">💬</button>
    </div>
  `;
}

async function initWhatsappWidget() {
  // Don't duplicate the widget if it's already on the page.
  if (document.getElementById("ggh-whatsapp-widget")) return;

  const info = await getContactInfo();
  applyContactInfoToPage(info);
  if (!info.whatsapp_link) return;

  const wrap = document.createElement("div");
  wrap.innerHTML = whatsappPopupHtml(info);
  document.body.appendChild(wrap.firstElementChild);

  const card = document.getElementById("ggh-wa-card");
  const fab = document.getElementById("ggh-wa-fab");
  const closeBtn = document.getElementById("ggh-wa-close");

  const lastDismissed = Number(localStorage.getItem(WHATSAPP_DISMISS_KEY) || 0);
  const recentlyDismissed = Date.now() - lastDismissed < WHATSAPP_DISMISS_MS;

  function showCard() { card.classList.remove("hidden"); }
  function hideCard() {
    card.classList.add("hidden");
    localStorage.setItem(WHATSAPP_DISMISS_KEY, String(Date.now()));
  }

  // Exposed globally so other pages/scripts (e.g. dashboard.js switching
  // tabs, opening the menu) can pop this card back up on demand — always,
  // regardless of the 30-minute "recently dismissed" cooldown below, which
  // only governs the very first automatic show on page load.
  window.gghShowWhatsappPopup = showCard;

  fab.addEventListener("click", () => {
    card.classList.contains("hidden") ? showCard() : hideCard();
  });
  closeBtn.addEventListener("click", hideCard);

  if (!recentlyDismissed) {
    // Small delay so it doesn't fight with page-load layout shifts.
    setTimeout(showCard, 1500);
  }

  // Never overlap the Support AI chat panel, checkout, or other modals —
  // hide the whole widget while any full-screen panel/form on the page
  // is open, and bring it back once it closes.
  const widget = document.getElementById("ggh-whatsapp-widget");
  const watchIds = ["aiPanel"];
  const observer = new MutationObserver(() => {
    const anyOpen = watchIds.some(id => {
      const el = document.getElementById(id);
      return el && !el.classList.contains("hidden");
    });
    widget.style.display = anyOpen ? "none" : "";
  });
  watchIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) observer.observe(el, { attributes: true, attributeFilter: ["class"] });
  });
}

document.addEventListener("DOMContentLoaded", initWhatsappWidget);

// ---------- Landing page nav ----------
document.addEventListener("DOMContentLoaded", () => {
  const heroCountrySelect = document.getElementById("deliveryCountry");
  if (heroCountrySelect && heroCountrySelect.closest(".hero-form")) {
    heroCountrySelect.innerHTML = `<option value="">Select delivery country</option>` +
      DELIVERY_COUNTRIES.map(c => `<option value="${c}">${c}</option>`).join("");
  }

  // ---------- Guest hamburger menu (landing page only) ----------
  const menuBtn = document.getElementById("menuBtn");
  const guestMenu = document.getElementById("guestMenu");
  const guestMenuOverlay = document.getElementById("guestMenuOverlay");
  const guestMenuClose = document.getElementById("guestMenuClose");
  const guestMenuCountries = document.getElementById("guestMenuCountries");

  if (menuBtn && guestMenu) {
    if (guestMenuCountries) {
      guestMenuCountries.innerHTML = DELIVERY_COUNTRIES
        .map(c => `<a href="signup.html" class="country-link">📍 ${c}</a>`)
        .join("");
    }

    const openGuestMenu = () => {
      guestMenu.classList.add("open");
      guestMenuOverlay.classList.remove("hidden");
    };
    const closeGuestMenu = () => {
      guestMenu.classList.remove("open");
      guestMenuOverlay.classList.add("hidden");
    };

    menuBtn.addEventListener("click", openGuestMenu);
    guestMenuClose && guestMenuClose.addEventListener("click", closeGuestMenu);
    guestMenuOverlay && guestMenuOverlay.addEventListener("click", closeGuestMenu);
  }
});
