(() => {
  const dialog = document.getElementById('home-explore');
  if (!dialog) return;
  document.querySelectorAll('[data-explore-open]').forEach(button => {
    button.addEventListener('click', event => {
      event.preventDefault();
      dialog.showModal();
    });
  });
  dialog.querySelector('[data-explore-close]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
})();

(() => {
  const banner = document.querySelector('.hp-promo');
  if (!banner) return;
  const slides = [...banner.querySelectorAll('[data-promo-slide]')];
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (slides.length < 2) return;
  let index = 0, changing = false, paused = false;
  const pause = banner.querySelector('[data-promo-pause]');
  pause.addEventListener('click', () => {
    paused = !paused;
    pause.textContent = paused ? 'Play' : 'Pause';
    pause.setAttribute('aria-label', paused ? 'Play promotions' : 'Pause promotions');
    pause.setAttribute('aria-pressed', String(paused));
  });
  banner.querySelector('[data-promo-next]').addEventListener('click', () => advance());
  async function advance() {
    if (changing) return;
    if (motion.matches) {
      slides[index].hidden = true;
      index = (index + 1) % slides.length;
      slides[index].hidden = false;
      return;
    }
    changing = true;
    const outgoing = slides[index];
    try {
      await outgoing.animate([
        {transform: 'translateX(0)', opacity: 1},
        {transform: 'translateX(110%)', opacity: 0}
      ], {duration: 250, easing: 'ease-in', fill: 'forwards'}).finished;
      outgoing.hidden = true;
      outgoing.getAnimations().forEach(animation => animation.cancel());
      index = (index + 1) % slides.length;
      const incoming = slides[index];
      incoming.hidden = false;
      await incoming.animate([
        {transform: 'translateY(100%)', opacity: 0},
        {transform: 'translateY(0)', opacity: 1}
      ], {duration: 350, easing: 'ease-out'}).finished;
    } finally {
      changing = false;
    }
  }
  setInterval(() => {
    if (paused || document.hidden || motion.matches || banner.contains(document.activeElement) || banner.matches(':hover')) return;
    advance();
  }, 4000);
})();
