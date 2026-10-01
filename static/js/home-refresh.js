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
  let index = 0, changing = false;
  // Each new message starts on a two-second cadence, including its animation.
  setInterval(async () => {
    if (changing || document.hidden || motion.matches || banner.contains(document.activeElement)) return;
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
  }, 2000);
})();

// Rotate decorative product categories independently of the promotional links.
(() => {
  const banner = document.querySelector('.hp-promo-shopping');
  if (!banner) return;
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const groups = [...banner.querySelectorAll('.hp-promo-art')].map(element => ({
    images: [...element.querySelectorAll('img')], index: 0
  }));
  let changing = false;
  setInterval(async () => {
    if (changing || document.hidden || motion.matches || banner.contains(document.activeElement)) return;
    changing = true;
    try {
      await Promise.all(groups.map(async group => {
        const nextIndex = (group.index + 1) % group.images.length;
        const next = group.images[nextIndex];
        if (!next || !next.complete || !next.naturalWidth) return;
        const current = group.images[group.index];
        await current.animate([{opacity: 1, transform: 'translateY(0)'}, {opacity: 0, transform: 'translateY(-8px)'}], {duration: 220}).finished;
        current.hidden = true;
        next.hidden = false;
        group.index = nextIndex;
        await next.animate([{opacity: 0, transform: 'translateY(8px)'}, {opacity: 1, transform: 'translateY(0)'}], {duration: 350, easing: 'ease-out'}).finished;
      }));
    } catch (_) {
      // A cancelled animation must not stop subsequent category rotations.
    } finally {
      changing = false;
    }
  }, 3200);
})();
