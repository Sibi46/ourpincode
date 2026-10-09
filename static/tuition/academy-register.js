(() => {
  const kind = document.querySelector('[name="kind"]');
  const section = document.querySelector('[data-academy-timings]');
  if(!kind || !section) return;
  function update() {
    section.hidden = kind.value !== 'academy';
    section.querySelectorAll('input').forEach(input => { input.disabled = section.hidden; input.required = !section.hidden && input.type === 'time'; });
  }
  kind.addEventListener('change', update); update();
})();
