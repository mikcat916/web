const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const loginConfig = window.APP_CONFIG || {};

loginForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";

  if (!loginConfig.mysqlReady) {
    loginError.textContent = "MySQL 当前不可用，暂时无法登录。";
    return;
  }

  const payload = Object.fromEntries(new FormData(loginForm).entries());

  try {
    const response = await fetch("/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "登录失败");
    }
    window.location.href = data.redirect || "/overview";
  } catch (error) {
    loginError.textContent = error.message;
  }
});
