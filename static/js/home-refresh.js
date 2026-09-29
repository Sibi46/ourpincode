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

(() => {
  const zip = document.querySelector('[data-promo-zip]');
  if (!zip) return;
  const pull = zip.querySelector('.hp-zip-pull');
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let pointer = null, startX = 0, progress = 0, opening = false, timer;
  const travel = () => Math.max(1, zip.clientWidth - pull.offsetWidth);
  function paint(value) {
    progress = Math.max(0, Math.min(1, value));
    zip.style.setProperty('--zip-progress', progress);
    zip.style.setProperty('--zip-travel', `${progress * travel()}px`);
  }
  function reset() {
    clearTimeout(timer);
    pointer = null;
    opening = false;
    zip.classList.remove('is-dragging', 'is-opening');
    paint(0);
  }
  function openRegistration() {
    if (opening) return;
    opening = true;
    paint(1);
    zip.classList.remove('is-dragging');
    zip.classList.add('is-opening');
    timer = setTimeout(() => window.location.assign(zip.href), motion.matches ? 0 : 180);
  }
  zip.addEventListener('pointerdown', event => {
    if (opening || pointer !== null || !event.isPrimary || event.button !== 0 || event.ctrlKey || event.metaKey || !event.target.closest('.hp-zip-pull')) return;
    pointer = event.pointerId;
    startX = event.clientX;
    zip.focus({preventScroll: true});
    zip.setPointerCapture(pointer);
    zip.classList.add('is-dragging');
    paint(0);
  });
  zip.addEventListener('pointermove', event => {
    if (event.pointerId !== pointer) return;
    paint((startX - event.clientX) / travel());
  });
  zip.addEventListener('pointerup', event => {
    if (event.pointerId !== pointer) return;
    paint((startX - event.clientX) / travel());
    const complete = progress >= 0.88;
    pointer = null;
    zip.releasePointerCapture(event.pointerId);
    if (complete) openRegistration();
    else reset();
  });
  zip.addEventListener('pointercancel', reset);
  zip.addEventListener('lostpointercapture', () => { if (pointer !== null) reset(); });
  zip.addEventListener('dragstart', event => event.preventDefault());
  zip.addEventListener('click', event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    // Enter / assistive-technology activation remains a normal accessible link.
    if (event.detail === 0) openRegistration();
  });
  zip.addEventListener('keydown', event => {
    if (event.key === 'Escape') reset();
  });
  window.addEventListener('pageshow', reset);
  window.addEventListener('resize', () => { if (!opening) reset(); });
})();
