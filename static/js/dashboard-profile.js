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
    const hint = document.createElement('small');
    hint.setAttribute('role', 'status');
    hint.style.cssText = 'display:block;color:#b42318;margin-top:6px';
    field.insertAdjacentElement('afterend', hint);
    field.addEventListener('input', () => {
      const original = field.value;
      const position = field.selectionStart;
      const remove = field.hasAttribute('data-profile-name') ? /[^\p{L}\p{M} ]/gu : /\p{N}/gu;
      const before = original.slice(0, position).replace(remove, '');
      field.value = original.replace(remove, '');
      if (position !== null) field.setSelectionRange(before.length, before.length);
      hint.textContent = original !== field.value ? 'Use letters without numbers. Invalid characters were removed.' : '';
      validate();
    });
    validate();
  });
  const category = form.elements.job_category;
  const types = form.elements.blue_collar_type;
  if (!category || !types) return;
  const options = JSON.parse(types.dataset.jobTypes);
  function updateTypes(changed) {
    const old = changed ? '' : types.value;
    types.replaceChildren(new Option('Select a job type', ''));
    const available = category.value === 'any'
      ? [...new Map(options.blue.concat(options.white)).entries()]
      : options[category.value] || [];
    available.forEach(([value, label]) => types.add(new Option(label, value)));
    types.value = old;
    types.disabled = false;
  }
  category.addEventListener('change', () => updateTypes(true));
  updateTypes(false);
})();
