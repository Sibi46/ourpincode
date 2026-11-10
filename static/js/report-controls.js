(() => {
  function start() {
    document.querySelectorAll('[data-address-text]').forEach(field => {
      field.addEventListener('input', () => field.setCustomValidity(field.value && !/\p{L}/u.test(field.value)
        ? 'Enter an address with a street, area or locality name.' : ''));
    });
    document.querySelectorAll('[data-word-limit]').forEach(field => {
      field.addEventListener('input', () => {
        const limit = Number(field.dataset.wordLimit);
        const words = field.value.match(/\S+/gu) || [];
        if (words.length > limit) field.value = words.slice(0, limit).join(' ');
        const counter = document.getElementById('desc-counter');
        if (counter) counter.textContent = Math.min(words.length, limit) + ' / ' + limit + ' words';
      });
    });
    document.querySelectorAll('[data-digits-only]').forEach(field => {
      field.addEventListener('input', () => { field.value = field.value.replace(/[^0-9]/g, '').slice(0, field.maxLength > 0 ? field.maxLength : undefined); });
    });
    document.querySelectorAll('[data-four-digit-year]').forEach(field => {
      const hint = document.createElement('small');
      hint.setAttribute('role', 'status');
      hint.style.color = '#b42318';
      field.insertAdjacentElement('afterend', hint);
      field.addEventListener('input', () => {
        const invalid = field.value && !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(field.value);
        if (invalid) field.value = '';
        const message = invalid || field.validity.badInput ? 'Enter a valid date with a four-digit year.' : '';
        hint.textContent = message;
        field.setCustomValidity(message);
      });
    });
    document.querySelectorAll('[data-password-toggle]').forEach(field => {
      const wrapper = document.createElement('div');
      wrapper.style.cssText = 'position:relative;width:100%;min-width:0';
      field.before(wrapper);
      wrapper.append(field);
      field.style.paddingRight = '48px';
      const button = document.createElement('button');
      button.type = 'button';
      button.setAttribute('aria-label', 'Show password');
      button.setAttribute('aria-pressed', 'false');
      button.style.cssText = 'position:absolute;right:4px;top:50%;transform:translateY(-50%);width:40px;height:40px;border:0;background:transparent;color:#475569;cursor:pointer;display:grid;place-items:center';
      button.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
      button.addEventListener('click', () => {
        const visible = field.type === 'password';
        field.type = visible ? 'text' : 'password';
        button.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
        button.setAttribute('aria-pressed', String(visible));
      });
      wrapper.append(button);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
