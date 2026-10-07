(() => {
  const form = document.getElementById('group-form');
  if (!form) return;
  const start = form.querySelector('[name="start_date"]'), end = form.querySelector('[name="end_date"]');
  function updateDates() {
    form.querySelectorAll('[data-weekday]').forEach(el => {
      if (!start.value || !end.value) { el.textContent = 'Choose dates above'; return; }
      const day = new Date(start.value + 'T00:00:00Z');
      const weekday = (day.getUTCDay() + 6) % 7;
      day.setUTCDate(day.getUTCDate() + (Number(el.dataset.weekday) - weekday + 7) % 7);
      el.textContent = day > new Date(end.value + 'T00:00:00Z') ? 'Outside selected dates' : day.toLocaleDateString('en-IN', {day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'});
    });
  }
  start.addEventListener('input', updateDates); end.addEventListener('input', updateDates); updateDates();
})();
