(() => {
  const dialog = document.getElementById('shopEntry');
  if (!dialog || typeof dialog.showModal !== 'function') return;
  const key = `shop-open:${dialog.dataset.shop}`;
  // Keep the shop open while the owner visits tools and returns in this tab.
  try { if (sessionStorage.getItem(key)) return; } catch (_) {}
  // Existing direct links and form submissions must reach their destination.
  if (location.search || location.hash) return;
  const doors = document.getElementById('shopDoors');
  let opening = false, lastTap = 0;
  function remember() { try { sessionStorage.setItem(key, '1'); } catch (_) {} }
  function open() {
    if (opening) return;
    opening = true;
    remember();
    dialog.classList.add('is-opening');
    setTimeout(() => {
      dialog.close();
      document.querySelector('#igTabs .ig-tab')?.focus({preventScroll: true});
    }, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 680);
  }
  doors.addEventListener('click', event => {
    if (event.detail === 0) { open(); return; }
    const now = performance.now();
    if (lastTap && now - lastTap < 450) open();
    lastTap = now;
  });
  doors.addEventListener('dblclick', open);
  document.getElementById('shopEntryOpen').addEventListener('click', open);
  dialog.addEventListener('cancel', remember);
  dialog.showModal();
})();
