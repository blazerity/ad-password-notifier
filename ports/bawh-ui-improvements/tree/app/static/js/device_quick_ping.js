(() => {
  const buttons = document.querySelectorAll("[data-device-quick-ping]");
  const meta = document.querySelector("[data-device-quick-ping-root]");
  if (!buttons.length || !meta || !window.BawhHttp) return;

  const { postJson } = window.BawhHttp;
  const url = meta.dataset.quickPingUrl || "";
  const csrf = meta.dataset.csrfToken || "";
  const statusHost = document.querySelector("[data-device-live-status]");
  if (!url) return;

  async function runPing(button) {
    button.disabled = true;
    button.classList.add("is-busy");
    try {
      const payload = await postJson(url, {}, csrf);
      if (statusHost && payload.status) {
        statusHost.dataset.status = payload.status;
        statusHost.textContent =
          payload.status === "online"
            ? "доступен"
            : payload.status === "offline"
              ? "недоступен"
              : "неизвестно";
        statusHost.classList.remove("text-bg-success", "text-bg-danger", "text-bg-secondary");
        if (payload.status === "online") {
          statusHost.classList.add("text-bg-success");
        } else if (payload.status === "offline") {
          statusHost.classList.add("text-bg-danger");
        } else {
          statusHost.classList.add("text-bg-secondary");
        }
      }
      const panel = document.querySelector(".device-object.panel");
      if (panel && payload.status) {
        panel.classList.remove("online", "offline", "unknown");
        panel.classList.add(payload.status);
      }
      button.title = payload.changed ? "Статус изменился" : "Статус без изменений";
    } catch (err) {
      button.title = err.message || "Ping не удался";
    } finally {
      button.disabled = false;
      button.classList.remove("is-busy");
    }
  }

  buttons.forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      runPing(button);
    });
  });
})();
