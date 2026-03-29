const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const loginConfig = window.APP_CONFIG || {};
const loginSubmitButton = loginForm?.querySelector('button[type="submit"]');

function setLoginSubmitting(submitting) {
  if (!loginSubmitButton) return;
  loginSubmitButton.disabled = submitting;
  loginSubmitButton.textContent = submitting ? "登录中..." : "登录";
}

loginForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";

  if (!loginConfig.mysqlReady) {
    loginError.textContent = "MySQL 当前不可用，暂时无法登录。";
    return;
  }

  const payload = Object.fromEntries(new FormData(loginForm).entries());
  payload.username = String(payload.username || "").trim();
  payload.password = String(payload.password || "").trim();

  if (!payload.username) {
    loginError.textContent = "请输入用户名。";
    return;
  }

  if (!payload.password) {
    loginError.textContent = "请输入密码。";
    return;
  }

  try {
    setLoginSubmitting(true);
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
  } finally {
    setLoginSubmitting(false);
  }
});
