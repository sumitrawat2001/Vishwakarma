(() => {
  const form = document.querySelector('[data-helper-form]');
  const log = document.querySelector('[data-helper-log]');
  const questionInput = document.getElementById('vastu-helper-question');
  const contextElement = document.getElementById('vastu-helper-context');
  const historyList = document.querySelector('[data-helper-history]');
  const newChatButton = document.querySelector('[data-helper-new-chat]');
  const consentPanel = document.querySelector('[data-helper-consent-panel]');
  const consentCheckbox = document.querySelector('[data-helper-openai-consent]');
  if (!form || !log || !questionInput || !contextElement || !historyList || !newChatButton || !consentPanel || !consentCheckbox) return;

  let context;
  try {
    context = JSON.parse(contextElement.textContent);
  } catch (error) {
    console.error('Could not read the Vastu consultant context.', error);
    historyList.textContent = 'Consultant details could not be loaded.';
    return;
  }

  let consultationId = '';
  let previewUrl = '';
  const initialGreeting = 'Namaste! Main aapko ghar ki directions aur chune gaye traditional rules samjha sakta hoon. Hindi, Hinglish ya English mein sawal poochhein.';
  const submitButton = form.querySelector('[type="submit"]');

  const addMessage = (text, role, className = '') => {
    const message = document.createElement('p');
    message.className = `vastu-helper-message ${role}${className ? ` ${className}` : ''}`;
    message.textContent = text;
    log.appendChild(message);
    log.scrollTop = log.scrollHeight;
    return message;
  };

  const addStoredMessage = (message, id) => {
    const bubble = addMessage(message.content || '', message.role);
    (message.attachments || []).forEach((attachment) => {
      if (!attachment.id) return;
      const image = document.createElement('img');
      image.className = 'vastu-chat-attachment';
      image.src = `/api/vastu/consultations/${encodeURIComponent(id)}/images/${encodeURIComponent(attachment.id)}`;
      image.alt = `Saved floor plan: ${attachment.filename || 'floor plan'}`;
      image.loading = 'lazy';
      bubble.appendChild(image);
    });
    return bubble;
  };

  const resetLog = () => {
    log.replaceChildren();
    addMessage(initialGreeting, 'assistant');
  };

  const requestJson = async (url, options) => {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed. Please try again.');
    return data;
  };

  const loadHistory = async () => {
    historyList.replaceChildren();
    const loading = document.createElement('small');
    loading.textContent = 'Loading consultation history…';
    historyList.appendChild(loading);
    try {
      const data = await requestJson('/api/vastu/consultations');
      historyList.replaceChildren();
      if (!data.items.length) {
        const empty = document.createElement('small');
        empty.textContent = 'No previous consultations yet.';
        historyList.appendChild(empty);
        return;
      }
      data.items.forEach((item) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'vastu-chat-history-item';
        button.dataset.consultationId = item.id;
        const heading = document.createElement('strong');
        heading.textContent = item.title || 'Vastu consultation';
        const preview = document.createElement('small');
        preview.textContent = item.last_message || 'Open this consultation';
        button.append(heading, preview);
        button.addEventListener('click', () => openConsultation(item.id));
        historyList.appendChild(button);
      });
    } catch (error) {
      historyList.replaceChildren();
      const failed = document.createElement('small');
      failed.className = 'is-error';
      failed.textContent = error.message || 'Consultation history is unavailable.';
      historyList.appendChild(failed);
    }
  };

  const openConsultation = async (id) => {
    try {
      const data = await requestJson(`/api/vastu/consultations/${encodeURIComponent(id)}`);
      consultationId = data.item.id;
      clearPreview();
      log.replaceChildren();
      (data.item.messages || []).forEach((message) => {
        if (message.role === 'user' || message.role === 'assistant') {
          addStoredMessage(message, consultationId);
        }
      });
      if (!data.item.messages?.length) resetLog();
      log.scrollTop = log.scrollHeight;
      historyList.querySelectorAll('.vastu-chat-history-item').forEach((button) => {
        button.classList.toggle('is-active', button.dataset.consultationId === consultationId);
      });
    } catch (error) {
      addMessage(error.message || 'Could not open this consultation.', 'assistant', 'is-error');
    }
  };

  const sendQuestion = async (rawQuestion) => {
    const question = rawQuestion.trim();
    if (!question || form.dataset.busy === 'true') return;
    const selectedImage = imageInput.files?.[0];
    if (selectedImage && !consentCheckbox.checked) {
      addMessage('Image bhejne se pehle OpenAI sharing consent checkbox select karein.', 'assistant', 'is-error');
      return;
    }
    const userBubble = addMessage(question, 'user');
    let localAttachment = null;
    if (selectedImage && previewUrl) {
      localAttachment = document.createElement('img');
      localAttachment.className = 'vastu-chat-attachment';
      localAttachment.src = previewUrl;
      localAttachment.alt = `Selected floor plan: ${selectedImage.name}`;
      userBubble.appendChild(localAttachment);
    }
    questionInput.value = '';
    form.dataset.busy = 'true';
    questionInput.disabled = true;
    submitButton.disabled = true;
    const typing = addMessage('Consultant is typing…', 'assistant', 'is-typing');
    try {
      const body = new FormData();
      body.set('question', question);
      body.set('consultation_id', consultationId);
      body.set('project_id', context.project_id || '');
      body.set('openai_consent', consentCheckbox.checked ? 'true' : 'false');
      if (selectedImage) body.set('floor_plan', selectedImage);
      const data = await requestJson('/api/vastu/chat', {
        method: 'POST',
        body,
      });
      typing.remove();
      consultationId = data.consultation_id;
      if (localAttachment && data.attachment) {
        localAttachment.src = `/api/vastu/consultations/${encodeURIComponent(consultationId)}/images/${encodeURIComponent(data.attachment.id)}`;
        localAttachment.alt = `Saved floor plan: ${data.attachment.filename || 'floor plan'}`;
        clearPreview();
      }
      addMessage(data.answer, 'assistant');
      await loadHistory();
      historyList.querySelectorAll('.vastu-chat-history-item').forEach((button) => {
        button.classList.toggle('is-active', button.dataset.consultationId === consultationId);
      });
    } catch (error) {
      typing.remove();
      addMessage(error.message || 'The consultant could not reply. Please try again.', 'assistant', 'is-error');
    } finally {
      form.dataset.busy = 'false';
      questionInput.disabled = false;
      submitButton.disabled = false;
      questionInput.focus();
    }
  };

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    sendQuestion(questionInput.value);
  });

  document.querySelectorAll('[data-helper-prompt]').forEach((button) => {
    button.addEventListener('click', () => sendQuestion(button.dataset.helperPrompt || ''));
  });

  newChatButton.addEventListener('click', () => {
    consultationId = '';
    clearPreview();
    historyList.querySelectorAll('.vastu-chat-history-item').forEach((button) => button.classList.remove('is-active'));
    resetLog();
    questionInput.focus();
  });

  const imageInput = form.querySelector('[data-helper-image]');
  const preview = form.querySelector('[data-helper-preview]');
  const previewImage = form.querySelector('[data-helper-preview-image]');
  const clearImageButton = form.querySelector('[data-helper-clear-image]');

  const clearPreview = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = '';
    preview.hidden = true;
    previewImage.removeAttribute('src');
    imageInput.value = '';
    consentPanel.hidden = true;
    consentCheckbox.checked = false;
  };

  imageInput.addEventListener('change', () => {
    const file = imageInput.files?.[0];
    if (!file) return;
    if (!/^image\/(png|jpeg|webp)$/i.test(file.type)) {
      clearPreview();
      addMessage('Sirf PNG, JPG ya WEBP image upload karein.', 'assistant');
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      clearPreview();
      addMessage('Image 8 MB ya usse chhoti honi chahiye. File resize karke dobara select karein.', 'assistant');
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    previewImage.src = previewUrl;
    preview.hidden = false;
    consentPanel.hidden = false;
    consentCheckbox.checked = false;
    addMessage('Plan preview ready hai. AI analysis aur account history mein save karne ke liye OpenAI sharing consent dein.', 'assistant');
  });

  clearImageButton.addEventListener('click', clearPreview);
  window.addEventListener('pagehide', () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, { once: true });

  loadHistory();
})();
