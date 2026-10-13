(() => {
  async function saveResource(button) {
    const resource = button.dataset.resource;
    const payload = JSON.parse(button.dataset.resourcePayload || '{}');
    button.disabled = true;
    try {
      const response = await fetch(`/api/${resource}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Unable to save resource.');
      button.textContent = 'Saved';
      button.classList.add('is-saved');
    } catch (error) {
      button.disabled = false;
      button.textContent = error.message;
    }
  }

  document.querySelectorAll('[data-resource-save]').forEach((button) => {
    button.addEventListener('click', () => saveResource(button));
  });
})();
