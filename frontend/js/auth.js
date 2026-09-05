document.addEventListener("DOMContentLoaded", () => {
  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errorEl = document.getElementById("loginError");
      errorEl.classList.add("hidden");
      try {
        const data = await apiFetch("/auth/login", {
          method: "POST",
          body: JSON.stringify({
            email: document.getElementById("email").value,
            password: document.getElementById("password").value,
          }),
        });
        setSession(data.token, data.user);
        // replace(), not href — drops the login/signup form from browser
        // history so a back-swipe from the dashboard can't land back on it.
        window.location.replace("dashboard.html");
      } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove("hidden");
      }
    });
  }

  const signupForm = document.getElementById("signupForm");
  if (signupForm) {
    signupForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errorEl = document.getElementById("signupError");
      errorEl.classList.add("hidden");
      try {
        const data = await apiFetch("/auth/signup", {
          method: "POST",
          body: JSON.stringify({
            full_name: document.getElementById("fullName").value,
            email: document.getElementById("email").value,
            phone: document.getElementById("phone").value,
            password: document.getElementById("password").value,
          }),
        });
        setSession(data.token, data.user);
        // replace(), not href — drops the login/signup form from browser
        // history so a back-swipe from the dashboard can't land back on it.
        window.location.replace("dashboard.html");
      } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove("hidden");
      }
    });
  }
});
