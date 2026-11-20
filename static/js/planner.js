(() => {
  const app = document.querySelector('.planner-app[data-planner-enhanced]');
  if (!app) return;

  const svg = app.querySelector('#room-layer');
  const layoutInput = app.querySelector('#layout-data');
  const architecturalInput = app.querySelector('#architectural-elements-data');
  const inspector = app.querySelector('#architectural-inspector');
  const alertBox = app.querySelector('#planner-alert');
  const canvas = app.querySelector('[id="3d-canvas"]');
  const threeStatus = app.querySelector('#planner-3d-status');
  const floorPlan = app.querySelector('#floor-plan');
  const compass = app.querySelector('.planner-compass');
  const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  const palette = Array.from(app.querySelectorAll('.room-tool'));
  const removePalette = Array.from(app.querySelectorAll('.room-remove-tool'));
  const openingRoomSelect = app.querySelector('#opening-room-select');
  const openingRoomInstance = app.querySelector('#opening-room-instance');
  const openingButtons = Array.from(app.querySelectorAll('[data-opening-kind]'));
  const dimensionInputs = Array.from(app.querySelectorAll('.room-dim-input'));
  const fields = {
    length: app.querySelector('#plot-length'),
    width: app.querySelector('#plot-width'),
    unit: app.querySelector('#unit-selector'),
    floors: app.querySelector('#floor-selector'),
    name: app.querySelector('#project-name'),
    hiddenName: app.querySelector('#form-project-name'),
    hiddenLength: app.querySelector('#form-plot-length'),
    hiddenWidth: app.querySelector('#form-plot-width'),
    hiddenUnit: app.querySelector('#form-unit'),
    hiddenFloors: app.querySelector('#form-floors'),
  };
  const controls = {
    view2d: app.querySelector('#view-2d'),
    view3d: app.querySelector('#view-toggle'),
    roof: app.querySelector('#roof-toggle'),
    cutaway: app.querySelector('#cutaway-toggle'),
    walls: app.querySelector('#walls-only-toggle'),
    cameraView: app.querySelector('#camera-view'),
    grid: app.querySelector('#grid-toggle'),
    floor: app.querySelector('#floor-level'),
    furniture: app.querySelector('#furniture-style'),
    finish: app.querySelector('#planner-finish'),
    lighting: app.querySelector('#planner-lighting'),
    zoomIn: app.querySelector('#zoom-in'),
    zoomOut: app.querySelector('#zoom-out'),
    zoomReadout: app.querySelector('#zoom-level'),
    resetCamera: app.querySelector('#camera-reset'),
  };

  const defaultDimensions = {
    Bedroom: { width: 12, depth: 10, height: 9 },
    'Master Bedroom': { width: 14, depth: 12, height: 9 },
    'Living Room': { width: 16, depth: 12, height: 9 },
    Kitchen: { width: 10, depth: 9, height: 9 },
    Bathroom: { width: 8, depth: 7, height: 9 },
    'Dining Room': { width: 12, depth: 10, height: 9 },
    Balcony: { width: 8, depth: 6, height: 9 },
    'Store Room': { width: 8, depth: 8, height: 9 },
    'Study Room': { width: 10, depth: 8, height: 9 },
    Parking: { width: 16, depth: 10, height: 9 },
  };
  const roomColors = ['#dce9f4', '#e7eee6', '#f4e9d8', '#e8e2f1', '#e2eeed'];
  const roomCounts = {};
  const roomPositions = {};
  const architecturalElements = [];
  let selectedElementId = null;
  const view = { width: 720, height: 500, inset: 30 };
  let zoom = 100;
  let is3d = false;
  let renderer = null;
  let scene = null;
  let camera = null;
  let modelRoot = null;
  let resizeObserver = null;
  let resizeHandler = null;
  let pointerState = null;
  let orbit = { azimuth: 0.78, elevation: 0.48, distance: 300, target: null, initial: null };
  const sceneState = {
    roofVisible: true,
    cutaway: false,
    wallsOnly: false,
    gridVisible: true,
    floorLevel: 'all',
    furnitureStyle: 'standard',
    finish: 'oak',
    lighting: 'daylight',
    cameraPreset: 'isometric',
  };
  const cameraPresets = {
    isometric: { azimuth: 0.78, elevation: 0.48 },
    top: { azimuth: 0.78, elevation: 1.32 },
    front: { azimuth: 0, elevation: 0.18 },
    side: { azimuth: Math.PI / 2, elevation: 0.18 },
  };

  const safeNumber = (value, fallback) => {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  };
  const roomKey = (room) => `form-room-${room.replaceAll(' ', '-').replaceAll('/', '-').replaceAll('.', '')}`;
  const roomCountField = (room) => app.querySelector(`#${CSS.escape(roomKey(room))}`);

  palette.forEach((button, index) => {
    const input = app.querySelectorAll('[id^="form-room-"]')[index];
    const count = Math.max(0, Math.floor(safeNumber(input?.value, 0)));
    if (count) roomCounts[button.dataset.room] = count;
  });

  if (layoutInput) {
    try {
      const saved = JSON.parse(layoutInput.value || '{}');
      Object.entries(saved).forEach(([room, positions]) => {
        if (!Array.isArray(positions)) return;
        roomPositions[room] = positions
          .filter((position) => Number.isFinite(Number(position?.x)) && Number.isFinite(Number(position?.y)))
          .map((position) => ({ x: Number(position.x), y: Number(position.y) }));
      });
    } catch (error) {
      console.error('Saved planner positions could not be read.', error);
      alertBox.hidden = false;
      alertBox.textContent = 'The saved room positions could not be read. You can continue arranging rooms and save a new layout.';
    }
  }

  const furnitureByRoom = {
    Bedroom: ['bed', 'wardrobe', 'side-table'],
    'Master Bedroom': ['bed', 'wardrobe', 'side-table'],
    'Living Room': ['sofa', 'coffee-table', 'tv'],
    Kitchen: ['counter', 'island', 'chair'],
    Bathroom: ['vanity', 'shower'],
    'Dining Room': ['dining-table', 'chair', 'chair'],
    Balcony: ['bench', 'planter'],
    'Store Room': ['shelf', 'cabinet'],
    'Study Room': ['desk', 'chair', 'shelf'],
    Parking: ['car'],
  };
  const furnitureSizes = {
    bed: [6.2, 6.8, 1.8], wardrobe: [4.4, 1.9, 6.4], 'side-table': [1.8, 1.8, 1.3],
    sofa: [7.5, 3.1, 2.2], 'coffee-table': [3.4, 2.2, 1.5], tv: [3.8, 0.2, 2.2],
    counter: [5.5, 2.2, 2.7], island: [4.5, 2.7, 1.5], chair: [1.8, 1.8, 1.8],
    'dining-table': [5.2, 3.5, 1.7], bench: [3.6, 1.4, 1.5], planter: [1.4, 1.4, 2.3],
    shelf: [4.4, 1.9, 6.4], cabinet: [4.4, 1.9, 3.1], desk: [4.4, 1.9, 2.5],
    vanity: [4.4, 1.9, 2.6], shower: [3.1, 3.1, 6.2], car: [6, 10, 2.6],
  };
  const unitFactor = () => (getPlot().unit === 'meter' ? 0.3048 : 1);
  const addElement = (room, roomIndex, kind, name, size, x, y, floor = 0, slot = 0) => {
    const factor = unitFactor();
    architecturalElements.push({
      id: `${room}-${roomIndex}-${kind}-${name}-${architecturalElements.length}`,
      kind,
      room,
      room_index: roomIndex,
      name,
      slot,
      floor,
      width: Math.round(size[0] * factor * 100) / 100,
      depth: Math.round(size[1] * factor * 100) / 100,
      height: Math.round(size[2] * factor * 100) / 100,
      x,
      y,
      rotation: 0,
    });
  };
  const elementYPosition = (item, roomSize, proposedY) => {
    if (item.kind === 'door') return roomSize.depth - item.depth;
    if (item.kind === 'window' || item.kind === 'ventilator') return 0;
    return Math.max(0, Math.min(roomSize.depth - item.depth, proposedY));
  };
  if (architecturalInput) {
    try {
      const saved = JSON.parse(architecturalInput.value || '[]');
      if (Array.isArray(saved)) {
        saved.filter((item) => item && typeof item === 'object').forEach((item) => architecturalElements.push(item));
      }
    } catch (error) {
      console.error('Saved architectural elements could not be read.', error);
      alertBox.hidden = false;
      alertBox.textContent = 'Saved door, window, ventilator, skylight, furniture, or stair data could not be read. You can continue planning and save a new layout.';
    }
  }

  const ensureArchitecturalElements = (dimensions) => {
    Object.entries(roomCounts).forEach(([room, count]) => {
      const roomSize = dimensions[room] || defaultDimensions[room] || { width: 12, depth: 10 };
      for (let roomIndex = 0; roomIndex < count; roomIndex += 1) {
        const hasKind = (kind) => architecturalElements.some((item) => item.room === room
          && Number(item.room_index) === roomIndex && item.kind === kind);
        if (room !== 'Parking') {
          const doorWidth = Math.min(3.1, roomSize.width);
          const windowWidth = Math.min(4.5, roomSize.width);
          if (!hasKind('door')) addElement(room, roomIndex, 'door', 'Door', [doorWidth, 0.25, 7.1], (roomSize.width - doorWidth) / 2, Math.max(0, roomSize.depth - 0.25));
          if (!hasKind('window')) addElement(room, roomIndex, 'window', 'Window', [windowWidth, 0.25, 3.9], Math.max(0, (roomSize.width - windowWidth) / 2), 0);
        }
        const furniture = furnitureByRoom[room] || ['cabinet'];
        furniture.forEach((name, index) => {
          if (architecturalElements.some((item) => item.room === room
            && Number(item.room_index) === roomIndex
            && item.kind === 'furniture'
            && item.name === name
            && Number(item.slot) === index)) return;
          const [defaultWidth, defaultDepth, height] = furnitureSizes[name] || furnitureSizes.cabinet;
          const width = Math.min(defaultWidth, roomSize.width);
          const depth = Math.min(defaultDepth, roomSize.depth);
          const x = Math.max(0, Math.min(roomSize.width - width, (roomSize.width - width) / 2 + (index - 1) * 1.2));
          const y = Math.max(0, Math.min(roomSize.depth - depth, (roomSize.depth - depth) / 2 + (index - 1) * 1.1));
          addElement(room, roomIndex, 'furniture', name, [width, depth, height], x, y, 0, index);
        });
      }
    });
    const firstRoom = Object.entries(roomCounts).find(([, count]) => count > 0);
    if (firstRoom && getPlot().floors > 1) {
      const [room, count] = firstRoom;
      const roomSize = dimensions[room] || defaultDimensions[room];
      for (let floor = 0; floor < getPlot().floors - 1; floor += 1) {
        const hasStairs = architecturalElements.some((item) => item.kind === 'stairs' && Number(item.floor) === floor);
        if (!hasStairs) {
          const stairWidth = Math.min(3.5, roomSize.width);
          const stairDepth = Math.min(10, roomSize.depth);
          addElement(room, count - 1, 'stairs', 'Stairs', [stairWidth, stairDepth, roomSize.height], 0, roomSize.depth - stairDepth, floor);
        }
      }
    }
    architecturalElements.forEach((item) => {
      const roomSize = dimensions[item.room];
      item.width = Math.min(Number(item.width) || 0.1, roomSize.width);
      item.depth = Math.min(Number(item.depth) || 0.1, roomSize.depth);
      item.height = Math.min(Number(item.height) || 0.1, roomSize.height);
      item.x = Math.max(0, Math.min(roomSize.width - item.width, Number(item.x) || 0));
      item.y = elementYPosition(item, roomSize, Number(item.y) || 0);
    });
    for (let index = architecturalElements.length - 1; index >= 0; index -= 1) {
      const item = architecturalElements[index];
      if (!roomCounts[item.room]
        || Number(item.room_index) >= roomCounts[item.room]
        || (item.kind === 'stairs' && Number(item.floor) >= getPlot().floors - 1)) architecturalElements.splice(index, 1);
    }
    if (!selectedArchitecturalElement()) selectedElementId = null;
  };

  const getRoomDimensions = () => {
    const dimensions = {};
    dimensionInputs.forEach((input) => {
      const room = input.dataset.room;
      const dimension = input.dataset.dimension;
      const defaults = defaultDimensions[room] || { width: 12, depth: 10, height: 9 };
      if (!dimensions[room]) dimensions[room] = { ...defaults };
      let value = safeNumber(input.value, defaults[dimension]);
      if (value <= 0) value = defaults[dimension];
      if (dimension === 'height') value = Math.min(value, 30);
      dimensions[room][dimension] = Math.round(value * 10) / 10;
      input.value = String(dimensions[room][dimension]);
      const hidden = app.querySelector(`[name="room_${dimension}_${CSS.escape(room)}"]`);
      if (hidden) hidden.value = String(dimensions[room][dimension]);
    });
    return dimensions;
  };

  const getPlot = () => ({
    length: Math.max(1, safeNumber(fields.length.value, 30)),
    width: Math.max(1, safeNumber(fields.width.value, 40)),
    floors: Math.max(1, Math.min(5, Math.floor(safeNumber(fields.floors.value, 1)))),
    unit: fields.unit.value === 'meter' ? 'meter' : 'ft',
  });

  const getScale = () => {
    const plot = getPlot();
    const insideWidth = view.width - view.inset * 2;
    const insideHeight = view.height - view.inset * 2;
    return {
      plot,
      pxPerUnitX: insideWidth / plot.width,
      pxPerUnitY: insideHeight / plot.length,
    };
  };

  const getRoomSizePixels = (room, dimensions, scale) => {
    const size = dimensions[room] || defaultDimensions[room] || { width: 12, depth: 10 };
    return {
      width: size.width * scale.pxPerUnitX,
      height: size.depth * scale.pxPerUnitY,
    };
  };

  const createPlacement = (room, index, dimensions, scale) => {
    const size = getRoomSizePixels(room, dimensions, scale);
    const col = index % 3;
    const row = Math.floor(index / 3);
    const x = view.inset + 18 + col * 205;
    const y = view.inset + 18 + row * 132;
    return {
      x: Math.max(view.inset, Math.min(view.width - view.inset - size.width, x)),
      y: Math.max(view.inset, Math.min(view.height - view.inset - size.height, y)),
    };
  };

  const findOpenPlacement = (room, dimensions, scale) => {
    const size = getRoomSizePixels(room, dimensions, scale);
    const maxX = Math.max(view.inset, view.width - view.inset - size.width);
    const maxY = Math.max(view.inset, view.height - view.inset - size.height);
    const gap = 8;
    for (let y = view.inset; y <= maxY; y += 16) {
      for (let x = view.inset; x <= maxX; x += 16) {
        const overlaps = Object.entries(roomPositions).some(([placedRoom, positions]) => {
          const placedSize = getRoomSizePixels(placedRoom, dimensions, scale);
          return positions.some((position) => (
            x < position.x + placedSize.width + gap
            && x + size.width + gap > position.x
            && y < position.y + placedSize.height + gap
            && y + size.height + gap > position.y
          ));
        });
        if (!overlaps) return { x, y };
      }
    }
    return null;
  };

  const ensurePlacements = (dimensions, scale) => {
    Object.entries(roomCounts).forEach(([room, count]) => {
      if (!roomPositions[room]) roomPositions[room] = [];
      while (roomPositions[room].length < count) {
        const placement = findOpenPlacement(room, dimensions, scale)
          || createPlacement(room, Object.values(roomPositions).reduce((total, positions) => total + positions.length, 0), dimensions, scale);
        roomPositions[room].push(placement);
      }
      roomPositions[room] = roomPositions[room].slice(0, count);
      const size = getRoomSizePixels(room, dimensions, scale);
      roomPositions[room] = roomPositions[room].map((position) => ({
        x: Math.max(view.inset, Math.min(Math.max(view.inset, view.width - view.inset - size.width), position.x)),
        y: Math.max(view.inset, Math.min(Math.max(view.inset, view.height - view.inset - size.height), position.y)),
      }));
    });
    Object.keys(roomPositions).forEach((room) => {
      if (!roomCounts[room]) delete roomPositions[room];
    });
  };

  const svgElement = (tag, attributes = {}) => {
    const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, String(value)));
    return element;
  };

  const updateCompass = () => {
    const north = directions.includes(compass.dataset.northDirection) ? compass.dataset.northDirection : 'N';
    const northIndex = directions.indexOf(north);
    compass.querySelectorAll('[data-plan-side]').forEach((label) => {
      const side = Number(label.dataset.planSide);
      label.textContent = directions[(northIndex + side) % directions.length];
      label.classList.toggle('is-north', side === 0);
    });
    const arrow = app.querySelector('.planner-north-arrow');
    if (arrow) arrow.style.transform = `rotate(${northIndex * 45}deg)`;
  };

  const updateWarnings = (dimensions, scale) => {
    const issues = [];
    Object.entries(roomCounts).forEach(([room, count]) => {
      const size = dimensions[room] || defaultDimensions[room];
      if (size.width > scale.plot.width || size.depth > scale.plot.length) {
        issues.push(`${room} (${size.width} × ${size.depth} ${scale.plot.unit}) is larger than the plot.`);
      }
    });
    const entries = [];
    Object.entries(roomCounts).forEach(([room, count]) => {
      const size = getRoomSizePixels(room, dimensions, scale);
      (roomPositions[room] || []).slice(0, count).forEach((position, index) => {
        entries.push({ room, index, x: position.x, y: position.y, width: size.width, height: size.height });
      });
    });
    for (let i = 0; i < entries.length; i += 1) {
      for (let j = i + 1; j < entries.length; j += 1) {
        const a = entries[i];
        const b = entries[j];
        const overlapX = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
        const overlapY = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
        if (overlapX > 2 && overlapY > 2) {
          issues.push(`${a.room} ${a.index + 1} overlaps ${b.room} ${b.index + 1}.`);
        }
      }
    }
    alertBox.hidden = issues.length === 0;
    alertBox.textContent = issues.length
      ? `${issues.slice(0, 4).join(' ')}${issues.length > 4 ? ` ${issues.length - 4} more issue(s).` : ''} Drag rooms apart or adjust their dimensions.`
      : '';
  };

  const selectedArchitecturalElement = () => architecturalElements.find((item) => item.id === selectedElementId);

  const updateArchitecturalInspector = () => {
    const item = selectedArchitecturalElement();
    inspector.hidden = !item;
    if (!item) return;
    app.querySelector('#architectural-item-name').textContent = `${item.name} · ${item.kind}`;
    app.querySelector('#architectural-item-room').textContent = `${item.room} ${Number(item.room_index) + 1} · ${getPlot().unit}`;
    ['width', 'depth', 'height'].forEach((dimension) => {
      app.querySelector(`#architectural-${dimension}`).value = String(item[dimension]);
    });
  };

  const updateOpeningTools = () => {
    const availableRooms = Object.entries(roomCounts).filter(([room, count]) => room !== 'Parking' && count > 0);
    const previousRoom = openingRoomSelect.value;
    const options = availableRooms.map(([room]) => new Option(room, room));
    openingRoomSelect.replaceChildren(new Option(
      options.length ? 'Choose room type' : 'Add a room first',
      '',
    ), ...options);
    const selectedRoom = availableRooms.some(([room]) => room === previousRoom)
      ? previousRoom
      : (availableRooms[0] || [])[0] || '';
    openingRoomSelect.value = selectedRoom;
    const roomCount = roomCounts[selectedRoom] || 0;
    openingRoomInstance.max = String(Math.max(1, roomCount));
    openingRoomInstance.disabled = roomCount === 0;
    openingRoomInstance.value = String(Math.min(roomCount || 1, Math.max(1, Math.floor(safeNumber(openingRoomInstance.value, 1)))));
    openingButtons.forEach((button) => { button.disabled = roomCount === 0 || architecturalElements.length >= 500; });
  };

  const renderArchitecturalElement = (roomGroup, item, dimensions, scale) => {
    const roomSize = dimensions[item.room] || defaultDimensions[item.room];
    if (item.kind === 'furniture') {
      const furnitureItems = furnitureByRoom[item.room] || ['cabinet'];
      const maxVisible = sceneState.furnitureStyle === 'minimal' ? 1
        : sceneState.furnitureStyle === 'standard' ? 2 : furnitureItems.length;
      if (Number(item.slot) >= maxVisible) return;
    }
    if (item.kind === 'stairs' && sceneState.floorLevel !== 'all'
      && Number(item.floor) !== Number(sceneState.floorLevel)) return;

    const x = Number(item.x) * scale.pxPerUnitX;
    const y = Number(item.y) * scale.pxPerUnitY;
    const width = Number(item.width) * scale.pxPerUnitX;
    const depth = Number(item.depth) * scale.pxPerUnitY;
    const group = svgElement('g', {
      class: `architectural-element is-${item.kind}${selectedElementId === item.id ? ' is-selected' : ''}`,
      transform: `translate(${x} ${y})`,
      tabindex: 0,
      role: 'group',
      'aria-label': `${item.name} in ${item.room}, ${item.width} by ${item.depth} by ${item.height} ${scale.plot.unit}. Drag to reposition.`,
    });
    group.dataset.elementId = item.id;
    group.dataset.room = item.room;
    group.dataset.roomIndex = String(item.room_index);
    const rect = svgElement('rect', {
      class: 'architectural-element-shape',
      width: Math.max(3, width),
      height: Math.max(3, depth),
      rx: item.kind === 'furniture' ? 4 : 1,
    });
    group.appendChild(rect);
    group.appendChild(svgElement('rect', {
      class: 'architectural-hit-target',
      x: 0,
      y: depth / 2 - Math.max(depth, 14) / 2,
      width: Math.max(3, width),
      height: Math.max(depth, 14),
    }));

    if (item.kind === 'stairs') {
      const count = 6;
      for (let index = 1; index < count; index += 1) {
        group.appendChild(svgElement('path', {
          class: 'architectural-detail',
          d: `M 0 ${depth * index / count} H ${width}`,
        }));
      }
      const arrow = svgElement('path', {
        class: 'architectural-detail',
        d: `M ${width / 2} ${depth - 12} V 12 m -5 5 l 5 -5 l 5 5`,
      });
      group.appendChild(arrow);
    } else if (item.kind === 'door') {
      const doorLeaf = Math.max(5, Math.min(width, depth) * 0.85);
      group.appendChild(svgElement('path', {
        class: 'architectural-detail',
        d: `M 0 ${depth} A ${doorLeaf} ${doorLeaf} 0 0 1 ${doorLeaf} ${depth - doorLeaf}`,
      }));
    } else if (item.kind === 'window') {
      group.appendChild(svgElement('path', {
        class: 'architectural-detail',
        d: `M 2 ${depth / 2} H ${width - 2} M 2 2 V ${depth - 2} M ${width - 2} 2 V ${depth - 2}`,
      }));
    } else if (item.kind === 'ventilator') {
      for (let index = 1; index < 4; index += 1) {
        group.appendChild(svgElement('path', {
          class: 'architectural-detail',
          d: `M 2 ${depth * index / 4} H ${width - 2}`,
        }));
      }
    } else if (item.kind === 'skylight') {
      group.appendChild(svgElement('path', {
        class: 'architectural-detail',
        d: `M 2 2 L ${width - 2} ${depth - 2} M ${width - 2} 2 L 2 ${depth - 2}`,
      }));
    } else {
      const nameLabel = svgElement('text', {
        class: 'architectural-name',
        x: width / 2,
        y: Math.min(depth - 4, 12),
        'text-anchor': 'middle',
      });
      nameLabel.textContent = item.name;
      group.appendChild(nameLabel);
    }

    const format = (value) => Number(value.toFixed(1)).toString();
    const sizeLabel = svgElement('text', {
      class: 'architectural-size',
      x: width / 2,
      y: -4,
      'text-anchor': 'middle',
    });
    sizeLabel.textContent = `W ${format(Number(item.width))} × D ${format(Number(item.depth))} × H ${format(Number(item.height))} ${scale.plot.unit}`;
    group.append(
      svgElement('path', {
        class: 'architectural-measure-line',
        d: `M 0 0 H ${width} M 0 -3 V 3 M ${width} -3 V 3 M ${width} 0 V ${depth} M ${width - 3} 0 H ${width + 3} M ${width - 3} ${depth} H ${width + 3}`,
      }),
    );
    group.appendChild(sizeLabel);
    roomGroup.appendChild(group);
  };

  const renderPlan = () => {
    if (!svg) return;
    const dimensions = getRoomDimensions();
    const scale = getScale();
    ensurePlacements(dimensions, scale);
    ensureArchitecturalElements(dimensions);
    svg.replaceChildren();

    const plotFill = svgElement('rect', {
      class: 'planner-plot-fill',
      x: view.inset,
      y: view.inset,
      width: view.width - view.inset * 2,
      height: view.height - view.inset * 2,
      rx: 5,
    });
    const plotOutline = svgElement('rect', {
      class: 'planner-plot-outline',
      x: view.inset,
      y: view.inset,
      width: view.width - view.inset * 2,
      height: view.height - view.inset * 2,
      rx: 5,
    });
    svg.append(plotFill);

    const dimLineTop = svgElement('path', {
      class: 'planner-dimension-line',
      d: `M ${view.inset} ${view.inset - 8} H ${view.width - view.inset}`,
    });
    const dimLabelTop = svgElement('text', {
      class: 'planner-dimension-label',
      x: view.width / 2,
      y: view.inset - 12,
      'text-anchor': 'middle',
    });
    dimLabelTop.textContent = `Plot W ${scale.plot.width} ${scale.plot.unit}`;
    const dimLineSide = svgElement('path', {
      class: 'planner-dimension-line',
      d: `M ${view.width - view.inset + 8} ${view.inset} V ${view.height - view.inset}`,
    });
    const dimLabelSide = svgElement('text', {
      class: 'planner-dimension-label',
      x: view.width - view.inset + 18,
      y: view.height / 2,
      transform: `rotate(90 ${view.width - view.inset + 18} ${view.height / 2})`,
      'text-anchor': 'middle',
    });
    dimLabelSide.textContent = `Plot D ${scale.plot.length} ${scale.plot.unit}`;
    svg.append(dimLineTop, dimLabelTop, dimLineSide, dimLabelSide);

    let entryIndex = 0;
    Object.entries(roomCounts).forEach(([room, count]) => {
      const size = getRoomSizePixels(room, dimensions, scale);
      for (let index = 0; index < count; index += 1) {
        const position = roomPositions[room][index];
        const roomDimensions = dimensions[room];
        const overflow = size.width > view.width - view.inset * 2 || size.height > view.height - view.inset * 2;
        const heightLabel = room === 'Parking' ? 'canopy height' : 'wall height';
        const group = svgElement('g', {
          class: `room-instance${overflow ? ' is-overflow' : ''}${room === 'Parking' ? ' is-parking' : ''}`,
          transform: `translate(${position.x} ${position.y})`,
          tabindex: 0,
          role: 'group',
          'aria-label': `${room} ${index + 1}, width ${dimensions[room].width}, depth ${dimensions[room].depth}, ${heightLabel} ${dimensions[room].height} ${scale.plot.unit}. Use arrow keys to move.`,
        });
        group.dataset.room = room;
        group.dataset.index = String(index);

        const rect = svgElement('rect', {
          class: 'room-rect',
          x: 0,
          y: 0,
          width: Math.max(2, size.width),
          height: Math.max(2, size.height),
          rx: 3,
          fill: roomColors[entryIndex % roomColors.length],
        });
        const label = svgElement('text', {
          class: 'room-label',
          x: 9,
          y: Math.min(size.height - 8, 24),
        });
        label.textContent = room;
        const sizeLabel = svgElement('text', {
          class: 'room-size',
          x: 9,
          y: Math.min(size.height - 4, 43),
        });
        sizeLabel.textContent = `W ${roomDimensions.width} × D ${roomDimensions.depth} × H ${roomDimensions.height} ${scale.plot.unit}`;
        const roomWidthLine = svgElement('path', {
          class: 'room-measure-line',
          d: `M 0 -8 H ${size.width} M 0 -11 V -5 M ${size.width} -11 V -5`,
        });
        const roomDepthLine = svgElement('path', {
          class: 'room-measure-line',
          d: `M ${size.width + 8} 0 V ${size.height} M ${size.width + 5} 0 H ${size.width + 11} M ${size.width + 5} ${size.height} H ${size.width + 11}`,
        });
        const roomWidthText = svgElement('text', {
          class: 'room-measure-label',
          x: size.width / 2,
          y: -11,
          'text-anchor': 'middle',
        });
        roomWidthText.textContent = `W ${roomDimensions.width} ${scale.plot.unit}`;
        const roomDepthText = svgElement('text', {
          class: 'room-measure-label',
          x: size.width + 15,
          y: size.height / 2,
          transform: `rotate(90 ${size.width + 15} ${size.height / 2})`,
          'text-anchor': 'middle',
        });
        roomDepthText.textContent = `D ${roomDimensions.depth} ${scale.plot.unit}`;
        const indexLabel = svgElement('text', {
          class: 'planner-room-index',
          x: Math.max(12, size.width - 9),
          y: 15,
          'text-anchor': 'end',
        });
        indexLabel.textContent = `#${index + 1}`;
        const parkingMarkings = room === 'Parking'
          ? svgElement('path', {
            class: 'parking-bay-marking',
            d: `M ${size.width * 0.34} ${size.height * 0.08} V ${size.height * 0.92} M ${size.width * 0.66} ${size.height * 0.08} V ${size.height * 0.92}`,
          })
          : null;
        group.append(rect, ...(parkingMarkings ? [parkingMarkings] : []), roomWidthLine, roomDepthLine, roomWidthText, roomDepthText, label, sizeLabel, indexLabel);
        architecturalElements
          .filter((item) => item.room === room && Number(item.room_index) === index)
          .filter((item) => room !== 'Parking' || !['door', 'window'].includes(item.kind))
          .forEach((item) => renderArchitecturalElement(group, item, dimensions, scale));
        svg.appendChild(group);
        entryIndex += 1;
      }
    });
    svg.append(plotOutline);
    palette.forEach((button) => {
      const count = roomCounts[button.dataset.room] || 0;
      button.querySelector('b').textContent = count ? String(count) : '+';
      const countInput = roomCountField(button.dataset.room);
      if (countInput) countInput.value = String(count);
      const removeButton = removePalette.find((item) => item.dataset.room === button.dataset.room);
      if (removeButton) removeButton.disabled = count === 0;
    });
    updateOpeningTools();
    const summaryRooms = app.querySelector('#planner-summary-rooms');
    if (summaryRooms) summaryRooms.textContent = String(Object.values(roomCounts).reduce((sum, count) => sum + count, 0));
    updateWarnings(dimensions, scale);
    attachPlanInteractions();
    attachArchitecturalInteractions();
    updateArchitecturalInspector();
    return { dimensions, scale };
  };

  let dragState = null;
  let architecturalDragState = null;
  const attachArchitecturalInteractions = () => {
    svg.querySelectorAll('.architectural-element').forEach((group) => {
      group.onpointerdown = (event) => {
        if (event.button !== undefined && event.button !== 0) return;
        const item = selectedArchitecturalElementById(group.dataset.elementId);
        if (!item) return;
        selectedElementId = item.id;
        updateArchitecturalInspector();
        const roomGroup = group.parentElement;
        const point = svg.createSVGPoint();
        point.x = event.clientX;
        point.y = event.clientY;
        const current = point.matrixTransform(roomGroup.getScreenCTM().inverse());
        architecturalDragState = {
          group,
          item,
          roomGroup,
          offsetX: current.x - item.x * getScale().pxPerUnitX,
          offsetY: current.y - item.y * getScale().pxPerUnitY,
          moved: false,
        };
        group.setPointerCapture?.(event.pointerId);
        event.stopPropagation();
        event.preventDefault();
      };
      group.onpointermove = (event) => {
        if (!architecturalDragState || architecturalDragState.group !== group) return;
        const point = svg.createSVGPoint();
        point.x = event.clientX;
        point.y = event.clientY;
        const current = point.matrixTransform(architecturalDragState.roomGroup.getScreenCTM().inverse());
        const scale = getScale();
        const roomSize = getRoomDimensions()[architecturalDragState.item.room];
        const maxX = Math.max(0, roomSize.width - architecturalDragState.item.width);
        const maxY = Math.max(0, roomSize.depth - architecturalDragState.item.depth);
        architecturalDragState.item.x = Math.max(0, Math.min(maxX, (current.x - architecturalDragState.offsetX) / scale.pxPerUnitX));
        architecturalDragState.item.y = elementYPosition(
          architecturalDragState.item,
          roomSize,
          (current.y - architecturalDragState.offsetY) / scale.pxPerUnitY,
        );
        group.setAttribute('transform', `translate(${architecturalDragState.item.x * scale.pxPerUnitX} ${architecturalDragState.item.y * scale.pxPerUnitY})`);
        architecturalDragState.moved = true;
        event.stopPropagation();
      };
      const finish = (event) => {
        if (!architecturalDragState || architecturalDragState.group !== group) return;
        const moved = architecturalDragState.moved;
        architecturalDragState = null;
        if (moved) renderPlan();
        event.stopPropagation();
      };
      group.onpointerup = finish;
      group.onpointercancel = finish;
      group.onkeydown = (event) => {
        const step = event.shiftKey ? 1 : 0.25;
        const delta = {
          ArrowLeft: [-step, 0], ArrowRight: [step, 0],
          ArrowUp: [0, -step], ArrowDown: [0, step],
        }[event.key];
        if (!delta) return;
        const item = selectedArchitecturalElementById(group.dataset.elementId);
        if (!item) return;
        const roomSize = getRoomDimensions()[item.room];
        item.x = Math.max(0, Math.min(roomSize.width - item.width, item.x + delta[0]));
        item.y = elementYPosition(item, roomSize, item.y + delta[1]);
        event.preventDefault();
        event.stopPropagation();
        renderPlan();
        svg.querySelector(`[data-element-id="${CSS.escape(item.id)}"]`)?.focus();
      };
      group.onclick = (event) => event.stopPropagation();
    });
  };
  const selectedArchitecturalElementById = (id) => architecturalElements.find((item) => item.id === id);

  const attachPlanInteractions = () => {
    svg.querySelectorAll('.room-instance').forEach((group) => {
      group.onpointerdown = (event) => {
        if (event.button !== undefined && event.button !== 0) return;
        const room = group.dataset.room;
        const index = Number(group.dataset.index);
        const point = svg.createSVGPoint();
        point.x = event.clientX;
        point.y = event.clientY;
        const current = point.matrixTransform(svg.getScreenCTM().inverse());
        const position = roomPositions[room][index];
        dragState = { group, room, index, offsetX: current.x - position.x, offsetY: current.y - position.y };
        group.setPointerCapture?.(event.pointerId);
        event.preventDefault();
      };
      group.onpointermove = (event) => {
        if (!dragState || dragState.group !== group) return;
        const point = svg.createSVGPoint();
        point.x = event.clientX;
        point.y = event.clientY;
        const current = point.matrixTransform(svg.getScreenCTM().inverse());
        const dimensions = getRoomDimensions();
        const scale = getScale();
        const size = getRoomSizePixels(roomPositions[dragState.room] ? dragState.room : group.dataset.room, dimensions, scale);
        const maxX = Math.max(view.inset, view.width - view.inset - size.width);
        const maxY = Math.max(view.inset, view.height - view.inset - size.height);
        const position = {
          x: Math.max(view.inset, Math.min(maxX, current.x - dragState.offsetX)),
          y: Math.max(view.inset, Math.min(maxY, current.y - dragState.offsetY)),
        };
        roomPositions[dragState.room][dragState.index] = position;
        group.setAttribute('transform', `translate(${position.x} ${position.y})`);
      };
      const endDrag = () => {
        if (!dragState || dragState.group !== group) return;
        dragState = null;
        renderPlan();
        if (is3d) buildModel();
      };
      group.onpointerup = endDrag;
      group.onpointercancel = endDrag;
      group.onkeydown = (event) => {
        const step = event.shiftKey ? 20 : 5;
        const room = group.dataset.room;
        const index = Number(group.dataset.index);
        const position = roomPositions[room][index];
        const directionsByKey = {
          ArrowLeft: [-step, 0],
          ArrowRight: [step, 0],
          ArrowUp: [0, -step],
          ArrowDown: [0, step],
        };
        const delta = directionsByKey[event.key];
        if (!delta) return;
        event.preventDefault();
        const dimensions = getRoomDimensions();
        const scale = getScale();
        const size = getRoomSizePixels(room, dimensions, scale);
        position.x = Math.max(view.inset, Math.min(view.width - view.inset - size.width, position.x + delta[0]));
        position.y = Math.max(view.inset, Math.min(view.height - view.inset - size.height, position.y + delta[1]));
        renderPlan();
        svg.querySelector(`[data-room="${CSS.escape(room)}"][data-index="${index}"]`)?.focus();
        if (is3d) buildModel();
      };
    });
  };

  const updateStats = () => {
    const plot = getPlot();
    const area = plot.length * plot.width;
    const unitLabel = plot.unit === 'meter' ? 'sq m' : 'sq ft';
    app.querySelector('#plot-area').textContent = `${area.toFixed(1)} ${unitLabel}`;
    app.querySelector('#built-area').textContent = `${(area * 0.7 * plot.floors).toFixed(1)} ${unitLabel}`;
    app.querySelector('#open-area').textContent = `${(area * 0.3).toFixed(1)} ${unitLabel}`;
    fields.hiddenName.value = fields.name.value;
    fields.hiddenLength.value = plot.length;
    fields.hiddenWidth.value = plot.width;
    fields.hiddenUnit.value = plot.unit;
    fields.hiddenFloors.value = plot.floors;
    app.querySelector('#planner-summary-name').textContent = fields.name.value || 'New plan';
    app.querySelector('#planner-summary-plot').textContent = `${plot.width} × ${plot.length} ${plot.unit}`;
    app.querySelector('#planner-summary-floors').textContent = String(plot.floors);
    updateFloorOptions(plot.floors);
  };

  const updateFloorOptions = (count) => {
    const current = controls.floor.value || 'all';
    controls.floor.replaceChildren(new Option('All floors', 'all'));
    for (let level = 0; level < count; level += 1) {
      const floorNumber = level + 1;
      const suffix = floorNumber % 100 >= 11 && floorNumber % 100 <= 13
        ? 'th'
        : ({ 1: 'st', 2: 'nd', 3: 'rd' }[floorNumber % 10] || 'th');
      const label = level === 0 ? 'Ground floor' : `${floorNumber}${suffix} floor`;
      controls.floor.add(new Option(label, String(level)));
    }
    controls.floor.value = current === 'all' || Number(current) < count ? current : 'all';
    sceneState.floorLevel = controls.floor.value;
  };

  ['width', 'depth', 'height'].forEach((dimension) => {
    app.querySelector(`#architectural-${dimension}`).addEventListener('change', (event) => {
      const item = selectedArchitecturalElement();
      if (!item) return;
      const value = Number(event.currentTarget.value);
      if (!Number.isFinite(value) || value <= 0) {
        event.currentTarget.value = String(item[dimension]);
        return;
      }
      item[dimension] = Math.round(value * 100) / 100;
      const roomSize = getRoomDimensions()[item.room];
      item.x = Math.min(item.x, Math.max(0, roomSize.width - item.width));
      item.y = Math.min(item.y, Math.max(0, roomSize.depth - item.depth));
      const result = renderPlan();
      if (is3d) buildModel(result);
    });
  });

  const update2DZoom = () => {
    controls.zoomReadout.textContent = `${zoom}%`;
    svg.style.transform = `scale(${zoom / 100})`;
  };

  palette.forEach((button) => {
    button.addEventListener('click', () => {
      const room = button.dataset.room;
      roomCounts[room] = (roomCounts[room] || 0) + 1;
      const result = renderPlan();
      if (is3d) buildModel(result);
      else {
        const bounds = floorPlan.getBoundingClientRect();
        if (bounds.top < 0 || bounds.bottom > window.innerHeight) {
          floorPlan.scrollIntoView({ behavior: 'instant', block: 'center' });
        }
      }
    });
  });

  openingRoomSelect.addEventListener('change', updateOpeningTools);
  openingRoomInstance.addEventListener('change', () => {
    const count = roomCounts[openingRoomSelect.value] || 0;
    openingRoomInstance.value = String(Math.min(count || 1, Math.max(1, Math.floor(safeNumber(openingRoomInstance.value, 1)))));
  });
  openingButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const room = openingRoomSelect.value;
      const roomIndex = Math.floor(safeNumber(openingRoomInstance.value, 1)) - 1;
      const roomCount = roomCounts[room] || 0;
      if (!room || architecturalElements.length >= 500 || roomIndex < 0 || roomIndex >= roomCount) return;

      const kind = button.dataset.openingKind;
      const dimension = getRoomDimensions()[room];
      const presets = {
        door: { label: 'Door', width: 3.1, depth: 0.25, height: 7.1 },
        window: { label: 'Window', width: 4.5, depth: 0.25, height: 3.9 },
        ventilator: { label: 'Ventilator', width: 1.8, depth: 0.25, height: 0.8 },
        skylight: { label: 'Skylight', width: 3, depth: 3, height: 0.1 },
      };
      const preset = presets[kind];
      if (!preset) return;

      const existingCount = architecturalElements.filter((item) => item.room === room
        && Number(item.room_index) === roomIndex && item.kind === kind).length;
      const width = Math.min(preset.width, dimension.width);
      const depth = Math.min(preset.depth, dimension.depth);
      const height = Math.min(preset.height, dimension.height);
      const maxX = Math.max(0, dimension.width - width);
      const maxY = Math.max(0, dimension.depth - depth);
      const offsets = [0.5, 0.85, 0.15, 0.65, 0.35];
      const offset = offsets[existingCount % offsets.length];
      const x = kind === 'door' ? maxX * offset
        : kind === 'window' ? maxX * offset
          : kind === 'ventilator' ? maxX
            : maxX * offset;
      const y = kind === 'door' ? maxY
        : kind === 'window' || kind === 'ventilator' ? 0
          : maxY * offsets[(existingCount + 2) % offsets.length];
      addElement(room, roomIndex, kind, `${preset.label} ${existingCount + 1}`, [width, depth, height], x, y, 0, existingCount);
      const addedItem = architecturalElements[architecturalElements.length - 1];
      addedItem.width = width;
      addedItem.depth = depth;
      addedItem.height = height;
      selectedElementId = addedItem.id;
      const result = renderPlan();
      if (is3d) buildModel(result);
      svg.querySelector(`[data-element-id="${CSS.escape(addedItem.id)}"]`)?.focus();
    });
  });

  removePalette.forEach((button) => {
    button.addEventListener('click', () => {
      const room = button.dataset.room;
      const count = roomCounts[room] || 0;
      if (!count) return;

      const removedIndex = count - 1;
      if (removedIndex === 0) delete roomCounts[room];
      else roomCounts[room] = removedIndex;
      roomPositions[room]?.splice(removedIndex, 1);
      if (roomPositions[room]?.length === 0) delete roomPositions[room];
      for (let index = architecturalElements.length - 1; index >= 0; index -= 1) {
        const element = architecturalElements[index];
        if (element.room === room && Number(element.room_index) >= removedIndex) {
          architecturalElements.splice(index, 1);
        }
      }
      if (!selectedArchitecturalElement()) selectedElementId = null;
      const result = renderPlan();
      if (is3d) buildModel(result);
    });
  });

  app.querySelector('#reset-layout').addEventListener('click', () => {
    Object.keys(roomCounts).forEach((room) => delete roomCounts[room]);
    Object.keys(roomPositions).forEach((room) => delete roomPositions[room]);
    const result = renderPlan();
    if (is3d) buildModel(result);
  });

  dimensionInputs.forEach((input) => input.addEventListener('change', () => {
    const result = renderPlan();
    if (is3d) buildModel(result);
  }));
  [fields.length, fields.width].forEach((input) => input.addEventListener('change', () => {
    const result = renderPlan();
    if (is3d) buildModel(result);
  }));
  [fields.length, fields.width, fields.floors, fields.unit, fields.name].forEach((input) => {
    input.addEventListener('input', () => {
      updateStats();
      const result = renderPlan();
      if (is3d) buildModel(result);
    });
    input.addEventListener('change', () => {
      updateStats();
      const result = renderPlan();
      if (is3d) buildModel(result);
    });
  });

  controls.grid.addEventListener('click', () => {
    sceneState.gridVisible = !sceneState.gridVisible;
    floorPlan.querySelector('.plan-grid').classList.toggle('hidden', !sceneState.gridVisible);
    if (modelRoot) modelRoot.traverse((object) => {
      if (object.userData.isGrid) object.visible = sceneState.gridVisible
        && (sceneState.floorLevel === 'all' || object.userData.floorIndex === Number(sceneState.floorLevel));
    });
    controls.grid.textContent = `Grid ${sceneState.gridVisible ? 'on' : 'off'}`;
    controls.grid.setAttribute('aria-pressed', String(sceneState.gridVisible));
  });
  controls.zoomIn.addEventListener('click', () => {
    zoom = Math.min(140, zoom + 10);
    update2DZoom();
  });
  controls.zoomOut.addEventListener('click', () => {
    zoom = Math.max(70, zoom - 10);
    update2DZoom();
  });

  app.querySelector('#planner-form').addEventListener('submit', () => {
    const saved = {};
    Object.entries(roomCounts).forEach(([room, count]) => {
      if (count > 0) saved[room] = (roomPositions[room] || []).slice(0, count);
    });
    layoutInput.value = JSON.stringify(saved);
    architecturalInput.value = JSON.stringify(architecturalElements);
  });

  const show3dStatus = (message) => {
    threeStatus.textContent = message;
    threeStatus.hidden = !message;
  };

  const setView = (use3d) => {
    is3d = use3d;
    floorPlan.hidden = use3d;
    canvas.hidden = !use3d;
    controls.view2d.classList.toggle('is-active', !use3d);
    controls.view2d.setAttribute('aria-pressed', String(!use3d));
    controls.view3d.classList.toggle('is-active', use3d);
    controls.view3d.setAttribute('aria-pressed', String(use3d));
    app.querySelector('#view-mode-label').textContent = use3d ? '3D preview' : '2D plan';
    app.querySelector('#planner-canvas-hint').textContent = use3d
      ? 'Click an opening to edit its dimensions; drag it to reposition · Drag elsewhere to orbit · Shift-drag or right-drag to pan · Scroll or pinch to zoom.'
      : 'Select an item to edit its dimensions; drag it to reposition. Room, plot, and object measurements use the selected unit.';
    if (use3d) {
      if (!window.THREE) {
        show3dStatus('3D preview is unavailable because the Three.js library did not load. Your 2D plan and saved layout are unaffected. Check your connection, then try 3D again.');
        return;
      }
      show3dStatus('Preparing your 3D preview…');
      requestAnimationFrame(() => {
        if (!is3d) return;
        try {
          setupRenderer();
          buildModel();
          renderer.setAnimationLoop(() => renderer.render(scene, camera));
          show3dStatus('');
        } catch (error) {
          console.error('The 3D preview could not be built.', error);
          show3dStatus('3D preview could not be started in this browser. Your plan remains saved in 2D. Try another browser or device with WebGL enabled.');
        }
      });
    } else if (renderer) {
      renderer.setAnimationLoop(null);
    }
  };

  controls.view2d.addEventListener('click', () => setView(false));
  controls.view3d.addEventListener('click', () => setView(true));

  const makeCanvasTexture = (kind, finish) => {
    const textureCanvas = document.createElement('canvas');
    textureCanvas.width = 256;
    textureCanvas.height = 256;
    const context = textureCanvas.getContext('2d');
    if (kind === 'wood') {
      const shades = finish === 'oak' ? ['#b9885d', '#d2a675', '#a97952'] : ['#c5b7a3', '#ded3c1', '#b6a992'];
      context.fillStyle = shades[0];
      context.fillRect(0, 0, 256, 256);
      for (let row = 0; row < 8; row += 1) {
        const y = row * 32;
        context.fillStyle = shades[row % shades.length];
        context.fillRect(0, y + 1, 256, 30);
        context.strokeStyle = 'rgba(77,47,26,.17)';
        context.lineWidth = 1;
        context.beginPath();
        context.moveTo(0, y + 9 + (row % 3) * 4);
        context.bezierCurveTo(70, y + 2, 160, y + 23, 256, y + 12);
        context.stroke();
        context.strokeStyle = 'rgba(255,244,222,.2)';
        context.beginPath();
        context.moveTo(0, y + 22);
        context.lineTo(256, y + 20 - (row % 2) * 3);
        context.stroke();
      }
    } else if (kind === 'fabric') {
      const shades = finish === 'slate' ? ['#687d8d', '#7b8f9d'] : ['#8197a7', '#98a9b5'];
      context.fillStyle = shades[0];
      context.fillRect(0, 0, 256, 256);
      for (let line = 0; line < 256; line += 4) {
        context.strokeStyle = line % 8 === 0 ? shades[1] : 'rgba(32,46,57,.16)';
        context.lineWidth = 1;
        context.beginPath();
        context.moveTo(line, 0);
        context.lineTo(line, 256);
        context.moveTo(0, line);
        context.lineTo(256, line);
        context.stroke();
      }
    } else {
      const base = finish === 'slate' ? '#77848c' : '#d8d1c5';
      context.fillStyle = base;
      context.fillRect(0, 0, 256, 256);
      context.strokeStyle = finish === 'slate' ? 'rgba(32,45,54,.36)' : 'rgba(112,105,94,.22)';
      context.lineWidth = 2;
      for (let i = 0; i <= 4; i += 1) {
        context.beginPath();
        context.moveTo(i * 64, 0);
        context.lineTo(i * 64, 256);
        context.moveTo(0, i * 64);
        context.lineTo(256, i * 64);
        context.stroke();
      }
    }
    const texture = new THREE.CanvasTexture(textureCanvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(2, 2);
    if ('colorSpace' in texture && THREE.SRGBColorSpace) texture.colorSpace = THREE.SRGBColorSpace;
    else if ('encoding' in texture) texture.encoding = THREE.sRGBEncoding;
    return texture;
  };

  const createMaterials = () => {
    const finish = sceneState.finish;
    const woodTexture = makeCanvasTexture('wood', finish);
    const tileTexture = makeCanvasTexture('tile', finish);
    const fabricTexture = makeCanvasTexture('fabric', finish);
    return {
      wall: new THREE.MeshStandardMaterial({ color: 0xf1f0eb, roughness: 0.88 }),
      floor: new THREE.MeshStandardMaterial({
        map: finish === 'oak' ? woodTexture : tileTexture,
        color: finish === 'slate' ? 0xb6c1c7 : 0xffffff,
        roughness: finish === 'oak' ? 0.72 : 0.58,
      }),
      parkingFloor: new THREE.MeshStandardMaterial({ color: 0x929da2, roughness: 0.94 }),
      parkingMarking: new THREE.MeshStandardMaterial({ color: 0xf3f0d8, roughness: 0.8 }),
      parkingPost: new THREE.MeshStandardMaterial({ color: 0x74838b, roughness: 0.72 }),
      parkingCanopy: new THREE.MeshStandardMaterial({ color: 0x506575, roughness: 0.58, metalness: 0.18 }),
      wood: new THREE.MeshStandardMaterial({ map: woodTexture, color: 0xffffff, roughness: 0.62 }),
      fabric: new THREE.MeshStandardMaterial({ map: fabricTexture, color: 0xffffff, roughness: 0.94 }),
      linen: new THREE.MeshStandardMaterial({ map: fabricTexture, color: 0xe7ddcf, roughness: 0.96 }),
      ceramic: new THREE.MeshStandardMaterial({ color: 0xd9e1e4, roughness: 0.28, metalness: 0.04 }),
      glass: new THREE.MeshStandardMaterial({ color: 0xa8d8e8, roughness: 0.14, metalness: 0.04, transparent: true, opacity: 0.58 }),
      metal: new THREE.MeshStandardMaterial({ color: 0x6e7c84, roughness: 0.36, metalness: 0.68 }),
      green: new THREE.MeshStandardMaterial({ color: 0x62856c, roughness: 0.9 }),
      roof: new THREE.MeshStandardMaterial({
        color: 0x758a98,
        roughness: 0.72,
        transparent: true,
        opacity: 0.78,
        depthWrite: false,
        side: THREE.DoubleSide,
      }),
      ground: new THREE.MeshStandardMaterial({ color: 0xbac7b7, roughness: 0.98 }),
      line: new THREE.LineBasicMaterial({ color: 0x667f91, transparent: true, opacity: 0.65 }),
    };
  };

  const addMesh = (parent, geometry, material, position, options = {}) => {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(position.x || 0, position.y || 0, position.z || 0);
    mesh.castShadow = options.castShadow !== false;
    mesh.receiveShadow = options.receiveShadow !== false;
    if (options.rotation) mesh.rotation.set(options.rotation.x || 0, options.rotation.y || 0, options.rotation.z || 0);
    parent.add(mesh);
    return mesh;
  };

  const addBox = (parent, material, width, height, depth, x, y, z) => (
    addMesh(parent, new THREE.BoxGeometry(width, height, depth), material, { x, y, z })
  );

  const addFurniture = (group, room, width, depth, materials, item, index, total, element, unitScale) => {
    const usableW = Math.max(2, width - 0.8);
    const usableD = Math.max(2, depth - 0.8);
    const clampX = (value, itemW) => Math.max(-usableW / 2 + itemW / 2, Math.min(usableW / 2 - itemW / 2, value));
    const clampZ = (value, itemD) => Math.max(-usableD / 2 + itemD / 2, Math.min(usableD / 2 - itemD / 2, value));
    const wood = materials.wood;
    const fabric = room === 'Living Room' || room.includes('Bedroom') ? materials.fabric : materials.ceramic;

    if (element) {
      const w = Math.min(element.width * unitScale, usableW);
      const d = Math.min(element.depth * unitScale, usableD);
      const h = Math.min(element.height * unitScale, 8);
      const x = clampX(-width / 2 + element.x * unitScale + w / 2, w);
      const z = clampZ(depth / 2 - element.y * unitScale - d / 2, d);
      if (item === 'car') {
        const vehicle = new THREE.MeshStandardMaterial({ color: 0x527b9b, roughness: 0.4, metalness: 0.22 });
        const wheelRadius = Math.min(0.34, Math.max(0.18, h * 0.14));
        const bodyHeight = Math.min(1.25, Math.max(0.6, h * 0.48));
        const bodyY = wheelRadius + bodyHeight / 2;
        addBox(group, vehicle, w, bodyHeight, d * 0.86, x, bodyY, z);
        addBox(group, materials.glass, w * 0.72, Math.min(0.85, h * 0.34), d * 0.48, x, bodyY + bodyHeight * 0.54, z - d * 0.03);
        [-1, 1].forEach((sideX) => [-1, 1].forEach((sideZ) => {
          addMesh(group, new THREE.CylinderGeometry(wheelRadius, wheelRadius, 0.2, 12), materials.metal, {
            x: x + sideX * (w / 2 - 0.04),
            y: wheelRadius,
            z: z + sideZ * d * 0.3,
          }, { rotation: { z: Math.PI / 2 } });
        }));
        return;
      }
      const body = item === 'bed' || item === 'sofa' ? fabric : wood;
      addBox(group, body, w, Math.min(h, item === 'bed' ? 1 : h), d, x, Math.min(h, item === 'bed' ? 1 : h) / 2 + 0.12, z);
      if (item === 'bed') {
        addBox(group, materials.linen, w * 0.92, 0.28, d * 0.72, x, 0.78, z + d * 0.08);
        addBox(group, materials.linen, w * 0.32, 0.16, d * 0.12, x, 1, z - d * 0.3);
      } else if (item === 'sofa') {
        addBox(group, fabric, w * 0.88, Math.min(h, 2), 0.3, x, Math.min(h, 2) / 2 + 0.3, z - d * 0.35);
      } else if (item.includes('table') || item === 'desk' || item === 'counter' || item === 'island') {
        addBox(group, wood, w, 0.18, d, x, Math.min(h, 2.8), z);
      } else if (item === 'car') {
        addBox(group, materials.glass, w * 0.72, 0.9, d * 0.4, x, Math.min(h, 2.4), z);
      }
      return;
    }

    if (item === 'bed') {
      const w = Math.min(6.2, usableW * 0.62);
      const d = Math.min(6.8, usableD * 0.63);
      const x = clampX(-usableW * 0.08, w);
      const z = clampZ(-usableD * 0.04, d);
      addBox(group, wood, w, 0.35, d, x, 0.28, z);
      addBox(group, materials.linen, w * 0.96, 0.38, d * 0.88, x, 0.62, z + 0.08);
      addBox(group, materials.linen, w * 0.31, 0.18, 0.75, x - w * 0.2, 0.91, z - d * 0.3);
      addBox(group, materials.linen, w * 0.31, 0.18, 0.75, x + w * 0.2, 0.91, z - d * 0.3);
      addBox(group, wood, w, 1.8, 0.18, x, 1.1, z - d / 2 + 0.1);
      return;
    }
    if (item === 'sofa') {
      const w = Math.min(7.5, usableW * 0.66);
      const d = Math.min(3.1, usableD * 0.3);
      const x = clampX(0, w);
      const z = clampZ(-usableD * 0.22, d);
      addBox(group, wood, w, 0.34, d, x, 0.42, z);
      addBox(group, fabric, w * 0.9, 0.6, d * 0.68, x, 0.88, z + d * 0.05);
      addBox(group, fabric, w * 0.9, 1.15, 0.42, x, 1.35, z - d * 0.34);
      addBox(group, fabric, 0.42, 0.88, d * 0.9, x - w * 0.46, 0.86, z);
      addBox(group, fabric, 0.42, 0.88, d * 0.9, x + w * 0.46, 0.86, z);
      return;
    }
    if (item === 'table' || item === 'dining-table') {
      const w = Math.min(item === 'dining-table' ? 5.2 : 3.8, usableW * 0.45);
      const d = Math.min(item === 'dining-table' ? 3.5 : 3.3, usableD * 0.38);
      const x = clampX(total > 1 ? (index - (total - 1) / 2) * usableW * 0.36 : 0, w);
      const z = clampZ(item === 'dining-table' ? 0.06 * usableD : usableD * 0.13, d);
      addBox(group, wood, w, 0.16, d, x, 1.55, z);
      [-1, 1].forEach((sx) => [-1, 1].forEach((sz) => addBox(group, wood, 0.16, 1.5, 0.16, x + sx * (w / 2 - 0.16), 0.78, z + sz * (d / 2 - 0.16))));
      return;
    }
    if (item === 'wardrobe' || item === 'cabinet' || item === 'shelf' || item === 'media-console' || item === 'counter' || item === 'vanity' || item === 'desk') {
      const w = Math.min(item === 'counter' ? 5.5 : 4.4, usableW * 0.38);
      const d = Math.min(item === 'counter' ? 2.2 : 1.9, usableD * 0.28);
      const h = item === 'wardrobe' || item === 'shelf' ? 6.4 : item === 'vanity' ? 2.6 : item === 'desk' ? 2.5 : 3.1;
      const x = clampX(item === 'counter' ? -usableW * 0.28 : usableW * 0.3, w);
      const z = clampZ(item === 'counter' ? 0 : -usableD * 0.3, d);
      addBox(group, item === 'vanity' ? materials.ceramic : wood, w, h, d, x, h / 2 + 0.18, z);
      if (item === 'wardrobe' || item === 'shelf') {
        for (let shelf = 1; shelf < 4; shelf += 1) addBox(group, materials.linen, w * 0.88, 0.08, d * 0.88, x, h * shelf / 4, z);
      }
      if (item === 'desk' || item === 'counter') addBox(group, materials.linen, w * 1.03, 0.1, d * 1.04, x, h + 0.1, z);
      return;
    }
    if (item === 'chair' || item === 'side-table' || item === 'bench') {
      const w = Math.min(item === 'bench' ? 3.6 : 1.8, usableW * 0.23);
      const d = Math.min(item === 'bench' ? 1.4 : 1.8, usableD * 0.22);
      const x = clampX((index % 2 ? 1 : -1) * usableW * 0.31, w);
      const z = clampZ(total > 1 ? usableD * 0.3 : 0, d);
      addBox(group, wood, w, 0.22, d, x, item === 'side-table' ? 1.25 : 0.92, z);
      if (item !== 'side-table') {
        addBox(group, wood, w, 0.95, 0.14, x, 1.43, z - d * 0.4);
        [-1, 1].forEach((sx) => [-1, 1].forEach((sz) => addBox(group, wood, 0.12, 0.82, 0.12, x + sx * (w / 2 - 0.12), 0.42, z + sz * (d / 2 - 0.12))));
      } else {
        addBox(group, wood, 0.12, 1.16, 0.12, x, 0.58, z);
      }
      return;
    }
    if (item === 'shower') {
      const w = Math.min(3.1, usableW * 0.27);
      const d = Math.min(3.1, usableD * 0.27);
      const x = clampX(usableW * 0.31, w);
      const z = clampZ(usableD * 0.3, d);
      addBox(group, materials.ceramic, w, 0.12, d, x, 0.24, z);
      addBox(group, materials.glass, 0.08, 6.2, d, x - w / 2, 3.35, z);
      return;
    }
    if (item === 'planter') {
      const x = clampX(usableW * 0.32, 1.4);
      const z = clampZ(usableD * 0.3, 1.4);
      addMesh(group, new THREE.CylinderGeometry(0.55, 0.64, 1.0, 10), wood, { x, y: 0.65, z });
      addMesh(group, new THREE.SphereGeometry(0.72, 10, 8), materials.green, { x, y: 1.6, z });
      return;
    }
    if (item === 'car') {
      const w = Math.min(6, usableW * 0.66);
      const d = Math.min(10, usableD * 0.66);
      const x = clampX(0, w);
      const z = clampZ(0, d);
      const vehicle = new THREE.MeshStandardMaterial({ color: 0x6485a5, roughness: 0.42, metalness: 0.25 });
      addBox(group, vehicle, w, 1.6, d, x, 1.0, z);
      addBox(group, materials.glass, w * 0.74, 1.15, d * 0.48, x, 2.25, z - d * 0.02);
      [-1, 1].forEach((sx) => [-1, 1].forEach((sz) => addMesh(group, new THREE.CylinderGeometry(0.36, 0.36, 0.22, 12), materials.metal, {
        x: x + sx * (w / 2 - 0.06), y: 0.72, z: z + sz * (d * 0.31),
      }, { rotation: { z: Math.PI / 2 } })));
      return;
    }
    if (item === 'coffee-table' || item === 'island') {
      const w = Math.min(item === 'island' ? 4.5 : 3.4, usableW * 0.4);
      const d = Math.min(item === 'island' ? 2.7 : 2.2, usableD * 0.28);
      const x = clampX(0, w);
      const z = clampZ(usableD * 0.14, d);
      addBox(group, wood, w, 0.2, d, x, 1.25, z);
      addBox(group, wood, 0.14, 1.1, 0.14, x - w * 0.4, 0.66, z);
      addBox(group, wood, 0.14, 1.1, 0.14, x + w * 0.4, 0.66, z);
      return;
    }
    if (item === 'tv') addBox(group, materials.metal, Math.min(3.8, usableW * 0.35), 2.2, 0.18, 0, 3.4, clampZ(usableD * 0.42, 0.2));
  };

  const roomFurniture = (room) => {
    const mapping = {
      Bedroom: ['bed', 'wardrobe', 'side-table'],
      'Master Bedroom': ['bed', 'wardrobe', 'side-table'],
      'Living Room': ['sofa', 'coffee-table', 'tv'],
      Kitchen: ['counter', 'island', 'chair'],
      Bathroom: ['vanity', 'shower'],
      'Dining Room': ['dining-table', 'chair', 'chair'],
      Balcony: ['bench', 'planter'],
      'Store Room': ['shelf', 'cabinet'],
      'Study Room': ['desk', 'chair', 'shelf'],
      Parking: ['car'],
    };
    return mapping[room] || ['cabinet'];
  };

  const clearModel = () => {
    if (!modelRoot) return;
    const geometries = new Set();
    const materials = new Set();
    const textures = new Set();
    modelRoot.traverse((object) => {
      if (object.geometry) geometries.add(object.geometry);
      const list = Array.isArray(object.material) ? object.material : [object.material];
      list.filter(Boolean).forEach((material) => {
        materials.add(material);
        Object.values(material).forEach((value) => {
          if (value && value.isTexture) textures.add(value);
        });
      });
    });
    modelRoot.clear();
    geometries.forEach((geometry) => geometry.dispose());
    materials.forEach((material) => material.dispose());
    textures.forEach((texture) => texture.dispose());
  };

  const createRoom = (root, materials, roomName, roomIndex, instanceIndex, dimensions, position, scale, floorIndex, elements = [], floorHeight = 10) => {
    const plot = scale.plot;
    const unitScale = plot.unit === 'meter' ? 3.28084 : 1;
    const roomW = dimensions.width * unitScale;
    const roomD = dimensions.depth * unitScale;
    const plotW = plot.width * unitScale;
    const plotD = plot.length * unitScale;
    const roomPx = getRoomSizePixels(roomName, { [roomName]: dimensions }, scale);
    const centerX = position.x + roomPx.width / 2 - view.inset;
    const centerY = position.y + roomPx.height / 2 - view.inset;
    const worldX = -plotW / 2 + (centerX / (view.width - view.inset * 2)) * plotW;
    const worldZ = plotD / 2 - (centerY / (view.height - view.inset * 2)) * plotD;
    const wallHeight = dimensions.height * unitScale;
    const t = 0.16;
    const levelY = floorIndex * floorHeight;
    const group = new THREE.Group();
    group.position.set(worldX, levelY, worldZ);
    group.userData.floorIndex = floorIndex;
    group.userData.roomName = roomName;
    group.userData.roomNumber = instanceIndex + 1;
    const tagOpeningMesh = (mesh, item, surface) => {
      mesh.userData.architecturalElementId = item.id;
      mesh.userData.openingSurface = surface;
      mesh.userData.openingRoomWidth = dimensions.width;
      mesh.userData.openingRoomDepth = dimensions.depth;
      mesh.userData.openingUnitScale = unitScale;
      mesh.userData.openingRoomWorldX = worldX;
      mesh.userData.openingRoomWorldZ = worldZ;
      return mesh;
    };

    const isParking = roomName === 'Parking';
    addBox(group, isParking ? materials.parkingFloor : materials.floor, roomW, 0.18, roomD, 0, 0.02, 0);
    if (isParking) {
      const postSize = Math.min(0.28, roomW / 8, roomD / 8);
      const canopyHeight = Math.max(3, wallHeight * 0.76);
      const postX = roomW / 2 - postSize / 2;
      const postZ = roomD / 2 - postSize / 2;
      [[-postX, -postZ], [postX, -postZ], [-postX, postZ], [postX, postZ]].forEach(([x, z]) => {
        addBox(group, materials.parkingPost, postSize, canopyHeight, postSize, x, canopyHeight / 2, z);
      });
      addBox(group, materials.parkingCanopy, roomW, 0.16, roomD, 0, canopyHeight + 0.08, 0);
      [-1, 1].forEach((side) => {
        addBox(group, materials.parkingMarking, 0.12, 0.025, roomD * 0.84, side * roomW * 0.38, 0.12, 0);
      });
    } else {
      addBox(group, materials.wall, t, wallHeight, roomD, -roomW / 2, wallHeight / 2, 0);
      addBox(group, materials.wall, t, wallHeight, roomD, roomW / 2, wallHeight / 2, 0);

      const windowBottom = Math.min(3.1, wallHeight * 0.4);
      const makeOpening = (item, bottom, top) => {
        const openingWidth = Math.min(Number(item.width) * unitScale, roomW);
        const left = Math.max(0, Math.min(roomW - openingWidth, Number(item.x) * unitScale));
        return {
          item,
          left,
          right: left + openingWidth,
          bottom: Math.max(0, Math.min(wallHeight, bottom)),
          top: Math.max(0, Math.min(wallHeight, top)),
          width: openingWidth,
        };
      };
      const wallOpenings = [
        ...elements.filter((item) => item.kind === 'window').map((item) => makeOpening(
          item,
          windowBottom,
          Math.min(windowBottom + Number(item.height) * unitScale, wallHeight - 0.15),
        )),
        ...elements.filter((item) => item.kind === 'ventilator').map((item) => {
          const openingHeight = Math.min(Number(item.height) * unitScale, wallHeight * 0.25);
          const openingBottom = Math.max(0.4, wallHeight - openingHeight - 0.5);
          return makeOpening(item, openingBottom, openingBottom + openingHeight);
        }),
      ].filter((opening) => opening.top > opening.bottom);
      const addWallWithOpenings = (wallZ, openings) => {
        const xCoordinates = [...new Set([0, roomW, ...openings.flatMap((opening) => [opening.left, opening.right])]
          .map((coordinate) => Math.round(coordinate * 10000) / 10000))].sort((a, b) => a - b);
        for (let index = 0; index < xCoordinates.length - 1; index += 1) {
          const left = xCoordinates[index];
          const right = xCoordinates[index + 1];
          const segmentWidth = right - left;
          if (segmentWidth <= 0.01) continue;
          const midpoint = (left + right) / 2;
          const verticalOpenings = openings
            .filter((opening) => midpoint > opening.left - 0.001 && midpoint < opening.right + 0.001)
            .map((opening) => [opening.bottom, opening.top])
            .sort((a, b) => a[0] - b[0]);
          let currentHeight = 0;
          verticalOpenings.forEach(([bottom, top]) => {
            const openingBottom = Math.max(currentHeight, bottom);
            if (openingBottom > currentHeight + 0.01) {
              const segmentHeight = openingBottom - currentHeight;
              addBox(group, materials.wall, segmentWidth, segmentHeight, t, -roomW / 2 + midpoint, currentHeight + segmentHeight / 2, wallZ);
            }
            currentHeight = Math.max(currentHeight, top);
          });
          if (wallHeight > currentHeight + 0.01) {
            const segmentHeight = wallHeight - currentHeight;
            addBox(group, materials.wall, segmentWidth, segmentHeight, t, -roomW / 2 + midpoint, currentHeight + segmentHeight / 2, wallZ);
          }
        }
      };
      const doorOpenings = elements.filter((item) => item.kind === 'door')
        .map((item) => makeOpening(item, 0, Math.min(Number(item.height) * unitScale, wallHeight)));
      addWallWithOpenings(-roomD / 2, doorOpenings);
      addWallWithOpenings(roomD / 2, wallOpenings);

      doorOpenings.forEach((opening) => {
        const centerX = -roomW / 2 + opening.left + opening.width / 2;
        const doorHeight = opening.top - opening.bottom;
        tagOpeningMesh(addBox(group, materials.wood, opening.width * 0.96, doorHeight, 0.08, centerX, doorHeight / 2, -roomD / 2 + 0.06), opening.item, 'wall');
        tagOpeningMesh(addBox(group, materials.metal, 0.08, 0.08, 0.12, centerX + opening.width * 0.32, doorHeight * 0.48, -roomD / 2 + 0.12), opening.item, 'wall');
      });

      elements.filter((item) => item.kind === 'window').forEach((window) => {
        const opening = wallOpenings.find((candidate) => candidate.item === window);
        if (!opening) return;
        const centerX = -roomW / 2 + opening.left + opening.width / 2;
        const centerY = (opening.bottom + opening.top) / 2;
        const openingHeight = opening.top - opening.bottom;
        const glass = tagOpeningMesh(addBox(group, materials.glass, opening.width * 0.92, openingHeight * 0.92, 0.05, centerX, centerY, roomD / 2 + 0.03), window, 'wall');
        glass.castShadow = false;
        [-1, 1].forEach((side) => tagOpeningMesh(addBox(group, materials.metal, 0.08, openingHeight, 0.1, centerX + side * opening.width * 0.46, centerY, roomD / 2 + 0.08), window, 'wall'));
        tagOpeningMesh(addBox(group, materials.metal, opening.width, 0.08, 0.1, centerX, opening.bottom, roomD / 2 + 0.08), window, 'wall');
        tagOpeningMesh(addBox(group, materials.metal, opening.width, 0.08, 0.1, centerX, opening.top, roomD / 2 + 0.08), window, 'wall');
      });

      wallOpenings.filter((opening) => opening.item.kind === 'ventilator').forEach((opening) => {
        const centerX = -roomW / 2 + opening.left + opening.width / 2;
        const centerY = (opening.bottom + opening.top) / 2;
        const openingHeight = opening.top - opening.bottom;
        for (let index = 1; index <= 3; index += 1) {
          tagOpeningMesh(addBox(group, materials.metal, opening.width * 0.86, 0.035, 0.05, centerX, opening.bottom + openingHeight * index / 4, roomD / 2 + t / 2 + 0.03), opening.item, 'wall');
        }
        tagOpeningMesh(addBox(group, materials.metal, opening.width, 0.05, 0.05, centerX, centerY, roomD / 2 + t / 2 + 0.035), opening.item, 'wall');
      });
    }

    const furnitureItems = roomFurniture(roomName);
    const furnitureCount = sceneState.furnitureStyle === 'minimal' ? 1 : sceneState.furnitureStyle === 'standard' ? 2 : furnitureItems.length;
    if (!sceneState.wallsOnly) {
      const roomFurnitureElements = elements.filter((item) => item.kind === 'furniture')
        .sort((a, b) => Number(a.slot) - Number(b.slot));
      furnitureItems.slice(0, furnitureCount).forEach((item, index, list) => {
        const element = roomFurnitureElements.find((candidate) => candidate.name === item && Number(candidate.slot) === index);
        addFurniture(group, roomName, roomW, roomD, materials, item, index, list.length, element, unitScale);
      });
    }

    const stairs = elements.find((item) => item.kind === 'stairs' && Number(item.floor) === floorIndex);
    if (stairs) {
      const stairW = Math.min(stairs.width * unitScale, roomW);
      const stairD = Math.min(stairs.depth * unitScale, roomD);
      const stairH = Math.min(stairs.height * unitScale, wallHeight);
      const stairX = -roomW / 2 + stairs.x * unitScale;
      const stairZ = roomD / 2 - stairs.y * unitScale - stairD;
      const stepCount = 8;
      for (let step = 0; step < stepCount; step += 1) {
        const stepDepth = stairD / stepCount;
        const stepHeight = stairH * (step + 1) / stepCount;
        addBox(group, materials.wood, stairW, stepHeight, stepDepth, stairX + stairW / 2, stepHeight / 2, stairZ + step * stepDepth + stepDepth / 2);
      }
    }

    if (!sceneState.wallsOnly) {
      const label = document.createElement('canvas');
      label.width = 512;
      label.height = 96;
      const context = label.getContext('2d');
      context.fillStyle = 'rgba(17, 39, 57, .88)';
      if (typeof context.roundRect === 'function') context.roundRect(2, 2, 508, 92, 18);
      else context.fillRect(2, 2, 508, 92);
      context.fill();
      context.fillStyle = '#ffffff';
      context.font = '700 40px Arial';
      context.textAlign = 'center';
      context.textBaseline = 'middle';
      context.fillText(roomName, 256, 48, 480);
      const texture = new THREE.CanvasTexture(label);
      const labelMaterial = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
      const sprite = new THREE.Sprite(labelMaterial);
      sprite.scale.set(Math.min(roomW * 0.8, 8), 1.4, 1);
      sprite.position.set(0, wallHeight + 0.5, 0);
      group.add(sprite);
    }

    root.add(group);
  };

  const buildModel = (plan) => {
    if (!scene || !window.THREE || !renderer) return;
    const current = plan || renderPlan();
    clearModel();
    const materials = createMaterials();
    modelRoot.userData.wallMaterial = materials.wall;
    const { dimensions, scale } = current;
    const plot = scale.plot;
    const unitScale = plot.unit === 'meter' ? 3.28084 : 1;
    const plotW = plot.width * unitScale;
    const plotD = plot.length * unitScale;
    const floorHeight = Math.max(10, ...Object.values(dimensions).map((room) => room.height * unitScale + 1));
    const highestWallHeight = Math.max(0, ...Object.values(dimensions).map((room) => room.height * unitScale));
    const roofY = (plot.floors - 1) * floorHeight + highestWallHeight + 0.12;
    const totalBuildingHeight = roofY + 0.09;
    const longest = Math.max(plot.length * unitScale, plot.width * unitScale, totalBuildingHeight, 20);
    const defaultTarget = new THREE.Vector3(0, totalBuildingHeight / 2, 0);
    const cameraPreset = cameraPresets[sceneState.cameraPreset] || cameraPresets.isometric;
    orbit.initial = {
      target: defaultTarget.clone(),
      azimuth: cameraPreset.azimuth,
      elevation: cameraPreset.elevation,
      distance: longest * 1.8,
    };
    const allFloors = Array.from({ length: plot.floors }, (_, index) => index);
    const selectedFloors = sceneState.floorLevel === 'all' ? allFloors : [Number(sceneState.floorLevel)];
    const ground = addMesh(modelRoot, new THREE.PlaneGeometry(plotW * 1.6, plotD * 1.6), materials.ground, {
      x: 0, y: -0.22, z: 0,
    }, { rotation: { x: -Math.PI / 2 }, castShadow: false });
    ground.userData.isGround = true;
    const gridSize = Math.max(plotW, plotD);
    allFloors.forEach((floor) => {
      const grid = new THREE.GridHelper(gridSize, Math.max(1, Math.min(60, Math.ceil(gridSize / 2))), 0x8798a4, 0xb7c2c8);
      grid.scale.set(plotW / gridSize, 1, plotD / gridSize);
      grid.position.y = floor * floorHeight + 0.035;
      grid.userData.isGrid = true;
      grid.userData.floorIndex = floor;
      modelRoot.add(grid);
    });

    const boundaryPoints = [
      new THREE.Vector3(-plotW / 2, 0, -plotD / 2),
      new THREE.Vector3(plotW / 2, 0, -plotD / 2),
      new THREE.Vector3(plotW / 2, 0, plotD / 2),
      new THREE.Vector3(-plotW / 2, 0, plotD / 2),
      new THREE.Vector3(-plotW / 2, 0, -plotD / 2),
    ];
    const boundary = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(boundaryPoints),
      materials.line,
    );
    modelRoot.add(boundary);

    let roomIndex = 0;
    Object.entries(roomCounts).forEach(([room, count]) => {
      const roomDims = dimensions[room] || defaultDimensions[room];
      for (let index = 0; index < count; index += 1) {
        selectedFloors.forEach((floor) => {
          const roomElements = architecturalElements.filter((item) => item.room === room && Number(item.room_index) === index);
          createRoom(modelRoot, materials, room, roomIndex, index, roomDims, roomPositions[room][index], scale, floor, roomElements, floorHeight);
        });
        roomIndex += 1;
      }
    });

    if (roomIndex === 0) {
      show3dStatus('Add rooms from the left panel to build a 3D preview. Your empty plan is ready for rooms.');
    } else {
      show3dStatus('');
    }

    const roof = addMesh(modelRoot, new THREE.BoxGeometry(plotW, 0.18, plotD), materials.roof, { x: 0, y: roofY, z: 0 }, { castShadow: false });
    roof.userData.isRoof = true;
    roof.userData.floorIndex = plot.floors - 1;
    const roofSurfaceY = roofY + 0.09;
    Object.entries(roomCounts).forEach(([room, count]) => {
      const roomDims = dimensions[room] || defaultDimensions[room];
      const roomW = roomDims.width * unitScale;
      const roomD = roomDims.depth * unitScale;
      const roomPx = getRoomSizePixels(room, dimensions, scale);
      for (let index = 0; index < count; index += 1) {
        const position = roomPositions[room][index];
        const centerX = position.x + roomPx.width / 2 - view.inset;
        const centerY = position.y + roomPx.height / 2 - view.inset;
        const worldX = -plotW / 2 + (centerX / (view.width - view.inset * 2)) * plotW;
        const worldZ = plotD / 2 - (centerY / (view.height - view.inset * 2)) * plotD;
        architecturalElements
          .filter((item) => item.room === room && Number(item.room_index) === index && item.kind === 'skylight')
          .forEach((skylight) => {
            const skylightW = Math.min(Number(skylight.width) * unitScale, roomW * 0.8);
            const skylightD = Math.min(Number(skylight.depth) * unitScale, roomD * 0.8);
            const skylightGroup = new THREE.Group();
            skylightGroup.position.set(worldX, roofSurfaceY, worldZ);
            skylightGroup.userData.floorIndex = plot.floors - 1;
            modelRoot.add(skylightGroup);
            const skylightX = -roomW / 2 + Number(skylight.x) * unitScale + skylightW / 2;
            const skylightZ = roomD / 2 - Number(skylight.y) * unitScale - skylightD / 2;
            const frame = addBox(skylightGroup, materials.metal, skylightW, 0.08, skylightD, skylightX, 0.04, skylightZ);
            const pane = addBox(skylightGroup, materials.glass, skylightW * 0.88, 0.04, skylightD * 0.88, skylightX, 0.1, skylightZ);
            [frame, pane].forEach((mesh) => {
              mesh.userData.architecturalElementId = skylight.id;
              mesh.userData.openingSurface = 'roof';
              mesh.userData.openingRoomWidth = roomDims.width;
              mesh.userData.openingRoomDepth = roomDims.depth;
              mesh.userData.openingUnitScale = unitScale;
              mesh.userData.openingRoomWorldX = worldX;
              mesh.userData.openingRoomWorldZ = worldZ;
            });
            pane.castShadow = false;
          });
      }
    });
    applySceneState();
  };

  const setLighting = () => {
    if (!scene || !renderer) return;
    const interior = sceneState.lighting === 'interior';
    scene.background.set(interior ? 0x243442 : 0xdce9f2);
    renderer.toneMappingExposure = interior ? 0.82 : 1.08;
    scene.children.forEach((child) => {
      if (child.userData.kind === 'ambient') child.intensity = interior ? 0.7 : 1.05;
      if (child.userData.kind === 'hemisphere') child.intensity = interior ? 0.4 : 1.05;
      if (child.userData.kind === 'sun') {
        child.intensity = interior ? 0.35 : 1.45;
        child.color.set(interior ? 0xffc98d : 0xffffff);
      }
    });
  };

  const applySceneState = () => {
    controls.roof.textContent = `Roof ${sceneState.roofVisible ? 'on' : 'off'}`;
    controls.roof.setAttribute('aria-pressed', String(sceneState.roofVisible));
    controls.cutaway.textContent = `Cutaway ${sceneState.cutaway ? 'on' : 'off'}`;
    controls.cutaway.setAttribute('aria-pressed', String(sceneState.cutaway));
    controls.walls.textContent = sceneState.wallsOnly ? 'Walls only' : 'Furniture on';
    controls.walls.setAttribute('aria-pressed', String(sceneState.wallsOnly));
    if (!modelRoot) return;
    const wallMaterial = modelRoot.userData.wallMaterial;
    if (wallMaterial) {
      wallMaterial.transparent = sceneState.cutaway;
      wallMaterial.opacity = sceneState.cutaway ? 0.22 : 1;
      wallMaterial.depthWrite = !sceneState.cutaway;
      wallMaterial.side = sceneState.cutaway ? THREE.DoubleSide : THREE.FrontSide;
      wallMaterial.needsUpdate = true;
    }
    modelRoot.traverse((object) => {
      if (object.userData.isRoof || object.userData.isGrid || object.userData.floorIndex !== undefined) {
        const floorVisible = sceneState.floorLevel === 'all'
          || object.userData.floorIndex === Number(sceneState.floorLevel);
        object.visible = floorVisible
          && (!object.userData.isRoof || sceneState.roofVisible)
          && (!object.userData.isGrid || sceneState.gridVisible);
      }
    });
  };

  const resetCamera = () => {
    if (!camera || !orbit.initial) return;
    orbit.azimuth = orbit.initial.azimuth;
    orbit.elevation = orbit.initial.elevation;
    orbit.distance = orbit.initial.distance;
    orbit.target.copy(orbit.initial.target);
    updateCamera();
  };

  const setCameraPreset = (name) => {
    const preset = cameraPresets[name];
    if (!preset) return;
    sceneState.cameraPreset = name;
    orbit.azimuth = preset.azimuth;
    orbit.elevation = preset.elevation;
    if (orbit.initial) {
      orbit.initial.azimuth = preset.azimuth;
      orbit.initial.elevation = preset.elevation;
    }
    updateCamera();
  };

  const updateCamera = () => {
    if (!camera || !orbit.target) return;
    const horizontal = orbit.distance * Math.cos(orbit.elevation);
    camera.position.set(
      orbit.target.x + horizontal * Math.sin(orbit.azimuth),
      orbit.target.y + orbit.distance * Math.sin(orbit.elevation),
      orbit.target.z + horizontal * Math.cos(orbit.azimuth),
    );
    camera.lookAt(orbit.target);
  };

  const setupRenderer = () => {
    if (renderer) {
      const width = Math.max(1, canvas.clientWidth);
      const height = Math.max(1, canvas.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      return;
    }
    if (!window.THREE || !canvas.clientWidth || !canvas.clientHeight) throw new Error('3D canvas has no size or Three.js is unavailable.');
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xdce9f2);
    const ambient = new THREE.AmbientLight(0xffffff, 1.05);
    ambient.userData.kind = 'ambient';
    scene.add(ambient);
    const hemisphere = new THREE.HemisphereLight(0xeaf5ff, 0x829080, 1.05);
    hemisphere.userData.kind = 'hemisphere';
    scene.add(hemisphere);
    const sun = new THREE.DirectionalLight(0xfff8ec, 1.45);
    sun.userData.kind = 'sun';
    sun.position.set(-80, 140, 80);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    sun.shadow.camera.left = -100;
    sun.shadow.camera.right = 100;
    sun.shadow.camera.top = 100;
    sun.shadow.camera.bottom = -100;
    sun.shadow.bias = -0.00015;
    scene.add(sun);
    modelRoot = new THREE.Group();
    scene.add(modelRoot);
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;
    if ('outputColorSpace' in renderer && THREE.SRGBColorSpace) renderer.outputColorSpace = THREE.SRGBColorSpace;
    else if ('outputEncoding' in renderer) renderer.outputEncoding = THREE.sRGBEncoding;
    canvas.appendChild(renderer.domElement);
    camera = new THREE.PerspectiveCamera(42, canvas.clientWidth / canvas.clientHeight, 0.05, 5000);
    const plot = getPlot();
    const unitScale = plot.unit === 'meter' ? 3.28084 : 1;
    const longest = Math.max(plot.length * unitScale, plot.width * unitScale, 20);
    const target = new THREE.Vector3(0, plot.floors * 4.5, 0);
    const cameraPreset = cameraPresets[sceneState.cameraPreset] || cameraPresets.isometric;
    orbit.target = target.clone();
    orbit.initial = {
      target: target.clone(),
      azimuth: cameraPreset.azimuth,
      elevation: cameraPreset.elevation,
      distance: longest * 1.8,
    };
    orbit.azimuth = cameraPreset.azimuth;
    orbit.elevation = cameraPreset.elevation;
    orbit.distance = orbit.initial.distance;
    updateCamera();
    renderer.setAnimationLoop(() => renderer.render(scene, camera));
    if (resizeObserver) resizeObserver.disconnect();
    resizeHandler = () => {
      if (!renderer || !camera) return;
      const width = Math.max(1, canvas.clientWidth);
      const height = Math.max(1, canvas.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    if (window.ResizeObserver) {
      resizeObserver = new ResizeObserver(resizeHandler);
      resizeObserver.observe(canvas);
    } else {
      window.addEventListener('resize', resizeHandler);
    }
    attachCameraControls();
    setLighting();
  };

  const attachCameraControls = () => {
    if (canvas.dataset.controlsAttached) return;
    canvas.dataset.controlsAttached = 'true';
    const pointers = new Map();
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let lastPoint = null;
    let lastPinch = null;
    const setRayFromEvent = (event) => {
      const bounds = renderer.domElement.getBoundingClientRect();
      pointer.set(
        ((event.clientX - bounds.left) / Math.max(bounds.width, 1)) * 2 - 1,
        -((event.clientY - bounds.top) / Math.max(bounds.height, 1)) * 2 + 1,
      );
      raycaster.setFromCamera(pointer, camera);
    };
    canvas.addEventListener('contextmenu', (event) => event.preventDefault());
    canvas.addEventListener('keydown', (event) => {
      const step = event.shiftKey ? 0.18 : 0.08;
      if (event.key === 'Home') {
        event.preventDefault();
        resetCamera();
        return;
      }
      if (event.shiftKey && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
        const right = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 0);
        const up = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 1);
        if (event.key === 'ArrowLeft') orbit.target.addScaledVector(right, -orbit.distance * step * 0.1);
        if (event.key === 'ArrowRight') orbit.target.addScaledVector(right, orbit.distance * step * 0.1);
        if (event.key === 'ArrowUp') orbit.target.addScaledVector(up, orbit.distance * step * 0.1);
        if (event.key === 'ArrowDown') orbit.target.addScaledVector(up, -orbit.distance * step * 0.1);
        event.preventDefault();
        updateCamera();
        return;
      }
      if (event.key === 'ArrowLeft') orbit.azimuth -= step;
      else if (event.key === 'ArrowRight') orbit.azimuth += step;
      else if (event.key === 'ArrowUp') orbit.elevation = Math.min(1.35, orbit.elevation + step);
      else if (event.key === 'ArrowDown') orbit.elevation = Math.max(0.12, orbit.elevation - step);
      else if (event.key === '+' || event.key === '=') orbit.distance = Math.max(2, orbit.distance * 0.9);
      else if (event.key === '-') orbit.distance = Math.min(3000, orbit.distance * 1.1);
      else return;
      event.preventDefault();
      updateCamera();
    });
    canvas.addEventListener('pointerdown', (event) => {
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      canvas.setPointerCapture?.(event.pointerId);
      if (pointers.size === 1) {
        let openingState = null;
        if (event.button === 0 && !event.shiftKey && modelRoot) {
          setRayFromEvent(event);
          const hit = raycaster.intersectObject(modelRoot, true)
            .find((intersection) => intersection.object.userData.architecturalElementId);
          const elementId = hit?.object.userData.architecturalElementId;
          const item = selectedArchitecturalElementById(elementId);
          if (hit && item) {
            const metadata = hit.object.userData;
            const surface = metadata.openingSurface;
            const normal = surface === 'roof' ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(0, 0, 1);
            selectedElementId = item.id;
            openingState = {
              mode: 'opening',
              itemId: item.id,
              surface,
              plane: new THREE.Plane().setFromNormalAndCoplanarPoint(normal, hit.point),
              roomWidth: metadata.openingRoomWidth,
              roomDepth: metadata.openingRoomDepth,
              unitScale: metadata.openingUnitScale,
              roomWorldX: metadata.openingRoomWorldX,
              roomWorldZ: metadata.openingRoomWorldZ,
              startX: event.clientX,
              startY: event.clientY,
              dragged: false,
              lastUpdate: 0,
            };
            updateArchitecturalInspector();
            renderPlan();
          }
        }
        pointerState = openingState || { mode: event.button === 2 || event.shiftKey ? 'pan' : 'orbit', x: event.clientX, y: event.clientY };
        lastPoint = { x: event.clientX, y: event.clientY };
      } else if (pointers.size === 2) {
        const points = Array.from(pointers.values());
        lastPinch = Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
        pointerState = { mode: 'pinch' };
      }
    });
    canvas.addEventListener('pointermove', (event) => {
      if (!pointers.has(event.pointerId)) return;
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (pointers.size >= 2 && pointerState?.mode === 'pinch') {
        const points = Array.from(pointers.values());
        const distance = Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
        if (lastPinch) orbit.distance = Math.max(2, Math.min(3000, orbit.distance * (lastPinch / Math.max(distance, 1))));
        lastPinch = distance;
        updateCamera();
        return;
      }
      if (!pointerState || !lastPoint) return;
      if (pointerState.mode === 'opening') {
        const dragDistance = Math.hypot(event.clientX - pointerState.startX, event.clientY - pointerState.startY);
        if (!pointerState.dragged && dragDistance < 4) return;
        pointerState.dragged = true;
        setRayFromEvent(event);
        const intersection = raycaster.ray.intersectPlane(pointerState.plane, new THREE.Vector3());
        const item = selectedArchitecturalElementById(pointerState.itemId);
        if (!intersection || !item) return;
        const unitScale = Math.max(Number(pointerState.unitScale) || 1, 0.001);
        const roomDimensions = getRoomDimensions()[item.room];
        const itemWidth = Number(item.width) || 0;
        const itemDepth = Number(item.depth) || 0;
        const nextX = (intersection.x - pointerState.roomWorldX) / unitScale
          + pointerState.roomWidth / 2 - itemWidth / 2;
        item.x = Math.max(0, Math.min(roomDimensions.width - itemWidth, nextX));
        if (pointerState.surface === 'roof') {
          const nextY = pointerState.roomDepth / 2
            - (intersection.z - pointerState.roomWorldZ) / unitScale - itemDepth / 2;
          item.y = Math.max(0, Math.min(roomDimensions.depth - itemDepth, nextY));
        }
        const now = performance.now();
        if (now - pointerState.lastUpdate > 50) {
          const result = renderPlan();
          buildModel(result);
          pointerState.lastUpdate = now;
        }
        return;
      }
      const dx = event.clientX - lastPoint.x;
      const dy = event.clientY - lastPoint.y;
      lastPoint = { x: event.clientX, y: event.clientY };
      if (pointerState.mode === 'orbit') {
        orbit.azimuth -= dx * 0.006;
        orbit.elevation = Math.max(0.12, Math.min(1.35, orbit.elevation + dy * 0.005));
      } else {
        const right = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 0);
        const up = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 1);
        const factor = orbit.distance / Math.max(canvas.clientHeight, 1);
        orbit.target.addScaledVector(right, -dx * factor);
        orbit.target.addScaledVector(up, dy * factor);
      }
      updateCamera();
    });
    const finishPointer = (event) => {
      pointers.delete(event.pointerId);
      if (!pointers.size) {
        if (pointerState?.mode === 'opening' && pointerState.dragged) {
          const result = renderPlan();
          buildModel(result);
        }
        pointerState = null;
        lastPoint = null;
        lastPinch = null;
      } else if (pointers.size === 1) {
        const point = Array.from(pointers.values())[0];
        pointerState = { mode: 'orbit' };
        lastPoint = { ...point };
        lastPinch = null;
      }
    };
    canvas.addEventListener('pointerup', finishPointer);
    canvas.addEventListener('pointercancel', finishPointer);
    canvas.addEventListener('wheel', (event) => {
      event.preventDefault();
      orbit.distance = Math.max(2, Math.min(3000, orbit.distance * (1 + event.deltaY * 0.001)));
      updateCamera();
    }, { passive: false });
  };

  controls.roof.addEventListener('click', () => {
    sceneState.roofVisible = !sceneState.roofVisible;
    applySceneState();
  });
  controls.cutaway.addEventListener('click', () => {
    sceneState.cutaway = !sceneState.cutaway;
    applySceneState();
  });
  controls.walls.addEventListener('click', () => {
    sceneState.wallsOnly = !sceneState.wallsOnly;
    if (is3d) buildModel();
    applySceneState();
  });
  controls.floor.addEventListener('change', () => {
    sceneState.floorLevel = controls.floor.value;
    if (is3d) buildModel();
    else renderPlan();
  });
  controls.furniture.addEventListener('change', () => {
    sceneState.furnitureStyle = controls.furniture.value;
    if (is3d) buildModel();
    else renderPlan();
  });
  controls.finish.addEventListener('change', () => {
    sceneState.finish = controls.finish.value;
    if (is3d) buildModel();
  });
  controls.lighting.addEventListener('change', () => {
    sceneState.lighting = controls.lighting.value;
    setLighting();
  });
  controls.cameraView.addEventListener('change', () => setCameraPreset(controls.cameraView.value));
  controls.resetCamera.addEventListener('click', resetCamera);
  window.addEventListener('pagehide', () => {
    if (renderer) {
      renderer.setAnimationLoop(null);
      clearModel();
      renderer.dispose();
      renderer.domElement.remove();
      renderer = null;
    }
    if (resizeObserver) resizeObserver.disconnect();
    if (resizeHandler) window.removeEventListener('resize', resizeHandler);
  }, { once: true });

  updateStats();
  updateCompass();
  const initialPlan = renderPlan();
  update2DZoom();
  if (initialPlan) {
    const savedNorth = compass.dataset.northDirection || 'N';
    app.querySelector('.planner-north-arrow')?.setAttribute('aria-label', `North is ${savedNorth}`);
  }
})();
