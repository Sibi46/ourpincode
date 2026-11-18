(() => {
  const kind = document.querySelector('[name="kind"]');
  const section = document.querySelector('[data-academy-timings]');
  if (!kind || !section) return;
  function update() {
    section.hidden = false;
    section.querySelectorAll('input').forEach(input => {
      input.disabled = false;
      input.required = kind.value === 'academy' && input.type === 'time';
    });
  }
  kind.addEventListener('change', update); update();
})();
