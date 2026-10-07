(() => {
  const form = document.getElementById('group-form');
  if (!form) return;
  function updateSlots() {
    form.querySelectorAll('[data-weekday]').forEach(el => {
      const checked = form.querySelector('[name="weekdays"][value="'+el.dataset.weekday+'"]').checked;
      el.disabled = !checked; el.required = checked;
      const start = form.querySelector('[name="day_start_'+el.dataset.weekday+'"]');
      el.setCustomValidity(checked && el.name.startsWith('day_end_') && start.value && el.value && el.value <= start.value ? 'End time must be after start time.' : '');
    });
  }
  function updateMode() {
    const mode = form.querySelector('[name="mode"]').value;
    for(const name of ['meeting_url', 'location']) {
      const show = name === 'meeting_url' ? ['online','hybrid'].includes(mode) : ['offline','hybrid'].includes(mode);
      const field = form.querySelector('[name="'+name+'"]');
      form.querySelector('[data-field="'+name+'"]').hidden = !show;
      field.disabled = !show; field.required = show;
    }
  }
  form.querySelectorAll('[name="weekdays"],[data-weekday]').forEach(el => el.addEventListener('input', updateSlots));
  form.querySelector('[name="mode"]').addEventListener('change',updateMode);
  updateSlots(); updateMode();
})();
