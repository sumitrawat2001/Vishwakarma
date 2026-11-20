(() => {
  const root = document.getElementById('estimator-app');
  const form = document.getElementById('material-estimation-form');
  if (!root || !form) return;

  const componentHost = document.getElementById('estimator-components');
  const steelHost = document.getElementById('estimator-steel-bars');
  const customMaterialHost = document.getElementById('estimator-custom-materials');
  const customMaterialCatalog = JSON.parse(root.dataset.catalog || '[]');
  const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 });
  const componentDefinitions = {
    foundation: { title: 'Foundation concrete', fields: [['quantity', 'Number of foundations', 1], ['length_m', 'Length (m)'], ['width_m', 'Width (m)'], ['depth_m', 'Depth (m)']] },
    footing: { title: 'Footing concrete', fields: [['quantity', 'Number of footings', 1], ['length_m', 'Length (m)'], ['width_m', 'Width (m)'], ['depth_m', 'Depth (m)']] },
    column: { title: 'RCC columns', fields: [['quantity', 'Number of columns', 1], ['width_m', 'Column width (m)'], ['depth_m', 'Column depth (m)'], ['height_m', 'Column height (m)']] },
    beam: { title: 'RCC beams', fields: [['quantity', 'Number of beams', 1], ['length_m', 'Length per beam (m)'], ['width_m', 'Beam width (m)'], ['depth_m', 'Beam depth (m)']] },
    slab: { title: 'RCC slab', fields: [['quantity', 'Number of slabs', 1], ['length_m', 'Length (m)'], ['width_m', 'Width (m)'], ['thickness_m', 'Thickness (m)']] },
    brick_wall: { title: 'Brick wall and mortar', fields: [['quantity', 'Number of wall sections', 1], ['length_m', 'Wall length (m)'], ['height_m', 'Wall height (m)'], ['thickness_m', 'Wall thickness (m)'], ['openings_area_m2', 'Total openings area (m²)', 0], ['brick_length_mm', 'Brick length (mm)', 190], ['brick_height_mm', 'Brick height (mm)', 90], ['brick_width_mm', 'Brick width (mm)', 90], ['mortar_joint_mm', 'Mortar joint (mm)', 10], ['mortar_cement_ratio', 'Mortar cement parts', 1], ['mortar_sand_ratio', 'Mortar sand parts', 6], ['mortar_dry_factor', 'Mortar dry-volume factor', 1.33]] },
    internal_plaster: { title: 'Internal plaster', fields: [['quantity', 'Number of areas', 1], ['area_m2', 'Plaster area per section (m²)'], ['thickness_mm', 'Thickness (mm)', 12], ['cement_ratio', 'Cement parts', 1], ['sand_ratio', 'Sand parts', 4], ['dry_volume_factor', 'Dry-volume factor', 1.33]] },
    external_plaster: { title: 'External plaster', fields: [['quantity', 'Number of areas', 1], ['area_m2', 'Plaster area per section (m²)'], ['thickness_mm', 'Thickness (mm)', 15], ['cement_ratio', 'Cement parts', 1], ['sand_ratio', 'Sand parts', 4], ['dry_volume_factor', 'Dry-volume factor', 1.33]] },
    flooring: { title: 'Flooring / tiles', fields: [['quantity', 'Number of floors / areas', 1], ['area_m2', 'Floor area per level (m²)']] },
    painting: { title: 'Painting', fields: [['quantity', 'Number of surfaces', 1], ['area_m2', 'Paint area per surface (m²)'], ['coats', 'Number of coats', 2], ['coverage_m2_per_litre', 'Coverage (m²/litre)', 10]] },
  };

  const makeLabelInput = (name, label, value, options = {}) => {
    const wrapper = document.createElement('label');
    wrapper.textContent = label;
    const input = document.createElement('input');
    input.type = 'number';
    input.min = String(options.min ?? 0);
    input.step = options.step || 'any';
    input.dataset.field = name;
    if (value !== undefined) input.value = String(value);
    if (options.required) input.required = true;
    if (options.max !== undefined) input.max = String(options.max);
    wrapper.appendChild(input);
    return wrapper;
  };

  const makeComponentCard = (type) => {
    const definition = componentDefinitions[type];
    if (!definition) return;
    const card = document.createElement('article');
    card.className = 'estimator-component-card';
    card.dataset.componentType = type;
    const heading = document.createElement('div');
    heading.className = 'estimator-card-heading';
    const title = document.createElement('h3');
    title.textContent = definition.title;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'estimator-remove';
    remove.textContent = 'Remove';
    remove.addEventListener('click', () => {
      card.remove();
      showEmpty(componentHost, 'Add the components shown in your plans or measurements.');
    });
    heading.append(title, remove);
    card.appendChild(heading);
    const fields = document.createElement('div');
    fields.className = 'estimator-fields';
    definition.fields.forEach(([key, label, defaultValue]) => {
      const required = defaultValue === undefined && !['openings_area_m2'].includes(key);
      fields.appendChild(makeLabelInput(key, label, defaultValue, { required, min: 0 }));
    });
    if (['foundation', 'footing', 'column', 'beam', 'slab'].includes(type)) {
      const gradeLabel = document.createElement('label');
      gradeLabel.textContent = 'Concrete grade';
      const grade = document.createElement('select');
      grade.dataset.field = 'mix_grade';
      ['M10', 'M15', 'M20', 'Other / design mix'].forEach((value) => {
        const option = document.createElement('option');
        option.value = value.startsWith('Other') ? 'OTHER' : value;
        option.textContent = value;
        grade.appendChild(option);
      });
      gradeLabel.appendChild(grade);
      fields.appendChild(gradeLabel);
      const ratioBox = document.createElement('div');
      ratioBox.className = 'estimator-fields estimator-custom-ratio';
      ratioBox.hidden = true;
      [['cement', 'Design cement parts'], ['sand', 'Design sand parts'], ['aggregate', 'Design aggregate parts']].forEach(([key, label]) => {
        ratioBox.appendChild(makeLabelInput(`mix_${key}`, label, '', { required: true, min: 0.01 }));
      });
      const updateCustomMixInputs = () => {
        ratioBox.hidden = grade.value !== 'OTHER';
        ratioBox.querySelectorAll('input').forEach((input) => { input.required = grade.value === 'OTHER'; });
      };
      grade.addEventListener('change', updateCustomMixInputs);
      updateCustomMixInputs();
      card.append(gradeLabel, ratioBox);
    }
    card.appendChild(fields);
    componentHost.appendChild(card);
    componentHost.querySelector('.estimator-empty')?.remove();
  };

  const makeSteelCard = (component) => {
    const card = document.createElement('article');
    card.className = 'estimator-component-card';
    card.dataset.steelComponent = component;
    const heading = document.createElement('div');
    heading.className = 'estimator-card-heading';
    const title = document.createElement('h3');
    title.textContent = `${component} reinforcement`;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'estimator-remove';
    remove.textContent = 'Remove';
    remove.addEventListener('click', () => {
      card.remove();
      showEmpty(steelHost, 'Add bar groups to prepare a preliminary schedule.');
    });
    heading.append(title, remove);
    card.appendChild(heading);
    const fields = document.createElement('div');
    fields.className = 'estimator-fields';
    const barCountField = makeLabelInput('number_of_bars', 'Number of bars (if no spacing)', '', { min: 1, max: 1000000, step: '1' });
    const spacingField = makeLabelInput('spacing_mm', 'Bar spacing (mm; optional)', '', { min: 1, max: 10000 });
    const runLengthField = makeLabelInput('run_length_m', 'Spacing run length (m)', '', { min: 0.001 });
    const barCountInput = barCountField.querySelector('input');
    const spacingInput = spacingField.querySelector('input');
    const runLengthInput = runLengthField.querySelector('input');
    const updateSteelCountInputs = () => {
      const useSpacing = spacingInput.value !== '';
      barCountInput.required = !useSpacing;
      runLengthInput.required = useSpacing;
    };
    spacingInput.addEventListener('input', updateSteelCountInputs);
    updateSteelCountInputs();
    fields.append(
      makeLabelInput('diameter_mm', 'Bar diameter (mm)', '', { required: true, min: 1, max: 100 }),
      barCountField,
      spacingField,
      runLengthField,
      makeLabelInput('bar_length_m', 'Length per bar (m)', '', { required: true, min: 0.001 }),
      makeLabelInput('lap_length_m', 'Lap length per bar (m)', 0, { min: 0 }),
      makeLabelInput('hook_bend_allowance_m', 'Hook / bend allowance per bar (m)', 0, { min: 0 }),
    );
    card.appendChild(fields);
    steelHost.appendChild(card);
    steelHost.querySelector('.estimator-empty')?.remove();
  };

  const makeCustomMaterialCard = () => {
    if (!customMaterialCatalog.length) {
      message('No custom materials are in the catalogue yet. Ask an administrator to add one.', true);
      return;
    }
    const card = document.createElement('article');
    card.className = 'estimator-component-card';
    card.dataset.customMaterial = 'true';
    const heading = document.createElement('div');
    heading.className = 'estimator-card-heading';
    const title = document.createElement('h3');
    title.textContent = 'Additional material';
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'estimator-remove';
    remove.textContent = 'Remove';
    remove.addEventListener('click', () => {
      card.remove();
      showEmpty(customMaterialHost, 'No additional material line items added.');
    });
    heading.append(title, remove);
    const fields = document.createElement('div');
    fields.className = 'estimator-fields';
    const materialLabel = document.createElement('label');
    materialLabel.textContent = 'Catalogue material';
    const materialSelect = document.createElement('select');
    materialSelect.dataset.field = 'catalog_id';
    materialSelect.required = true;
    const blankOption = document.createElement('option');
    blankOption.value = '';
    blankOption.textContent = 'Choose a material';
    materialSelect.appendChild(blankOption);
    customMaterialCatalog.forEach((material) => {
      const option = document.createElement('option');
      option.value = material.id;
      option.textContent = `${material.name} (${material.unit})`;
      materialSelect.appendChild(option);
    });
    materialLabel.appendChild(materialSelect);
    fields.append(
      materialLabel,
      makeLabelInput('quantity', 'Quantity', '', { required: true, min: 0.001 }),
      makeLabelInput('unit_price', 'Manual rate per unit (optional)', '', { min: 0 }),
    );
    card.append(heading, fields);
    customMaterialHost.appendChild(card);
    customMaterialHost.querySelector('.estimator-empty')?.remove();
  };

  const showEmpty = (host, text) => {
    if (!host.children.length) {
      const empty = document.createElement('p');
      empty.className = 'estimator-empty';
      empty.textContent = text;
      host.appendChild(empty);
    }
  };

  document.querySelectorAll('[data-add-component]').forEach((button) => {
    button.addEventListener('click', () => makeComponentCard(button.dataset.addComponent));
  });
  document.querySelectorAll('[data-add-steel]').forEach((button) => {
    button.addEventListener('click', () => makeSteelCard(button.dataset.addSteel));
  });
  document.getElementById('add-custom-material').addEventListener('click', makeCustomMaterialCard);

  const district = form.elements.namedItem('district');
  const locality = form.elements.namedItem('locality');
  const villages = JSON.parse(root.dataset.villages || '{}');
  district.addEventListener('change', () => {
    const list = document.getElementById('estimator-locality-options');
    list.replaceChildren();
    (villages[district.value] || []).forEach((name) => {
      const option = document.createElement('option');
      option.value = name;
      list.appendChild(option);
    });
    locality.value = '';
  });

  const readFields = (element) => {
    const data = {};
    element.querySelectorAll('[data-field]').forEach((input) => {
      if (input.value !== '') data[input.dataset.field] = input.type === 'number' ? Number(input.value) : input.value;
    });
    if (data.mix_grade === 'OTHER') {
      data.mix_grade = 'Design mix';
      data.mix_ratio = {
        cement: data.mix_cement, sand: data.mix_sand, aggregate: data.mix_aggregate,
      };
      delete data.mix_cement;
      delete data.mix_sand;
      delete data.mix_aggregate;
    }
    return data;
  };

  const collectPayload = () => {
    const components = Array.from(componentHost.querySelectorAll('[data-component-type]'), (card) => ({
      ...readFields(card), type: card.dataset.componentType,
    }));
    const steelBars = Array.from(steelHost.querySelectorAll('[data-steel-component]'), (card) => ({
      ...readFields(card), component: card.dataset.steelComponent,
    }));
    const customMaterials = Array.from(customMaterialHost.querySelectorAll('[data-custom-material]'), (card) => readFields(card));
    const data = new FormData(form);
    const payload = Object.fromEntries(data.entries());
    ['built_up_area_sqft', 'wastage_percent', 'dry_volume_factor', 'water_cement_ratio',
      'labour_area_sqft', 'labour_days', 'transport_distance_km', 'transport_trips',
      'other_material_cost', 'equipment_cost', 'other_expenses'].forEach((key) => {
      if (payload[key] === '') delete payload[key];
      else payload[key] = Number(payload[key]);
    });
    payload.components = components;
    payload.steel_bars = steelBars;
    payload.custom_materials = customMaterials;
    payload.manual_rates = {};
    document.querySelectorAll('[data-manual-rate]').forEach((input) => {
      if (input.value !== '') payload.manual_rates[input.dataset.manualRate] = Number(input.value);
    });
    return payload;
  };

  const addCell = (row, value, tag = 'td') => {
    const cell = document.createElement(tag);
    cell.textContent = value == null ? '—' : String(value);
    row.appendChild(cell);
    return cell;
  };

  const renderCostBreakdown = (estimate) => {
    const host = document.getElementById('estimator-cost-breakdown');
    const costs = estimate.costs;
    const slices = Object.entries(estimate.materials || {})
      .filter(([, material]) => Number.isFinite(material.amount) && material.amount > 0)
      .map(([name, material]) => ({
        name: name.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()),
        amount: material.amount,
      }));

    (estimate.custom_materials || []).forEach((material) => {
      if (Number.isFinite(material.amount) && material.amount > 0) {
        slices.push({ name: material.name, amount: material.amount });
      }
    });

    [
      ['Labour', costs.labour_cost],
      ['Transportation', costs.transportation_cost],
      ['Other materials', costs.other_material_cost],
      ['Equipment', costs.equipment_cost],
      ['Other expenses', costs.other_expenses],
    ].forEach(([name, amount]) => {
      if (Number.isFinite(amount) && amount > 0) slices.push({ name, amount });
    });

    slices.sort((first, second) => second.amount - first.amount);
    host.replaceChildren();
    const total = slices.reduce((sum, item) => sum + item.amount, 0);
    if (!total) {
      const empty = document.createElement('p');
      empty.className = 'estimator-cost-empty';
      empty.textContent = 'Cost diagram will appear when at least one item has a priced quantity.';
      host.appendChild(empty);
      return;
    }

    const colors = ['#3478f6', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#f97316', '#6366f1', '#22c55e'];
    const layout = document.createElement('div');
    layout.className = 'estimator-cost-layout';
    const chart = document.createElement('div');
    chart.className = 'estimator-donut-chart';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 120 120');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `Cost breakdown across ${slices.length} priced items`);

    const circumference = 2 * Math.PI * 42;
    let offset = 0;
    slices.forEach((item, index) => {
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      const length = circumference * item.amount / total;
      circle.setAttribute('cx', '60');
      circle.setAttribute('cy', '60');
      circle.setAttribute('r', '42');
      circle.setAttribute('fill', 'none');
      circle.setAttribute('stroke', colors[index % colors.length]);
      circle.setAttribute('stroke-width', '15');
      circle.setAttribute('stroke-linecap', 'round');
      circle.setAttribute('stroke-dasharray', `${length} ${circumference - length}`);
      circle.setAttribute('stroke-dashoffset', String(-offset));
      circle.setAttribute('transform', 'rotate(-90 60 60)');
      svg.appendChild(circle);
      offset += length;
    });

    const center = document.createElement('div');
    center.className = 'estimator-donut-center';
    const centerLabel = document.createElement('span');
    centerLabel.textContent = 'PRICED TOTAL';
    const centerAmount = document.createElement('strong');
    centerAmount.textContent = money.format(costs.known_total);
    center.append(centerLabel, centerAmount);
    chart.append(svg, center);

    const legend = document.createElement('div');
    legend.className = 'estimator-cost-legend';
    slices.forEach((item, index) => {
      const row = document.createElement('div');
      row.className = 'estimator-cost-legend-item';
      const name = document.createElement('span');
      name.className = 'estimator-cost-legend-name';
      const swatch = document.createElement('i');
      swatch.style.setProperty('--cost-swatch', colors[index % colors.length]);
      swatch.setAttribute('aria-hidden', 'true');
      const label = document.createElement('span');
      label.textContent = item.name;
      name.append(swatch, label);
      const percent = document.createElement('span');
      percent.className = 'estimator-cost-legend-percent';
      percent.textContent = `${Math.round(item.amount / total * 100)}%`;
      const amount = document.createElement('strong');
      amount.textContent = money.format(item.amount);
      row.append(name, percent, amount);
      legend.appendChild(row);
    });
    layout.append(chart, legend);
    host.appendChild(layout);
  };

  const renderResults = (estimate, historyId) => {
    const resultRoot = document.getElementById('estimator-results');
    resultRoot.hidden = false;
    const costs = estimate.costs;
    document.getElementById('known-total').textContent = money.format(costs.known_total);
    document.getElementById('cost-per-sqft').textContent = costs.cost_per_sq_ft == null ? '—' : money.format(costs.cost_per_sq_ft);
    document.getElementById('cost-per-sqm').textContent = costs.cost_per_sq_m == null ? '—' : money.format(costs.cost_per_sq_m);
    document.getElementById('estimate-completeness').textContent = costs.complete
      ? 'All required entered quantities have a rate.'
      : `Partial estimate; missing rates: ${costs.unpriced_items.join(', ')}`;
    renderCostBreakdown(estimate);
    const pdfLink = document.getElementById('estimate-pdf-link');
    pdfLink.href = `/material-estimation/${encodeURIComponent(historyId)}/report.pdf`;
    pdfLink.hidden = false;

    const fallback = document.getElementById('estimator-fallback-notice');
    const locationRank = { country: 1, state: 2, district: 3, locality: 4 };
    const requestedRank = estimate.pricing_location.locality ? 4
      : estimate.pricing_location.district ? 3
        : estimate.pricing_location.state ? 2 : 1;
    const isFallback = (price) => price?.rate != null && price.level !== 'manual'
      && locationRank[price.level] < requestedRank;
    const materialFallbacks = Object.entries(estimate.materials)
      .filter(([, material]) => isFallback(material))
      .map(([name, material]) => `${name} uses ${material.level} pricing`);
    const serviceFallbacks = Object.entries(estimate.service_prices || {})
      .filter(([, price]) => isFallback(price))
      .map(([name, price]) => `${name} uses ${price.level} pricing`);
    const customFallbacks = (estimate.custom_materials || [])
      .filter((material) => isFallback(material))
      .map((material) => `${material.name} uses ${material.level} pricing`);
    const fallbackSources = [...materialFallbacks, ...serviceFallbacks, ...customFallbacks];
    fallback.hidden = fallbackSources.length === 0;
    fallback.textContent = fallbackSources.length
      ? `A more specific location rate was unavailable. Fallback used: ${fallbackSources.join('; ')}.`
      : '';

    const quantityTable = document.createElement('table');
    quantityTable.className = 'estimator-table';
    const head = quantityTable.createTHead().insertRow();
    ['Material', 'Quantity', 'Rate', 'Cost', 'Source / level'].forEach((label) => addCell(head, label, 'th'));
    const body = quantityTable.createTBody();
    Object.entries(estimate.materials).forEach(([key, material]) => {
      const row = body.insertRow();
      addCell(row, key.replaceAll('_', ' '));
      addCell(row, `${material.quantity} ${material.unit}`);
      addCell(row, material.rate == null ? 'Not priced' : money.format(material.rate));
      addCell(row, material.amount == null ? '—' : money.format(material.amount));
      addCell(row, material.source ? `${material.source} · ${material.level || ''}` : 'No sourced price');
    });
    (estimate.custom_materials || []).forEach((material) => {
      const row = body.insertRow();
      addCell(row, material.name);
      addCell(row, `${material.quantity} ${material.unit}`);
      addCell(row, material.rate == null ? 'Not priced' : money.format(material.rate));
      addCell(row, material.amount == null ? '—' : money.format(material.amount));
      addCell(row, material.source ? `${material.source} · ${material.level || ''}` : 'No sourced price');
    });
    Object.entries(estimate.service_prices || {}).forEach(([key, service]) => {
      if (!service) return;
      const row = body.insertRow();
      addCell(row, key.replaceAll('_', ' '));
      addCell(row, service.rate == null ? 'Rate not entered' : `${key === 'labour' ? 'Area / day basis' : 'KM × trips'} @ ${money.format(service.rate)}`);
      addCell(row, service.level || '—');
      const amount = key === 'labour' ? costs.labour_cost : costs.transportation_cost;
      addCell(row, amount == null ? 'Not priced' : money.format(amount));
      addCell(row, service.source || 'No sourced price');
    });
    const costsRow = body.insertRow();
    addCell(costsRow, 'Labour / transportation / equipment / other');
    addCell(costsRow, '');
    addCell(costsRow, '');
    addCell(costsRow, `${costs.labour_cost == null ? 'Labour not priced' : money.format(costs.labour_cost)} · ${costs.transportation_cost == null ? 'Transport not priced' : money.format(costs.transportation_cost)} · Custom materials ${money.format(costs.custom_material_cost)} · Other materials ${money.format(costs.other_material_cost)} · Equipment/other ${money.format(costs.equipment_cost + costs.other_expenses)}`);
    addCell(costsRow, '');
    document.getElementById('quantity-summary').replaceChildren(quantityTable);

    const componentTable = document.createElement('table');
    componentTable.className = 'estimator-table';
    const componentHead = componentTable.createTHead().insertRow();
    ['Component', 'Quantity / volume', 'Breakdown / formula'].forEach((label) => addCell(componentHead, label, 'th'));
    const componentBody = componentTable.createTBody();
    estimate.components.forEach((component) => {
      const row = componentBody.insertRow();
      addCell(row, `${component.name} (${component.type.replaceAll('_', ' ')})`);
      addCell(row, component.wet_volume_m3 != null ? `${component.wet_volume_m3} m³` : `${component.area_m2 ?? component.net_wall_area_m2 ?? ''} m²`);
      const detail = component.concrete
        ? `${component.concrete.cement_bags} bags cement · ${component.concrete.sand_cft} CFT sand · ${component.concrete.aggregate_cft} CFT aggregate · ${component.concrete.water_litres} L water. ${component.concrete.formula}`
        : component.formula || `${component.bricks ?? ''} bricks · ${component.cement_bags ?? ''} cement bags · ${component.sand_cft ?? ''} CFT sand · ${component.tiles_sq_ft ?? ''} sq ft tiles · ${component.paint_litres ?? ''} L paint`;
      addCell(row, detail);
    });
    estimate.steel_bbs.forEach((bar) => {
      const row = componentBody.insertRow();
      addCell(row, `${bar.component} steel Ø${bar.diameter_mm} mm`);
      addCell(row, `${bar.bar_count} bars · ${bar.total_length_m} m · ${bar.weight_kg} kg`);
      addCell(row, bar.formula);
    });
    (estimate.custom_materials || []).forEach((material) => {
      const row = componentBody.insertRow();
      addCell(row, material.name);
      addCell(row, `${material.quantity} ${material.unit}`);
      addCell(row, material.amount == null ? 'No saved location price or manual rate.' : `${money.format(material.amount)} · ${material.source}`);
    });
    document.getElementById('component-breakdown').replaceChildren(componentTable);

    const assumptions = document.getElementById('estimator-assumptions');
    assumptions.replaceChildren();
    const assumptionTitle = document.createElement('strong');
    assumptionTitle.textContent = 'Calculation assumptions';
    assumptions.appendChild(assumptionTitle);
    estimate.assumptions.forEach((text) => {
      const p = document.createElement('p');
      p.textContent = text;
      assumptions.appendChild(p);
    });
    const sourceList = document.getElementById('estimator-price-sources');
    sourceList.textContent = `Price source date: ${estimate.price_updated_at || 'No official market rates available for these materials.'}`;
    appendHistory(estimate, historyId);
  };

  const appendHistory = (estimate, historyId) => {
    const host = document.getElementById('estimator-history-list');
    let list = host.querySelector('.estimator-history-list');
    if (!list) {
      list = document.createElement('div');
      list.className = 'estimator-history-list';
      host.replaceChildren(list);
    }
    const row = document.createElement('article');
    row.className = 'estimator-history-item';
    const details = document.createElement('div');
    const name = document.createElement('strong');
    name.textContent = estimate.project.name;
    const locationText = document.createElement('span');
    locationText.textContent = `${estimate.project.locality || estimate.project.district || 'No location'} · Saved just now`;
    details.append(name, locationText);
    const link = document.createElement('a');
    link.className = 'button secondary';
    link.href = `/material-estimation/${encodeURIComponent(historyId)}/report.pdf`;
    link.textContent = 'PDF report';
    row.append(details, link);
    list.prepend(row);
  };

  const message = (text, isError = false) => {
    const node = document.getElementById('estimator-message');
    node.hidden = false;
    node.className = `estimator-alert ${isError ? 'error' : 'success'}`;
    node.textContent = text;
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const componentCards = componentHost.querySelectorAll('[data-component-type]');
    const steelCards = steelHost.querySelectorAll('[data-steel-component]');
    const customCards = customMaterialHost.querySelectorAll('[data-custom-material]');
    if (!componentCards.length && !steelCards.length && !customCards.length) {
      message('Add at least one building component or steel bar group.', true);
      return;
    }
    if (!form.reportValidity() || !Array.from(componentCards).every((card) => card.querySelector('input:invalid') === null)) {
      message('Check required dimensions and values before calculating.', true);
      return;
    }
    const button = document.getElementById('calculate-estimate');
    button.disabled = true;
    button.textContent = 'Calculating…';
    try {
      const response = await fetch('/api/material-estimation/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(collectPayload()),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Unable to calculate estimate.');
      renderResults(data.estimate, data.history_id);
      message('Estimate calculated and saved. Prices without a verified source remain unpriced.');
      document.getElementById('estimator-results').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      message(error.message || 'Unable to calculate estimate.', true);
    } finally {
      button.disabled = false;
      button.textContent = 'Calculate and save estimate →';
    }
  });
})();
