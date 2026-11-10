(() => {
  function start() {
    document.querySelectorAll('[data-person-name],[data-profile-name]').forEach(input => {
      const validate = () => input.setCustomValidity(input.value && !/^[\p{L}\p{M} ]+$/u.test(input.value)
        ? 'Use letters and spaces only.' : '');
      const hint = document.createElement('small');
      hint.setAttribute('role', 'status');
      hint.style.cssText = 'display:block;color:#b42318;margin-top:6px';
      input.insertAdjacentElement('afterend', hint);
      input.addEventListener('input', () => {
        const original = input.value;
        const position = input.selectionStart;
        const clean = value => value.replace(/[^\p{L}\p{M} ]/gu, '');
        input.value = clean(original);
        if (position !== null) input.setSelectionRange(clean(original.slice(0, position)).length, clean(original.slice(0, position)).length);
        hint.textContent = original !== input.value ? 'Use letters and spaces only. Invalid characters were removed.' : '';
        validate();
      });
      validate();
    });
    const description = document.querySelector('textarea[name="description"][maxlength="500"]');
    const chars = document.getElementById('descCharValue');
    const words = document.getElementById('descWordCount');
    if (description && chars && words) {
      const update = () => {
        chars.textContent = description.value.length;
        words.textContent = description.value.trim() ? description.value.trim().split(/\s+/u).length : 0;
      };
      description.addEventListener('input', update);
      description.addEventListener('change', update);
      window.addEventListener('pageshow', update);
      update();
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
