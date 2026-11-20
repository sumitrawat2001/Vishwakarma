(() => {
  const root = document.getElementById('structural-studio');
  if (!root || !root.querySelector('[data-studio-enabled]')) return;

  const projectId = root.dataset.projectId;
  const unit = root.dataset.projectUnit === 'meter' ? 'm' : 'ft';
  const unitFactor = unit === 'ft' ? 0.3048 : 1;
  const plotLength = Math.max(Number(root.dataset.plotLength) || 30, 0.1);
  const plotWidth = Math.max(Number(root.dataset.plotWidth) || 40, 0.1);
  const floors = Math.max(1, Math.floor(Number(root.dataset.floors) || 1));
  const designForm = document.getElementById('structural-properties');
  const drawing = document.getElementById('structural-drawing');
  const canvasHost = document.getElementById('structural-3d');
  const message = document.getElementById('studio-message');
  const results = document.getElementById('structural-estimate-results');
  const stageButtons = Array.from(document.querySelectorAll('.simulation-stage'));
  const stages = ['Excavation', 'PCC', 'Foundation footing', 'Foundation columns', 'Plinth beam', 'Brickwork', 'Columns', 'Beams', 'Slab', 'Roofing', 'Finishing'];

  const lengthDefault = (meters) => Number((meters / unitFactor).toFixed(3));
  const fields = {
    foundation: [
      ['footing_type', 'Foundation type', 'select', 'isolated', ['isolated|Isolated footing', 'combined|Combined footing', 'strip|Strip footing', 'raft|Raft foundation']],
      ['footing_count', 'Footing count (planning input)', 'number', 4, 1, 100000, 1],
      ['footing_length', `Footing length (${unit})`, 'number', lengthDefault(1.5), 0.1, 10000, 0.01],
      ['footing_width', `Footing width (${unit})`, 'number', lengthDefault(1.5), 0.1, 10000, 0.01],
      ['footing_depth', `Footing thickness (${unit})`, 'number', lengthDefault(0.45), 0.05, 100, 0.01],
      ['foundation_depth', `Excavation depth (${unit})`, 'number', lengthDefault(0.9), 0.1, 100, 0.01],
      ['soil_bearing_capacity', 'Soil bearing capacity (kPa)', 'number', 150, 1, 10000, 1],
      ['dead_load_kpa', 'Dead load reference (kPa; record only)', 'number', 0, 0, 100000, 0.1],
      ['live_load_kpa', 'Live load reference (kPa; record only)', 'number', 0, 0, 100000, 0.1],
      ['wind_speed_ms', 'Wind speed reference (m/s; record only)', 'number', 0, 0, 500, 0.1],
      ['seismic_lateral_load_kn', 'Seismic action reference (kN; record only)', 'number', 0, 0, 10000000, 0.1],
      ['engineering_reference', 'Engineer-specified IS reference (record only)', 'text', ''],
      ['column_width', `Column width (${unit})`, 'number', lengthDefault(0.3), 0.1, 100, 0.01],
      ['column_depth', `Column depth (${unit})`, 'number', lengthDefault(0.3), 0.1, 100, 0.01],
      ['pcc_thickness', `PCC thickness (${unit})`, 'number', lengthDefault(0.1), 0, 100, 0.01],
      ['foundation_concrete_grade', 'Foundation concrete grade', 'select', 'M20', ['M10|M10', 'M15|M15', 'M20|M20']],
      ['pcc_concrete_grade', 'PCC concrete grade', 'select', 'M10', ['M10|M10', 'M15|M15', 'M20|M20']],
      ['steel_grade', 'Reinforcement steel grade', 'select', 'Fe500', ['Fe415|Fe415', 'Fe500|Fe500', 'Fe550|Fe550']],
      ['footing_main_bars_x', 'Footing bars — X direction', 'number', 8, 2, 1000, 1],
      ['footing_main_bars_y', 'Footing bars — Y direction', 'number', 8, 2, 1000, 1],
      ['footing_bar_diameter', 'Footing bar diameter (mm)', 'number', 12, 4, 50, 1],
      ['footing_bar_spacing', 'Footing bar spacing (mm)', 'number', 150, 25, 1000, 5],
    ],
    plinth: [
      ['plinth_height', `Plinth height (${unit})`, 'number', lengthDefault(0.45), 0, 100, 0.01],
      ['plinth_beam_width', `Plinth beam width (${unit})`, 'number', lengthDefault(0.23), 0.1, 100, 0.01],
      ['plinth_beam_depth', `Plinth beam depth (${unit})`, 'number', lengthDefault(0.3), 0.1, 100, 0.01],
      ['plinth_beam_length', `Total plinth beam length (${unit})`, 'number', 2 * (plotLength + plotWidth), 0.1, 100000, 0.01],
      ['plinth_beam_main_bars', 'Plinth beam main bars (entered)', 'number', 4, 2, 1000, 1],
      ['plinth_beam_bar_diameter', 'Plinth beam bar diameter (mm)', 'number', 12, 4, 50, 1],
      ['plinth_beam_stirrup_diameter', 'Plinth beam stirrup (mm)', 'number', 8, 4, 25, 1],
      ['plinth_beam_stirrup_spacing', 'Plinth beam stirrup spacing (mm)', 'number', 150, 25, 1000, 5],
      ['dpc_thickness', `DPC thickness (${unit})`, 'number', lengthDefault(0.025), 0, 10, 0.001],
      ['ground_fill_depth', `Ground filling depth (${unit})`, 'number', lengthDefault(0.3), 0, 100, 0.01],
      ['plinth_pcc_thickness', `Plinth PCC thickness (${unit})`, 'number', lengthDefault(0.1), 0, 100, 0.01],
      ['plinth_masonry_height', `Plinth masonry height (${unit})`, 'number', lengthDefault(0.6), 0, 100, 0.01],
      ['plinth_wall_thickness', `Plinth wall thickness (${unit})`, 'number', lengthDefault(0.23), 0.1, 10, 0.01],
    ],
    column: [
      ['column_count', 'Column count', 'number', 4, 1, 100000, 1],
      ['column_origin_x', `Column layout offset X (${unit})`, 'number', lengthDefault(1), 0, 10000, 0.01],
      ['column_origin_y', `Column layout offset Y (${unit})`, 'number', lengthDefault(1), 0, 10000, 0.01],
      ['column_layout', 'Column position pattern', 'select', 'grid', ['grid|Evenly spaced grid (schematic)', 'perimeter|Perimeter pattern (schematic)']],
      ['column_width', `Column width (${unit})`, 'number', lengthDefault(0.3), 0.1, 100, 0.01],
      ['column_depth', `Column depth (${unit})`, 'number', lengthDefault(0.3), 0.1, 100, 0.01],
      ['column_height', `Floor-to-floor height (${unit})`, 'number', lengthDefault(3), 1, 100, 0.01],
      ['column_main_bars', 'Longitudinal bars (entered)', 'number', 8, 4, 1000, 1],
      ['column_bar_diameter', 'Main bar diameter (mm)', 'number', 16, 4, 50, 1],
      ['column_stirrup_diameter', 'Stirrup diameter (mm)', 'number', 8, 4, 25, 1],
      ['column_stirrup_spacing', 'Stirrup spacing (mm)', 'number', 150, 25, 1000, 5],
      ['column_concrete_grade', 'Concrete grade', 'select', 'M20', ['M10|M10', 'M15|M15', 'M20|M20']],
    ],
    beam: [
      ['beam_count', 'Beam count per floor', 'number', 4, 1, 100000, 1],
      ['beam_length', `Beam length (${unit})`, 'number', lengthDefault((plotLength + plotWidth) / 2 * unitFactor), 0.1, 10000, 0.01],
      ['beam_width', `Beam width (${unit})`, 'number', lengthDefault(0.23), 0.1, 100, 0.01],
      ['beam_depth', `Beam depth (${unit})`, 'number', lengthDefault(0.45), 0.1, 100, 0.01],
      ['beam_main_bars', 'Main bars (entered)', 'number', 4, 2, 1000, 1],
      ['beam_bar_diameter', 'Main bar diameter (mm)', 'number', 16, 4, 50, 1],
      ['beam_stirrup_diameter', 'Stirrup diameter (mm)', 'number', 8, 4, 25, 1],
      ['beam_stirrup_spacing', 'Stirrup spacing (mm)', 'number', 150, 25, 1000, 5],
      ['beam_concrete_grade', 'Concrete grade', 'select', 'M20', ['M10|M10', 'M15|M15', 'M20|M20']],
    ],
    slab: [
      ['slab_length', `Slab length (${unit})`, 'number', plotLength, 0.1, 10000, 0.01],
      ['slab_width', `Slab width (${unit})`, 'number', plotWidth, 0.1, 10000, 0.01],
      ['slab_thickness', `Slab thickness (${unit})`, 'number', lengthDefault(0.125), 0.05, 10, 0.01],
      ['slab_main_direction', 'Main reinforcement direction', 'select', 'short', ['short|Short span (entered)', 'long|Long span (entered)']],
      ['slab_main_bar_diameter', 'Main bar diameter (mm)', 'number', 10, 4, 50, 1],
      ['slab_main_bar_spacing', 'Main bar spacing (mm)', 'number', 150, 25, 1000, 5],
      ['slab_distribution_bar_diameter', 'Distribution bar diameter (mm)', 'number', 8, 4, 50, 1],
      ['slab_distribution_bar_spacing', 'Distribution bar spacing (mm)', 'number', 200, 25, 1000, 5],
      ['slab_opening_length', `Opening length (${unit})`, 'number', 0, 0, 10000, 0.01],
      ['slab_opening_width', `Opening width (${unit})`, 'number', 0, 0, 10000, 0.01],
      ['slab_concrete_grade', 'Concrete grade', 'select', 'M20', ['M10|M10', 'M15|M15', 'M20|M20']],
    ],
    wall: [
      ['wall_type', 'Wall type', 'select', 'external', ['external|External masonry', 'internal|Internal masonry', 'partition|Partition wall']],
      ['wall_length', `Total wall length (${unit})`, 'number', 2 * (plotLength + plotWidth), 0.1, 100000, 0.01],
      ['wall_height', `Wall height (${unit})`, 'number', lengthDefault(2.7), 0.1, 1000, 0.01],
      ['wall_thickness', `Wall thickness (${unit})`, 'number', lengthDefault(0.2), 0.05, 10, 0.01],
      ['door_count', 'Door openings (count)', 'number', 1, 0, 1000, 1],
      ['door_width', `Door width (${unit})`, 'number', lengthDefault(0.9), 0.1, 100, 0.01],
      ['door_height', `Door height (${unit})`, 'number', lengthDefault(2.1), 0.1, 100, 0.01],
      ['window_count', 'Window openings (count)', 'number', 2, 0, 1000, 1],
      ['window_width', `Window width (${unit})`, 'number', lengthDefault(1.2), 0.1, 100, 0.01],
      ['window_height', `Window height (${unit})`, 'number', lengthDefault(1.2), 0.1, 100, 0.01],
      ['window_sill_height', `Window sill height (${unit})`, 'number', lengthDefault(0.9), 0, 100, 0.01],
      ['brick_length_mm', 'Brick length (mm)', 'number', 190, 1, 1000, 1],
      ['brick_height_mm', 'Brick height (mm)', 'number', 90, 1, 1000, 1],
      ['brick_width_mm', 'Brick width (mm)', 'number', 90, 1, 1000, 1],
    ],
    staircase: [
      ['stair_width', `Stair width (${unit})`, 'number', lengthDefault(1), 0.1, 100, 0.01],
      ['stair_floor_height', `Floor height (${unit})`, 'number', lengthDefault(3), 1, 100, 0.01],
      ['stair_flight_length', `Flight run (${unit})`, 'number', lengthDefault(5.2), 0.1, 100, 0.01],
      ['stair_tread', `Tread (${unit})`, 'number', lengthDefault(0.28), 0.1, 10, 0.01],
      ['stair_riser', `Riser (${unit})`, 'number', lengthDefault(0.17), 0.05, 2, 0.01],
      ['stair_flights', 'Flights per floor (entered)', 'number', 2, 1, 20, 1],
      ['stair_waist_thickness', `Waist slab thickness (${unit})`, 'number', lengthDefault(0.15), 0.05, 2, 0.01],
    ],
    reinforcement: [
      ['rebar_cover', `Nominal cover reference (${unit})`, 'number', lengthDefault(0.04), 0, 1, 0.001],
      ['bar_lap_length', `Lap allowance per bar (${unit})`, 'number', 0, 0, 10, 0.01],
      ['bar_hook_allowance', `Hook / bend allowance per bar (${unit})`, 'number', 0, 0, 10, 0.01],
      ['rebar_note', 'Schedule status', 'select', 'preliminary', ['preliminary|Preliminary user-entered schedule', 'verified|Engineer-verified input (not verified here)']],
    ],
    simulation: [],
  };

  const state = {
    module: 'foundation',
    view: 'top',
    stage: 0,
    savedId: root.dataset.designId || '',
    dirty: false,
    estimate: null,
    rates: {},
    three: null,
    sceneObjects: [],
    cameraOrbit: { azimuth: 0.75, elevation: 0.55, distance: 0 },
    animationTimer: null,
  };

  function setMessage(text, isError = false) {
    message.textContent = text;
    message.classList.toggle('is-error', isError);
  }
  const markEstimateStale = () => {
    if (!state.estimate) return;
    state.estimate = null;
    results.innerHTML = '<p class="estimate-placeholder">Inputs changed. Recalculate to update this geometry-based estimate.</p>';
  };

  const labels = {
    foundation: 'Foundation design',
    plinth: 'Plinth design',
    column: 'Column design',
    beam: 'Beam design',
    slab: 'Slab design',
    wall: 'Wall & masonry design',
    staircase: 'Staircase design',
    reinforcement: 'Reinforcement details',
    simulation: '3D construction simulation',
  };

  const defaultValues = {};
  Object.values(fields).flat().forEach((field) => { defaultValues[field[0]] = field[3]; });
  defaultValues.footing_count = 4;
  defaultValues.foundation_concrete_grade = 'M20';
  defaultValues.steel_grade = 'Fe500';
  defaultValues.plinth_beam_length = 2 * (plotLength + plotWidth);
  defaultValues.plinth_beam_main_bars = 4;
  defaultValues.plinth_beam_bar_diameter = 12;

  const readInitialDesign = () => {
    try {
      const saved = JSON.parse(root.dataset.initialDesign || '{}');
      return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
    } catch (error) {
      console.error('Saved structural design could not be read.', error);
      setMessage('Saved design data could not be read; default planning inputs are shown.', true);
      return {};
    }
  };
  let values = { ...defaultValues, ...readInitialDesign() };
  let roomContext = { rooms: {}, room_dimensions: {}, layout_data: {} };
  try {
    roomContext = JSON.parse(document.getElementById('planner-structural-context')?.textContent || '{}');
  } catch (error) {
    console.error('Saved planner room context could not be read.', error);
    setMessage('Planner room placements are unavailable; project dimensions are still linked.', true);
  }
  try {
    state.rates = JSON.parse(root.dataset.initialRates || '{}');
  } catch (error) {
    console.error('Saved structural rate overrides could not be read.', error);
  }

  const number = (key, fallback = 0) => {
    const parsed = Number(values[key]);
    return Number.isFinite(parsed) ? parsed : fallback;
  };
  const meters = (key, fallback = 0) => Math.max(0, number(key, fallback)) * unitFactor;
  const integer = (key, fallback = 1) => Math.max(1, Math.floor(number(key, fallback)));
  const nonNegativeInteger = (key) => Math.max(0, Math.floor(number(key, 0)));
  const fmt = (value, digits = 2) => Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: digits });
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
  const makeField = (field) => {
    const [key, title, type, defaultValue, min, max, step] = field;
    const label = document.createElement('label');
    label.textContent = title;
    if (type === 'select') {
      const select = document.createElement('select');
      select.dataset.property = key;
      field[4].forEach((optionText) => {
        const [optionValue, optionLabel] = optionText.split('|');
        const option = document.createElement('option');
        option.value = optionValue;
        option.textContent = optionLabel;
        select.appendChild(option);
      });
      label.appendChild(select);
      return label;
    }
    if (type === 'text') {
      const input = document.createElement('input');
      input.type = 'text';
      input.maxLength = 100;
      input.dataset.property = key;
      input.value = String(values[key] ?? defaultValue);
      label.classList.add('property-wide');
      label.appendChild(input);
      return label;
    }
    const input = document.createElement('input');
    input.type = 'number';
    input.min = String(min);
    input.max = String(max);
    input.step = String(step);
    input.dataset.property = key;
    input.value = String(values[key] ?? defaultValue);
    input.required = true;
    label.appendChild(input);
    return label;
  };

  const updatePropertyForm = () => {
    designForm.replaceChildren();
    const shared = document.createElement('div');
    shared.className = 'property-summary property-wide';
    shared.textContent = `Saved planner plot: ${fmt(plotLength)} × ${fmt(plotWidth)} ${unit} · ${floors} floor(s) · dimensions are linked read-only.`;
    designForm.appendChild(shared);
    (fields[state.module] || []).forEach((field) => designForm.appendChild(makeField(field)));
    if (state.module === 'foundation') {
      const note = document.createElement('p');
      note.className = 'property-wide';
      note.textContent = 'Load and soil entries are recorded only. No dead/live/wind/seismic combination, soil-pressure check, code clause or design resistance is calculated.';
      designForm.appendChild(note);
    }
    if (state.module === 'simulation') {
      const note = document.createElement('p');
      note.className = 'property-wide';
      note.textContent = 'Select construction stages below. Geometry is refreshed from the project plot and entered section dimensions.';
      designForm.appendChild(note);
    }
    designForm.querySelectorAll('[data-property]').forEach((input) => {
      const field = fields[state.module].find((item) => item[0] === input.dataset.property);
      if (field && field[2] === 'select') input.value = values[field[0]] ?? field[3];
      input.addEventListener('input', () => {
        values[input.dataset.property] = input.type === 'number' ? input.value : input.value;
        state.dirty = true;
        markEstimateStale();
        updateSummary();
        renderDrawing();
        rebuildModel();
      });
      input.addEventListener('change', () => {
        values[input.dataset.property] = input.value;
        state.dirty = true;
        state.estimate = null;
        renderDrawing();
        rebuildModel();
      });
    });
    document.getElementById('active-module-label').textContent = labels[state.module];
    document.getElementById('studio-unit-note').textContent = `Dimensions in ${unit} · bars in mm`;
    updateSummary();
    renderDrawing();
  };

  const updateSummary = () => {
    const host = document.getElementById('property-summary');
    if (state.module === 'foundation') {
      host.innerHTML = `<span>Type: ${escapeHtml(String(values.footing_type || 'isolated').replace('_', ' '))}</span><span>Footing: ${fmt(number('footing_length'))} × ${fmt(number('footing_width'))} × ${fmt(number('footing_depth'))} ${unit}</span><span>Soil capacity: ${fmt(number('soil_bearing_capacity'))} kPa (entered; not checked)</span>`;
    } else if (state.module === 'simulation') {
      host.textContent = '3D stages are illustrative and do not represent construction approval.';
    } else {
      host.innerHTML = `<span>Plot: ${fmt(plotLength)} × ${fmt(plotWidth)} ${unit}</span><span>Floors: ${floors}</span><span>Changes require saving to persist.</span>`;
    }
  };

  const dimensionText = (x1, y1, x2, y2, text, offset = 15) => {
    if (Math.abs(y2 - y1) < 1) {
      return `<line x1="${x1}" y1="${y1 + offset}" x2="${x2}" y2="${y2 + offset}" class="dim-line"/><line x1="${x1}" y1="${y1 + offset - 5}" x2="${x1}" y2="${y1 + offset + 5}" class="dim-line"/><line x1="${x2}" y1="${y2 + offset - 5}" x2="${x2}" y2="${y2 + offset + 5}" class="dim-line"/><text x="${(x1 + x2) / 2}" y="${y1 + offset - 4}" text-anchor="middle" class="dim-text">${escapeHtml(text)}</text>`;
    }
    return `<line x1="${x1 + offset}" y1="${y1}" x2="${x2 + offset}" y2="${y2}" class="dim-line"/><line x1="${x1 + offset - 5}" y1="${y1}" x2="${x1 + offset + 5}" y2="${y1}" class="dim-line"/><line x1="${x2 + offset - 5}" y1="${y2}" x2="${x2 + offset + 5}" y2="${y2}" class="dim-line"/><text x="${x1 + offset + 10}" y="${(y1 + y2) / 2}" class="dim-text">${escapeHtml(text)}</text>`;
  };

  const svgStyle = '<style>.outline{fill:#fff;stroke:#1d4665;stroke-width:3}.concrete{fill:#dce8f1;stroke:#55738d;stroke-width:2}.column{fill:#829db3;stroke:#284f6d;stroke-width:2}.wall{fill:#b5c5d2;stroke:#536f84;stroke-width:2}.steel{fill:#d74d44;stroke:#a42d26;stroke-width:1}.dim-line{stroke:#4380a9;stroke-width:1;marker-start:url(#arr);marker-end:url(#arr)}.dim-text{font:12px Arial,sans-serif;fill:#28668e}.label{font:13px Arial,sans-serif;fill:#203c52}.muted{font:11px Arial,sans-serif;fill:#718596}.section-line{stroke:#627d91;stroke-width:1.5;stroke-dasharray:6 4}</style><defs><marker id="arr" markerWidth="7" markerHeight="7" refX="3.5" refY="3.5" orient="auto"><path d="M7 0L0 3.5 7 7" fill="none" stroke="#4380a9"/></marker></defs>';

  const drawTop = () => {
    const maxLength = Math.max(plotLength, plotWidth, 0.1);
    const scale = 330 / maxLength;
    const w = plotLength * scale;
    const h = plotWidth * scale;
    const x = (760 - w) / 2;
    const y = 65 + (310 - h) / 2;
    const count = integer('footing_count', 4);
    const cols = Math.max(1, Math.ceil(Math.sqrt(count)));
    const rows = Math.ceil(count / cols);
    const fw = Math.min(110, Math.max(12, meters('footing_length') / (plotLength * unitFactor) * w));
    const fd = Math.min(110, Math.max(12, meters('footing_width') / (plotWidth * unitFactor) * h));
    const cw = Math.max(7, meters('column_width') / (plotLength * unitFactor) * w);
    const cd = Math.max(7, meters('column_depth') / (plotWidth * unitFactor) * h);
    let marks = '';
    const roomCounts = roomContext.rooms || {};
    const roomDimensions = roomContext.room_dimensions || {};
    const roomPlacements = roomContext.layout_data || {};
    Object.entries(roomCounts).forEach(([roomName, roomCount]) => {
      const positions = Array.isArray(roomPlacements[roomName]) ? roomPlacements[roomName] : [];
      const dims = roomDimensions[roomName] || {};
      positions.slice(0, Number(roomCount) || 0).forEach((position) => {
        const rx = x + Math.max(0, Math.min(1, (Number(position.x) - 30) / 660)) * w;
        const ry = y + Math.max(0, Math.min(1, (Number(position.y) - 30) / 440)) * h;
        const rw = Math.max(4, Number(dims.width || 0) / plotWidth * w);
        const rh = Math.max(4, Number(dims.depth || 0) / plotLength * h);
        marks += `<rect x="${rx}" y="${ry}" width="${Math.min(rw, x + w - rx)}" height="${Math.min(rh, y + h - ry)}" fill="#dbeaf3" fill-opacity=".26" stroke="#5483a2" stroke-dasharray="5 4"/><text x="${rx + 4}" y="${ry + 14}" class="muted">${escapeHtml(roomName)}</text>`;
      });
    });
    for (let i = 0; i < count; i += 1) {
      const cx = x + (i % cols + 0.5) * w / cols;
      const cy = y + (Math.floor(i / cols) + 0.5) * h / rows;
      marks += `<rect x="${cx - fw / 2}" y="${cy - fd / 2}" width="${fw}" height="${fd}" class="concrete"/><rect x="${cx - cw / 2}" y="${cy - cd / 2}" width="${cw}" height="${cd}" class="column"/>`;
    }
    return `${svgStyle}<text x="34" y="34" class="label">${escapeHtml(labels[state.module])} · schematic plan</text><rect x="${x}" y="${y}" width="${w}" height="${h}" class="outline"/>${marks}${dimensionText(x, y + h, x + w, y + h, `${fmt(plotLength)} ${unit}`)}${dimensionText(x + w, y, x + w, y + h, `${fmt(plotWidth)} ${unit}`, 24)}<text x="40" y="430" class="muted">Footing marks use evenly distributed schematic positions; verify actual grid coordinates.</text><text x="${x + 8}" y="${y + 18}" class="muted">PLOT LIMIT</text>`;
  };

  const drawSection = () => {
    const baseY = 355;
    const footingW = 245;
    const footingH = Math.max(25, Math.min(85, meters('footing_depth') * 90));
    const pccH = Math.max(3, Math.min(20, meters('pcc_thickness') * 90));
    const colW = 60;
    const colH = 155;
    const x = (760 - footingW) / 2;
    const columnX = (760 - colW) / 2;
    let rebar = '';
    const bars = Math.max(2, Math.min(20, Math.floor(number('footing_main_bars_x', 8))));
    for (let index = 0; index < bars; index += 1) {
      const bx = x + (index + 0.5) * footingW / bars;
      rebar += `<circle cx="${bx}" cy="${baseY - 7}" r="3.3" class="steel"/>`;
    }
    return `${svgStyle}<text x="34" y="34" class="label">Foundation section · reinforcement schematic</text><line x1="120" y1="${baseY}" x2="640" y2="${baseY}" class="section-line"/><rect x="${x}" y="${baseY - footingH}" width="${footingW}" height="${footingH}" class="concrete"/><rect x="${x}" y="${baseY}" width="${footingW}" height="${pccH}" class="wall"/><rect x="${columnX}" y="${baseY - footingH - colH}" width="${colW}" height="${colH}" class="column"/>${rebar}${dimensionText(x, baseY, x + footingW, baseY, `${fmt(number('footing_length'))} ${unit}`)}${dimensionText(x + footingW, baseY - footingH, x + footingW, baseY, `${fmt(number('footing_depth'))} ${unit}`, 22)}<text x="${columnX + colW + 12}" y="${baseY - footingH - colH / 2}" class="label">Column</text><text x="${x}" y="${baseY + 36}" class="muted">PCC ${fmt(number('pcc_thickness'))} ${unit}</text><text x="40" y="430" class="muted">Bars are shown schematically; cover, anchorage, bends and design checks are not performed.</text>`;
  };

  const drawFront = () => {
    const floorHeight = meters('column_height', lengthDefault(3));
    const maxHeight = Math.max(floorHeight * floors, 0.5);
    const w = 470;
    const h = Math.min(280, maxHeight * 50);
    const x = 145;
    const base = 370;
    const floorGap = h / floors;
    const columnCount = Math.min(integer('column_count', 4), 12);
    let structure = '';
    for (let i = 0; i < columnCount; i += 1) {
      const cx = x + (i + 0.5) * w / columnCount;
      structure += `<rect x="${cx - 6}" y="${base - h}" width="12" height="${h}" class="column"/>`;
    }
    for (let floor = 0; floor <= floors; floor += 1) {
      const beamY = base - floor * floorGap;
      structure += `<rect x="${x}" y="${beamY - 8}" width="${w}" height="12" class="concrete"/>`;
    }
    return `${svgStyle}<text x="34" y="34" class="label">Front elevation · ${floors} floor(s)</text><line x1="${x - 30}" y1="${base}" x2="${x + w + 35}" y2="${base}" class="section-line"/><rect x="${x}" y="${base + 7}" width="${w}" height="35" class="concrete"/>${structure}<text x="${x}" y="${base + 62}" class="muted">Foundation line · plinth · beams · floor slabs</text>${dimensionText(x + w + 15, base, x + w + 15, base - h, `${fmt(maxHeight / unitFactor)} ${unit}`, 18)}<text x="40" y="430" class="muted">Frame positions are an illustrative distribution from the entered column count.</text>`;
  };

  const drawReinforcement = () => {
    const baseY = 350;
    const x = 245;
    const width = 270;
    const height = 145;
    const count = Math.max(2, Math.min(14, integer('footing_main_bars_x', 8)));
    let bars = '';
    for (let i = 0; i < count; i += 1) {
      const bx = x + 20 + i * (width - 40) / (count - 1);
      bars += `<circle cx="${bx}" cy="${baseY - 18}" r="4" class="steel"/>`;
    }
    return `${svgStyle}<text x="34" y="34" class="label">Reinforcement detail · user-entered reference</text><rect x="${x}" y="${baseY - height}" width="${width}" height="${height}" rx="7" class="concrete"/><rect x="${x + width / 2 - 31}" y="${baseY - height - 90}" width="62" height="90" class="column"/><line x1="${x + 8}" y1="${baseY - 11}" x2="${x + width - 8}" y2="${baseY - 11}" class="steel"/>${bars}<text x="${x + width + 15}" y="${baseY - 55}" class="label">Ø${fmt(number('footing_bar_diameter'), 0)} @ ${fmt(number('footing_bar_spacing'), 0)} mm (entered)</text><text x="${x + width + 15}" y="${baseY - 34}" class="muted">No code check / BBS verification</text>${dimensionText(x, baseY, x + width, baseY, `${fmt(number('footing_length'))} ${unit}`)}<text x="40" y="430" class="muted">This diagram does not calculate required reinforcement or confirm development length / cover.</text>`;
  };

  const drawModuleSchematic = () => {
    const components = {
      plinth: {
        planLength: plotLength, planWidth: plotWidth,
        width: number('plinth_beam_width'), depth: number('plinth_beam_depth'),
        height: number('plinth_height'), count: 1,
        bars: number('plinth_beam_main_bars'), diameter: number('plinth_beam_bar_diameter'),
        spacing: number('plinth_beam_stirrup_spacing'),
      },
      column: {
        planLength: number('column_width'), planWidth: number('column_depth'),
        width: number('column_width'), depth: number('column_depth'),
        height: number('column_height'), count: integer('column_count', 4),
        bars: number('column_main_bars'), diameter: number('column_bar_diameter'),
        spacing: number('column_stirrup_spacing'),
      },
      beam: {
        planLength: number('beam_length'), planWidth: number('beam_width'),
        width: number('beam_width'), depth: number('beam_depth'),
        height: number('beam_depth'), count: integer('beam_count', 4),
        bars: number('beam_main_bars'), diameter: number('beam_bar_diameter'),
        spacing: number('beam_stirrup_spacing'),
      },
      slab: {
        planLength: number('slab_length'), planWidth: number('slab_width'),
        width: number('slab_length'), depth: number('slab_thickness'),
        height: number('slab_thickness'), count: 1,
        bars: 0, diameter: number('slab_main_bar_diameter'),
        spacing: number('slab_distribution_bar_spacing'),
      },
      wall: {
        planLength: number('wall_length'), planWidth: number('wall_thickness'),
        width: number('wall_thickness'), depth: number('wall_thickness'),
        height: number('wall_height'), count: 1,
        bars: 0, diameter: 0, spacing: 0,
      },
      staircase: {
        planLength: number('stair_flight_length'), planWidth: number('stair_width'),
        width: number('stair_width'), depth: number('stair_waist_thickness'),
        height: number('stair_floor_height'), count: integer('stair_flights', 2),
        bars: 0, diameter: 0, spacing: 0,
      },
      reinforcement: {
        planLength: number('column_width'), planWidth: number('column_depth'),
        width: number('column_width'), depth: number('column_depth'),
        height: number('column_height'), count: integer('column_count', 4),
        bars: number('column_main_bars'), diameter: number('column_bar_diameter'),
        spacing: number('column_stirrup_spacing'),
      },
      simulation: {
        planLength: plotLength, planWidth: plotWidth,
        width: plotLength, depth: plotWidth,
        height: number('column_height', lengthDefault(3)) * floors, count: floors,
        bars: 0, diameter: 0, spacing: 0,
      },
    };
    const component = components[state.module];
    if (!component) return '';

    const title = escapeHtml(labels[state.module]);
    const x = 155;
    const baseY = 355;
    const horizontal = Math.max(35, Math.min(470, component.planLength * 24));
    const vertical = Math.max(28, Math.min(255, component.planWidth * 24));
    const left = (760 - horizontal) / 2;
    const top = 92 + (260 - vertical) / 2;
    let details = '';
    let dimensionX1 = x;
    let dimensionX2 = x + 450;
    let dimensionY1 = baseY;
    let dimensionY2 = 120;
    let dimensionWidth = component.width;
    let dimensionHeight = state.module === 'beam' ? component.depth : component.height;

    if (state.view === 'top') {
      if (state.module === 'plinth') {
        details = `<rect x="${left + 14}" y="${top + 14}" width="${horizontal - 28}" height="${vertical - 28}" class="concrete"/>`;
      } else if (state.module === 'column' || state.module === 'reinforcement') {
        const marks = Math.min(component.count, 100);
        const columns = Math.max(1, Math.ceil(Math.sqrt(marks)));
        const rows = Math.ceil(marks / columns);
        for (let index = 0; index < marks; index += 1) {
          const cx = left + (index % columns + 0.5) * horizontal / columns;
          const cy = top + (Math.floor(index / columns) + 0.5) * vertical / rows;
          details += `<rect x="${cx - 9}" y="${cy - 9}" width="18" height="18" class="column"/>`;
        }
      } else if (state.module === 'beam') {
        details = `<line x1="${left + 10}" y1="${top + vertical / 2}" x2="${left + horizontal - 10}" y2="${top + vertical / 2}" class="section-line"/>`;
      } else if (state.module === 'slab') {
        const openingWidth = Math.min(horizontal - 20, number('slab_opening_length') * 24);
        const openingHeight = Math.min(vertical - 20, number('slab_opening_width') * 24);
        if (openingWidth > 0 && openingHeight > 0) {
          details = `<rect x="${left + (horizontal - openingWidth) / 2}" y="${top + (vertical - openingHeight) / 2}" width="${openingWidth}" height="${openingHeight}" class="wall"/><text x="${left + horizontal / 2}" y="${top + vertical / 2}" text-anchor="middle" class="muted">Opening</text>`;
        }
      } else if (state.module === 'wall') {
        details = `<line x1="${left + horizontal * 0.34}" y1="${top}" x2="${left + horizontal * 0.34}" y2="${top + vertical}" class="section-line"/><line x1="${left + horizontal * 0.7}" y1="${top}" x2="${left + horizontal * 0.7}" y2="${top + vertical}" class="section-line"/>`;
      } else if (state.module === 'staircase') {
        const steps = Math.max(2, Math.min(20, Math.floor(number('stair_flight_length') / Math.max(number('stair_tread'), 0.1))));
        for (let index = 1; index < steps; index += 1) {
          const stepX = left + index * horizontal / steps;
          details += `<line x1="${stepX}" y1="${top}" x2="${stepX}" y2="${top + vertical}" class="section-line"/>`;
        }
      }
      return `${svgStyle}<text x="34" y="34" class="label">${title} · schematic plan</text><rect x="${left}" y="${top}" width="${horizontal}" height="${vertical}" class="outline"/>${details}${dimensionText(left, top + vertical, left + horizontal, top + vertical, `${fmt(component.planLength)} ${unit}`)}${dimensionText(left + horizontal, top, left + horizontal, top + vertical, `${fmt(component.planWidth)} ${unit}`, 24)}<text x="40" y="430" class="muted">Plan geometry uses entered dimensions; layout and detailing remain schematic.</text>`;
    }

    if (state.view === 'reinforcement') {
      const barCount = Math.max(0, Math.min(20, Math.floor(component.bars)));
      const cageWidth = Math.max(110, Math.min(310, component.width * 110));
      const cageHeight = Math.max(75, Math.min(205, component.height * 55));
      const cageX = (760 - cageWidth) / 2;
      const cageTop = baseY - cageHeight;
      for (let index = 0; index < barCount; index += 1) {
        const bx = cageX + 12 + index * (cageWidth - 24) / Math.max(1, barCount - 1);
        details += `<circle cx="${bx}" cy="${baseY - 10}" r="4" class="steel"/>`;
      }
      let reinforcementLabel = `${fmt(component.bars, 0)} main bars entered · Ø${fmt(component.diameter, 0)} mm · stirrups @ ${fmt(component.spacing, 0)} mm`;
      if (state.module === 'slab') {
        reinforcementLabel = `Main Ø${fmt(number('slab_main_bar_diameter'), 0)} @ ${fmt(number('slab_main_bar_spacing'), 0)} mm · distribution Ø${fmt(number('slab_distribution_bar_diameter'), 0)} @ ${fmt(number('slab_distribution_bar_spacing'), 0)} mm`;
      } else if (state.module === 'wall') {
        reinforcementLabel = `${nonNegativeInteger('door_count')} door and ${nonNegativeInteger('window_count')} window opening(s)`;
      } else if (state.module === 'staircase') {
        reinforcementLabel = 'Reinforcement not entered';
      }
      return `${svgStyle}<text x="34" y="34" class="label">${title} · reinforcement reference</text><rect x="${cageX}" y="${cageTop}" width="${cageWidth}" height="${cageHeight}" rx="6" class="concrete"/><line x1="${cageX + 8}" y1="${baseY - 10}" x2="${cageX + cageWidth - 8}" y2="${baseY - 10}" class="steel"/>${details}<text x="${cageX}" y="${cageTop - 16}" class="label">${escapeHtml(reinforcementLabel)}</text><text x="40" y="430" class="muted">Schematic user-entered reinforcement only; no capacity, anchorage, cover or code checks.</text>`;
    }

    if (state.module === 'staircase') {
      const steps = Math.max(2, Math.min(20, Math.floor(number('stair_floor_height') / Math.max(number('stair_riser'), 0.05))));
      let staircase = '';
      for (let index = 0; index < steps; index += 1) {
        const stepX = x + index * 350 / steps;
        const stepY = baseY - (index + 1) * 195 / steps;
        staircase += `<path d="M${stepX} ${stepY}h${350 / steps}v${195 / steps}" fill="none" stroke="#55738d" stroke-width="4"/>`;
      }
      details = `${staircase}<line x1="${x}" y1="${baseY}" x2="${x + 350}" y2="${baseY - 195}" class="steel"/>`;
      dimensionX1 = x;
      dimensionX2 = x + 350;
      dimensionY1 = baseY;
      dimensionY2 = baseY - 195;
      dimensionWidth = component.planLength;
      dimensionHeight = component.height;
    } else {
      const frontLength = state.view === 'front' && ['plinth', 'beam', 'slab', 'wall'].includes(state.module);
      const displayedWidth = frontLength ? component.planLength : component.width;
      const shapeWidth = Math.max(36, Math.min(430, displayedWidth * 24));
      const shapeHeight = Math.max(22, Math.min(230, (state.module === 'slab' ? component.height : component.height) * 70));
      const shapeX = (760 - shapeWidth) / 2;
      const shapeY = baseY - shapeHeight;
      const style = state.module === 'wall' ? 'wall' : state.module === 'column' || state.module === 'reinforcement' ? 'column' : 'concrete';
      details = `<rect x="${shapeX}" y="${shapeY}" width="${shapeWidth}" height="${shapeHeight}" class="${style}"/>`;
      dimensionX1 = shapeX;
      dimensionX2 = shapeX + shapeWidth;
      dimensionY1 = baseY;
      dimensionY2 = shapeY;
      dimensionWidth = frontLength ? component.planLength : component.width;
      dimensionHeight = state.module === 'beam' ? component.depth : component.height;
      if (state.module === 'wall') {
        const doorWidth = Math.min(shapeWidth / 3, number('door_width') * 55);
        const doorHeight = Math.min(shapeHeight, number('door_height') * 55);
        const windowWidth = Math.min(shapeWidth / 4, number('window_width') * 45);
        const windowHeight = Math.min(shapeHeight / 3, number('window_height') * 35);
        details += `<rect x="${shapeX + shapeWidth * 0.22}" y="${shapeY + shapeHeight - doorHeight}" width="${doorWidth}" height="${doorHeight}" class="outline"/><rect x="${shapeX + shapeWidth * 0.65}" y="${shapeY + shapeHeight * 0.28}" width="${windowWidth}" height="${windowHeight}" class="outline"/>`;
      }
      if (state.module === 'plinth') {
        details += `<line x1="${shapeX - 28}" y1="${shapeY + shapeHeight * 0.55}" x2="${shapeX + shapeWidth + 28}" y2="${shapeY + shapeHeight * 0.55}" class="steel"/><text x="${shapeX + shapeWidth + 34}" y="${shapeY + shapeHeight * 0.55}" class="muted">DPC</text>`;
      }
      if (state.module === 'column' || state.module === 'reinforcement') {
        const marks = Math.min(component.count, 100);
        const columns = Math.max(1, Math.ceil(Math.sqrt(marks)));
        for (let index = 0; index < marks; index += 1) {
          const cx = shapeX + (index % columns + 0.5) * shapeWidth / columns;
          details += `<line x1="${cx}" y1="${shapeY}" x2="${cx}" y2="${baseY}" class="steel"/>`;
        }
      }
    }
    const titleText = state.view === 'front' ? 'front elevation' : 'section';
    return `${svgStyle}<text x="34" y="34" class="label">${title} · ${titleText} schematic</text><line x1="120" y1="${baseY}" x2="640" y2="${baseY}" class="section-line"/>${details}${dimensionText(dimensionX1, dimensionY1, dimensionX2, dimensionY1, `${fmt(dimensionWidth)} ${unit}`)}${dimensionText(dimensionX2, dimensionY1, dimensionX2, dimensionY2, `${fmt(dimensionHeight)} ${unit}`, 20)}<text x="40" y="430" class="muted">Illustrative dimensions only; no structural adequacy or code compliance is implied.</text>`;
  };

  const renderDrawing = () => {
    const shapes = {
      top: drawTop,
      section: drawSection,
      front: drawFront,
      reinforcement: drawReinforcement,
    };
    drawing.innerHTML = state.module === 'foundation' ? shapes[state.view]() : drawModuleSchematic();
    document.querySelectorAll('.studio-view[data-view]').forEach((button) => {
      button.classList.toggle('is-active', button.dataset.view === state.view);
    });
    document.getElementById('drawing-view-caption').textContent = state.view.replace('_', ' ').toUpperCase();
  };

  const columnPositions = (length, width, count) => {
    const cols = Math.max(1, Math.ceil(Math.sqrt(count)));
    const rows = Math.ceil(count / cols);
    const offsetX = Math.min(meters('column_origin_x'), length * 0.45);
    const offsetZ = Math.min(meters('column_origin_y'), width * 0.45);
    const usableX = Math.max(length - offsetX * 2, length * 0.1);
    const usableZ = Math.max(width - offsetZ * 2, width * 0.1);
    const positions = [];
    for (let i = 0; i < count; i += 1) {
      if (values.column_layout === 'perimeter' && count >= 4) {
        const perimeter = [
          [offsetX, offsetZ], [length - offsetX, offsetZ],
          [length - offsetX, width - offsetZ], [offsetX, width - offsetZ],
        ];
        if (i < perimeter.length) positions.push(perimeter[i]);
        else positions.push([
          offsetX + (i % (cols - 1 || 1)) * usableX / Math.max(cols - 1, 1),
          offsetZ + (Math.floor(i / cols) % (rows - 1 || 1)) * usableZ / Math.max(rows - 1, 1),
        ]);
      } else {
        positions.push([
          offsetX + ((i % cols) + 0.5) * usableX / cols,
          offsetZ + (Math.floor(i / cols) + 0.5) * usableZ / rows,
        ]);
      }
    }
    return positions;
  };

  const rebuildModel = () => {
    if (!window.THREE) {
      document.getElementById('three-fallback').hidden = false;
      return;
    }
    if (!state.three) {
      try {
        initializeThree();
      } catch (error) {
        console.error('The 3D structural preview could not be initialized.', error);
        document.getElementById('three-fallback').hidden = false;
        document.getElementById('three-fallback').textContent = '3D preview could not be initialized in this browser. Use the SVG/PNG drawings instead.';
        return;
      }
    }
    const { THREE, scene, root: modelRoot } = state.three;
    while (modelRoot.children.length) {
      const object = modelRoot.children[modelRoot.children.length - 1];
      modelRoot.remove(object);
      object.geometry?.dispose();
      if (Array.isArray(object.material)) object.material.forEach((item) => item.dispose());
      else object.material?.dispose();
    }
    state.sceneObjects = [];
    const length = Math.max(meters('slab_length', plotLength), 1);
    const width = Math.max(meters('slab_width', plotWidth), 1);
    const foundationDepth = Math.max(meters('foundation_depth'), meters('footing_depth') + meters('pcc_thickness'));
    const footingLength = meters('footing_length');
    const footingWidth = meters('footing_width');
    const footingDepth = meters('footing_depth');
    const pcc = meters('pcc_thickness');
    const colW = meters('column_width');
    const colD = meters('column_depth');
    const floorHeight = meters('column_height', lengthDefault(3));
    const plinthHeight = meters('plinth_height');
    const beamWidth = meters('beam_width');
    const beamDepth = meters('beam_depth');
    const slabDepth = meters('slab_thickness');
    const count = Math.min(integer('column_count', 4), 100);
    const positions = columnPositions(length, width, count);
    const columns = Math.max(1, Math.ceil(Math.sqrt(count)));
    const rows = Math.ceil(count / columns);
    const color = (hex, opacity = 1) => new THREE.MeshStandardMaterial({ color: hex, roughness: 0.76, transparent: opacity < 1, opacity, depthWrite: opacity >= 1 });
    const addBox = (category, stage, x, y, z, sx, sy, sz, hex, opacity = 1) => {
      const geometry = new THREE.BoxGeometry(Math.max(sx, 0.02), Math.max(sy, 0.02), Math.max(sz, 0.02));
      const mesh = new THREE.Mesh(geometry, color(hex, opacity));
      mesh.position.set(x, y, z);
      mesh.userData = { category, stage };
      modelRoot.add(mesh);
      state.sceneObjects.push(mesh);
    };
    const footingCount = Math.min(integer('footing_count', 4), 100);
    const footingPoints = positions.slice(0, footingCount);
    if (values.footing_type === 'raft') {
      const raftLength = Math.min(footingLength, length);
      const raftWidth = Math.min(footingWidth, width);
      addBox('excavation', 0, length / 2, -foundationDepth / 2, width / 2, raftLength + 0.4, foundationDepth, raftWidth + 0.4, '#a98e6a', 0.20);
      if (pcc > 0) addBox('pcc', 1, length / 2, -foundationDepth + pcc / 2, width / 2, raftLength + 0.12, pcc, raftWidth + 0.12, '#b8c5ce');
      addBox('footing', 2, length / 2, -foundationDepth + pcc + footingDepth / 2, width / 2, raftLength, footingDepth, raftWidth, '#8fa9bd');
    } else if (values.footing_type === 'strip') {
      const stripLength = Math.min(footingLength, length);
      const stripWidth = Math.min(footingWidth, width);
      [
        [length / 2, stripWidth / 2, stripLength, footingDepth, stripWidth],
        [length / 2, width - stripWidth / 2, stripLength, footingDepth, stripWidth],
        [stripWidth / 2, width / 2, stripWidth, footingDepth, stripLength],
        [length - stripWidth / 2, width / 2, stripWidth, footingDepth, stripLength],
      ].forEach(([x, z, sx, sy, sz]) => {
        addBox('excavation', 0, x, -foundationDepth / 2, z, sx + 0.4, foundationDepth, sz + 0.4, '#a98e6a', 0.20);
        if (pcc > 0) addBox('pcc', 1, x, -foundationDepth + pcc / 2, z, sx + 0.12, pcc, sz + 0.12, '#b8c5ce');
        addBox('footing', 2, x, -foundationDepth + pcc + footingDepth / 2, z, sx, footingDepth, sz, '#8fa9bd');
      });
    } else {
      footingPoints.forEach(([x, z]) => {
        addBox('excavation', 0, x, -foundationDepth / 2, z, footingLength + 0.55, foundationDepth, footingWidth + 0.55, '#a98e6a', 0.20);
        if (pcc > 0) addBox('pcc', 1, x, -foundationDepth + pcc / 2, z, footingLength + 0.16, pcc, footingWidth + 0.16, '#b8c5ce');
        addBox('footing', 2, x, -foundationDepth + pcc + footingDepth / 2, z, footingLength, footingDepth, footingWidth, '#8fa9bd');
      });
    }
    footingPoints.forEach(([x, z]) => {
      if (values.footing_type === 'raft' || values.footing_type === 'strip') return;
      const footingTop = -foundationDepth + pcc + footingDepth;
      const columnHeight = Math.max(plinthHeight - footingTop, 0.1);
      addBox('columns', 3, x, footingTop + columnHeight / 2, z,
        colW, columnHeight, colD, '#557b98');
    });
    if (values.footing_type === 'raft' || values.footing_type === 'strip') {
      positions.forEach(([x, z]) => {
        const footingTop = -foundationDepth + pcc + footingDepth;
        const columnHeight = Math.max(plinthHeight - footingTop, 0.1);
        addBox('columns', 3, x, footingTop + columnHeight / 2, z,
          colW, columnHeight, colD, '#557b98');
      });
    }
    const beamY = plinthHeight;
    addBox('beams', 4, length / 2, beamY, 0, length, meters('plinth_beam_depth'), meters('plinth_beam_width'), '#6888a0');
    addBox('beams', 4, length / 2, beamY, width, length, meters('plinth_beam_depth'), meters('plinth_beam_width'), '#6888a0');
    addBox('beams', 4, 0, beamY, width / 2, meters('plinth_beam_width'), meters('plinth_beam_depth'), width, '#6888a0');
    addBox('beams', 4, length, beamY, width / 2, meters('plinth_beam_width'), meters('plinth_beam_depth'), width, '#6888a0');
    const wallHeight = Math.max(meters('wall_height'), 0.2);
    const wallThickness = Math.max(meters('wall_thickness'), 0.1);
    const addWallWithOpenings = (z, openingWidth, openingHeight, openingCount, sillHeight) => {
      const count = Math.min(nonNegativeInteger(openingCount), 24);
      const widthEach = Math.min(meters(openingWidth), length / Math.max(count, 1) * 0.8);
      const heightEach = Math.min(meters(openingHeight), wallHeight);
      const sill = Math.min(meters(sillHeight), Math.max(wallHeight - heightEach, 0));
      const openings = Array.from({ length: count }, (_, index) => {
        const center = length * (index + 1) / (count + 1);
        return { left: center - widthEach / 2, right: center + widthEach / 2 };
      });
      let cursor = 0;
      openings.forEach((opening) => {
        if (opening.left > cursor) {
          addBox('walls', 5, (cursor + opening.left) / 2, plinthHeight + wallHeight / 2, z,
            opening.left - cursor, wallHeight, wallThickness, '#b7c5cf');
        }
        if (sill > 0) {
          addBox('walls', 5, (opening.left + opening.right) / 2, plinthHeight + sill / 2, z,
            opening.right - opening.left, sill, wallThickness, '#b7c5cf');
        }
        if (sill + heightEach < wallHeight) {
          addBox('walls', 5, (opening.left + opening.right) / 2,
            plinthHeight + sill + (wallHeight - sill - heightEach) / 2, z,
            opening.right - opening.left, wallHeight - sill - heightEach, wallThickness, '#b7c5cf');
        }
        cursor = opening.right;
      });
      if (cursor < length) {
        addBox('walls', 5, (cursor + length) / 2, plinthHeight + wallHeight / 2, z,
          length - cursor, wallHeight, wallThickness, '#b7c5cf');
      }
    };
    addWallWithOpenings(0, 'door_width', 'door_height', 'door_count', 0);
    addWallWithOpenings(width - wallThickness / 2, 'window_width', 'window_height', 'window_count', 'window_sill_height');
    addBox('walls', 5, wallThickness / 2, plinthHeight + wallHeight / 2, width / 2, wallThickness, wallHeight, width, '#b7c5cf');
    addBox('walls', 5, length - wallThickness / 2, plinthHeight + wallHeight / 2, width / 2, wallThickness, wallHeight, width, '#b7c5cf');
    Object.entries(roomContext.rooms || {}).forEach(([roomName, roomCount]) => {
      const roomSize = (roomContext.room_dimensions || {})[roomName] || {};
      const placements = (roomContext.layout_data || {})[roomName] || [];
      placements.slice(0, Number(roomCount) || 0).forEach((position) => {
        const roomLength = Math.max(0.1, Number(roomSize.depth || 0) * unitFactor);
        const roomWidth = Math.max(0.1, Number(roomSize.width || 0) * unitFactor);
        const x = Math.max(0, Math.min(length - roomLength, (Number(position.y) - 30) / 440 * length));
        const z = Math.max(0, Math.min(width - roomWidth, (Number(position.x) - 30) / 660 * width));
        const roomHeight = Math.min(meters('wall_height'), Math.max(0.1, Number(roomSize.height || 0) * unitFactor));
        const thickness = Math.min(wallThickness, 0.18);
        addBox('walls', 5, x + roomLength / 2, plinthHeight + roomHeight / 2, z,
          roomLength, roomHeight, thickness, '#91a9bb');
        addBox('walls', 5, x + roomLength / 2, plinthHeight + roomHeight / 2, z + roomWidth,
          roomLength, roomHeight, thickness, '#91a9bb');
        addBox('walls', 5, x, plinthHeight + roomHeight / 2, z + roomWidth / 2,
          thickness, roomHeight, roomWidth, '#91a9bb');
        addBox('walls', 5, x + roomLength, plinthHeight + roomHeight / 2, z + roomWidth / 2,
          thickness, roomHeight, roomWidth, '#91a9bb');
      });
    });
    const dpc = meters('dpc_thickness');
    if (dpc > 0) addBox('walls', 4, length / 2, plinthHeight + dpc / 2, width / 2, length, dpc, width, '#d2bd98');
    const fillDepth = meters('ground_fill_depth');
    if (fillDepth > 0) addBox('slab', 4, length / 2, fillDepth / 2, width / 2, length, fillDepth, width, '#d0c4ae', 0.75);
    const plinthPcc = meters('plinth_pcc_thickness');
    if (plinthPcc > 0) addBox('pcc', 4, length / 2, fillDepth + plinthPcc / 2, width / 2, length, plinthPcc, width, '#b8c5ce');
    positions.forEach(([x, z]) => {
      const colHeight = Math.max(floorHeight * floors, 0.2);
      addBox('columns', 6, x, plinthHeight + colHeight / 2, z, colW, colHeight, colD, '#557b98');
    });
    for (let floor = 1; floor <= floors; floor += 1) {
      const level = plinthHeight + floor * floorHeight - beamDepth / 2;
      addBox('beams', 7, length / 2, level, 0, length, beamDepth, beamWidth, '#597a94');
      addBox('beams', 7, length / 2, level, width, length, beamDepth, beamWidth, '#597a94');
      addBox('beams', 7, 0, level, width / 2, beamWidth, beamDepth, width, '#597a94');
      addBox('beams', 7, length, level, width / 2, beamWidth, beamDepth, width, '#597a94');
      const openingLength = Math.min(meters('slab_opening_length'), length);
      const openingWidth = Math.min(meters('slab_opening_width'), width);
      const slabY = level + beamDepth / 2 + slabDepth / 2;
      if (openingLength > 0 && openingWidth > 0) {
        const sideLength = (length - openingLength) / 2;
        const sideWidth = (width - openingWidth) / 2;
        if (sideLength > 0) {
          addBox('slab', 8, sideLength / 2, slabY, width / 2, sideLength, slabDepth, width, '#91aabc');
          addBox('slab', 8, length - sideLength / 2, slabY, width / 2, sideLength, slabDepth, width, '#91aabc');
        }
        if (sideWidth > 0) {
          addBox('slab', 8, length / 2, slabY, sideWidth / 2, openingLength, slabDepth, sideWidth, '#91aabc');
          addBox('slab', 8, length / 2, slabY, width - sideWidth / 2, openingLength, slabDepth, sideWidth, '#91aabc');
        }
      } else {
        addBox('slab', 8, length / 2, slabY, width / 2, length, slabDepth, width, '#91aabc');
      }
    }
    const stairSteps = Math.max(1, Math.min(30, Math.ceil(meters('stair_floor_height') / Math.max(meters('stair_riser'), 0.05))));
    const stairRise = meters('stair_floor_height') / stairSteps;
    const stairRun = Math.min(meters('stair_tread'), meters('stair_flight_length') / stairSteps);
    const stairWidth = meters('stair_width');
    for (let floor = 0; floor < Math.max(floors - 1, 1); floor += 1) {
      for (let step = 0; step < stairSteps; step += 1) {
        addBox('slab', 8, Math.min(length, 0.2 + (step + 0.5) * stairRun),
          plinthHeight + floor * floorHeight + (step + 0.5) * stairRise,
          Math.min(width, 0.2 + stairWidth / 2), stairRun, stairRise, stairWidth, '#8ba3b7');
      }
    }
    addBox('slab', 9, length / 2, plinthHeight + floors * floorHeight + 0.12, width / 2, length + 0.2, 0.18, width + 0.2, '#c2d0da');
    addBox('slab', 10, length / 2, plinthHeight + floors * floorHeight + 0.22, width / 2, length + 0.22, 0.025, width + 0.22, '#d6dfe5');
    const stage = state.stage;
    const visibleCategories = new Set(
      Array.from(document.querySelectorAll('.simulation-properties input[data-element]:checked'))
        .map((input) => input.dataset.element),
    );
    const categoryMap = {
      excavation: 'excavation', pcc: 'pcc', footing: 'footing',
      columns: 'columns', beams: 'beams', slab: 'slab', walls: 'walls',
    };
    state.sceneObjects.forEach((object) => {
      object.visible = object.userData.stage <= stage && visibleCategories.has(categoryMap[object.userData.category]);
    });
    scene.updateMatrixWorld(true);
    state.three.renderer.render(scene, state.three.camera);
  };

  const initializeThree = () => {
    const THREE = window.THREE;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#edf3f7');
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace || renderer.outputColorSpace;
    canvasHost.appendChild(renderer.domElement);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 10000);
    const modelRoot = new THREE.Group();
    scene.add(modelRoot);
    scene.add(new THREE.HemisphereLight('#ffffff', '#8297a9', 2.0));
    const keyLight = new THREE.DirectionalLight('#ffffff', 2.2);
    keyLight.position.set(1, 2, 1);
    scene.add(keyLight);
    const grid = new THREE.GridHelper(Math.max(plotLength * unitFactor, plotWidth * unitFactor) * 1.6, 22, '#9eafbc', '#d2dde5');
    grid.position.y = -0.02;
    scene.add(grid);
    state.three = { THREE, scene, renderer, camera, root: modelRoot, grid };
    const target = new THREE.Vector3(meters('slab_length') / 2, meters('column_height') * floors / 2, meters('slab_width') / 2);
    state.three.target = target;
    state.cameraOrbit.distance = Math.max(meters('slab_length'), meters('slab_width')) * 2.5;

    const resize = () => {
      const width = Math.max(canvasHost.clientWidth, 1);
      const height = Math.max(canvasHost.clientHeight, 1);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.render(scene, camera);
    };
    if (window.ResizeObserver) new ResizeObserver(resize).observe(canvasHost);
    window.addEventListener('resize', resize);

    const updateCamera = () => {
      const orbit = state.cameraOrbit;
      const horizontal = orbit.distance * Math.cos(orbit.elevation);
      camera.position.set(
        target.x + horizontal * Math.sin(orbit.azimuth),
        target.y + orbit.distance * Math.sin(orbit.elevation),
        target.z + horizontal * Math.cos(orbit.azimuth),
      );
      camera.lookAt(target);
      renderer.render(scene, camera);
    };
    state.three.updateCamera = updateCamera;
    renderer.domElement.addEventListener('pointerdown', (event) => {
      renderer.domElement.setPointerCapture(event.pointerId);
      renderer.domElement.dataset.dragX = String(event.clientX);
      renderer.domElement.dataset.dragY = String(event.clientY);
    });
    renderer.domElement.addEventListener('pointermove', (event) => {
      if (!renderer.domElement.hasPointerCapture(event.pointerId)) return;
      const oldX = Number(renderer.domElement.dataset.dragX);
      const oldY = Number(renderer.domElement.dataset.dragY);
      state.cameraOrbit.azimuth -= (event.clientX - oldX) * 0.008;
      state.cameraOrbit.elevation = Math.max(-0.2, Math.min(1.35, state.cameraOrbit.elevation + (event.clientY - oldY) * 0.006));
      renderer.domElement.dataset.dragX = String(event.clientX);
      renderer.domElement.dataset.dragY = String(event.clientY);
      updateCamera();
    });
    renderer.domElement.addEventListener('wheel', (event) => {
      event.preventDefault();
      state.cameraOrbit.distance = Math.max(1, Math.min(5000, state.cameraOrbit.distance * (event.deltaY > 0 ? 1.1 : 0.9)));
      updateCamera();
    }, { passive: false });
    try {
      resize();
      updateCamera();
    } catch (error) {
      console.error('The 3D structural preview could not be initialized.', error);
      document.getElementById('three-fallback').hidden = false;
      document.getElementById('three-fallback').textContent = '3D preview could not be initialized in this browser. Use the SVG/PNG drawings instead.';
    }
  };

  const updateStage = (stage) => {
    state.stage = Math.max(0, Math.min(10, stage));
    stageButtons.forEach((button) => button.classList.toggle('is-active', Number(button.dataset.stage) === state.stage));
    document.getElementById('simulation-stage-label').textContent = `Stage ${state.stage + 1} / 11 · ${stages[state.stage]}`;
    rebuildModel();
  };

  const waitForThree = (attempt = 0) => {
    if (window.THREE) {
      document.getElementById('three-fallback').hidden = true;
      rebuildModel();
      return;
    }
    if (attempt >= 20) {
      document.getElementById('three-fallback').hidden = false;
      document.getElementById('three-fallback').textContent = 'Three.js could not be loaded. The dimensioned 2D drawing remains available.';
      return;
    }
    window.setTimeout(() => waitForThree(attempt + 1), 250);
  };

  const resetCamera = () => {
    if (!state.three) return;
    state.cameraOrbit = {
      azimuth: 0.75,
      elevation: 0.55,
      distance: Math.max(meters('slab_length'), meters('slab_width')) * 2.5,
    };
    state.three.updateCamera();
  };

  const barGroups = () => {
    const groups = [];
    const addSpacedBars = (component, diameter, spacing, run, length, quantity = 1) => {
      if (diameter <= 0 || spacing <= 0 || run <= 0 || length <= 0) return;
      groups.push({
        component: `${component} @ ${fmt(spacing, 0)} mm`,
        diameter_mm: diameter,
        number_of_bars: (Math.ceil(run * 1000 / spacing) + 1) * quantity,
        bar_length_m: length,
        lap_length_m: meters('bar_lap_length'),
        hook_bend_allowance_m: meters('bar_hook_allowance'),
      });
    };
    const addFixedBars = (component, diameter, count, length) => {
      if (diameter <= 0 || count <= 0 || length <= 0) return;
      groups.push({
        component,
        diameter_mm: diameter,
        number_of_bars: count,
        bar_length_m: length,
        lap_length_m: meters('bar_lap_length'),
        hook_bend_allowance_m: meters('bar_hook_allowance'),
      });
    };
    const footingCount = integer('footing_count', 4);
    addSpacedBars('Footing main bars X', number('footing_bar_diameter'), number('footing_bar_spacing'),
      meters('footing_width'), meters('footing_length'), footingCount);
    addSpacedBars('Footing main bars Y', number('footing_bar_diameter'), number('footing_bar_spacing'),
      meters('footing_length'), meters('footing_width'), footingCount);
    const columnHeight = meters('column_height') * floors;
    addFixedBars('Column longitudinal bars', number('column_bar_diameter'),
      integer('column_main_bars') * integer('column_count'), columnHeight);
    addSpacedBars('Column stirrups', number('column_stirrup_diameter'), number('column_stirrup_spacing'),
      columnHeight, 2 * (meters('column_width') + meters('column_depth')),
      integer('column_count'));
    const beamRun = meters('beam_length');
    addFixedBars('Beam longitudinal bars', number('beam_bar_diameter'),
      integer('beam_main_bars') * integer('beam_count') * floors, beamRun);
    addSpacedBars('Beam stirrups', number('beam_stirrup_diameter'), number('beam_stirrup_spacing'),
      beamRun, 2 * (meters('beam_width') + meters('beam_depth')),
      integer('beam_count') * floors);
    const plinthLength = meters('plinth_beam_length');
    addFixedBars('Plinth beam longitudinal bars', number('plinth_beam_bar_diameter'),
      integer('plinth_beam_main_bars'), plinthLength);
    addSpacedBars('Plinth beam stirrups', number('plinth_beam_stirrup_diameter'),
      number('plinth_beam_stirrup_spacing'), plinthLength,
      2 * (meters('plinth_beam_width') + meters('plinth_beam_depth')));
    const slabL = meters('slab_length');
    const slabW = meters('slab_width');
    addSpacedBars('Slab main bars', number('slab_main_bar_diameter'), number('slab_main_bar_spacing'),
      values.slab_main_direction === 'long' ? slabW : slabL,
      values.slab_main_direction === 'long' ? slabL : slabW, floors);
    addSpacedBars('Slab distribution bars', number('slab_distribution_bar_diameter'), number('slab_distribution_bar_spacing'),
      slabL, slabW, floors);
    return groups;
  };

  const makeComponents = () => {
    const components = [];
    const addConcrete = (name, type, geometry, quantity, grade) => {
      if (quantity > 0) components.push({ name, type, ...geometry, quantity, mix_grade: grade });
    };
    const footings = integer('footing_count');
    const footingL = meters('footing_length');
    const footingW = meters('footing_width');
    const footingD = meters('footing_depth');
    const pcc = meters('pcc_thickness');
    if (pcc > 0) addConcrete('Foundation PCC', 'foundation', { length_m: footingL, width_m: footingW, depth_m: pcc }, footings,
      values.pcc_concrete_grade || 'M10');
    addConcrete('Foundation footing', 'footing', { length_m: footingL, width_m: footingW, depth_m: footingD },
      footings, values.foundation_concrete_grade || 'M20');
    const perimeter = 2 * (plotLength + plotWidth) * unitFactor;
    addConcrete('Plinth beam', 'beam', {
      length_m: meters('plinth_beam_length', perimeter / unitFactor),
      width_m: meters('plinth_beam_width'), depth_m: meters('plinth_beam_depth'),
    }, 1, values.foundation_concrete_grade || 'M20');
    if (number('plinth_masonry_height') > 0) {
      components.push({
        name: 'Plinth brick masonry', type: 'brick_wall',
        length_m: perimeter, height_m: meters('plinth_masonry_height'),
        thickness_m: meters('plinth_wall_thickness'), openings_area_m2: 0,
        brick_length_mm: number('brick_length_mm', 190), brick_height_mm: number('brick_height_mm', 90),
        brick_width_mm: Math.min(number('brick_width_mm', 90), meters('plinth_wall_thickness') * 1000),
        quantity: 1,
      });
    }
    addConcrete('RCC columns', 'column', {
      width_m: meters('column_width'), depth_m: meters('column_depth'), height_m: meters('column_height'),
    }, integer('column_count') * floors, values.column_concrete_grade || 'M20');
    addConcrete('RCC beams', 'beam', {
      length_m: meters('beam_length'), width_m: meters('beam_width'), depth_m: meters('beam_depth'),
    }, integer('beam_count') * floors, values.beam_concrete_grade || 'M20');
    const slabArea = meters('slab_length') * meters('slab_width');
    const openingArea = meters('slab_opening_length') * meters('slab_opening_width');
    if (slabArea > openingArea) {
        addConcrete('RCC slabs', 'slab', {
          length_m: meters('slab_length'), width_m: meters('slab_width'), thickness_m: meters('slab_thickness'),
          openings_area_m2: openingArea,
        }, floors, values.slab_concrete_grade || 'M20');
    }
    addConcrete('Staircase waist slab', 'slab', {
      length_m: meters('stair_width'), width_m: meters('stair_flight_length'),
      thickness_m: meters('stair_waist_thickness'),
    }, integer('stair_flights') * Math.max(floors - 1, 1), values.slab_concrete_grade || 'M20');
    const wallLength = meters('wall_length');
    const wallHeight = meters('wall_height');
    const wallThickness = meters('wall_thickness');
    const wallOpeningArea = (
      nonNegativeInteger('door_count') * meters('door_width') * meters('door_height')
      + nonNegativeInteger('window_count') * meters('window_width') * meters('window_height')
    );
    if (wallLength > 0 && wallHeight > 0 && wallThickness > 0) {
      const wallBrickWidth = Math.min(number('brick_width_mm', 90), wallThickness * 1000);
      components.push({
        name: `${values.wall_type || 'External'} masonry`, type: 'brick_wall',
        length_m: wallLength, height_m: wallHeight, thickness_m: wallThickness,
        openings_area_m2: wallOpeningArea,
        brick_length_mm: number('brick_length_mm', 190),
        brick_height_mm: number('brick_height_mm', 90),
        brick_width_mm: wallBrickWidth,
        quantity: 1,
      });
    }
    return components;
  };

  const buildEstimatePayload = () => {
    const rates = {};
    document.querySelectorAll('[data-manual-rate]').forEach((input) => {
      if (input.value !== '') rates[input.dataset.manualRate] = Number(input.value);
    });
    const extras = {};
    document.querySelectorAll('[data-rate]').forEach((input) => {
      if (input.value !== '') extras[input.dataset.rate] = Number(input.value);
    });
    const builtUpSqft = plotLength * unitFactor * plotWidth * unitFactor * floors * 10.7639104167;
    return {
      project_name: root.dataset.projectName || 'Structural design',
      country: 'India',
      state: document.getElementById('pricing-state').value.trim() || 'Uttarakhand',
      district: document.getElementById('pricing-district').value.trim(),
      built_up_area_sqft: builtUpSqft,
      components: makeComponents(),
      steel_bars: barGroups(),
      wastage_percent: extras.wastage ?? 5,
      manual_rates: rates,
      labour_days: extras.labour_rate == null ? (extras.labour_days || 0) : 0,
      structural_extras: extras,
    };
  };

  const validateDesign = () => {
    for (const field of Object.values(fields).flat()) {
      if (field[2] !== 'number') continue;
      const value = Number(values[field[0]]);
      if (!Number.isFinite(value) || value < field[4] || value > field[5]) {
        throw new Error(`${field[1]} must be between ${field[4]} and ${field[5]}.`);
      }
    }
    if (meters('foundation_depth') < meters('footing_depth') + meters('pcc_thickness')) {
      throw new Error('Excavation depth must include the entered footing and PCC thickness.');
    }
    const grossSlabArea = meters('slab_length') * meters('slab_width');
    const slabOpeningArea = meters('slab_opening_length') * meters('slab_opening_width');
    if (slabOpeningArea >= grossSlabArea) {
      throw new Error('Slab opening area must be less than the gross slab area.');
    }
    const wallOpeningArea = nonNegativeInteger('door_count') * meters('door_width') * meters('door_height')
      + nonNegativeInteger('window_count') * meters('window_width') * meters('window_height');
    if (wallOpeningArea >= meters('wall_length') * meters('wall_height')) {
      throw new Error('Combined door and window areas must be less than the gross wall area.');
    }
    if (meters('door_height') > meters('wall_height')
      || meters('window_sill_height') + meters('window_height') > meters('wall_height')) {
      throw new Error('Door and window openings must fit within the entered wall height.');
    }
  };

  const computeExtraQuantities = () => {
    const excavation = integer('footing_count') * meters('footing_length') * meters('footing_width') * meters('foundation_depth');
    const f = integer('footing_count');
    const footingShuttering = f * 2 * (meters('footing_length') + meters('footing_width')) * meters('footing_depth');
    const columnShuttering = integer('column_count') * floors * 2
      * (meters('column_width') + meters('column_depth')) * meters('column_height');
    const beamShuttering = integer('beam_count') * floors
      * (2 * meters('beam_depth') + meters('beam_width')) * meters('beam_length');
    const slabShuttering = floors * Math.max(
      meters('slab_length') * meters('slab_width') - meters('slab_opening_length') * meters('slab_opening_width'),
      0,
    );
    return {
      excavation,
      shuttering: footingShuttering + columnShuttering + beamShuttering + slabShuttering,
      pcc: f * meters('footing_length') * meters('footing_width') * meters('pcc_thickness'),
      rcc: makeComponents().filter((item) => ['footing', 'column', 'beam', 'slab'].includes(item.type))
        .reduce((sum, item) => {
          if (item.type === 'footing') return sum + item.length_m * item.width_m * item.depth_m * item.quantity;
          if (item.type === 'column') return sum + item.width_m * item.depth_m * item.height_m * item.quantity;
          if (item.type === 'beam') return sum + item.length_m * item.width_m * item.depth_m * item.quantity;
          return sum + item.length_m * item.width_m * item.thickness_m * item.quantity;
        }, 0),
    };
  };

  const renderEstimate = (estimate, extra) => {
    const summary = estimate.costs || {};
    const extraInputs = {};
    document.querySelectorAll('[data-rate]').forEach((input) => {
      extraInputs[input.dataset.rate] = input.value === '' ? null : Number(input.value);
    });
    const extraCosts = {
      excavation: extraInputs.excavation == null ? null : extra.excavation * extraInputs.excavation,
      shuttering: extraInputs.shuttering == null ? null : extra.shuttering * extraInputs.shuttering,
      labour: extraInputs.labour_days == null || extraInputs.labour_rate == null
        ? null : extraInputs.labour_days * extraInputs.labour_rate,
    };
    const pricedExtras = Object.values(extraCosts).filter((value) => value != null).reduce((sum, value) => sum + value, 0);
    const knownTotal = Number(summary.known_total || 0) + pricedExtras;
    const materials = estimate.materials || {};
    const quantityRows = Object.entries(materials)
      .filter(([, material]) => Number(material.quantity) > 0)
      .map(([key, material]) => `<tr><td>${escapeHtml(key.replaceAll('_', ' '))}</td><td>${fmt(material.quantity, 3)} ${escapeHtml(material.unit || '')}</td><td>${material.rate == null ? 'Not priced' : `INR ${fmt(material.amount, 2)} (${escapeHtml(material.source || 'source unavailable')})`}</td></tr>`)
      .join('');
    const componentRows = (estimate.components || []).map((component) => {
      const volume = component.wet_volume_m3 != null ? `${fmt(component.wet_volume_m3, 4)} m³ RCC/PCC` : `${fmt(component.masonry_volume_m3, 4)} m³ masonry`;
      const formulas = component.formula || component.concrete?.formula || '';
      return `<tr><td>${escapeHtml(component.name)}</td><td>${volume}</td><td>${escapeHtml(formulas)}</td></tr>`;
    }).join('');
    const stageNames = ['Foundation', 'Plinth', 'Columns', 'Beams', 'Slabs', 'Walls'];
    const byStage = Object.fromEntries(stageNames.map((name) => [name, {
      volume: 0, cement: 0, sand: 0, aggregate: 0, bricks: 0, steel: 0, formulas: [],
    }]));
    const stageFor = (name) => {
      const key = String(name).toLowerCase();
      if (key.includes('foundation')) return 'Foundation';
      if (key.includes('footing')) return 'Foundation';
      if (key.includes('plinth')) return 'Plinth';
      if (key.includes('column')) return 'Columns';
      if (key.includes('beam')) return 'Beams';
      if (key.includes('slab') || key.includes('staircase')) return 'Slabs';
      if (key.includes('masonry')) return 'Walls';
      return null;
    };
    (estimate.components || []).forEach((component) => {
      const stage = stageFor(component.name);
      if (!stage) return;
      const row = byStage[stage];
      row.volume += Number(component.wet_volume_m3 || component.masonry_volume_m3 || 0);
      row.cement += Number(component.concrete?.cement_kg || 0) / 50 + Number(component.cement_bags || 0);
      row.sand += Number(component.concrete?.sand_cft || component.sand_cft || 0);
      row.aggregate += Number(component.concrete?.aggregate_cft || 0);
      row.bricks += Number(component.bricks || 0);
      if (component.formula || component.concrete?.formula) row.formulas.push(component.formula || component.concrete.formula);
    });
    (estimate.steel_bbs || []).forEach((bar) => {
      const stage = stageFor(bar.component);
      if (stage) byStage[stage].steel += Number(bar.weight_kg || 0);
    });
    const stageRows = stageNames.map((name) => {
      const row = byStage[name];
      return `<tr><td>${name}</td><td>${fmt(row.volume, 4)} m³</td><td>${fmt(row.cement, 2)}</td><td>${fmt(row.sand, 3)} CFT</td><td>${fmt(row.aggregate, 3)} CFT</td><td>${fmt(row.bricks, 0)}</td><td>${fmt(row.steel, 2)} kg</td></tr>`;
    }).join('');
    const labourAmount = extraCosts.labour == null ? summary.labour_cost : extraCosts.labour;
    const extraRows = [
      ['Excavation', extra.excavation, 'm³', 'Count × footing length × footing width × entered excavation depth', extraCosts.excavation],
      ['Shuttering', extra.shuttering, 'm²', 'Footing sides + column sides + beam sides/soffits + slab soffits; openings and reuse excluded', extraCosts.shuttering],
      ['Labour', extraInputs.labour_days || 0, 'days', 'User-entered days × entered or sourced day rate; no default productivity assumed', labourAmount],
    ].map(([name, qty, unitName, formula, amount]) => `<tr><td>${name}</td><td>${fmt(qty, 3)} ${unitName}</td><td>${formula}</td><td>${amount == null ? 'Rate not entered' : `INR ${fmt(amount, 2)}`}</td></tr>`).join('');
    const steelRows = (estimate.steel_bbs || []).map((bar) => `<tr><td>${escapeHtml(bar.component)}</td><td>${fmt(bar.bar_count, 0)} bars × ${fmt(bar.length_each_m, 3)} m</td><td>${fmt(bar.weight_kg, 3)} kg · ${escapeHtml(bar.formula || '')}</td></tr>`).join('');
    results.innerHTML = `
      <div class="structural-result-summary">
        <div><span>Concrete volume</span><strong>${fmt(extra.rcc, 3)} m³ RCC + ${fmt(extra.pcc, 3)} m³ PCC</strong></div>
        <div><span>Excavation</span><strong>${fmt(extra.excavation, 3)} m³</strong></div>
        <div><span>Steel (entered bar schedule)</span><strong>${fmt(estimate.quantities?.steel, 2)} kg</strong></div>
        <div><span>Priced material total</span><strong>INR ${fmt(summary.material_cost, 2)}</strong></div>
        <div><span>Known construction total</span><strong>INR ${fmt(knownTotal, 2)}</strong></div>
      </div>
      <h3>Materials · existing sourced-rate estimator</h3>
      <table class="structural-result-table"><thead><tr><th>Material</th><th>Quantity</th><th>Available rate / amount</th></tr></thead><tbody>${quantityRows || '<tr><td colspan="3">No calculated material rows.</td></tr>'}</tbody></table>
      <h3>Separate preliminary quantities by stage</h3>
      <table class="structural-result-table"><thead><tr><th>Stage</th><th>Concrete / masonry</th><th>Cement bags*</th><th>Sand</th><th>Aggregate</th><th>Bricks</th><th>Steel†</th></tr></thead><tbody>${stageRows}</tbody></table>
      <p class="structural-result-warning">*Stage cement subtotals use component details and may differ from the combined whole-bag total. †Steel uses the user-entered bar counts, spacing and lengths; it is not design steel.</p>
      <h3>Component formulas</h3>
      <table class="structural-result-table"><thead><tr><th>Component</th><th>Calculated geometry</th><th>Formula / basis</th></tr></thead><tbody>${componentRows}</tbody></table>
      <h3>Supplementary quantities</h3>
      <table class="structural-result-table"><thead><tr><th>Stage</th><th>Quantity</th><th>Formula / basis</th><th>Cost</th></tr></thead><tbody>${extraRows}</tbody></table>
      <h3>Preliminary steel schedule</h3>
      <table class="structural-result-table"><thead><tr><th>Member</th><th>Bar count / length</th><th>Weight and formula</th></tr></thead><tbody>${steelRows || '<tr><td colspan="3">Enter reinforcement dimensions to calculate the user-entered bar groups.</td></tr>'}</tbody></table>
      <p class="structural-result-warning">Known total is partial when material prices are unavailable${summary.unpriced_items?.length ? `: ${escapeHtml(summary.unpriced_items.join(', '))}` : ''}. Excavation, shuttering and labour are included only when you enter corresponding rates. Quantities use the entered geometry and displayed formulas; steel and detailing are not designed or code-checked. Verify all loads, foundations, materials, workmanship and applicable IS standards with a licensed engineer.</p>`;
  };

  const sendEstimate = async () => {
    const button = document.getElementById('calculate-structural-estimate');
    try {
      validateDesign();
    } catch (error) {
      setMessage(error.message, true);
      results.innerHTML = `<p class="structural-result-warning">${escapeHtml(error.message)}</p>`;
      return;
    }
    button.disabled = true;
    button.textContent = 'Calculating…';
    setMessage('Sending geometry to the existing material estimator…');
    try {
      const payload = buildEstimatePayload();
      const response = await fetch('/api/material-estimation/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Material estimate could not be calculated.');
      state.estimate = data.estimate;
      renderEstimate(data.estimate, computeExtraQuantities());
      setMessage('Geometry-based estimate saved in Material Estimation history.');
    } catch (error) {
      console.error('Structural material estimation failed.', error);
      results.innerHTML = `<p class="structural-result-warning">${escapeHtml(error.message || 'Material estimate could not be calculated.')}</p>`;
      setMessage(error.message || 'Material estimate could not be calculated.', true);
    } finally {
      button.disabled = false;
      button.textContent = 'Calculate materials & costs';
    }
  };

  const collectRates = () => {
    const rates = {};
    document.querySelectorAll('[data-rate]').forEach((input) => {
      rates[input.dataset.rate] = input.value;
    });
    document.querySelectorAll('[data-manual-rate]').forEach((input) => {
      rates[input.dataset.manualRate] = input.value;
    });
    rates.pricing_state = document.getElementById('pricing-state').value;
    rates.pricing_district = document.getElementById('pricing-district').value;
    return rates;
  };

  const applyRates = (rateValues) => {
    if (!rateValues || typeof rateValues !== 'object') return;
    document.querySelectorAll('[data-rate]').forEach((input) => {
      if (rateValues[input.dataset.rate] != null) input.value = rateValues[input.dataset.rate];
    });
    document.querySelectorAll('[data-manual-rate]').forEach((input) => {
      if (rateValues[input.dataset.manualRate] != null) input.value = rateValues[input.dataset.manualRate];
    });
    if (rateValues.pricing_state) document.getElementById('pricing-state').value = rateValues.pricing_state;
    if (rateValues.pricing_district) document.getElementById('pricing-district').value = rateValues.pricing_district;
  };

  const saveDesign = async () => {
    const button = document.getElementById('save-structural-design');
    const name = document.getElementById('design-name').value.trim();
    if (!name) {
      setMessage('Enter a name for this design set before saving.', true);
      return;
    }
    try {
      validateDesign();
    } catch (error) {
      setMessage(error.message, true);
      return;
    }
    button.disabled = true;
    button.textContent = 'Saving…';
    try {
      const payload = { name, design_data: { ...values }, rates: collectRates() };
      const isUpdate = Boolean(state.savedId);
      const url = isUpdate ? `/api/structural_designs/${encodeURIComponent(state.savedId)}` : `/api/structural_designs?project_id=${encodeURIComponent(projectId)}`;
      const response = await fetch(url, {
        method: isUpdate ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Design could not be saved.');
      const item = data.item;
      state.savedId = item.id;
      state.dirty = false;
      const select = document.getElementById('saved-design-select');
      let option = Array.from(select.options).find((candidate) => candidate.value === item.id);
      if (!option) {
        option = document.createElement('option');
        option.value = item.id;
        select.appendChild(option);
      }
      option.textContent = item.name;
      select.value = item.id;
      const pdfLink = document.getElementById('download-structural-pdf');
      pdfLink.href = root.dataset.pdfTemplate.replace('DESIGN_ID', encodeURIComponent(item.id));
      pdfLink.hidden = false;
      setMessage('Design saved to this project.');
    } catch (error) {
      console.error('Structural design save failed.', error);
      setMessage(error.message || 'Design could not be saved.', true);
    } finally {
      button.disabled = false;
      button.textContent = 'Save design';
    }
  };

  const loadDesign = async () => {
    const designId = document.getElementById('saved-design-select').value;
    if (!designId) {
      setMessage('Choose a saved design to load.', true);
      return;
    }
    try {
      const response = await fetch(`/api/structural_designs/${encodeURIComponent(designId)}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Design could not be loaded.');
      values = { ...defaultValues, ...(data.item.design_data || {}) };
      state.rates = data.item.rates || {};
      applyRates(state.rates);
      state.savedId = data.item.id;
      state.dirty = false;
      document.getElementById('design-name').value = data.item.name;
      updatePropertyForm();
      rebuildModel();
      const pdfLink = document.getElementById('download-structural-pdf');
      pdfLink.href = root.dataset.pdfTemplate.replace('DESIGN_ID', encodeURIComponent(state.savedId));
      pdfLink.hidden = false;
      setMessage(`Loaded “${data.item.name}”.`);
    } catch (error) {
      console.error('Structural design load failed.', error);
      setMessage(error.message || 'Design could not be loaded.', true);
    }
  };

  const downloadBlob = (blob, filename) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const downloadSvg = () => {
    const source = new XMLSerializer().serializeToString(drawing);
    downloadBlob(new Blob([source], { type: 'image/svg+xml;charset=utf-8' }), 'structural-drawing.svg');
  };

  const downloadPng = () => {
    const source = new XMLSerializer().serializeToString(drawing);
    const blob = new Blob([source], { type: 'image/svg+xml;charset=utf-8' });
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = 1520;
      canvas.height = 920;
      const context = canvas.getContext('2d');
      context.fillStyle = '#ffffff';
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((png) => {
        if (!png) {
          setMessage('PNG export failed in this browser.', true);
          return;
        }
        downloadBlob(png, 'structural-drawing.png');
      }, 'image/png');
      URL.revokeObjectURL(image.src);
    };
    image.onerror = () => {
      URL.revokeObjectURL(image.src);
      setMessage('PNG export failed; download the SVG drawing instead.', true);
    };
    image.src = URL.createObjectURL(blob);
  };

  document.querySelectorAll('.studio-module').forEach((button) => {
    button.addEventListener('click', () => {
      state.module = button.dataset.module;
      document.querySelectorAll('.studio-module').forEach((item) => item.classList.toggle('is-active', item === button));
      updatePropertyForm();
      if (state.module === 'simulation') {
        canvasHost.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
  });
  document.querySelectorAll('.studio-view[data-view]').forEach((button) => {
    button.addEventListener('click', () => {
      state.view = button.dataset.view;
      renderDrawing();
    });
  });
  stageButtons.forEach((button) => button.addEventListener('click', () => updateStage(Number(button.dataset.stage))));
  document.getElementById('save-structural-design').addEventListener('click', saveDesign);
  document.getElementById('load-structural-design').addEventListener('click', loadDesign);
  document.getElementById('calculate-structural-estimate').addEventListener('click', sendEstimate);
  document.getElementById('download-svg').addEventListener('click', downloadSvg);
  document.getElementById('download-png').addEventListener('click', downloadPng);
  document.getElementById('reset-properties').addEventListener('click', () => {
    values = { ...defaultValues };
    state.dirty = true;
    markEstimateStale();
    updatePropertyForm();
    rebuildModel();
  });
  document.getElementById('structural-project').addEventListener('change', (event) => {
    if (state.dirty && !window.confirm('Discard unsaved design changes and switch project?')) {
      event.target.value = projectId;
      return;
    }
    window.location.href = `/structural-design?project_id=${encodeURIComponent(event.target.value)}`;
  });
  document.getElementById('simulation-play').addEventListener('click', (event) => {
    const button = event.currentTarget;
    if (state.animationTimer) {
      clearInterval(state.animationTimer);
      state.animationTimer = null;
      button.textContent = 'Play stages';
      return;
    }
    if (state.stage >= 10) updateStage(0);
    button.textContent = 'Pause stages';
    state.animationTimer = window.setInterval(() => {
      if (state.stage >= 10) {
        clearInterval(state.animationTimer);
        state.animationTimer = null;
        button.textContent = 'Play stages';
        return;
      }
      updateStage(state.stage + 1);
    }, 900);
  });
  document.getElementById('simulation-reset').addEventListener('click', resetCamera);
  document.querySelectorAll('.simulation-properties input[data-element]').forEach((input) => {
    input.addEventListener('change', rebuildModel);
  });

  document.querySelectorAll('[data-rate], [data-manual-rate], #pricing-state, #pricing-district').forEach((input) => {
    input.addEventListener('input', () => {
      state.dirty = true;
      markEstimateStale();
    });
  });
  document.getElementById('pricing-state').addEventListener('input', () => { state.dirty = true; });
  document.getElementById('pricing-district').addEventListener('input', () => { state.dirty = true; });

  updatePropertyForm();
  applyRates(state.rates);
  updateStage(0);
  waitForThree();
})();
