// Витрина Polka: каталог, корзина и события для GTM.
// События в dataLayer: add_to_cart, form_submit, scroll_50, click_phone.

(function () {
  const cfg = window.TQL_CONFIG || {};
  window.dataLayer = window.dataLayer || [];

  // --- GTM ---------------------------------------------------------------
  if (cfg.gtmId && !cfg.gtmId.includes("XXXX")) {
    window.dataLayer.push({ "gtm.start": Date.now(), event: "gtm.js" });
    const s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtm.js?id=" + cfg.gtmId;
    document.head.appendChild(s);
  }

  function track(event, params) {
    const payload = Object.assign({ event: event }, params || {});
    window.dataLayer.push(payload);
    console.info("[dataLayer]", payload);
  }

  // --- Каталог -----------------------------------------------------------
  const PRODUCTS = [
    { id: "p1", name: "Плед «Туман»", price: 4900, tone: "#9DB4AB" },
    { id: "p2", name: "Подушка «Мох»", price: 1900, tone: "#6F8F72" },
    { id: "p3", name: "Скатерть «Лён»", price: 3200, tone: "#D9CBB3" },
    { id: "p4", name: "Покрывало «Глина»", price: 6400, tone: "#B9785B" },
    { id: "p5", name: "Полотенце «Соль»", price: 1200, tone: "#E8E4DC" },
    { id: "p6", name: "Плед «Ночь»", price: 5200, tone: "#3F4A5A" },
  ];
  const rub = (n) => n.toLocaleString("ru-RU") + " ₽";
  const byId = (id) => PRODUCTS.find((p) => p.id === id);

  // --- Корзина в localStorage --------------------------------------------
  const CART_KEY = "polka_cart";
  function readCart() {
    try { return JSON.parse(localStorage.getItem(CART_KEY)) || []; } catch (e) { return []; }
  }
  function writeCart(items) {
    try { localStorage.setItem(CART_KEY, JSON.stringify(items)); } catch (e) { /* приватный режим */ }
    renderCartBadge();
  }
  function addToCart(id) {
    const items = readCart();
    items.push(id);
    writeCart(items);
    const p = byId(id);
    track("add_to_cart", { product_id: id, product_name: p.name, value: p.price });
    toast("Добавлено в корзину: " + p.name);
  }
  function renderCartBadge() {
    document.querySelectorAll("[data-cart-count]").forEach((el) => {
      el.textContent = readCart().length;
    });
  }

  function toast(text) {
    let el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.classList.add("show");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove("show"), 1800);
  }

  // --- Рендер страниц ----------------------------------------------------
  function productCard(p) {
    return `
      <article class="card" data-product="${p.id}">
        <a href="product.html?id=${p.id}" class="card-media" style="--tone:${p.tone}" aria-label="${p.name}"></a>
        <div class="card-body">
          <a href="product.html?id=${p.id}" class="card-title">${p.name}</a>
          <div class="card-row">
            <span class="price">${rub(p.price)}</span>
            <button class="btn btn-small" data-add="${p.id}">В корзину</button>
          </div>
        </div>
      </article>`;
  }

  function renderCatalog() {
    const grid = document.querySelector("[data-catalog]");
    if (grid) grid.innerHTML = PRODUCTS.map(productCard).join("");
  }

  function renderProduct() {
    const box = document.querySelector("[data-product-page]");
    if (!box) return;
    const id = new URLSearchParams(location.search).get("id") || "p1";
    const p = byId(id) || PRODUCTS[0];
    document.title = p.name + " — Polka";
    box.innerHTML = `
      <div class="product-media" style="--tone:${p.tone}"></div>
      <div class="product-info">
        <p class="eyebrow">Домашний текстиль</p>
        <h1>${p.name}</h1>
        <p class="lead">Плотный лён и хлопок, мягкая стирка, шьём небольшими партиями.</p>
        <p class="price price-big">${rub(p.price)}</p>
        <button class="btn" data-add="${p.id}">Добавить в корзину</button>
      </div>`;
  }

  function renderCart() {
    const box = document.querySelector("[data-cart]");
    if (!box) return;
    const items = readCart().map(byId).filter(Boolean);
    if (!items.length) {
      box.innerHTML = `<p class="muted">Корзина пуста. <a href="index.html#catalog">Перейти в каталог</a></p>`;
      return;
    }
    const total = items.reduce((s, p) => s + p.price, 0);
    box.innerHTML = `
      <ul class="cart-list">${items.map((p) => `<li><span>${p.name}</span><span>${rub(p.price)}</span></li>`).join("")}</ul>
      <div class="cart-total"><span>Итого</span><strong>${rub(total)}</strong></div>
      <a class="btn" href="contact.html">Оформить заявку</a>
      <button class="btn btn-ghost" data-clear>Очистить</button>`;
  }

  // --- События -----------------------------------------------------------
  document.addEventListener("click", (e) => {
    const add = e.target.closest("[data-add]");
    if (add) {
      e.preventDefault();
      addToCart(add.dataset.add);
    }
    const phone = e.target.closest("[data-phone]");
    if (phone) track("click_phone", { location: phone.dataset.phone });
    if (e.target.closest("[data-clear]")) {
      writeCart([]);
      renderCart();
    }
  });

  // scroll_50 — один раз за страницу
  let scrolled = false;
  window.addEventListener("scroll", () => {
    if (scrolled) return;
    const doc = document.documentElement;
    const depth = (window.scrollY + window.innerHeight) / doc.scrollHeight;
    if (depth >= 0.5) {
      scrolled = true;
      track("scroll_50", { page: location.pathname });
    }
  }, { passive: true });

  // form_submit — заявка никуда не отправляется, только событие
  document.addEventListener("submit", (e) => {
    const form = e.target.closest("[data-lead-form]");
    if (!form) return;
    e.preventDefault();
    track("form_submit", { form: "lead", items_in_cart: readCart().length });
    form.reset();
    const ok = document.querySelector("[data-form-ok]");
    if (ok) ok.hidden = false;
  });

  document.querySelectorAll("[data-phone-text]").forEach((el) => {
    el.textContent = cfg.phone || "";
    el.href = "tel:" + (cfg.phone || "").replace(/[^+\d]/g, "");
  });

  renderCatalog();
  renderProduct();
  renderCart();
  renderCartBadge();
})();
