(() => {
  const form = document.getElementById('group-form');
  if (!form) return;
  const modeField = form.querySelector('[name="mode"]');
  function updateSlots() {
    form.querySelectorAll('[data-day]').forEach(row => {
      const checked = row.querySelector('[name="weekdays"]').checked;
      row.querySelector('.day-times').hidden = !checked;
      row.querySelectorAll('input[type="time"]').forEach(input => {
        input.disabled = !checked; input.required = false;
      });
      row.querySelectorAll('.remove-slot').forEach(button => {
        button.hidden = row.querySelectorAll('.time-slot').length === 1;
      });
    });
  }
  form.addEventListener('click', event => {
    const row = event.target.closest('[data-day]');
    if (!row) return;
    if (event.target.closest('.add-slot')) {
      row.querySelector('[name="weekdays"]').checked = true;
      const slots = row.querySelector('.day-times');
      if (slots.children.length < 24) {
        const slot = slots.firstElementChild.cloneNode(true);
        slot.querySelector('input').value = '';
        slots.appendChild(slot);
        updateSlots(); slot.querySelector('input').focus();
      }
    } else if (event.target.closest('.remove-slot') && row.querySelectorAll('.time-slot').length > 1) {
      event.target.closest('.time-slot').remove();
    }
    updateSlots();
  });

  function updateMode() {
    if (!modeField) return;
    const mode = modeField.value;
    for(const name of ['meeting_url', 'location']) {
      const show = name === 'meeting_url' ? ['online','hybrid'].includes(mode) : ['offline','hybrid'].includes(mode);
      const field = form.querySelector('[name="'+name+'"]');
      const wrapper = form.querySelector('[data-field="'+name+'"]');
      if (!field || !wrapper) continue;
      wrapper.hidden = !show;
      field.disabled = !show; field.required = show;
    }
  }
  form.querySelectorAll('[name="weekdays"]').forEach(el => el.addEventListener('input', updateSlots));
  if (modeField) modeField.addEventListener('change',updateMode);
  updateSlots(); updateMode();
})();
