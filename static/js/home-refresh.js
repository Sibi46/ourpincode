(() => {
  const dialog = document.getElementById('home-explore');
  if (!dialog) return;
  document.querySelectorAll('[data-explore-open]').forEach(button => {
    button.addEventListener('click', event => {
      event.preventDefault();
      dialog.showModal();
    });
  });
  dialog.querySelector('[data-explore-close]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
})();
