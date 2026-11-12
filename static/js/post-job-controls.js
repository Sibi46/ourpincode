(() => {
  function start() {
    const form = document.getElementById('jobForm');
    if (!form) return;
    const title = document.getElementById('f-title');
    const location = document.getElementById('f-location');
    const deadline = document.getElementById('f-deadline');
    const customIndustry = document.getElementById('indCustomInput');
    title.addEventListener('input', () => title.setCustomValidity(title.value && !/\p{L}/u.test(title.value)
      ? 'Enter a job title containing letters.' : ''));
    customIndustry.addEventListener('input', () => customIndustry.setCustomValidity(''));
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
        const input = document.getElementById('indCustomInput'); input.value = value;
        indAddCustom({key: 'Enter', preventDefault() {}});
      });
      Object.entries(data).forEach(([name, value]) => {
        if (['csrfmiddlewaretoken', 'industry', 'skills', '_skills_display'].includes(name)) return;
        const field = form.elements.namedItem(name);
        if (field && field.tagName) {
          if (field.type === 'checkbox') field.checked = !!value;
          else field.value = value;
        }
      });
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
  }
  if (document.readyState !== 'complete') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
