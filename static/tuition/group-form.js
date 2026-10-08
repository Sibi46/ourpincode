(() => {
  const form = document.getElementById('group-form');
  if (!form) return;
  function updateSlots() {
    form.querySelectorAll('[data-day]').forEach(row => {
      const checked = row.querySelector('[name="weekdays"]').checked;
      row.querySelectorAll('input[type="time"]').forEach(input => {
        input.disabled = !checked; input.required = checked;
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
    const mode = form.querySelector('[name="mode"]').value;
    for(const name of ['meeting_url', 'location']) {
      const show = name === 'meeting_url' ? ['online','hybrid'].includes(mode) : ['offline','hybrid'].includes(mode);
      const field = form.querySelector('[name="'+name+'"]');
      form.querySelector('[data-field="'+name+'"]').hidden = !show;
      field.disabled = !show; field.required = show;
    }
  }
  form.querySelectorAll('[name="weekdays"]').forEach(el => el.addEventListener('input', updateSlots));
  form.querySelector('[name="mode"]').addEventListener('change',updateMode);
  updateSlots(); updateMode();
})();
