(() => {
  const form = document.getElementById('project-estimate-form');
  if (!form) return;

  const phaseCards = Array.from(form.querySelectorAll('[data-phase]'));
  const phaseLinks = Array.from(form.querySelectorAll('[data-phase-link]'));
  const liveTotal = form.querySelector('[data-estimate-live-total]');
  const liveCount = form.querySelector('[data-estimate-live-count]');
  const resultsLink = form.querySelector('[data-estimate-results-link]');
  const phaseCount = form.querySelector('[data-estimate-phase-count]');
  const pricedCount = form.querySelector('[data-estimate-priced-count]');
  const unpricedCount = form.querySelector('[data-estimate-unpriced-count]');
  const progressBar = form.querySelector('[data-estimate-progress]');
  const progressLabel = form.querySelector('[data-estimate-progress-label]');
  const hasResults = Boolean(document.getElementById('estimate-results'));
  const currency = new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  });

  if (resultsLink && hasResults) resultsLink.hidden = false;

  const updateEstimate = () => {
    let total = 0;
    let pricedItems = 0;
    let enteredItems = 0;
    let unpricedItems = 0;
    let activePhases = 0;

    phaseCards.forEach((phase) => {
      const items = Array.from(phase.querySelectorAll('[data-estimate-item]'));
      let phaseItems = 0;

      items.forEach((item) => {
        const quantityInput = item.querySelector('[data-estimate-quantity]');
        const rateInput = item.querySelector('[data-estimate-rate]');
        const amountLabel = item.querySelector('[data-estimate-amount]');
        const quantity = Number(quantityInput.value);
        const rate = Number(rateInput.value);
        const hasQuantity = quantityInput.value.trim() !== '' && Number.isFinite(quantity) && quantity > 0;
        const hasRate = rateInput.value.trim() !== '' && Number.isFinite(rate) && rate >= 0;

        item.classList.toggle('has-quantity', hasQuantity);
        if (hasQuantity) {
          enteredItems += 1;
          phaseItems += 1;
        }

        if (hasQuantity && hasRate) {
          const amount = quantity * rate;
          if (Number.isFinite(amount)) {
            total += amount;
            pricedItems += 1;
            amountLabel.textContent = currency.format(amount);
          } else {
            amountLabel.textContent = '—';
          }
        } else {
          amountLabel.textContent = '—';
          if (hasQuantity) unpricedItems += 1;
        }
      });

      const status = phase.querySelector('[data-phase-status]');
      if (status) {
        if (phaseItems) activePhases += 1;
        status.textContent = phaseItems
          ? `${phaseItems} item${phaseItems === 1 ? '' : 's'} added`
          : 'Not started';
        status.classList.toggle('has-items', phaseItems > 0);
      }
    });

    const contingencyInput = form.querySelector('[name="contingency_percent"]');
    const contingency = Number(contingencyInput.value);
    if (contingencyInput.value.trim() !== '' && Number.isFinite(contingency) && contingency > 0 && contingency <= 100) {
      total += total * contingency / 100;
    }

    if (liveTotal) liveTotal.textContent = currency.format(total);
    if (phaseCount) phaseCount.textContent = `${activePhases} / ${phaseCards.length}`;
    if (pricedCount) pricedCount.textContent = String(pricedItems);
    if (unpricedCount) unpricedCount.textContent = String(unpricedItems);
    if (progressBar) {
      progressBar.setAttribute('aria-valuenow', String(activePhases));
      progressBar.querySelector('span').style.width = `${phaseCards.length ? activePhases / phaseCards.length * 100 : 0}%`;
    }
    if (progressLabel) {
      progressLabel.textContent = `${activePhases} of ${phaseCards.length} phases started`;
    }
    if (liveCount) {
      if (!enteredItems) {
        liveCount.textContent = 'Abhi koi item add nahi kiya';
      } else {
        const itemLabel = `${enteredItems} item${enteredItems === 1 ? '' : 's'} entered`;
        liveCount.textContent = unpricedItems
          ? `${itemLabel} · ${unpricedItems} ka rate pending`
          : `${pricedItems} item${pricedItems === 1 ? '' : 's'} priced`;
      }
    }
  };

  phaseLinks.forEach((link) => {
    link.addEventListener('click', () => {
      const target = document.getElementById(`phase-${link.dataset.phaseLink}`);
      if (target) target.open = true;
    });
  });

  phaseCards.forEach((phase) => {
    phase.addEventListener('toggle', () => {
      const link = phaseLinks.find((item) => item.dataset.phaseLink === phase.dataset.phase);
      if (link) link.classList.toggle('is-active', phase.open);
    });
  });

  form.addEventListener('input', updateEstimate);
  updateEstimate();

  const exportButton = document.querySelector('[data-estimate-export]');
  const results = document.getElementById('estimate-results');
  if (exportButton && results) {
    exportButton.addEventListener('click', () => {
      const csvCell = (value) => {
        let text = String(value ?? '').trim();
        if (/^[\s]*[=+\-@]/.test(text)) text = `'${text}`;
        return `"${text.replace(/"/g, '""')}"`;
      };
      const rows = [['Project', 'Phase', 'Work item', 'Quantity', 'Rate', 'Amount']];
      const projectName = results.querySelector('.estimate-result-heading h2').textContent.trim();

      results.querySelectorAll('.estimate-result-phase').forEach((phase) => {
        const phaseName = phase.querySelector('.estimate-phase-total h3').textContent.trim();
        phase.querySelectorAll('.result-table tbody tr').forEach((row) => {
          rows.push([
            projectName,
            phaseName,
            ...Array.from(row.querySelectorAll('td'), (cell) => cell.textContent.trim()),
          ]);
        });
      });

      results.querySelectorAll('.estimate-grand-total > div').forEach((summaryRow) => {
        const label = summaryRow.querySelector('span').textContent.trim();
        const amount = summaryRow.querySelector('strong').textContent.trim();
        rows.push([projectName, '', label, '', '', amount]);
      });

      const csv = `\uFEFF${rows.map((row) => row.map(csvCell).join(',')).join('\r\n')}`;
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const safeName = projectName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'vishwakarma-estimate';
      link.href = downloadUrl;
      link.download = `${safeName}-estimate.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
    });
  }
})();
