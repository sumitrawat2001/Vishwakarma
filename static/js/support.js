(() => {
  const form = document.querySelector('[data-support-chat]');
  if (!form) return;

  const input = form.querySelector('#question');
  const button = form.querySelector('#support-send');
  const chatWindow = document.querySelector('#support-chat-window');
  const status = document.querySelector('#support-status');
  const errorBox = document.querySelector('#support-error');
  const defaultButtonText = button ? button.textContent : 'Ask Vishwakarma AI';

  const addBubble = (role, text) => {
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${role === 'user' ? 'user-bubble' : 'assistant-bubble'}`;

    const label = document.createElement('span');
    label.className = 'bubble-label';
    label.textContent = role === 'user' ? 'You' : 'Vishwakarma AI';

    const message = document.createElement('p');
    message.textContent = text;
    bubble.append(label, message);
    chatWindow.appendChild(bubble);
    chatWindow.scrollTop = chatWindow.scrollHeight;
  };

  const setError = (message) => {
    errorBox.textContent = message || '';
    errorBox.hidden = !message;
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question || !button) return;

    setError('');
    addBubble('user', question);
    input.value = '';
    button.disabled = true;
    button.classList.add('support-loading');
    button.textContent = 'Vishwakarma AI is thinking...';
    if (status) status.textContent = 'Working...';

    try {
      const response = await fetch('/api/support/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'The support request failed.');
      addBubble('assistant', data.answer || 'I could not generate an answer right now.');
      if (status) status.textContent = data.source === 'ai' ? 'Live AI' : 'Project-aware AI';
    } catch (error) {
      console.error(error);
      setError('Vishwakarma AI could not respond right now. Please try again.');
      if (status) status.textContent = 'Connection issue';
    } finally {
      button.disabled = false;
      button.classList.remove('support-loading');
      button.textContent = defaultButtonText;
      input.focus();
    }
  });

  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
})();
