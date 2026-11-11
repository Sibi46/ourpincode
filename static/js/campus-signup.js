(function () {
  'use strict';
  document.querySelectorAll('input[type="password"]').forEach((input, index) => {
    if (input.closest('.campus-password')) return;
    if (!input.id) input.id = 'campus-password-' + index;
    const wrapper = document.createElement('div');
    wrapper.className = 'campus-password';
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'campus-password-toggle';
    button.setAttribute('aria-controls', input.id);
    button.setAttribute('aria-label', 'Show password');
    button.setAttribute('aria-pressed', 'false');
    button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/><path class="eye-slash" d="m3 3 18 18"/></svg>';
    button.addEventListener('click', () => {
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.setAttribute('aria-pressed', String(show));
      button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    });
    wrapper.appendChild(button);
  });
})();
