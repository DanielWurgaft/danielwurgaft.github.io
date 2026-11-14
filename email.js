// Click the envelope: copy the address and show it, instead of opening a mail app.
(() => {
  const btn = document.getElementById("email");
  const pop = document.getElementById("email-pop");
  if (!btn || !pop) return;
  const addr = btn.dataset.email;
  let timer;

  btn.addEventListener("click", async () => {
    let copied = false;
    try { await navigator.clipboard.writeText(addr); copied = true; } catch {}
    pop.innerHTML = "";
    const a = document.createElement("span");
    a.className = "addr";
    a.textContent = addr;
    pop.append(a);
    if (copied) pop.append(" · copied");
    pop.classList.add("show");
    // Select the text too, so it is easy to copy by hand if the clipboard was blocked.
    const r = document.createRange(); r.selectNodeContents(a);
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
    clearTimeout(timer);
    timer = setTimeout(() => pop.classList.remove("show"), 4000);
  });

  document.addEventListener("click", e => {
    if (!e.target.closest(".email-wrap")) pop.classList.remove("show");
  });
})();
