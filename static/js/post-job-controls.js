(() => {
  function start() {
    const form = document.getElementById('jobForm');
    if (!form) return;
    const summary = document.createElement('p');
    summary.id = 'job-validation-error';
    summary.setAttribute('role', 'alert');
    summary.style.cssText = 'padding:14px;margin:12px 0;background:#fff0ee;color:#9a211d;border-radius:10px';
    summary.hidden = true;
    form.prepend(summary);
    let revealing = false, reporting = false;
    form.addEventListener('invalid', event => {
      if (reporting) return;
      event.preventDefault();
      if (revealing) return;
      revealing = true;
      const field = event.target;
      const panel = field.closest('.pj-step-panel');
      if (panel) goStep(Number(panel.id.replace('panel-', '')));
      if (field.id === 'salMin' || field.id === 'salMax') document.getElementById('salAmountRow').style.display = 'block';
      summary.textContent = field.validationMessage || 'Please correct the highlighted field.';
      summary.hidden = false;
      requestAnimationFrame(() => {
        field.focus();
        reporting = true;
        field.reportValidity();
        reporting = false;
        revealing = false;
      });
    }, true);
    form.addEventListener('input', event => {
      if (event.target.validity && event.target.validity.valid) summary.hidden = true;
    });
    const title = document.getElementById('f-title');
    const location = document.getElementById('f-location');
    const deadline = document.getElementById('f-deadline');
    const titleHint = document.createElement('small');
    titleHint.id = 'job-title-error';
    titleHint.setAttribute('role', 'status');
    titleHint.style.color = '#b42318';
    title.after(titleHint);
    title.setAttribute('aria-describedby', titleHint.id);
    function validateTitle() {
      const invalid = !!title.value && !/\p{L}/u.test(title.value);
      const message = invalid ? 'Enter a job title containing letters. Numbers alone are not a valid job title.' : '';
      title.setCustomValidity(message);
      title.setAttribute('aria-invalid', String(invalid));
      titleHint.textContent = message;
    }
    title.addEventListener('input', validateTitle);
    title.addEventListener('blur', validateTitle);
    const locationHint = document.createElement('small');
    locationHint.setAttribute('role', 'status');
    locationHint.style.color = '#b42318';
    location.after(locationHint);
    location.addEventListener('input', () => {
      const before = location.value;
      location.value = before.replace(/\p{N}/gu, '');
      locationHint.textContent = before !== location.value ? 'Use the area name without numbers.' : '';
      location.setCustomValidity(location.value && !/\p{L}/u.test(location.value) ? 'Enter a location name containing letters.' : '');
    });
    deadline.addEventListener('input', () => {
      const digits = deadline.value.replace(/[^0-9]/g, '').slice(0, 8);
      deadline.value = digits.slice(0, 2) + (digits.length > 2 ? '/' + digits.slice(2, 4) : '')
        + (digits.length > 4 ? '/' + digits.slice(4) : '');
      const [day, month, year] = deadline.value.split('/').map(Number);
      const parsed = new Date(0);
      parsed.setFullYear(year, month - 1, day);
      const valid = digits.length === 8 && year > 0 && parsed.getFullYear() === year
        && parsed.getMonth() === month - 1 && parsed.getDate() === day;
      deadline.setCustomValidity(!digits.length || valid ? '' : 'Enter a valid date as DD/MM/YYYY with a four-digit year.');
    });
    form.addEventListener('submit', event => {
      const description = document.getElementById('f-desc');
      const skills = document.getElementById('f-skills');
      const pin = document.getElementById('f-pincode');
      let invalid = null, step = 2;
      if (!/\p{L}/u.test(title.value)) invalid = title;
      else if ((description.value.match(/\S+/gu) || []).length > 150) {
        invalid = description; description.setCustomValidity('Keep the job description within 150 words.');
      } else if (deadline.value && !deadline.checkValidity()) { invalid = deadline; step = 3; }
      else if (skills.value.trim()) { invalid = skills; step = 3; skills.setCustomValidity('Click Add to save this skill.'); }
      else if (!/^[1-9][0-9]{5}$/.test(pin.value)) { invalid = pin; step = 4; }
      else if (!location.checkValidity()) { invalid = location; step = 4; }
      if (invalid) {
        event.preventDefault();
        goStep(step);
        invalid.focus(); invalid.reportValidity();
      }
    });
    document.getElementById('add-skill').addEventListener('click', () => document.getElementById('f-skills').setCustomValidity(''));
    document.getElementById('f-desc').addEventListener('input', () => document.getElementById('f-desc').setCustomValidity(''));
    const posted = document.getElementById('job-posted-data');
    if (posted) {
      const data = JSON.parse(posted.textContent);
      if (['blue', 'white'].includes(data.collar_type)) selectCollar(data.collar_type);
      (data.industry || '').split(',').map(value => value.trim()).filter(Boolean).forEach(value => {
        const chip = [...document.querySelectorAll('.ind-chip')].find(el => el.dataset.val.toLowerCase() === value.toLowerCase());
        if (chip && !chip.classList.contains('selected')) toggleIndustry(chip);
      });
      Object.entries(data).forEach(([name, value]) => {
        if (['csrfmiddlewaretoken', 'industry', 'skills', '_skills_display'].includes(name)) return;
        const field = form.elements.namedItem(name);
        if (field && field.tagName) {
          if (field.type === 'checkbox') field.checked = !!value;
          else field.value = value;
        }
      });
      const salaryType = [...document.querySelectorAll('.sal-pill')].find(button => button.dataset.val === data.salary_type);
      if (salaryType) salPickType(data.salary_type, salaryType);
      validateSalRange();
      if (data.skills && window.restoreJobSkills) window.restoreJobSkills(data.skills);
      if (data.category) {
        const role = document.getElementById('f-role');
        if (![...role.options].some(option => option.value === data.category)) role.add(new Option(data.category, data.category));
        role.value = data.category;
      }
      if (data._skills_display) document.getElementById('f-skills').value = data._skills_display;
      // Keep server-invalid text visible; do not truncate the submitted value on re-render.
      document.getElementById('desc-count').textContent = (data.description || '').match(/\S+/gu)?.length || 0;
      goStep(2);
      document.getElementById('job-errors').scrollIntoView({block: 'start'});
    }
    validateTitle();
  }
  if (document.readyState !== 'complete') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
