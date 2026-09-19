/* Вход и регистрация. Одна логика на оба кабинета.

   Кому предназначена страница, определяет её собственный атрибут
   data-audience, а не переключатель внутри формы: раньше тумблер роли
   стоял прямо в форме, и по экрану нельзя было понять, кабинет это
   для ресторана или для гостя.

   ВАЖНО: страница влияет только на оформление и на роль при РЕГИСТРАЦИИ.
   При входе роль всегда определяет сервер по учётной записи — открыв
   кабинет заведения, гость всё равно попадёт в гостевой. Адрес страницы
   правами не управляет и управлять не должен. */

(function () {
  const AUDIENCE = document.body.dataset.audience === "partner" ? "partner" : "guest";
  const API = "/api/auth";
  const $ = (id) => document.getElementById(id);

  const params = new URLSearchParams(location.search);
  const refId = +(params.get("ref") || 0);
  // Куда вернуть после входа, если гость пришёл с конкретной страницы.
  const next = params.get("next") || "";

  const CABINET = { guest: "/guest.html", partner: "/tihiy-chas-cabinet.html" };
  const TITLES = {
    guest: { login: "Кабинет гостя", register: "Регистрация гостя" },
    partner: { login: "Кабинет заведения", register: "Подключить заведение" },
  };

  let mode = refId ? "register" : "login";

  function render() {
    const isReg = mode === "register";
    document.querySelectorAll(".tab").forEach((t) =>
      t.classList.toggle("active", t.dataset.mode === mode));
    ["nameField", "phoneField", "consentField"].forEach((id) =>
      $(id).classList.toggle("show", isReg));
    // Подсказка про модерацию есть только на партнёрской странице.
    const hint = $("orgHint");
    if (hint) hint.classList.toggle("show", isReg);
    $("password").autocomplete = isReg ? "new-password" : "current-password";
    $("submit").textContent = isReg
      ? (AUDIENCE === "partner" ? "Подключить заведение" : "Создать аккаунт")
      : "Войти";
    $("title").textContent = TITLES[AUDIENCE][mode];
    $("msg").textContent = "";
    $("msg").className = "msg";
  }

  document.querySelectorAll(".tab").forEach((t) => {
    t.onclick = () => { mode = t.dataset.mode; render(); };
  });
  render();

  function say(text, ok) {
    const box = $("msg");
    box.textContent = text;
    box.className = "msg " + (ok ? "ok" : "err");
  }

  $("form").onsubmit = async (e) => {
    e.preventDefault();
    say("", true);
    const email = $("email").value.trim();
    const password = $("password").value;

    if (mode === "register" && !$("consent").checked) {
      say("Нужно принять условия, чтобы продолжить");
      return;
    }

    $("submit").disabled = true;
    try {
      const url = `${API}/${mode === "register" ? "register" : "login"}`;
      const body = mode === "register"
        ? {
            email, password,
            name: $("name").value.trim(),
            phone: $("phone").value.trim(),
            // Роль при регистрации задаёт страница. При входе не шлём её вовсе:
            // там решает сервер.
            role: AUDIENCE,
            consent: $("consent").checked,
            ref: refId,
          }
        : { email, password };

      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        say(data.detail || "Не получилось, попробуйте ещё раз");
        return;
      }

      const role = (data.user && data.user.role) === "partner" ? "partner" : "guest";
      // Учётка может оказаться не той, что ждёт эта страница: гость открыл
      // вход для заведений или наоборот. Это не ошибка — просто говорим,
      // куда ведём, вместо молчаливого прыжка не туда, куда человек шёл.
      if (role !== AUDIENCE && mode === "login") {
        say(role === "guest"
          ? "Это гостевой аккаунт — открываем кабинет гостя."
          : "Это аккаунт заведения — открываем кабинет заведения.", true);
      } else {
        say("Готово, открываем кабинет…", true);
      }

      const dest = (next && next.startsWith("/") && !next.startsWith("//"))
        ? next : CABINET[role];
      setTimeout(() => { location.href = dest; }, role !== AUDIENCE ? 1200 : 500);
    } catch (err) {
      say("Сервер не отвечает, попробуйте позже");
    } finally {
      $("submit").disabled = false;
    }
  };
})();
