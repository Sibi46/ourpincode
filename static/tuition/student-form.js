(() => {
  const form = document.getElementById('student-form');
  if (!form) return;
  const dob = form.querySelector('[name="dob"]'), age = form.querySelector('[name="age"]');
  const today = form.dataset.today.split('-').map(Number);
  function updateAge() {
    age.readOnly = !!dob.value;
    if (!dob.value) return;
    const birth = dob.value.split('-').map(Number);
    const years = today[0] - birth[0] - (today[1] < birth[1] || (today[1] === birth[1] && today[2] < birth[2]) ? 1 : 0);
    age.value = years >= 0 && years <= 120 ? years : '';
  }
  dob.addEventListener('input', updateAge); updateAge();
})();
