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
  let audio, soundBuffer, lastSound = 0;
  function prepareSound() {
    try {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) return;
      if (!audio) {
        audio = new Audio();
        soundBuffer = audio.createBuffer(1, Math.ceil(audio.sampleRate * .045), audio.sampleRate);
        const samples = soundBuffer.getChannelData(0);
        for (let i = 0; i < samples.length; i++) samples[i] = (Math.random() * 2 - 1) * (1 - i / samples.length);
      }
      if (audio.state === 'suspended') audio.resume().catch(() => {});
    } catch (_) { /* Sound is optional; registration always remains available. */ }
  }
  function zipSound() {
    if (!audio || audio.state !== 'running' || !soundBuffer || audio.currentTime - lastSound < .035) return;
    lastSound = audio.currentTime;
    const source = audio.createBufferSource();
    const filter = audio.createBiquadFilter();
    const gain = audio.createGain();
    source.buffer = soundBuffer;
    filter.type = 'bandpass';
    filter.frequency.value = 2400;
    filter.Q.value = .7;
    gain.gain.value = .13;
    source.connect(filter).connect(gain).connect(audio.destination);
    source.onended = () => { source.disconnect(); filter.disconnect(); gain.disconnect(); };
    source.start();
  }
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
    zip.classList.remove('is-dragging');
    zip.classList.add('is-opening');
    paint(1);
    timer = setTimeout(() => window.location.assign(zip.href), motion.matches ? 0 : 320);
  }
  zip.addEventListener('pointerdown', event => {
    if (opening || pointer !== null || !event.isPrimary || event.button !== 0 || event.ctrlKey || event.metaKey || !event.target.closest('.hp-zip-pull')) return;
    pointer = event.pointerId;
    prepareSound();
    startX = event.clientX;
    zip.focus({preventScroll: true});
    zip.setPointerCapture(pointer);
    zip.classList.add('is-dragging');
    paint(0);
  });
  zip.addEventListener('pointermove', event => {
    if (event.pointerId !== pointer) return;
    const previous = progress;
    paint((startX - event.clientX) / travel());
    if (Math.abs(progress - previous) > .004) zipSound();
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
