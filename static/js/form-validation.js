(() => {
  function start() {
    document.querySelectorAll('[data-person-name]').forEach(input => {
      const validate = () => input.setCustomValidity(input.value && !/^[\p{L}\p{M} ]+$/u.test(input.value)
        ? 'Use letters and spaces only.' : '');
      input.addEventListener('input', validate);
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
