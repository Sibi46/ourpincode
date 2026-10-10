(() => {
  const categories = document.getElementById('id_categories');
  if (!categories) return;
  const fields = document.querySelectorAll('[data-teaching-field^="category_"]');
  const legacy = document.querySelector('[data-teaching-field="new_subjects"]');
  function update() {
    const selected = new Set(Array.from(categories.querySelectorAll('input:checked')).map(input => input.value));
    fields.forEach(field => {
      const active = selected.has(field.dataset.teachingField.slice(9));
      field.hidden = !active;
      field.querySelectorAll('input,button').forEach(input => { input.disabled = !active; });
      field.querySelectorAll('input').forEach(input => { input.placeholder = 'Enter a name'; });
      const add = field.querySelector('[data-add-subject]');
      if (add) { add.textContent = '+ Add name'; add.setAttribute('aria-label', 'Add name'); }
    });
    if (legacy) {
      const hasValues = Array.from(legacy.querySelectorAll('input')).some(input => input.value.trim());
      legacy.hidden = selected.size > 0 && !hasValues;
    }
  }
  categories.addEventListener('change', update);
  update();
})();
