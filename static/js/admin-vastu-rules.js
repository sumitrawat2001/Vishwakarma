(() => {
  const form = document.querySelector('[data-admin-rule-form]');
  const status = document.querySelector('[data-admin-rule-status]');
  const title = document.querySelector('[data-admin-form-title]');
  const resetButtons = document.querySelectorAll('[data-admin-rule-reset]');
  const rulesElement = document.getElementById('admin-vastu-rules');
  if (!form || !status || !title || !rulesElement) return;

  let rules = [];
  try {
    rules = JSON.parse(rulesElement.textContent);
  } catch (error) {
    status.textContent = 'Could not load the configured rules.';
    status.classList.add('is-error');
    console.error('Could not read the admin Vastu rule data.', error);
    return;
  }

  const field = (name) => form.elements.namedItem(name);
  const setStatus = (message, isError = false) => {
    status.textContent = message;
    status.classList.toggle('is-error', isError);
  };
  const resetForm = () => {
    form.reset();
    field('id').value = '';
    field('enabled').checked = true;
    title.textContent = 'Add a rule';
    setStatus('');
  };

  resetButtons.forEach((button) => button.addEventListener('click', resetForm));

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const id = field('id').value;
    const payload = {
      rule_name: field('rule_name').value.trim(),
      component: field('component').value,
      preferred_direction: field('preferred_direction').value,
      alternative_directions: [...form.querySelectorAll('[name="alternative_directions"]:checked')]
        .map((input) => input.value),
      priority: field('priority').value,
      recommendation: field('recommendation').value.trim(),
      source: field('source').value.trim(),
      description: field('description').value.trim(),
      applicable_conditions: field('applicable_conditions').value.trim(),
      alternative_if_relocation_not_possible: field('alternative_if_relocation_not_possible').value.trim(),
      enabled: field('enabled').checked,
    };
    const endpoint = id
      ? `/api/admin/vastu/rules/${encodeURIComponent(id)}`
      : '/api/admin/vastu/rules';
    try {
      const response = await fetch(endpoint, {
        method: id ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not save this rule.');
      setStatus('Rule saved.');
      window.location.reload();
    } catch (error) {
      setStatus(error.message || 'Could not save this rule.', true);
    }
  });

  document.querySelectorAll('[data-admin-rule-edit]').forEach((button) => {
    button.addEventListener('click', () => {
      const rule = rules.find((item) => item.id === button.dataset.adminRuleEdit);
      if (!rule) return;
      field('id').value = rule.id;
      field('rule_name').value = rule.rule_name || '';
      field('component').value = rule.component || '';
      field('preferred_direction').value = rule.preferred_direction || '';
      field('priority').value = rule.priority || 'medium';
      field('recommendation').value = rule.recommendation || '';
      field('source').value = rule.source || '';
      field('description').value = rule.description || '';
      field('applicable_conditions').value = rule.applicable_conditions || '';
      field('alternative_if_relocation_not_possible').value = rule.alternative_if_relocation_not_possible || '';
      field('enabled').checked = rule.enabled !== false;
      const alternatives = new Set(rule.alternative_directions || []);
      form.querySelectorAll('[name="alternative_directions"]').forEach((input) => {
        input.checked = alternatives.has(input.value);
      });
      title.textContent = `Edit: ${rule.rule_name}`;
      setStatus('');
      form.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  document.querySelectorAll('[data-admin-rule-toggle]').forEach((button) => {
    button.addEventListener('click', async () => {
      const id = button.dataset.adminRuleToggle;
      try {
        const response = await fetch(`/api/admin/vastu/rules/${encodeURIComponent(id)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: button.dataset.enabled !== 'true' }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Could not update this rule.');
        window.location.reload();
      } catch (error) {
        setStatus(error.message || 'Could not update this rule.', true);
      }
    });
  });

  document.querySelectorAll('[data-admin-rule-delete]').forEach((button) => {
    button.addEventListener('click', async () => {
      if (!window.confirm('Delete this shared Vastu rule?')) return;
      try {
        const response = await fetch(`/api/admin/vastu/rules/${encodeURIComponent(button.dataset.adminRuleDelete)}`, {
          method: 'DELETE',
        });
        if (!response.ok) {
          const result = await response.json();
          throw new Error(result.error || 'Could not delete this rule.');
        }
        window.location.reload();
      } catch (error) {
        setStatus(error.message || 'Could not delete this rule.', true);
      }
    });
  });
})();
