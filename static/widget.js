(() => {
  if (document.getElementById("da-rag-widget")) return;
  const origin = new URL(document.currentScript.src).origin;
  const host = document.createElement("div");
  host.id = "da-rag-widget";
  const shadow = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = `
    :host { position: fixed; right: 18px; bottom: 18px; z-index: 2147483000; font-family: system-ui, sans-serif; }
    button { display: block; margin-left: auto; border: 0; border-radius: 999px; padding: 13px 17px; background: #1c5548; color: white; box-shadow: 0 8px 28px #102c3240; font: 700 14px system-ui, sans-serif; cursor: pointer; }
    button:hover { background: #174638; }
    iframe { display: none; width: min(390px, calc(100vw - 28px)); height: min(650px, calc(100dvh - 92px)); margin-bottom: 12px; border: 1px solid #c7d8d0; border-radius: 18px; background: white; box-shadow: 0 16px 60px #102c3240; }
    :host([open]) iframe { display: block; }
    @media (max-width: 480px) { :host { right: 14px; bottom: 14px; } iframe { height: calc(100dvh - 90px); } }
  `;
  const frame = document.createElement("iframe");
  frame.title = "Assistente de estudos da disciplina Disruptive Architectures";
  frame.loading = "lazy";
  frame.src = `${origin}/?embed=1`;
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "✦ Pergunte à disciplina";
  button.setAttribute("aria-expanded", "false");
  button.addEventListener("click", () => {
    const open = host.toggleAttribute("open");
    button.setAttribute("aria-expanded", String(open));
    button.textContent = open ? "Fechar chat" : "✦ Pergunte à disciplina";
  });
  shadow.append(style, frame, button);
  document.body.append(host);
})();
