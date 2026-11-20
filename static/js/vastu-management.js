(() => {
  const ruleForm = document.querySelector('[data-custom-rule-form]');
  const rulesList = document.querySelector('[data-custom-rules-list]');
  const ruleStatus = document.querySelector('[data-rule-status]');
  const reportsList = document.querySelector('[data-report-list]');
  const reportStatus = document.querySelector('[data-report-status]');
  const saveReportButton = document.querySelector('[data-save-report]');
  if (!ruleForm || !rulesList || !ruleStatus || !reportsList || !reportStatus) return;

  const directions = {
    N: 'North', NE: 'Northeast', E: 'East', SE: 'Southeast',
    S: 'South', SW: 'Southwest', W: 'West', NW: 'Northwest',
  };
  const componentLabels = Object.fromEntries(
    Array.from(ruleForm.elements.component.options, (option) => [option.value, option.textContent])
  );
  const escapeText = (value) => String(value ?? '');
  const showStatus = (element, message, isError = false) => {
    element.textContent = message;
    element.classList.toggle('is-error', isError);
  };
  const request = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `Request failed (${response.status}).`);
    }
    return response.status === 204 ? null : response.json();
  };

  const updateEmptyRuleState = () => {
    const existing = rulesList.querySelector('[data-custom-rule]');
    if (!existing && !rulesList.querySelector('[data-custom-rules-empty]')) {
      const empty = document.createElement('p');
      empty.className = 'vastu-empty-state';
      empty.dataset.customRulesEmpty = '';
      empty.textContent = 'Abhi koi custom rule save nahi hai. Neeche form se pehla rule banao.';
      rulesList.appendChild(empty);
    } else if (existing) {
      rulesList.querySelector('[data-custom-rules-empty]')?.remove();
    }
  };

  const renderRule = (rule) => {
    const article = document.createElement('article');
    article.className = 'vastu-custom-rule';
    article.dataset.customRule = '';
    article.dataset.ruleId = escapeText(rule.id);

    const heading = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = escapeText(rule.rule_name);
    const subheading = document.createElement('span');
    subheading.textContent = `${componentLabels[rule.component] || rule.component} · ${rule.priority} priority`;
    heading.append(title, subheading);

    const directionsLine = document.createElement('p');
    directionsLine.textContent = `Preferred: ${directions[rule.preferred_direction] || rule.preferred_direction}${rule.alternative_directions?.length ? ` · Alternatives: ${rule.alternative_directions.map((direction) => directions[direction] || direction).join(', ')}` : ''}`;
    const description = document.createElement('small');
    description.textContent = rule.description || 'No description provided.';

    const actions = document.createElement('div');
    actions.className = 'vastu-rule-actions';
    const enabledLabel = document.createElement('label');
    enabledLabel.className = 'vastu-rule-enabled';
    const enabled = document.createElement('input');
    enabled.type = 'checkbox';
    enabled.checked = Boolean(rule.enabled);
    enabled.dataset.ruleEnabled = '';
    enabledLabel.append(enabled, document.createTextNode(' Enabled'));
    const edit = document.createElement('button');
    edit.type = 'button';
    edit.dataset.editRule = '';
    edit.textContent = 'Edit';
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.dataset.deleteRule = '';
    remove.textContent = 'Delete';
    actions.append(enabledLabel, edit, remove);
    article.append(heading, directionsLine, description, actions);
    return article;
  };

  const loadRules = async () => {
    showStatus(ruleStatus, 'Loading saved rules…');
    try {
      const { items } = await request('/api/vastu/rules');
      rulesList.querySelectorAll('[data-custom-rule]').forEach((item) => item.remove());
      items.forEach((rule) => rulesList.appendChild(renderRule(rule)));
      updateEmptyRuleState();
      showStatus(ruleStatus, items.length ? `${items.length} saved rule${items.length === 1 ? '' : 's'} loaded.` : '');
    } catch (error) {
      showStatus(ruleStatus, `Custom rules load nahi hue: ${error.message}`, true);
    }
  };

  const resetRuleForm = () => {
    ruleForm.reset();
    ruleForm.elements.rule_id.value = '';
    ruleForm.querySelector('[data-save-rule]').textContent = 'Save Rule';
    ruleForm.querySelector('[data-cancel-rule]').hidden = true;
  };

  const readRuleForm = () => ({
    rule_name: ruleForm.elements.rule_name.value.trim(),
    component: ruleForm.elements.component.value,
    preferred_direction: ruleForm.elements.preferred_direction.value,
    alternative_directions: Array.from(
      ruleForm.querySelectorAll('[name="alternative_directions"]:checked'),
      (input) => input.value
    ),
    description: ruleForm.elements.description.value.trim(),
    priority: ruleForm.elements.priority.value,
    recommendation: ruleForm.elements.recommendation.value.trim(),
  });

  ruleForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const saveButton = ruleForm.querySelector('[data-save-rule]');
    saveButton.disabled = true;
    showStatus(ruleStatus, 'Saving rule…');
    try {
      const id = ruleForm.elements.rule_id.value;
      const { item } = await request(id ? `/api/vastu/rules/${encodeURIComponent(id)}` : '/api/vastu/rules', {
        method: id ? 'PATCH' : 'POST',
        body: JSON.stringify(readRuleForm()),
      });
      if (id) {
        rulesList.querySelector(`[data-rule-id="${CSS.escape(id)}"]`)?.replaceWith(renderRule(item));
      } else {
        rulesList.prepend(renderRule(item));
      }
      updateEmptyRuleState();
      resetRuleForm();
      showStatus(ruleStatus, 'Rule saved. Ye rule sirf aapke account mein hai.');
    } catch (error) {
      showStatus(ruleStatus, `Rule save nahi hua: ${error.message}`, true);
    } finally {
      saveButton.disabled = false;
    }
  });

  ruleForm.querySelector('[data-cancel-rule]').addEventListener('click', resetRuleForm);

  rulesList.addEventListener('click', async (event) => {
    const article = event.target.closest('[data-custom-rule]');
    if (!article) return;
    const id = article.dataset.ruleId;
    try {
      if (event.target.closest('[data-edit-rule]')) {
        const { item } = await request(`/api/vastu/rules/${encodeURIComponent(id)}`);
        ruleForm.elements.rule_id.value = item.id;
        ruleForm.elements.rule_name.value = item.rule_name;
        ruleForm.elements.component.value = item.component;
        ruleForm.elements.preferred_direction.value = item.preferred_direction;
        ruleForm.elements.description.value = item.description || '';
        ruleForm.elements.priority.value = item.priority;
        ruleForm.elements.recommendation.value = item.recommendation || '';
        ruleForm.querySelectorAll('[name="alternative_directions"]').forEach((input) => {
          input.checked = (item.alternative_directions || []).includes(input.value);
        });
        ruleForm.querySelector('[data-save-rule]').textContent = 'Update Rule';
        ruleForm.querySelector('[data-cancel-rule]').hidden = false;
        ruleForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
        ruleForm.elements.rule_name.focus();
        return;
      }
      if (event.target.closest('[data-delete-rule]')) {
        if (!window.confirm('Delete this custom rule?')) return;
        await request(`/api/vastu/rules/${encodeURIComponent(id)}`, { method: 'DELETE' });
        article.remove();
        updateEmptyRuleState();
        showStatus(ruleStatus, 'Custom rule deleted.');
        return;
      }
    } catch (error) {
      showStatus(ruleStatus, `Rule action nahi ho saka: ${error.message}`, true);
    }
  });

  rulesList.addEventListener('change', async (event) => {
    if (!event.target.matches('[data-rule-enabled]')) return;
    const article = event.target.closest('[data-custom-rule]');
    const checkbox = event.target;
    checkbox.disabled = true;
    try {
      await request(`/api/vastu/rules/${encodeURIComponent(article.dataset.ruleId)}`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled: checkbox.checked }),
      });
      showStatus(ruleStatus, `Rule ${checkbox.checked ? 'enabled' : 'disabled'}.`);
    } catch (error) {
      checkbox.checked = !checkbox.checked;
      showStatus(ruleStatus, `Rule state update nahi hua: ${error.message}`, true);
    } finally {
      checkbox.disabled = false;
    }
  });

  const renderReport = (report) => {
    const article = document.createElement('article');
    article.className = 'vastu-saved-report';
    article.dataset.savedReport = '';
    article.dataset.reportId = escapeText(report.id);
    const titleGroup = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = escapeText(report.report_name);
    const details = document.createElement('span');
    const score = report.analysis?.score;
    details.textContent = `${(report.analysis?.analysis_mode || 'standard')} mode · Score ${score ?? 'not available'}`;
    titleGroup.append(title, details);
    const plot = document.createElement('small');
    plot.textContent = `${report.plot_length} × ${report.plot_width} ${report.unit} · ${report.created_at}`;
    const actions = document.createElement('div');
    actions.className = 'vastu-rule-actions';
    const open = document.createElement('a');
    open.href = `/vastu?report_id=${encodeURIComponent(report.id)}`;
    open.textContent = 'Open report';
    const pdf = document.createElement('a');
    pdf.href = `/vastu/reports/${encodeURIComponent(report.id)}.pdf`;
    pdf.textContent = 'PDF';
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.dataset.deleteReport = '';
    remove.textContent = 'Delete';
    actions.append(open, pdf, remove);
    article.append(titleGroup, plot, actions);
    return article;
  };

  const loadReports = async () => {
    showStatus(reportStatus, 'Loading saved reports…');
    try {
      const { items } = await request('/api/vastu/reports');
      reportsList.querySelectorAll('[data-saved-report]').forEach((item) => item.remove());
      items.forEach((report) => reportsList.appendChild(renderReport(report)));
      if (!items.length && !reportsList.querySelector('[data-reports-empty]')) {
        const empty = document.createElement('p');
        empty.className = 'vastu-empty-state';
        empty.dataset.reportsEmpty = '';
        empty.textContent = 'Abhi saved report nahi hai. Analysis run karke “Save Report” choose karo.';
        reportsList.appendChild(empty);
      } else if (items.length) {
        reportsList.querySelector('[data-reports-empty]')?.remove();
      }
      showStatus(reportStatus, items.length ? `${items.length} saved report${items.length === 1 ? '' : 's'} loaded.` : '');
    } catch (error) {
      showStatus(reportStatus, `Reports load nahi hue: ${error.message}`, true);
    }
  };

  reportsList.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-delete-report]');
    if (!button) return;
    const article = button.closest('[data-saved-report]');
    if (!window.confirm('Delete this saved analysis report?')) return;
    button.disabled = true;
    try {
      await request(`/api/vastu/reports/${encodeURIComponent(article.dataset.reportId)}`, { method: 'DELETE' });
      article.remove();
      await loadReports();
      showStatus(reportStatus, 'Saved report deleted.');
    } catch (error) {
      button.disabled = false;
      showStatus(reportStatus, `Report delete nahi hua: ${error.message}`, true);
    }
  });

  if (saveReportButton) {
    saveReportButton.addEventListener('click', async () => {
      saveReportButton.disabled = true;
      showStatus(reportStatus, 'Saving report…');
      try {
        await request('/api/vastu/reports', {
          method: 'POST',
          body: JSON.stringify({ project_id: saveReportButton.dataset.projectId }),
        });
        await loadReports();
        showStatus(reportStatus, 'Analysis report saved to your private report history.');
      } catch (error) {
        showStatus(reportStatus, `Report save nahi hua: ${error.message}`, true);
      } finally {
        saveReportButton.disabled = false;
      }
    });
  }

  loadRules();
  loadReports();
})();
