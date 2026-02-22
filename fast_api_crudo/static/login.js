/* 🍖 Crudo Login Page */

(function () {
    const CFG = window.CRUDO_LOGIN_CONFIG;
    const errorEl = document.getElementById("login-error");
    const form = document.getElementById("login-form");

    // Show error from URL params (OAuth errors)
    const params = new URLSearchParams(window.location.search);
    const urlError = params.get("error");
    if (urlError) {
        const messages = {
            oauth_failed: "Google sign-in failed. Please try again.",
            not_allowed: "Your Google account is not authorized to access this panel.",
        };
        showError(messages[urlError] || "Authentication error.");
    }

    function showError(msg) {
        errorEl.textContent = msg;
        errorEl.classList.add("visible");
    }

    function hideError() {
        errorEl.classList.remove("visible");
    }

    if (form && CFG.hasBasic) {
        form.addEventListener("submit", async function (ev) {
            ev.preventDefault();
            hideError();

            const username = document.getElementById("username").value.trim();
            const password = document.getElementById("password").value;
            const btn = document.getElementById("login-submit");

            if (!username || !password) {
                showError("Please enter username and password.");
                return;
            }

            btn.disabled = true;
            btn.textContent = "Signing in\u2026";

            try {
                const res = await fetch(CFG.prefix + "/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password }),
                });

                const data = await res.json();

                if (!res.ok) {
                    showError(data.detail || "Login failed.");
                    btn.disabled = false;
                    btn.textContent = "Sign In";
                    return;
                }

                // Redirect to main panel
                window.location.href = CFG.prefix + "/";
            } catch (err) {
                showError("Network error. Please try again.");
                btn.disabled = false;
                btn.textContent = "Sign In";
            }
        });
    }
})();
