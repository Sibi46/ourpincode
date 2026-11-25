/* Dismiss server-rendered notifications with a horizontal swipe. */
(() => {
  let gesture = null;
  document.addEventListener('pointerdown', event => {
    const toast = event.target.closest('.toast');
    if (!toast || event.target.closest('button,a,input,select,textarea')) return;
    if (event.pointerType === 'mouse') event.preventDefault();
    toast.setPointerCapture(event.pointerId);
    gesture = {toast, id: event.pointerId, x: event.clientX, y: event.clientY};
  });
  document.addEventListener('pointerup', event => {
    if (!gesture || event.pointerId !== gesture.id) return;
    const {toast, x, y} = gesture;
    gesture = null;
    const dx = event.clientX - x;
    const dy = event.clientY - y;
    if (Math.abs(dx) >= 60 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      toast.remove();
    }
  });
  document.addEventListener('pointercancel', () => { gesture = null; });
})();
