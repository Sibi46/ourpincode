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
  const self = form.querySelector('[name="self_registration"]');
  function guardianFields() {
    if (!self) return;
    for (const name of ['relationship', 'attestation']) {
      const field = form.querySelector('[name="'+name+'"]');
      if (!field) continue;
      field.required = !self.checked; field.disabled = self.checked;
      field.closest('[data-student-field]').hidden = self.checked;
    }
  }
  if(self) self.addEventListener('change', guardianFields);
  guardianFields();
  dob.addEventListener('input', updateAge); updateAge();
})();
