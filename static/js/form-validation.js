(() => {
  function start() {
    document.querySelectorAll('[data-digits-only]').forEach(input => {
      input.addEventListener('input', () => { input.value = input.value.replace(/[^0-9]/g, ''); });
    });
    document.querySelectorAll('[data-no-digits]').forEach(input => {
      const validate = () => input.setCustomValidity(/\p{N}/u.test(input.value) ? 'Numbers are not allowed in this field.' : '');
      input.addEventListener('input', validate);
      validate();
    });
    const category = document.querySelector('[data-job-category]');
    const jobType = document.querySelector('[data-job-type]');
    if (category && jobType) {
      const blue = JSON.parse(document.getElementById('profile-blue-types').textContent);
      const white = JSON.parse(document.getElementById('profile-white-types').textContent);
      const updateTypes = () => {
        const previous = jobType.value;
        const options = category.value === 'white' ? white : category.value === 'blue' ? blue : blue.concat(white);
        jobType.replaceChildren(new Option('Choose a job type', ''));
        options.forEach(([value, label]) => jobType.add(new Option(label, value)));
        if (options.some(([value]) => value === previous)) jobType.value = previous;
      };
      category.addEventListener('change', updateTypes);
    }
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
