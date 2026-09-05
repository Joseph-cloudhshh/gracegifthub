let CASHBACK_RATE = 0.02;
let selectedAddressCountry = null;
let currentWalletBalance = 0;
let shopState = { category: "", query: "" };
let shopSearchDebounce = null;

document.addEventListener("DOMContentLoaded", () => {
  const user = getUser();
  if (!user) {
    window.location.href = "login.html";
    return;
  }

  // Baseline history entry for the dashboard's own tab navigation (see
  // activateTab/popstate below) — this is separate from login/signup's
  // history.replace(), which is what keeps a swipe-back gesture from
  // landing you on the login form in the first place.
  history.replaceState({ tab: "overview" }, "", "#overview");

  document.getElementById("userName") && (document.getElementById("userName").textContent = user.full_name);
  const hour = new Date().getHours();
  const greetingWord = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  document.getElementById("greeting").textContent = `${greetingWord}, ${user.full_name.split(" ")[0]}! 👋`;

  const recipientEmailInput = document.getElementById("recipientEmail");
  if (recipientEmailInput && !recipientEmailInput.value) recipientEmailInput.value = user.email || "";

  document.getElementById("logoutBtn").addEventListener("click", () => {
    clearSession();
    window.location.href = "index.html";
  });

  setupTabs();
  setupMobileMenu();
  setupAddressesTab();
  setupProfileTab();
  setupShopSearch();
  setupWalletTab();
  populateCheckoutCountries();
  loadOverview();
  loadShop();
  loadOrders();
  loadCart();
  loadWallet();

  document.getElementById("checkoutForm").addEventListener("submit", handleCheckout);
});

// ---------- WhatsApp popup: pop it back up on key dashboard actions ----------
// Product-not-found help should resurface whenever the customer visits
// Shop, Profile, Orders, or Cart/Checkout, or opens the menu — not just
// once on first page load. The card still has its own close ("cancel")
// button (see main.js) so the customer can dismiss it each time it shows.
function pingWhatsappPopup() {
  if (typeof window.gghShowWhatsappPopup === "function") {
    window.gghShowWhatsappPopup();
  }
}

// ---------- Mobile menu ----------
function setupMobileMenu() {
  const menuBtn = document.getElementById("mobileMenuBtn");
  const closeBtn = document.getElementById("closeMenuBtn");
  const nav = document.getElementById("sidebarNav");
  const overlay = document.getElementById("sidebarOverlay");
  if (!menuBtn || !nav) return;

  const open = () => { nav.classList.add("open"); overlay.classList.remove("hidden"); pingWhatsappPopup(); };
  const close = () => { nav.classList.remove("open"); overlay.classList.add("hidden"); };

  menuBtn.addEventListener("click", open);
  closeBtn && closeBtn.addEventListener("click", close);
  overlay && overlay.addEventListener("click", close);
}

function closeMobileMenu() {
  document.getElementById("sidebarNav")?.classList.remove("open");
  document.getElementById("sidebarOverlay")?.classList.add("hidden");
}

// ---------- Sidebar mobile-menu setup (country quick-list removed) ----------
// ---------- Tabs ----------
function activateTab(tabName, opts = {}) {
  document.querySelectorAll(".sidebar-nav a[data-tab]").forEach(l => l.classList.remove("active"));
  const navMatch = document.querySelector(`.sidebar-nav a[data-tab="${tabName}"]`);
  if (navMatch) navMatch.classList.add("active");
  document.querySelectorAll(".dash-tab").forEach(t => t.classList.add("hidden"));
  const target = document.getElementById(`tab-${tabName}`);
  if (target) target.classList.remove("hidden");
  if (tabName === "addresses") renderCountryGrid();
  if (tabName === "profile") loadProfileForm();
  if (tabName === "wallet") loadWallet();
  if (tabName === "cart") { loadWallet(); loadCart(); }
  if (["shop", "profile", "orders", "cart"].includes(tabName)) pingWhatsappPopup();
  window.scrollTo({ top: 0, behavior: "smooth" });

  const backBtn = document.getElementById("dashBackBtn");
  if (backBtn) backBtn.classList.toggle("hidden", tabName === "overview");

  // Keep the browser's own back button/swipe-back gesture inside the
  // dashboard: switching tabs pushes a history entry (so swiping back
  // moves between tabs, not out to the login page), while landing on
  // "overview" replaces the entry instead of stacking on top of it.
  if (!opts.fromPopState) {
    if (tabName === "overview") {
      history.replaceState({ tab: tabName }, "", "#" + tabName);
    } else {
      history.pushState({ tab: tabName }, "", "#" + tabName);
    }
  }
}

window.addEventListener("popstate", (e) => {
  const tab = (e.state && e.state.tab) || "overview";
  activateTab(tab, { fromPopState: true });
});

function setupTabs() {
  const links = document.querySelectorAll("[data-tab]");
  links.forEach(link => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      activateTab(link.dataset.tab);
      closeMobileMenu();
    });
  });

  document.getElementById("dashBackBtn")?.addEventListener("click", () => {
    activateTab("overview");
  });
}

function badgeClass(status) {
  return `badge badge-${status}`;
}

// ---------- Shop (search + categories) ----------
async function loadCategories() {
  const wrap = document.getElementById("categoryChips");
  if (!wrap) return;
  try {
    const categories = await apiFetch("/products/categories");
    const chips = [`<button type="button" class="category-chip ${!shopState.category ? 'active' : ''}" data-category="">All</button>`]
      .concat(categories.map(c => `
        <button type="button" class="category-chip ${shopState.category === c.category ? 'active' : ''}" data-category="${c.category}">
          ${c.category} (${c.count})
        </button>`));
    wrap.innerHTML = chips.join("");
    wrap.querySelectorAll(".category-chip").forEach(btn => {
      btn.addEventListener("click", () => {
        shopState.category = btn.dataset.category;
        document.getElementById("shopSearchInput").value = "";
        shopState.query = "";
        document.getElementById("shopSearchClear").classList.add("hidden");
        loadCategories();
        loadShop();
      });
    });
  } catch (e) {
    console.error(e);
  }
}

function setupShopSearch() {
  const input = document.getElementById("shopSearchInput");
  const clearBtn = document.getElementById("shopSearchClear");
  if (!input) return;

  input.addEventListener("input", () => {
    clearBtn.classList.toggle("hidden", !input.value);
    clearTimeout(shopSearchDebounce);
    shopSearchDebounce = setTimeout(() => {
      shopState.query = input.value.trim();
      loadShop();
    }, 300);
  });

  clearBtn.addEventListener("click", () => {
    input.value = "";
    shopState.query = "";
    clearBtn.classList.add("hidden");
    loadShop();
  });
}

function productCardHtml(p) {
  const outOfStock = p.in_stock === false;
  return `
    <div class="product-card">
      <img src="${p.image_url || ''}" alt="${p.name}" onerror="this.style.display='none'">
      <div class="pc-body">
        <h4>${p.name}</h4>
        <div class="pc-meta">${p.category || ''}</div>
        <div class="price">${formatNaira(p.price)}</div>
        ${outOfStock ? `<div class="pc-meta out-of-stock">Out of stock</div>` : ''}
        <button ${outOfStock ? 'disabled' : ''} onclick="addToCart(${p.id})">
          ${outOfStock ? 'Out of stock' : 'Add to cart'}
        </button>
      </div>
    </div>
  `;
}

// Groups a flat product list into [category, products[]] pairs, ordered by
// how many products are in each category (most first), so the categories
// with the most gifts show up first while still keeping order stable for
// ties. Products with no category (shouldn't normally happen) fall under
// a generic "Gifts" bucket rather than being dropped.
function groupProductsByCategory(products) {
  const map = new Map();
  products.forEach(p => {
    const cat = (p.category && String(p.category).trim()) || "Gifts";
    if (!map.has(cat)) map.set(cat, []);
    map.get(cat).push(p);
  });
  return [...map.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]));
}

function categorySectionHtml(category, items) {
  return `
    <div class="category-section">
      <h3 class="category-section-title">${category}</h3>
      <div class="product-grid">
        ${items.map(productCardHtml).join("")}
      </div>
    </div>
  `;
}

async function loadShop() {
  const grid = document.getElementById("productGrid");
  if (!document.getElementById("categoryChips").dataset.loaded) {
    document.getElementById("categoryChips").dataset.loaded = "1";
    loadCategories();
  }
  try {
    let products;
    if (shopState.query) {
      products = await apiFetch(`/products/search?q=${encodeURIComponent(shopState.query)}`);
    } else {
      const qs = shopState.category ? `?category=${encodeURIComponent(shopState.category)}` : "";
      products = await apiFetch(`/products${qs}`);
    }
    if (!products.length) {
      grid.innerHTML = `<div class="no-results"><p class="muted">No products found${shopState.query ? ` for "${shopState.query}"` : ''}.</p></div>`;
      return;
    }
    const grouped = groupProductsByCategory(products);
    grid.innerHTML = grouped.map(([category, items]) => categorySectionHtml(category, items)).join("");
  } catch (e) {
    grid.innerHTML = `<p class="muted">Couldn't load gifts right now: ${e.message}</p>`;
  }
}

async function addToCart(productId) {
  try {
    await apiFetch("/cart/add", {
      method: "POST",
      body: JSON.stringify({ product_id: productId, quantity: 1 }),
    });
    await loadOverview();
    await loadCart();
  } catch (e) {
    alert(e.message);
  }
}

// ---------- Overview ----------
async function loadOverview() {
  try {
    const orders = await apiFetch("/orders");
    const cart = await apiFetch("/cart");

    const totalSpent = orders.reduce((sum, o) => sum + o.total, 0);
    const cashback = Math.round(totalSpent * CASHBACK_RATE);

    document.getElementById("statOrders").textContent = orders.length;
    document.getElementById("statSpent").textContent = formatNaira(totalSpent);
    document.getElementById("statCashback").textContent = formatNaira(cashback);
    document.getElementById("cashbackHeroValue").textContent = formatNaira(cashback);

    updateCartBadge(cart.items.reduce((n, i) => n + i.quantity, 0));

    const recent = orders.slice(0, 3);
    document.getElementById("recentOrders").innerHTML = recent.length
      ? recent.map(orderRowHtml).join("")
      : `<p class="muted">No orders yet — your first gift is one click away.</p>`;
  } catch (e) {
    console.error(e);
  }
}

function updateCartBadge(count) {
  const badge = document.getElementById("cartBadge");
  if (!badge) return;
  if (count > 0) {
    badge.textContent = count;
    badge.classList.remove("hidden");
  } else {
    badge.classList.add("hidden");
  }
}

// ---------- Orders ----------
async function loadOrders() {
  try {
    const orders = await apiFetch("/orders");
    document.getElementById("allOrders").innerHTML = orders.length
      ? orders.map(orderRowHtml).join("")
      : `<p class="muted">No orders yet.</p>`;
  } catch (e) {
    console.error(e);
  }
}

function orderRowHtml(o) {
  return `
    <div class="order-row">
      <div>
        <strong>#${o.order_ref}</strong>
        <div class="muted" style="font-size:.8rem">${new Date(o.created_at).toLocaleDateString()}</div>
      </div>
      <span class="${badgeClass(o.status)}">${o.status.replace("_", " ")}</span>
      <strong>${formatNaira(o.total)}</strong>
    </div>
  `;
}

// ---------- Cart ----------
let currentCashbackBalance = 0;

async function loadCart() {
  try {
    const [cart, orders] = await Promise.all([apiFetch("/cart"), apiFetch("/orders")]);
    const deliveryFee = 5000;
    const totalSpent = orders.reduce((sum, o) => sum + o.total, 0);
    currentCashbackBalance = Math.round(totalSpent * CASHBACK_RATE);

    const summaryWrap = document.getElementById("cartSummaryWrap");
    const form = document.getElementById("checkoutForm");

    if (!cart.items.length) {
      document.getElementById("cartItems").innerHTML = `
        <div class="empty-cart">
          <div class="empty-cart-icon">🛍️</div>
          <p class="muted">Your cart is empty.</p>
          <a href="#" data-tab="shop" class="btn-primary small">Shop Gifts</a>
        </div>`;
      document.querySelectorAll('#cartItems [data-tab]').forEach(el => {
        el.addEventListener("click", (e) => { e.preventDefault(); activateTab("shop"); });
      });
      summaryWrap.classList.add("hidden");
      form.classList.add("hidden");
      updateCartBadge(0);
      return;
    }

    document.getElementById("cartItems").innerHTML = cart.items.map(i => `
      <div class="cart-row">
        <span>${i.product.name}</span>
        <div class="qty-control">
          <button type="button" onclick="changeQty(${i.id}, ${i.quantity - 1})">−</button>
          <span>${i.quantity}</span>
          <button type="button" onclick="changeQty(${i.id}, ${i.quantity + 1})">+</button>
        </div>
        <span>${formatNaira(i.product.price * i.quantity)}</span>
        <button type="button" class="remove-btn" onclick="removeCartItem(${i.id})" aria-label="Remove">✕</button>
      </div>
    `).join("");

    summaryWrap.classList.remove("hidden");
    form.classList.remove("hidden");

    document.getElementById("cartSubtotal").textContent = formatNaira(cart.subtotal);
    document.getElementById("cartDelivery").textContent = formatNaira(deliveryFee);

    const cashbackRow = document.getElementById("cashbackRow");
    const useCashbackBox = document.getElementById("useCashback");
    if (currentCashbackBalance > 0) {
      cashbackRow.classList.remove("hidden");
      document.getElementById("cashbackAvailable").textContent = formatNaira(currentCashbackBalance);
    } else {
      cashbackRow.classList.add("hidden");
      useCashbackBox.checked = false;
    }

    recalcCartTotal(cart.subtotal, deliveryFee);
    useCashbackBox.onchange = () => recalcCartTotal(cart.subtotal, deliveryFee);

    // Wallet payment option: enable/disable based on current balance vs. total.
    updateWalletPaymentOption(cart.subtotal + deliveryFee - (useCashbackBox.checked ? Math.min(currentCashbackBalance, cart.subtotal) : 0));
    useCashbackBox.addEventListener("change", () => {
      const discount = useCashbackBox.checked ? Math.min(currentCashbackBalance, cart.subtotal) : 0;
      updateWalletPaymentOption(cart.subtotal + deliveryFee - discount);
    });

    updateCartBadge(cart.items.reduce((n, i) => n + i.quantity, 0));
  } catch (e) {
    console.error(e);
  }
}

function updateWalletPaymentOption(orderTotal) {
  const walletRadio = document.getElementById("payMethodWallet");
  const gatewayRadio = document.getElementById("payMethodGateway");
  const note = document.getElementById("walletInsufficientNote");
  const balEl = document.getElementById("payMethodWalletBalance");
  if (!walletRadio) return;
  balEl.textContent = formatNaira(currentWalletBalance);
  const sufficient = currentWalletBalance >= orderTotal && orderTotal > 0;
  walletRadio.disabled = !sufficient;
  if (!sufficient) {
    if (walletRadio.checked) gatewayRadio.checked = true;
    note.classList.remove("hidden");
  } else {
    note.classList.add("hidden");
  }
}

function recalcCartTotal(subtotal, deliveryFee) {
  const useCashbackBox = document.getElementById("useCashback");
  const discount = useCashbackBox && useCashbackBox.checked
    ? Math.min(currentCashbackBalance, subtotal)
    : 0;
  document.getElementById("cartTotal").textContent = formatNaira(subtotal + deliveryFee - discount);
}

async function changeQty(itemId, newQty) {
  try {
    await apiFetch(`/cart/update/${itemId}`, {
      method: "PUT",
      body: JSON.stringify({ quantity: newQty }),
    });
    await loadCart();
    await loadOverview();
  } catch (e) {
    alert(e.message);
  }
}

async function removeCartItem(itemId) {
  try {
    await apiFetch(`/cart/remove/${itemId}`, { method: "DELETE" });
    await loadCart();
    await loadOverview();
  } catch (e) {
    alert(e.message);
  }
}

// ---------- Wallet ----------
async function loadWallet() {
  try {
    const wallet = await apiFetch("/wallet");
    currentWalletBalance = wallet.balance;
    const balEl = document.getElementById("walletBalanceValue");
    if (balEl) balEl.textContent = formatNaira(wallet.balance);
    const payBalEl = document.getElementById("payMethodWalletBalance");
    if (payBalEl) payBalEl.textContent = formatNaira(wallet.balance);

    const txWrap = document.getElementById("walletTransactions");
    if (txWrap) {
      const txs = await apiFetch("/wallet/transactions");
      txWrap.innerHTML = txs.length
        ? txs.map(walletTxRowHtml).join("")
        : `<p class="muted">No wallet transactions yet.</p>`;
    }
  } catch (e) {
    console.error(e);
  }
}

function walletTxRowHtml(t) {
  const sign = t.tx_type === "funding" || t.tx_type === "refund" ? "+" : "−";
  const label = t.tx_type === "funding" ? "Wallet funding" : t.tx_type === "refund" ? "Refund" : "Purchase";
  return `
    <div class="order-row">
      <div>
        <strong>${label}</strong>
        <div class="muted" style="font-size:.8rem">${new Date(t.created_at).toLocaleString()}</div>
      </div>
      <span class="${t.status === 'successful' ? 'badge badge-delivered' : t.status === 'failed' ? 'badge badge-cancelled' : 'badge badge-pending'}">${t.status}</span>
      <strong>${sign}${formatNaira(t.amount)}</strong>
    </div>
  `;
}

function setupWalletTab() {
  const form = document.getElementById("fundWalletForm");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const amount = Number(document.getElementById("fundAmount").value);
    if (!amount || amount < 100) {
      alert("Please enter a valid amount (minimum ₦100).");
      return;
    }
    try {
      const init = await apiFetch("/wallet/fund/initiate", {
        method: "POST",
        body: JSON.stringify({ amount }),
      });
      launchPayscribeForWalletFunding(init);
    } catch (err) {
      alert(err.message);
    }
  });
}

function launchPayscribeForWalletFunding(init) {
  // Payscribe hosted/redirect checkout: the backend returns a checkout_url
  // once routes/wallet.py's TODO is wired up to Payscribe's real
  // initiate-transaction endpoint. Until then, checkout_url is null and we
  // can't send the customer anywhere safely.
  if (!init.checkout_url) {
    alert("Wallet funding via Payscribe isn't fully configured yet. Please contact support.");
    return;
  }
  // On return from Payscribe, the customer should land back here (or on a
  // dedicated return page) which then calls /wallet/fund/verify/<tx_ref>.
  window.location.href = init.checkout_url;
}

// ---------- Checkout ----------
function populateCheckoutCountries() {
  const select = document.getElementById("deliveryCountry");
  if (!select) return;
  select.innerHTML = `<option value="" disabled selected>Select a country</option>` +
    DELIVERY_COUNTRIES.map(c => `<option value="${c}">${c}</option>`).join("");

  select.addEventListener("change", async () => {
    try {
      const book = await getAddressBook();
      const saved = book[select.value];
      if (saved) {
        document.getElementById("recipientName").value = document.getElementById("recipientName").value || saved.full_name;
        document.getElementById("recipientPhone").value = document.getElementById("recipientPhone").value || saved.phone;
        document.getElementById("deliveryAddress").value =
          [saved.street, saved.city, saved.state, saved.postal_code].filter(Boolean).join(", ");
      }
    } catch (e) {
      console.error(e);
    }
  });
}

async function handleCheckout(e) {
  e.preventDefault();
  const useCashbackBox = document.getElementById("useCashback");
  const discount = useCashbackBox && useCashbackBox.checked ? currentCashbackBalance : 0;
  const paymentMethod = (document.querySelector('input[name="paymentMethod"]:checked') || {}).value || "gateway";

  try {
    const order = await apiFetch("/orders/checkout", {
      method: "POST",
      body: JSON.stringify({
        recipient_name: document.getElementById("recipientName").value,
        recipient_phone: document.getElementById("recipientPhone").value,
        recipient_email: document.getElementById("recipientEmail").value,
        delivery_country: document.getElementById("deliveryCountry").value,
        delivery_address: document.getElementById("deliveryAddress").value,
        gift_message: document.getElementById("giftMessage").value,
        discount: discount,
      }),
    });

    if (paymentMethod === "wallet") {
      try {
        await apiFetch(`/orders/${order.id}/pay-with-wallet`, { method: "POST" });
        alert("Payment successful! Your gift is on its way.");
        window.location.href = "dashboard.html";
      } catch (err) {
        // Server does the final balance check — if it says insufficient,
        // fall back to the gateway instead of leaving the order stuck.
        alert(err.message + " You can complete payment via the gateway instead.");
        const payInit = await apiFetch(`/payments/initiate/${order.id}`, { method: "POST" });
        launchPayscribeCheckout(payInit, order.id);
      }
      return;
    }

    const payInit = await apiFetch(`/payments/initiate/${order.id}`, { method: "POST" });
    launchPayscribeCheckout(payInit, order.id);
  } catch (err) {
    alert(err.message);
  }
}

function launchPayscribeCheckout(payInit, orderId) {
  // Payscribe hosted/redirect checkout: the backend returns a checkout_url
  // once routes/payments.py's TODO is wired up to Payscribe's real
  // initiate-transaction endpoint. Until then, checkout_url is null and we
  // can't send the customer anywhere safely.
  if (!payInit.checkout_url) {
    alert("Checkout via Payscribe isn't fully configured yet. Please contact support.");
    return;
  }
  // On return from Payscribe, the customer should land back here (or on a
  // dedicated return page) which then calls /payments/verify/<tx_ref>.
  window.location.href = payInit.checkout_url;
}

// ---------- Addresses ----------
let addressBookCache = {};

function setupAddressesTab() {
  const form = document.getElementById("addressForm");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!selectedAddressCountry) return;
    const submitBtn = form.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    try {
      await saveAddress(selectedAddressCountry, {
        fullName: document.getElementById("addrFullName").value,
        phone: document.getElementById("addrPhone").value,
        street: document.getElementById("addrStreet").value,
        city: document.getElementById("addrCity").value,
        state: document.getElementById("addrState").value,
        postal: document.getElementById("addrPostal").value,
      });
      await renderCountryGrid();
      await openAddressForm(selectedAddressCountry);
    } catch (err) {
      alert(err.message);
    } finally {
      submitBtn.disabled = false;
    }
  });

  document.getElementById("deleteAddressBtn").addEventListener("click", async () => {
    if (!selectedAddressCountry) return;
    const existing = addressBookCache[selectedAddressCountry];
    if (!existing) return;
    if (!confirm(`Remove the saved address for ${selectedAddressCountry}?`)) return;
    try {
      await deleteAddressById(existing.id);
      selectedAddressCountry = null;
      document.getElementById("addressFormWrap").classList.add("hidden");
      await renderCountryGrid();
    } catch (err) {
      alert(err.message);
    }
  });

  renderSavedAddresses();
}

async function renderCountryGrid() {
  const grid = document.getElementById("countryGrid");
  try {
    addressBookCache = await getAddressBook();
  } catch (e) {
    console.error(e);
  }
  const book = addressBookCache;
  grid.innerHTML = DELIVERY_COUNTRIES.map(c => `
    <button type="button" class="country-chip ${book[c] ? 'has-address' : ''} ${selectedAddressCountry === c ? 'selected' : ''}" data-country="${c}">
      📍 ${c} ${book[c] ? '<span class="chip-check">✓</span>' : ''}
    </button>
  `).join("");
  grid.querySelectorAll(".country-chip").forEach(btn => {
    btn.addEventListener("click", () => openAddressForm(btn.dataset.country));
  });
  renderSavedAddresses();
}

async function openAddressForm(country) {
  selectedAddressCountry = country;
  const wrap = document.getElementById("addressFormWrap");

  if (!addressBookCache || Object.keys(addressBookCache).length === 0) {
    try { addressBookCache = await getAddressBook(); } catch (e) { console.error(e); }
  }
  const existing = addressBookCache[country];

  document.getElementById("addressFormTitle").textContent = existing
    ? `Edit address — ${country}`
    : `Add address — ${country}`;

  document.getElementById("addrFullName").value = existing ? existing.full_name : "";
  document.getElementById("addrPhone").value = existing ? existing.phone : "";
  document.getElementById("addrStreet").value = existing ? existing.street : "";
  document.getElementById("addrCity").value = existing ? existing.city : "";
  document.getElementById("addrState").value = existing ? existing.state : "";
  document.getElementById("addrPostal").value = existing ? existing.postal_code : "";

  document.getElementById("deleteAddressBtn").classList.toggle("hidden", !existing);

  wrap.classList.remove("hidden");

  const grid = document.getElementById("countryGrid");
  if (grid) {
    grid.querySelectorAll(".country-chip").forEach(btn => {
      btn.classList.toggle("selected", btn.dataset.country === country);
    });
  }
  wrap.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSavedAddresses() {
  const wrap = document.getElementById("savedAddressList");
  const book = addressBookCache;
  const countries = Object.keys(book);
  wrap.innerHTML = countries.length
    ? countries.map(c => {
        const a = book[c];
        return `
          <div class="order-row address-row">
            <div>
              <strong>📍 ${c}</strong>
              <div class="muted" style="font-size:.8rem">${[a.street, a.city, a.state].filter(Boolean).join(", ")}</div>
            </div>
            <button type="button" class="link-arrow" data-country="${c}">Edit</button>
          </div>
        `;
      }).join("")
    : `<p class="muted">No saved addresses yet — pick a country above to add one.</p>`;

  wrap.querySelectorAll("button[data-country]").forEach(btn => {
    btn.addEventListener("click", () => openAddressForm(btn.dataset.country));
  });
}

// ---------- Profile ----------
function setupProfileTab() {
  document.getElementById("profileForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const user = getUser();
    const token = getToken();
    user.full_name = document.getElementById("profileFullName").value || user.full_name;
    user.phone = document.getElementById("profilePhone").value;
    setSession(token, user);
    document.getElementById("greeting").textContent =
      `${greetingWordNow()}, ${user.full_name.split(" ")[0]}! 👋`;
    alert("Profile updated.");
  });
}

function greetingWordNow() {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

function loadProfileForm() {
  const user = getUser();
  document.getElementById("profileFullName").value = user.full_name || "";
  document.getElementById("profileEmail").value = user.email || "";
  document.getElementById("profilePhone").value = user.phone || "";
}
