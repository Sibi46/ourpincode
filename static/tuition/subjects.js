document.querySelectorAll('[data-subject-inputs]').forEach(box => {
  box.addEventListener('click', event => {
    const rows = box.querySelectorAll('.subject-row');
    if (event.target.closest('[data-add-subject]') && rows.length < 10) {
      const row = rows[0].cloneNode(true); row.querySelector('input').value = '';
      box.insertBefore(row, box.querySelector('[data-add-subject]')); row.querySelector('input').focus();
    } else if(event.target.closest('[data-remove-subject]')) {
      const row = event.target.closest('.subject-row');
      if(rows.length > 1) row.remove(); else row.querySelector('input').value = '';
    }
  });
});
