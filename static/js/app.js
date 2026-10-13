document.querySelectorAll('.filter-pill').forEach((pill) => {
  pill.addEventListener('click', () => {
    document.querySelectorAll('.filter-pill').forEach((item) => item.classList.remove('active'));
    pill.classList.add('active');
  });
});

const themeToggle = document.querySelector('.theme-toggle');
const applyTheme = (isDark) => {
  document.body.classList.toggle('dark-mode', isDark);
  if (themeToggle) {
    const dot = themeToggle.querySelector('.theme-toggle-dot');
    if (dot) dot.textContent = isDark ? '☾' : '☀';
    themeToggle.setAttribute('aria-pressed', String(isDark));
  }
  try {
    localStorage.setItem('smart-house-theme', isDark ? 'dark' : 'light');
  } catch (error) {
    // no-op if storage is not available
  }
};

if (themeToggle) {
  const storedTheme = (() => {
    try {
      return localStorage.getItem('smart-house-theme') === 'dark';
    } catch (error) {
      return false;
    }
  })();
  applyTheme(storedTheme);
  themeToggle.addEventListener('click', () => applyTheme(!document.body.classList.contains('dark-mode')));
}

document.querySelectorAll('form').forEach((form) => { form.addEventListener('submit', () => { const button = form.querySelector('button[type="submit"]'); if (button) { button.disabled = true; button.style.opacity = '.7'; } }); });

const planner = document.querySelector('.planner-app');
const applySimulationForm = async (formId, endpoint, resultMapper) => {
  const form = document.getElementById(formId);
  if (!form) return;

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    if (button) {
      button.disabled = true;
      button.textContent = 'Running...';
    }

    const formData = new FormData(form);
    const payload = {};
    formData.forEach((value, key) => {
      payload[key] = value;
    });

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Simulation request failed.');
      }

      resultMapper(data);
    } catch (error) {
      console.error(error);
      if (form.nextElementSibling && form.nextElementSibling.classList.contains('simulation-message')) {
        form.nextElementSibling.textContent = error.message;
      } else {
        const message = document.createElement('div');
        message.className = 'simulation-message error';
        message.textContent = error.message;
        form.parentNode.insertBefore(message, form.nextSibling);
      }
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = button.dataset.originalText || button.textContent.replace('Running...', 'Run Simulation');
      }
    }
  });
};

const setReadout = (targetId, value) => {
  const target = document.getElementById(targetId);
  if (target) {
    target.textContent = value;
  }
};

const buildSimulationSummary = () => ({
  material: {
    indicative_strength: document.getElementById('material-strength')?.textContent || '—',
    estimated_material_cost: document.getElementById('material-cost')?.textContent || '—',
    durability_indicator: document.getElementById('material-durability')?.textContent || '—',
    overall_result: document.getElementById('material-result')?.textContent || '—',
  },
  load: {
    stress_indicator: document.getElementById('load-stress')?.textContent || '—',
    stress_level: document.getElementById('load-level')?.textContent || '—',
    simulation_result: document.getElementById('load-result')?.textContent || '—',
  },
  rainwater: {
    estimated_water_collected: document.getElementById('rainwater-collected')?.textContent || '—',
    monthly_potential: document.getElementById('rainwater-monthly')?.textContent || '—',
    tank_status: document.getElementById('rainwater-tank')?.textContent || '—',
  },
  solar: {
    capacity_kw: document.getElementById('solar-capacity')?.textContent || '—',
    panels: document.getElementById('solar-panels')?.textContent || '—',
    daily_generation_kwh: document.getElementById('solar-daily')?.textContent || '—',
    monthly_generation_kwh: document.getElementById('solar-monthly')?.textContent || '—',
  },
  cost: {
    total_estimated_cost: document.getElementById('cost-total')?.textContent || '—',
    base_cost: document.getElementById('cost-base')?.textContent || '—',
    labour_cost: document.getElementById('cost-labour')?.textContent || '—',
  },
  generated_at: new Date().toISOString(),
});

const bindSimulationLab = () => {
  const materialForm = document.getElementById('material-form');
  if (materialForm) {
    materialForm.querySelector('button[type="submit"]').dataset.originalText = 'Run Simulation';
    applySimulationForm('material-form', '/api/simulation/material', (data) => {
      setReadout('material-strength', data.indicative_strength || '—');
      setReadout('material-cost', `₹${Number(data.estimated_material_cost || 0).toLocaleString()}`);
      setReadout('material-durability', data.durability_indicator || '—');
      setReadout('material-result', data.overall_result || '—');
    });
  }

  const loadForm = document.getElementById('load-form');
  if (loadForm) {
    loadForm.querySelector('button[type="submit"]').dataset.originalText = 'Run Simulation';
    const loadSlider = loadForm.querySelector('input[name="load_value"]');
    const loadReadout = document.getElementById('load-value-readout');
    if (loadSlider && loadReadout) {
      loadSlider.addEventListener('input', () => {
        loadReadout.textContent = loadSlider.value;
      });
    }

    applySimulationForm('load-form', '/api/simulation/load', (data) => {
      setReadout('load-stress', data.stress_indicator || '—');
      setReadout('load-level', data.stress_level || '—');
      setReadout('load-result', data.simulation_result || '—');
      const building = document.querySelector('.load-building');
      if (building) {
        building.dataset.loadState = data.stress_level ? data.stress_level.toLowerCase() : 'medium';
      }
    });
  }

  const rainwaterForm = document.getElementById('rainwater-form');
  if (rainwaterForm) {
    rainwaterForm.querySelector('button[type="submit"]').dataset.originalText = 'Run Simulation';
    applySimulationForm('rainwater-form', '/api/simulation/rainwater', (data) => {
      setReadout('rainwater-collected', `${Number(data.estimated_water_collected || 0).toLocaleString()} L`);
      setReadout('rainwater-monthly', `${Number(data.monthly_potential || 0).toLocaleString()} L`);
      setReadout('rainwater-tank', data.tank_status || '—');
    });
  }

  const solarForm = document.getElementById('solar-form');
  if (solarForm) {
    solarForm.querySelector('button[type="submit"]').dataset.originalText = 'Run Simulation';
    applySimulationForm('solar-form', '/api/simulation/solar', (data) => {
      setReadout('solar-capacity', `${Number(data.capacity_kw || 0).toFixed(2)} kW`);
      setReadout('solar-panels', String(data.panels || 0));
      setReadout('solar-daily', `${Number(data.daily_generation_kwh || 0).toFixed(2)} kWh`);
      setReadout('solar-monthly', `${Number(data.monthly_generation_kwh || 0).toFixed(2)} kWh`);
    });
  }

  const costForm = document.getElementById('cost-form');
  if (costForm) {
    costForm.querySelector('button[type="submit"]').dataset.originalText = 'Run Simulation';
    applySimulationForm('cost-form', '/api/simulation/cost', (data) => {
      setReadout('cost-base', `₹${Number(data.base_cost || 0).toLocaleString()}`);
      setReadout('cost-material', `₹${Number(data.material_cost || 0).toLocaleString()}`);
      setReadout('cost-labour', `₹${Number(data.labour_cost || 0).toLocaleString()}`);
      setReadout('cost-contingency', `₹${Number(data.contingency || 0).toLocaleString()}`);
      setReadout('cost-total', `₹${Number(data.total_estimated_cost || 0).toLocaleString()}`);
    });
  }

  const whatIfForm = document.getElementById('whatif-form');
  if (whatIfForm) {
    whatIfForm.querySelector('button[type="submit"]').dataset.originalText = 'Run Simulation';
    applySimulationForm('whatif-form', '/api/simulation/what-if', (data) => {
      setReadout('whatif-before-area', `${Number(data.built_up_area || 0).toLocaleString()} sq ft`);
      setReadout('whatif-after-area', `${Number(data.built_up_area || 0).toLocaleString()} sq ft`);
      setReadout('whatif-materials', `${Object.keys(data.estimated_material_requirement || {}).length} item types`);
      setReadout('whatif-cost', `₹${Number(data.estimated_construction_cost || 0).toLocaleString()}`);
      setReadout('whatif-solar', `${Number(data.solar_potential?.monthly_generation_kwh || 0).toFixed(2)} kWh`);
      setReadout('whatif-rainwater', `${Number(data.rainwater_potential?.monthly_potential || 0).toFixed(2)} L`);
    });
  }

  const costSliders = document.querySelectorAll('#cost-form input[type="range"]');
  costSliders.forEach((slider) => {
    slider.addEventListener('input', () => {
      const label = slider.closest('label');
      if (label) {
        const existing = label.querySelector('.slider-output');
        const value = `${slider.value}%`;
        if (existing) {
          existing.textContent = value;
        } else {
          const span = document.createElement('span');
          span.className = 'slider-output';
          span.textContent = value;
          label.appendChild(span);
        }
      }
    });
  });

  const viewTabs = document.querySelectorAll('.view-tab');
  const building = document.getElementById('visual-building');
  if (viewTabs.length && building) {
    viewTabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        viewTabs.forEach((item) => item.classList.toggle('active', item === tab));
        building.classList.remove('front', 'side', 'top');
        building.classList.add(tab.dataset.view || 'front');
      });
    });
  }

  const styleSelect = document.getElementById('visual-style-select');
  if (styleSelect && building) {
    styleSelect.addEventListener('change', () => {
      const style = styleSelect.value;
      building.dataset.style = style;
      building.style.filter = style === 'eco' ? 'saturate(1.2) contrast(1.05)' : style === 'classic' ? 'sepia(0.2)' : 'none';
    });
  }

  const visualFloorSelect = document.getElementById('visual-floor-select');
  if (visualFloorSelect && building) {
    const applyFloorSelection = () => {
      const floorCount = visualFloorSelect.value === 'all' ? '4' : visualFloorSelect.value;
      building.dataset.floorCount = floorCount;
      building.dataset.floorLabel = visualFloorSelect.value === 'all' ? 'All floors' : `${floorCount} floor${floorCount > 1 ? 's' : ''}`;
    };
    visualFloorSelect.addEventListener('change', applyFloorSelection);
    applyFloorSelection();
  }

  const saveSimulationForm = document.getElementById('save-simulation-form');
  if (saveSimulationForm) {
    saveSimulationForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const selectedProject = document.getElementById('simulation-project-select');
      if (!selectedProject || !selectedProject.value) {
        return;
      }

      const outcome = {
        material: document.getElementById('material-strength')?.textContent || '—',
        load: document.getElementById('load-stress')?.textContent || '—',
        rainwater: document.getElementById('rainwater-collected')?.textContent || '—',
        solar: document.getElementById('solar-capacity')?.textContent || '—',
        cost: document.getElementById('cost-total')?.textContent || '—'
      };

      try {
        const response = await fetch('/api/simulation/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_id: selectedProject.value, outcome })
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || 'Unable to save simulation.');
        }
        const successMessage = document.createElement('div');
        successMessage.className = 'simulation-message success';
        successMessage.textContent = data.message || 'Simulation saved to project.';
        saveSimulationForm.insertAdjacentElement('afterend', successMessage);
      } catch (error) {
        const errorMessage = document.createElement('div');
        errorMessage.className = 'simulation-message error';
        errorMessage.textContent = error.message;
        saveSimulationForm.insertAdjacentElement('afterend', errorMessage);
      }
    });
  }

  const exportButton = document.getElementById('export-simulation-report');
  if (exportButton) {
    exportButton.addEventListener('click', async () => {
      try {
        const response = await fetch('/api/simulation/export', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ summary: buildSimulationSummary() })
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.error || 'Unable to export the simulation report.');
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'construction-simulation-report.pdf';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      } catch (error) {
        const existingMessage = document.querySelector('.simulation-message.error[data-export-message="true"]');
        if (existingMessage) existingMessage.remove();
        const message = document.createElement('div');
        message.className = 'simulation-message error';
        message.dataset.exportMessage = 'true';
        message.textContent = error.message;
        const savePanel = document.querySelector('.simulation-save-panel');
        if (savePanel) savePanel.insertAdjacentElement('beforeend', message);
      }
    });
  }
};

const bindPlannerApp = () => {
	const roomLayer = document.querySelector('#room-layer');
	const roomCounts = {};
	const roomPlacements = {};
	const palette = [...document.querySelectorAll('.room-tool')];
	const roomDimensionInputs = [...document.querySelectorAll('.room-dim-input')];
	const colors = ['#d7eadb', '#f4d8bb', '#d8e1f1', '#f1e0b6', '#e4d6e8'];
	const createPlacement = (room, index) => {
		const slots = 3;
		const columns = 3;
		const x = 140 + (index % columns) * 210;
		const y = 90 + Math.floor(index / slots) * 150;
		return { x, y };
	};
	const defaultRoomDimensions = {
		'Bedroom': { width: 12, depth: 10 },
		'Master Bedroom': { width: 14, depth: 12 },
		'Living Room': { width: 16, depth: 12 },
		'Kitchen': { width: 10, depth: 9 },
		'Bathroom': { width: 8, depth: 7 },
		'Dining Room': { width: 12, depth: 10 },
		'Balcony': { width: 8, depth: 6 },
		'Store Room': { width: 8, depth: 8 },
		'Study Room': { width: 10, depth: 8 },
		'Parking': { width: 16, depth: 10 }
	};
	const syncRoomDimensions = () => {
		const roomDimensions = {};
		roomDimensionInputs.forEach((input) => {
			const room = input.dataset.room;
			const dimension = input.dataset.dimension;
			if (!roomDimensions[room]) roomDimensions[room] = { ...defaultRoomDimensions[room] };
			const defaults = defaultRoomDimensions[room] || { width: 12, depth: 10 };
			const value = Number(input.value) || defaults[dimension] || 0;
			roomDimensions[room][dimension] = Number(value.toFixed(1));
			input.value = roomDimensions[room][dimension];
			const hiddenField = document.querySelector(`input[name="room_${dimension}_${room}"]`);
			if (hiddenField) hiddenField.value = roomDimensions[room][dimension];
		});
		return roomDimensions;
	};
	const ensureRoomPlacements = () => {
		Object.entries(roomCounts).forEach(([room, count]) => {
			if (!roomPlacements[room]) {
				roomPlacements[room] = [];
			}
			while (roomPlacements[room].length < count) {
				const slotIndex = roomPlacements[room].length;
				roomPlacements[room].push(createPlacement(room, slotIndex));
			}
			roomPlacements[room] = roomPlacements[room].slice(0, count);
		});
		Object.keys(roomPlacements).forEach((room) => {
			if (!roomCounts[room] || roomCounts[room] <= 0) {
				delete roomPlacements[room];
			}
		});
	};
	const render = () => {
		roomLayer.innerHTML = '';
		const roomDimensions = syncRoomDimensions();
		const active = Object.entries(roomCounts).filter(([, count]) => count > 0);
		if (active.length === 0) {
			console.warn('No rooms added. Adding a sample room for visualization.');
			roomCounts['Sample Room'] = 1;
		}
		ensureRoomPlacements();
		const roomEntries = [];
		Object.entries(roomCounts).forEach(([name, count]) => {
			const placements = roomPlacements[name] || [];
			for (let index = 0; index < count; index += 1) {
				const position = placements[index] || createPlacement(name, index);
				roomEntries.push({ name, index, position });
			}
		});
		const roomWidth = 190;
		const roomHeight = 125;
		roomEntries.forEach(({ name, index, position }, entryIndex) => {
			const dimensions = roomDimensions[name] || defaultRoomDimensions[name] || { width: 12, depth: 10 };
			const x = position.x;
			const y = position.y;
			const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
			group.setAttribute('class', 'room-instance');
			group.dataset.room = name;
			group.dataset.index = String(index);
			group.innerHTML = `<rect class="room-rect" x="${x}" y="${y}" width="${roomWidth}" height="${roomHeight}" rx="3" fill="${colors[entryIndex % colors.length]}"/><text class="room-label" x="${x + 14}" y="${y + 55}">${name}</text><text class="room-size" x="${x + 14}" y="${y + 78}">Approx. ${dimensions.width}' × ${dimensions.depth}'</text><text class="room-size" x="${x + roomWidth - 18}" y="${y + 22}" text-anchor="end">×${index + 1}</text>`;
			roomLayer.appendChild(group);
		});
		palette.forEach((button) => { button.querySelector('b').textContent = roomCounts[button.dataset.room] || '+'; });
		document.querySelectorAll('[id^="form-room-"]').forEach((input, index) => { input.value = roomCounts[palette[index]?.dataset.room] || 0; });
		const draggableGroups = roomLayer.querySelectorAll('.room-instance');
		draggableGroups.forEach((group) => {
			group.addEventListener('pointerdown', (event) => {
				event.preventDefault();
				const room = group.dataset.room;
				const index = Number(group.dataset.index);
				const currentPosition = roomPlacements[room]?.[index] || createPlacement(room, index);
				const pointer = roomLayer.createSVGPoint();
				pointer.x = event.clientX;
				pointer.y = event.clientY;
				const transformed = pointer.matrixTransform(roomLayer.getScreenCTM().inverse());
				let dragState = {
					room,
					index,
					offsetX: transformed.x - currentPosition.x,
					offsetY: transformed.y - currentPosition.y,
				};
				const handlePointerMove = (moveEvent) => {
					const nextPoint = roomLayer.createSVGPoint();
					nextPoint.x = moveEvent.clientX;
					nextPoint.y = moveEvent.clientY;
					const nextTransformed = nextPoint.matrixTransform(roomLayer.getScreenCTM().inverse());
					const clampedX = Math.max(80, Math.min(620, nextTransformed.x - dragState.offsetX));
					const clampedY = Math.max(60, Math.min(410, nextTransformed.y - dragState.offsetY));
					if (!roomPlacements[dragState.room]) roomPlacements[dragState.room] = [];
					roomPlacements[dragState.room][dragState.index] = { x: clampedX, y: clampedY };
					render();
				};
				const handlePointerUp = () => {
					window.removeEventListener('pointermove', handlePointerMove);
					window.removeEventListener('pointerup', handlePointerUp);
				};
				window.addEventListener('pointermove', handlePointerMove);
				window.addEventListener('pointerup', handlePointerUp);
			});
		});
	};
	palette.forEach((button) => button.addEventListener('click', () => { const room = button.dataset.room; roomCounts[room] = (roomCounts[room] || 0) + 1; render(); }));
	roomDimensionInputs.forEach((input) => input.addEventListener('input', () => {
		syncRoomDimensions();
		render();
		if (is3DView && renderer) {
			const existingCanvas = canvas3D.querySelector('canvas');
			if (existingCanvas) existingCanvas.remove();
			renderer = null;
			scene = null;
			init3D();
		}
	}));
	const updateStats = () => { const length = Number(document.querySelector('#plot-length').value) || 0; const width = Number(document.querySelector('#plot-width').value) || 0; const floors = Number(document.querySelector('#floor-selector').value) || 1; const area = length * width; document.querySelector('#plot-area').textContent = `${area.toFixed(0)} sq ft`; document.querySelector('#built-area').textContent = `${(area * .7 * floors).toFixed(0)} sq ft`; document.querySelector('#open-area').textContent = `${(area * .3).toFixed(0)} sq ft`; document.querySelector('#form-project-name').value = document.querySelector('#project-name').value; document.querySelector('#form-plot-length').value = length; document.querySelector('#form-plot-width').value = width; document.querySelector('#form-unit').value = document.querySelector('#unit-selector').value; document.querySelector('#form-floors').value = floors; syncRoomDimensions(); };
	document.querySelectorAll('#plot-length,#plot-width,#project-name,#floor-selector,#unit-selector').forEach((input) => input.addEventListener('input', updateStats));
	document.querySelector('#reset-layout').addEventListener('click', () => { Object.keys(roomCounts).forEach((key) => delete roomCounts[key]); render(); });
	document.querySelector('#grid-toggle').addEventListener('click', () => document.querySelector('.plan-grid').classList.toggle('hidden'));
	let zoom = 100; const changeZoom = (amount) => { zoom = Math.max(70, Math.min(130, zoom + amount)); document.querySelector('#zoom-level').textContent = `${zoom}%`; document.querySelector('#floor-plan').style.transform = `scale(${zoom / 100})`; document.querySelector('#floor-plan').style.transformOrigin = 'top left'; }; document.querySelector('#zoom-in').addEventListener('click', () => changeZoom(10)); document.querySelector('#zoom-out').addEventListener('click', () => changeZoom(-10));
	updateStats(); render();
	
	// 3D Visualization Feature
	let is3DView = false;
	let scene, camera, renderer;
	const viewToggle = document.querySelector('#view-toggle');
	const roofToggle = document.querySelector('#roof-toggle');
	const wallsOnlyToggle = document.querySelector('#walls-only-toggle');
	const furnitureStyleSelect = document.querySelector('#furniture-style');
	const floorLevelSelect = document.querySelector('#floor-level');
	const viewModeLabel = document.querySelector('#view-mode-label');
	const canvas3D = document.getElementById('3d-canvas');
	const floorPlan = document.querySelector('#floor-plan');
	const roomHeights = {
		'Bedroom': 16,
		'Master Bedroom': 18,
		'Living Room': 20,
		'Kitchen': 15,
		'Bathroom': 12,
		'Dining Room': 16,
		'Balcony': 10,
		'Store Room': 12,
		'Study Room': 14,
		'Parking': 12,
	};
	const roomFurnitureMap = {
		'Bedroom': ['bed', 'wardrobe'],
		'Master Bedroom': ['bed', 'cabinet', 'desk'],
		'Living Room': ['sofa', 'table', 'tv'],
		'Kitchen': ['counter', 'cabinet', 'island'],
		'Bathroom': ['vanity', 'shower'],
		'Dining Room': ['table', 'chair'],
		'Balcony': ['bench', 'planter'],
		'Store Room': ['shelf'],
		'Study Room': ['desk', 'chair'],
		'Parking': ['car']
	};
	const sceneState = {
		roofVisible: true,
		wallsOnly: false,
		furnitureStyle: 'standard',
		floorLevel: 'all'
	};
	const applySceneState = () => {
		if (!scene) return;
		scene.traverse((obj) => {
			if (obj.userData && obj.userData.isRoof) obj.visible = sceneState.roofVisible;
			if (obj.userData && obj.userData.isFurniture) obj.visible = !sceneState.wallsOnly;
			if (obj.userData && obj.userData.isLabel) obj.visible = !sceneState.wallsOnly;
			if (obj.userData && obj.userData.floorIndex !== undefined) {
				const visibleFloors = sceneState.floorLevel === 'all' ? [0, 1] : sceneState.floorLevel === 'ground' ? [0] : [1];
				obj.visible = visibleFloors.includes(obj.userData.floorIndex);
			}
		});
		if (roofToggle) roofToggle.textContent = `Roof: ${sceneState.roofVisible ? 'On' : 'Off'}`;
		if (wallsOnlyToggle) wallsOnlyToggle.textContent = `Walls only: ${sceneState.wallsOnly ? 'On' : 'Off'}`;
	};
	
	const init3D = () => {
		try {
		if (!canvas3D) {
			console.error('3D canvas element not found');
			return;
		}
		if (canvas3D.style.display === 'none') {
			canvas3D.style.display = 'block';
		}
		const fallbackWidth = canvas3D.clientWidth || canvas3D.parentElement?.clientWidth || 720;
		const fallbackHeight = canvas3D.clientHeight || 520;
		canvas3D.style.width = '100%';
		canvas3D.style.height = `${fallbackHeight}px`;
		if (fallbackWidth <= 0 || fallbackHeight <= 0) {
			console.error('3D canvas has no size');
			return;
		}
		if (renderer) {
			renderer.dispose();
			const canvas = canvas3D.querySelector('canvas');
			if (canvas) canvas.remove();
			renderer = null;
			scene = null;
			camera = null;
		}
			scene = new THREE.Scene();
			scene.background = new THREE.Color(0xf5f1e8);
			scene.fog = new THREE.Fog(0xf5f1e8, 600, 1800);
		
		camera = new THREE.PerspectiveCamera(52, canvas3D.clientWidth / canvas3D.clientHeight, 0.1, 2000);
		const cameraTarget = new THREE.Vector3(0, 52, 0);
		let azimuth = 1.1;
		let elevation = 0.62;
		let distance = 820;
		const updateCamera = () => {
			const x = cameraTarget.x + distance * Math.sin(azimuth) * Math.cos(elevation);
			const y = cameraTarget.y + distance * Math.sin(elevation);
			const z = cameraTarget.z + distance * Math.cos(azimuth) * Math.cos(elevation);
			camera.position.set(x, y, z);
			camera.lookAt(cameraTarget);
		};
		updateCamera();
		
		renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
		renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
		renderer.setSize(canvas3D.clientWidth, canvas3D.clientHeight);
		renderer.shadowMap.enabled = true;
		renderer.shadowMap.type = THREE.PCFSoftShadowMap;
		canvas3D.appendChild(renderer.domElement);
		
		const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
		scene.add(ambientLight);
		const hemiLight = new THREE.HemisphereLight(0xeaf6ff, 0x9ba68d, 0.9);
		scene.add(hemiLight);
		const directionalLight = new THREE.DirectionalLight(0xffffff, 0.9);
		directionalLight.position.set(200, 320, 140);
		directionalLight.castShadow = true;
		directionalLight.shadow.mapSize.width = 2048;
		directionalLight.shadow.mapSize.height = 2048;
		scene.add(directionalLight);
		
		const ground = new THREE.Mesh(
			new THREE.PlaneGeometry(900, 700),
			new THREE.MeshStandardMaterial({ color: 0xdfead5, roughness: 0.95, metalness: 0.05 })
		);
		ground.rotation.x = -Math.PI / 2;
		ground.receiveShadow = true;
		scene.add(ground);
		
		const basePad = new THREE.Mesh(
			new THREE.BoxGeometry(700, 18, 520),
			new THREE.MeshStandardMaterial({ color: 0xe0d9c7, roughness: 0.9 })
		);
		basePad.position.y = 9;
		basePad.receiveShadow = true;
		scene.add(basePad);
		
		const active = Object.entries(roomCounts).filter(([, count]) => count > 0);
		const roomDimensions = syncRoomDimensions();
		const roomColors = {
			'Bedroom': 0xf4d8bb,
			'Master Bedroom': 0xf0c6a5,
			'Living Room': 0xd7eadb,
			'Kitchen': 0xf1e0b6,
			'Bathroom': 0xd8e1f1,
			'Dining Room': 0xe4d6e8,
			'Balcony': 0xcfe9de,
			'Store Room': 0xdfe7ce,
			'Study Room': 0xf5d9d9,
			'Parking': 0xbfc8d6,
		};
		
		const maxRoomHeight = Math.max(...Object.values(roomHeights), 14);
		const createGableRoof = (width, depth, height, roofHeight) => {
			const roofGroup = new THREE.Group();
			const slope = Math.atan2(roofHeight, width / 2);
			const roofMaterial = new THREE.MeshStandardMaterial({ color: 0xa85a3a, roughness: 0.72, side: THREE.DoubleSide, transparent: true, opacity: 0.58 });
			const panelLength = Math.sqrt((width / 2) ** 2 + roofHeight ** 2);
			const panelGeometry = new THREE.BoxGeometry(panelLength + 18, 6, depth + 24);
			const leftPanel = new THREE.Mesh(panelGeometry, roofMaterial);
			leftPanel.position.set(-width / 4, roofHeight / 2, 0);
			leftPanel.rotation.z = slope;
			leftPanel.castShadow = true;
			leftPanel.receiveShadow = true;
			roofGroup.add(leftPanel);
			const rightPanel = new THREE.Mesh(panelGeometry, roofMaterial);
			rightPanel.position.set(width / 4, roofHeight / 2, 0);
			rightPanel.rotation.z = -slope;
			rightPanel.castShadow = true;
			rightPanel.receiveShadow = true;
			roofGroup.add(rightPanel);
			roofGroup.position.y = height + 12;
			roofGroup.userData.isRoof = true;
			return roofGroup;
		};
		const roofGroup = createGableRoof(760, 560, maxRoomHeight, 32);
		scene.add(roofGroup);
		const furnitureScaleMap = { minimal: 0.7, standard: 1, luxury: 1.3 };
		const furnitureCountMap = { minimal: 1, standard: 2, luxury: 3 };
		const selectedFloorCount = Math.max(1, Number(document.querySelector('#floor-selector')?.value || 1));
		const visibleFloors = (() => {
			if (sceneState.floorLevel === 'all') {
				return Array.from({ length: selectedFloorCount }, (_, index) => index);
			}
			const floorLevelMap = { ground: 0, first: 1, second: 2, third: 3, fourth: 4 };
			const requestedFloor = floorLevelMap[sceneState.floorLevel] ?? 0;
			return requestedFloor < selectedFloorCount ? [requestedFloor] : [0];
		})();
		active.forEach(([name, count], index) => {
			const dimensions = roomDimensions[name] || defaultRoomDimensions[name] || { width: 12, depth: 10 };
			const roomWidth = Math.max(90, Math.min(230, dimensions.width * 12));
			const roomDepth = Math.max(90, Math.min(210, dimensions.depth * 12));
			const roomHeight = roomHeights[name] || 14;
			const columns = 2;
			const xOffset = ((index % columns) - 0.5) * 220;
			const zOffset = (Math.floor(index / columns) - 0.5) * 180;
			for (let i = 0; i < count; i++) {
				visibleFloors.forEach((floorIndex) => {
					const roomGroup = new THREE.Group();
					roomGroup.userData.floorIndex = floorIndex;
					const roomX = xOffset + (i % 2) * 95;
					const roomZ = zOffset + Math.floor(i / 2) * 90;
					const levelOffset = floorIndex === 0 ? 0 : 100;
					const floor = new THREE.Mesh(
						new THREE.BoxGeometry(roomWidth, 4, roomDepth),
						new THREE.MeshStandardMaterial({ color: 0xf7f4ee, roughness: 0.9 })
					);
					floor.position.set(roomX, 2 + levelOffset, roomZ);
					floor.castShadow = true;
					floor.receiveShadow = true;
					roomGroup.add(floor);
					const wallMaterial = new THREE.MeshStandardMaterial({ color: roomColors[name] || 0xb9d8c6, roughness: 0.72, side: THREE.DoubleSide });
					const wallThickness = 5;
					const wallHeight = roomHeight;
					const doorWidth = Math.min(38, roomWidth * 0.24);
					const doorHeight = Math.min(48, wallHeight * 0.7);
					const frontWallLength = roomWidth - doorWidth;
					const sideWallLength = roomDepth - 18;
					const frontLeft = new THREE.Mesh(new THREE.BoxGeometry(frontWallLength / 2, wallHeight, wallThickness), wallMaterial);
					const frontRight = new THREE.Mesh(new THREE.BoxGeometry(frontWallLength / 2, wallHeight, wallThickness), wallMaterial);
					const backWall = new THREE.Mesh(new THREE.BoxGeometry(roomWidth, wallHeight, wallThickness), wallMaterial);
					const leftWall = new THREE.Mesh(new THREE.BoxGeometry(wallThickness, wallHeight, sideWallLength), wallMaterial);
					const rightWall = new THREE.Mesh(new THREE.BoxGeometry(wallThickness, wallHeight, sideWallLength), wallMaterial);
					frontLeft.position.set(roomX - doorWidth / 2, wallHeight / 2 + 4 + levelOffset, roomZ - roomDepth / 2);
					frontRight.position.set(roomX + doorWidth / 2 + frontWallLength / 2, wallHeight / 2 + 4 + levelOffset, roomZ - roomDepth / 2);
					backWall.position.set(roomX, wallHeight / 2 + 4 + levelOffset, roomZ + roomDepth / 2);
					leftWall.position.set(roomX - roomWidth / 2, wallHeight / 2 + 4 + levelOffset, roomZ);
					rightWall.position.set(roomX + roomWidth / 2, wallHeight / 2 + 4 + levelOffset, roomZ);
					[
						frontLeft, frontRight, backWall, leftWall, rightWall
					].forEach((wall) => {
						wall.castShadow = true;
						wall.receiveShadow = true;
						roomGroup.add(wall);
					});
					const doorFrame = new THREE.Mesh(
						new THREE.BoxGeometry(doorWidth + 8, doorHeight + 8, 8),
						new THREE.MeshStandardMaterial({ color: 0xa56b43, roughness: 0.7, metalness: 0.15 })
					);
					doorFrame.position.set(roomX, doorHeight / 2 + 4 + levelOffset, roomZ - roomDepth / 2 + 4);
					roomGroup.add(doorFrame);
					const doorPanel = new THREE.Mesh(
						new THREE.BoxGeometry(doorWidth, doorHeight, 4),
						new THREE.MeshStandardMaterial({ color: 0x8d5d44, roughness: 0.8 })
					);
					doorPanel.position.set(roomX, doorHeight / 2 + 4 + levelOffset, roomZ - roomDepth / 2 + 7);
					roomGroup.add(doorPanel);
					const furniture = roomFurnitureMap[name] || ['cabinet'];
					const furnitureCount = {
						minimal: 1,
						standard: 2,
						luxury: furniture.length
					}[sceneState.furnitureStyle] || 2;
					const furnitureItems = furniture.slice(0, furnitureCount);
					const furniturePositions = {
						bedroom: [-30, 0, -20],
						livingroom: [-30, -10, 0, 10],
						kitchen: [-25, -5, 15],
						diningroom: [-20, 0, 20],
						default: [-25, 0, 15]
					};
					const normalizedName = name.toLowerCase().replace(/\s+/g, '');
					const positions = furniturePositions[normalizedName] || furniturePositions.default;
					furnitureItems.forEach((item, fi) => {
						let geometry = new THREE.BoxGeometry(20, 14, 18);
						let color = 0x8b7a66;
						if (item === 'bed') { geometry = new THREE.BoxGeometry(52, 12, 34); color = 0x8d8d8d; }
						if (item === 'wardrobe') { geometry = new THREE.BoxGeometry(18, 36, 12); color = 0x7d6a61; }
						if (item === 'sofa') { geometry = new THREE.BoxGeometry(55, 16, 22); color = 0x9ca6a0; }
						if (item === 'table') { geometry = new THREE.BoxGeometry(30, 10, 30); color = 0x7e6d59; }
						if (item === 'tv') { geometry = new THREE.BoxGeometry(26, 18, 4); color = 0x2f3742; }
						if (item === 'counter') { geometry = new THREE.BoxGeometry(48, 10, 24); color = 0xc7bca0; }
						if (item === 'cabinet') { geometry = new THREE.BoxGeometry(24, 18, 16); color = 0x8b744f; }
						if (item === 'island') { geometry = new THREE.BoxGeometry(34, 14, 20); color = 0xa98b5f; }
						if (item === 'vanity') { geometry = new THREE.BoxGeometry(26, 18, 16); color = 0xdbc9b7; }
						if (item === 'shower') { geometry = new THREE.BoxGeometry(24, 18, 24); color = 0xb9d7e3; }
						if (item === 'chair') { geometry = new THREE.BoxGeometry(16, 14, 16); color = 0xcaa27b; }
						if (item === 'bench') { geometry = new THREE.BoxGeometry(32, 10, 14); color = 0x9a8d7d; }
						if (item === 'planter') { geometry = new THREE.BoxGeometry(18, 12, 18); color = 0x5f8c67; }
						if (item === 'shelf') { geometry = new THREE.BoxGeometry(28, 22, 12); color = 0x8b7a66; }
						if (item === 'desk') { geometry = new THREE.BoxGeometry(42, 10, 22); color = 0x8c6d5e; }
						if (item === 'car') { geometry = new THREE.BoxGeometry(42, 12, 20); color = 0x4e6f9d; }
						const scaleMultiplier = furnitureScaleMap[sceneState.furnitureStyle] || 1;
						const furnitureMesh = new THREE.Mesh(
							geometry,
							new THREE.MeshStandardMaterial({ color, roughness: 0.75, metalness: 0.1 })
						);
						furnitureMesh.scale.setScalar(scaleMultiplier);
						const baseX = Array.isArray(positions) ? positions[fi % positions.length] || (-30 + fi * 20) : (-30 + fi * 20);
						const xPos = typeof baseX === 'number' ? baseX : -30 + fi * 20;
						const zPos = -35 + Math.floor(fi / 2) * 30;
						furnitureMesh.position.set(roomX + xPos, item === 'car' ? 8 + levelOffset : 8 + levelOffset + geometry.parameters.height / 2, roomZ + zPos);
						furnitureMesh.castShadow = true;
						furnitureMesh.receiveShadow = true;
						furnitureMesh.userData.isFurniture = true;
						roomGroup.add(furnitureMesh);
					});
					const labelCanvas = document.createElement('canvas');
					labelCanvas.width = 1024;
					labelCanvas.height = 240;
					const labelContext = labelCanvas.getContext('2d');
					labelContext.clearRect(0, 0, labelCanvas.width, labelCanvas.height);
					labelContext.fillStyle = 'rgba(24, 33, 29, 0.92)';
					labelContext.fillRect(0, 0, labelCanvas.width, labelCanvas.height);
					labelContext.fillStyle = '#ffffff';
					labelContext.font = '700 96px Arial';
					labelContext.textAlign = 'center';
					labelContext.textBaseline = 'middle';
					labelContext.fillText(name, labelCanvas.width / 2, labelCanvas.height / 2);
					const labelTexture = new THREE.CanvasTexture(labelCanvas);
					labelTexture.needsUpdate = true;
					labelTexture.minFilter = THREE.LinearFilter;
					labelTexture.magFilter = THREE.LinearFilter;
					const labelMaterial = new THREE.SpriteMaterial({
						map: labelTexture,
						transparent: true,
						depthTest: false,
						depthWrite: false,
						sizeAttenuation: true
					});
					const label = new THREE.Sprite(labelMaterial);
					label.scale.set(roomWidth * 0.75, 42, 1);
					label.position.set(roomX, roomHeight + 18 + levelOffset, roomZ);
					label.userData.isLabel = true;
					roomGroup.add(label);
					scene.add(roomGroup);
				});
			}
		});
		applySceneState();
		let isDragging = false;
		let previousMousePosition = { x: 0, y: 0 };
		canvas3D.addEventListener('mousedown', (event) => {
			isDragging = true;
			previousMousePosition = { x: event.clientX, y: event.clientY };
		});
		canvas3D.addEventListener('mousemove', (event) => {
			if (!isDragging) return;
			const deltaX = event.clientX - previousMousePosition.x;
			const deltaY = event.clientY - previousMousePosition.y;
			azimuth -= deltaX * 0.005;
			elevation = Math.min(Math.PI / 2.1, Math.max(0.2, elevation + deltaY * 0.004));
			previousMousePosition = { x: event.clientX, y: event.clientY };
			updateCamera();
		});
		canvas3D.addEventListener('mouseup', () => { isDragging = false; });
		canvas3D.addEventListener('mouseleave', () => { isDragging = false; });
		canvas3D.addEventListener('wheel', (event) => {
			event.preventDefault();
			distance = Math.min(980, Math.max(180, distance + event.deltaY * 0.02));
			updateCamera();
		}, { passive: false });
		window.addEventListener('resize', () => {
			if (!canvas3D) return;
			camera.aspect = canvas3D.clientWidth / canvas3D.clientHeight;
			camera.updateProjectionMatrix();
			renderer.setSize(canvas3D.clientWidth, canvas3D.clientHeight);
		});
		const animate = () => {
			requestAnimationFrame(animate);
			renderer.render(scene, camera);
		};
		animate();
		} catch (error) {
			console.error('Error initializing 3D scene:', error);
		}
	};
	if (roofToggle) {
		roofToggle.addEventListener('click', () => {
			sceneState.roofVisible = !sceneState.roofVisible;
			applySceneState();
		});
	}
	if (wallsOnlyToggle) {
		wallsOnlyToggle.addEventListener('click', () => {
			sceneState.wallsOnly = !sceneState.wallsOnly;
			applySceneState();
		});
	}
	if (furnitureStyleSelect) {
		furnitureStyleSelect.addEventListener('change', () => {
			sceneState.furnitureStyle = furnitureStyleSelect.value;
			if (renderer) {
				const existingCanvas = canvas3D.querySelector('canvas');
				if (existingCanvas) existingCanvas.remove();
				renderer = null;
				scene = null;
				init3D();
			}
		});
	}
	if (floorLevelSelect) {
		floorLevelSelect.addEventListener('change', () => {
			sceneState.floorLevel = floorLevelSelect.value;
			if (renderer && scene) applySceneState();
		});
	}
	if (viewToggle) {
		const toggle3DView = () => {
			is3DView = !is3DView;
			if (is3DView) {
				floorPlan.style.display = 'none';
				canvas3D.style.display = 'block';
				canvas3D.style.width = '100%';
				canvas3D.style.height = '520px';
				viewToggle.textContent = '2D View';
				viewModeLabel.textContent = '3D immersive view';
				requestAnimationFrame(() => {
					if (canvas3D && canvas3D.clientWidth > 0 && canvas3D.clientHeight > 0) {
						init3D();
					}
				});
			} else {
				floorPlan.style.display = 'block';
				canvas3D.style.display = 'none';
				viewToggle.textContent = '3D View';
				viewModeLabel.textContent = '2D plan view';
			}
		};
		viewToggle.addEventListener('click', toggle3DView);
	}
}

if (document.getElementById('material-form') || document.getElementById('load-form') || document.getElementById('cost-form') || document.getElementById('whatif-form')) {
  bindSimulationLab();
}

if (document.querySelector('.planner-app')) {
  bindPlannerApp();
}