(function () {
  'use strict';
  const form = document.getElementById('dashboard-profile-form');
  if (!form) return;
  form.querySelectorAll('[data-profile-name],[data-profile-text]').forEach(field => {
    function validate() {
      const invalid = field.hasAttribute('data-profile-name')
        ? field.value && !/^[\p{L}\p{M} ]+$/u.test(field.value)
        : /\p{N}/u.test(field.value);
      field.setCustomValidity(invalid ? 'Use text without numbers.' : '');
    }
    field.addEventListener('input', validate);
    validate();
  });
  const category = form.elements.job_category;
  const types = form.elements.blue_collar_type;
  if (!category || !types) return;
  const options = JSON.parse(types.dataset.jobTypes);
  function updateTypes(changed) {
    const old = changed ? '' : types.value;
    types.replaceChildren(new Option('Select a job type', ''));
    (options[category.value] || []).forEach(([value, label]) => types.add(new Option(label, value)));
    types.value = old;
    types.disabled = category.value === 'any';
  }
  category.addEventListener('change', () => updateTypes(true));
  updateTypes(false);
})();
