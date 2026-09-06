// Makes the admin pages work even when the frontend (Netlify) and backend
// (e.g. PythonAnywhere) are on different domains. Every existing fetch('/admin/api/...')
// call in dashboard.html / login.html keeps working unchanged: this file
// transparently (1) prefixes the configured backend URL, and (2) attaches
// the admin's saved token as an Authorization header, since a same-site
// cookie can't cross domains but the backend already accepts a Bearer token
// as a fallback.
(function () {
  const BACKEND = (window.APP_CONFIG && window.APP_CONFIG.BACKEND_URL) || "";
  const _fetch = window.fetch.bind(window);

  window.fetch = function (input, init) {
    let url = input;
    let isAdmin = typeof url === "string" && url.indexOf("/admin/api") === 0;

    if (isAdmin) {
      init = init || {};
      const token = localStorage.getItem("ggh_admin_token");
      if (token) {
        init.headers = Object.assign({}, init.headers, { Authorization: "Bearer " + token });
      }
      url = BACKEND + url;
    }

    return _fetch(url, init).then(async (res) => {
      // Admin login endpoint: stash the token from the JSON body so we can
      // send it as a header on every later cross-origin request. This is
      // AWAITED (not fire-and-forget) so the token is guaranteed saved
      // before doLogin()'s `await fetch(...)` resolves and the page
      // navigates to the dashboard — otherwise the navigation could win
      // the race and the dashboard would load with no token yet saved,
      // bouncing straight back to the login page.
      if (isAdmin && typeof input === "string" && input.indexOf("/admin/api/login") === 0) {
        try {
          const data = await res.clone().json();
          if (data && data.token) localStorage.setItem("ggh_admin_token", data.token);
        } catch (e) {}
      }
      if (isAdmin && typeof input === "string" && input.indexOf("/admin/api/logout") === 0) {
        localStorage.removeItem("ggh_admin_token");
      }
      return res;
    });
  };
})();
