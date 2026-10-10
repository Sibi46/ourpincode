(() => {
  const category = document.getElementById('id_categories');
  const box = document.querySelector('.teacher-register [data-subject-inputs]');
  if (!category || !box) return;
  const field = box.closest('.registration-field');
  const label = field.querySelector('label');
  const help = field.querySelector('.field-help');
  const prompts = {
    academic: ['subject', 'English, Maths, Science'],
    sports: ['sport', 'Cricket, Football, Badminton'],
    fitness: ['fitness class', 'Yoga, Strength Training, Aerobics'],
    cooking: ['cooking class', 'Baking, Cake Decorating, Indian Cooking'],
    skills: ['skill', 'Tailoring, Carpentry, Public Speaking'],
    music: ['music class', 'Piano, Guitar, Singing'],
    dance: ['dance style', 'Bharatanatyam, Ballet, Hip-hop'],
    arts: ['art or craft', 'Drawing, Painting, Pottery'],
    languages: ['language', 'English, Tamil, Hindi'],
    technology: ['technology course', 'Computer Basics, Python, Web Design'],
    other: ['class or skill', 'Enter what you teach']
  };
  function update() {
    const selected = Array.from(category.querySelectorAll('input:checked')).map(input => prompts[input.value]).filter(Boolean);
    const [name, examples] = selected.length > 1
      ? ['subject, class or skill', selected.map(item => item[1].split(',')[0]).join(', ')]
      : selected[0] || prompts.academic;
    if (label && label.firstChild) label.firstChild.textContent = `Type ${name} names `;
    if (help) help.textContent = `Use + to add another ${name}. Up to 10 entries. Examples: ${examples}.`;
    box.querySelectorAll('input').forEach(input => {
      input.placeholder = examples;
      input.setAttribute('aria-label', `${name} name`);
    });
  }
  category.addEventListener('change', update);
  box.addEventListener('click', () => update());
  update();
})();
