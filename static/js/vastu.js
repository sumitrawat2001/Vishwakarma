(() => {
  const compassDirections = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];

  const setCompass = (north) => {
    const northIndex = compassDirections.indexOf(north);
    if (northIndex < 0) return;

    document.querySelectorAll('.vastu-compass [data-compass-side], .vastu-plan [data-compass-side]').forEach((label) => {
      const side = Number(label.dataset.compassSide);
      label.textContent = compassDirections[(northIndex + side) % compassDirections.length];
    });

    const needle = document.querySelector('.compass-needle');
    if (needle) needle.style.transform = `translate(-50%, -50%) rotate(${northIndex * 45}deg)`;
  };

  const directionSelect = document.getElementById('north-direction');
  if (directionSelect) {
    setCompass(directionSelect.value);
    directionSelect.addEventListener('change', () => setCompass(directionSelect.value));
  }

  const projectSelect = document.getElementById('vastu-project-select');
  if (projectSelect) {
    projectSelect.addEventListener('change', () => {
      const url = new URL(window.location.href);
      url.pathname = '/vastu';
      if (projectSelect.value) url.searchParams.set('project_id', projectSelect.value);
      else url.searchParams.delete('project_id');
      window.location.assign(url.toString());
    });
  }

  const plannerCompass = document.querySelector('.planner-compass');
  if (plannerCompass) {
    const northIndex = compassDirections.indexOf(plannerCompass.dataset.northDirection || 'N');
    plannerCompass.querySelectorAll('[data-plan-side]').forEach((label) => {
      const side = Number(label.dataset.planSide);
      label.textContent = compassDirections[(Math.max(0, northIndex) + side) % compassDirections.length];
    });
  }
})();
