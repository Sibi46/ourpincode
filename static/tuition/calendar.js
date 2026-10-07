(() => {
  function showDay() {
    const link = document.querySelector('.calendar-day.today') || document.querySelector('.calendar-day');
    const id = location.hash.slice(1) || (link ? link.hash.slice(1) : '');
    if (!/^day-\d{4}-\d{2}-\d{2}$/.test(id)) return;
    const day = document.getElementById(id);
    if (day) {
      document.querySelectorAll('.calendar-detail').forEach(item => { item.hidden = item !== day; });
      day.open = true;
      if (location.hash) day.scrollIntoView({block:'start'});
    }
  }
  document.querySelectorAll('.calendar-day').forEach(link => link.addEventListener('click', () => requestAnimationFrame(showDay)));
  window.addEventListener('hashchange', showDay); showDay();
})();
