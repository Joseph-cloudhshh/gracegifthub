/**
 * Support AI — a lightweight, rule-based chat widget scoped to what this
 * site can actually do (browse/buy gifts, check orders, contact info).
 * It is NOT a general-purpose AI: anything outside that scope gets a
 * consistent "message the admin" response, since there's no admin
 * dashboard/live agent wired up yet.
 */

const AI_ADMIN_EMAIL_FALLBACK = "supportgracegifthub@gmail.com";
let AI_ADMIN_EMAIL = AI_ADMIN_EMAIL_FALLBACK;
if (typeof getContactInfo === "function") {
  getContactInfo().then(info => { if (info && info.support_email) AI_ADMIN_EMAIL = info.support_email; });
}

const AI_SUGGESTIONS = [
  { label: "How do I buy a gift?", key: "buy" },
  { label: "How do I check my order?", key: "order" },
  { label: "Contact information", key: "contact" },
];

const AI_RESPONSES = [
  {
    key: "buy",
    match: /\b(buy|purchase|order.*gift|how.*(buy|shop)|add.*cart|checkout)\b/i,
    reply:
      "To buy a gift: go to **Shop Gifts** in the menu, pick a product and tap " +
      "**Add to cart**. When you're ready, open **Cart**, fill in the delivery " +
      "address, and tap **Proceed to Payment** to pay securely with Payscribe.",
  },
  {
    key: "order",
    match: /\b(track|order status|my order|check.*order|where.*order|delivery status)\b/i,
    reply:
      "You can see all your orders under **My Orders** on the Home tab, or the " +
      "**Orders** link in the menu — it shows the status and total for each one.",
  },
  {
    key: "contact",
    match: /\b(contact|reach|phone|email|call|support number)\b/i,
    reply: () =>
      `You can reach us by email at ${AI_ADMIN_EMAIL}, or check the **Support** ` +
      "tab in the menu for the full contact details.",
  },
  {
    key: "cashback",
    match: /\bcashback\b/i,
    reply: () =>
      "You earn 2% cashback on every completed order, shown on your Home tab. " +
      "You can apply your cashback balance toward your next order at checkout.",
  },
  {
    key: "address",
    match: /\b(address|delivery location|shipping address)\b/i,
    reply: () =>
      "Manage your delivery addresses under **My Addresses** — you can save one " +
      "per country and reuse it at checkout.",
  },
];

function aiFallback() {
  return "I can only help with things related to Gracegifthub for now — " +
    "buying gifts, checking orders, cashback, addresses, or contact info. " +
    `For anything else, please message our admin at ${AI_ADMIN_EMAIL}. ` +
    "We're working on a full admin support dashboard soon!";
}

function aiRespond(userText) {
  const hit = AI_RESPONSES.find(r => r.match.test(userText));
  return hit ? (typeof hit.reply === "function" ? hit.reply() : hit.reply) : aiFallback();
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("supportAiBtn");
  const panel = document.getElementById("aiPanel");
  const overlay = document.getElementById("aiOverlay");
  const closeBtn = document.getElementById("aiCloseBtn");
  const messages = document.getElementById("aiMessages");
  const suggestionsWrap = document.getElementById("aiSuggestions");
  const form = document.getElementById("aiForm");
  const input = document.getElementById("aiInput");

  if (!btn || !panel) return; // not on this page

  let started = false;

  function addMessage(text, from) {
    const div = document.createElement("div");
    div.className = `ai-msg ${from}`;
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  function renderSuggestions() {
    suggestionsWrap.innerHTML = "";
    AI_SUGGESTIONS.forEach(s => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "ai-chip";
      chip.textContent = s.label;
      chip.addEventListener("click", () => handleUserMessage(s.label));
      suggestionsWrap.appendChild(chip);
    });
  }

  function handleUserMessage(text) {
    if (!text.trim()) return;
    addMessage(text, "user");
    input.value = "";
    setTimeout(() => addMessage(aiRespond(text), "bot"), 250);
  }

  function openPanel() {
    panel.classList.remove("hidden");
    overlay.classList.remove("hidden");
    if (!started) {
      started = true;
      addMessage(
        "Hi! I'm the Gracegifthub support assistant. Ask me how to buy " +
        "a gift, check an order, or get in touch with us — or tap a suggestion below.",
        "bot"
      );
      renderSuggestions();
    }
    input && input.focus();
  }

  function closePanel() {
    panel.classList.add("hidden");
    overlay.classList.add("hidden");
  }

  btn.addEventListener("click", openPanel);
  closeBtn && closeBtn.addEventListener("click", closePanel);
  overlay && overlay.addEventListener("click", closePanel);

  form && form.addEventListener("submit", (e) => {
    e.preventDefault();
    handleUserMessage(input.value);
  });
});
