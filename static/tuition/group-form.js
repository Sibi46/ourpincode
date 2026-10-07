(() => {
  const form = document.getElementById('group-form');
  if (!form) return;
  const start = form.querySelector('[name="start_date"]'), end = form.querySelector('[name="end_date"]');
  function updateDates() {
    form.querySelectorAll('[data-weekday]').forEach(el => {
      const checked = form.querySelector('[name="weekdays"][value="'+el.dataset.weekday+'"]').checked;
      el.disabled = !checked; el.required = checked;
      el.min = start.value; el.max = end.value;
      if (checked && !el.value && start.value && end.value) {
        const day = new Date(start.value + 'T00:00:00Z');
        day.setUTCDate(day.getUTCDate() + (Number(el.dataset.weekday) - (day.getUTCDay()+6)%7 + 7)%7);
        if(day <= new Date(end.value+'T00:00:00Z')) el.value = day.toISOString().slice(0,10);
      }
      const selectedDay = el.value ? (new Date(el.value+'T00:00:00Z').getUTCDay()+6)%7 : null;
      el.setCustomValidity(checked && el.value && selectedDay !== Number(el.dataset.weekday) ? 'Choose a date matching this weekday.' : '');
    });
  }
  form.querySelectorAll('[name="weekdays"],[data-weekday]').forEach(el => el.addEventListener('change', updateDates));
  start.addEventListener('input', updateDates); end.addEventListener('input', updateDates); updateDates();
})();
