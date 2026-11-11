(function () {
  'use strict';
  const form = document.getElementById('dashboard-profile-form');
  if (!form) return;
  const status = document.getElementById('profile-save-status');
  if (status) form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    if (button.disabled) return;
    const data = new FormData(form);
    button.disabled = true;
    status.style.color = '#344054';
    status.textContent = 'Saving profile...';
    try {
      const response = await fetch(form.action, {
        method: 'POST', body: data, credentials: 'same-origin',
        headers: {'X-Requested-With': 'XMLHttpRequest'}
      });
      if (response.redirected) {
        window.location.assign(response.url);
        return;
      }
      if (response.ok && (response.headers.get('Content-Type') || '').includes('application/json')) {
        const result = await response.json();
        status.style.color = '#166534';
        status.textContent = result.message;
      } else {
        const page = new DOMParser().parseFromString(await response.text(), 'text/html');
        const errors = page.querySelector('.account-errors');
        status.style.color = '#b42318';
        status.textContent = errors ? errors.textContent : 'Unable to save. Please check your details and try again.';
      }
    } catch (error) {
      status.style.color = '#b42318';
      status.textContent = 'Unable to connect. Please try saving again.';
    } finally {
      button.disabled = false;
    }
  });
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
