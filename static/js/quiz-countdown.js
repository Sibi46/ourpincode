(() => {
  const timer = document.querySelector('[data-next-quiz-at]');
  if (!timer) return;
  const target = Date.parse(timer.dataset.nextQuizAt);
  const serverNow = Date.parse(timer.dataset.serverNow);
  if (!Number.isFinite(target) || !Number.isFinite(serverNow)) return;
  const offset = serverNow - Date.now();
  const status = document.getElementById('quiz-countdown-status');
  const start = document.getElementById('next-quiz-start');
  function update() {
    const seconds = Math.max(0, Math.ceil((target - (Date.now() + offset)) / 1000));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor(seconds % 3600 / 60);
    const rest = seconds % 60;
    timer.textContent = [hours, minutes, rest].map(value => String(value).padStart(2, '0')).join(':');
    if (seconds === 0) {
      status.textContent = 'Your next daily quiz is ready.';
      start.hidden = false;
    }
    return seconds;
  }
  if (update() > 0) {
    const interval = setInterval(() => { if (update() === 0) clearInterval(interval); }, 1000);
    document.addEventListener('visibilitychange', update);
  }
})();
