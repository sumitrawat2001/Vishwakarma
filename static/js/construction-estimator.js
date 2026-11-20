(function () {
  const form = document.getElementById('construction-estimator-form');
  if (!form) return;

  const floorSlider = form.querySelector('#floor-count');
  const floorReadout = form.querySelector('[data-floor-readout]');
  const areaInput = form.querySelector('#area-per-floor');
  const carpetCheckbox = form.querySelector('#carpet-area');
  const stateSelect = form.querySelector('#construction-location');
  const citySelect = form.querySelector('#construction-city');
  const rateInput = form.querySelector('#rate-per-sqft');
  const qualityRates = { simple: 1500, standard: 1800, premium: 2300, luxury: 3000 };
  const cityDataUrl = form.dataset.cityDataUrl;
  let cityDirectory = null;

  floorSlider?.addEventListener('input', () => {
    floorReadout.textContent = floorSlider.value === '1' ? '1' : floorSlider.value;
  });

  carpetCheckbox?.addEventListener('change', () => {
    if (carpetCheckbox.checked) {
      areaInput.dataset.originalValue = areaInput.value;
      areaInput.value = Math.round(Number(areaInput.value || 0) * 1.25);
    } else if (areaInput.dataset.originalValue) {
      areaInput.value = areaInput.dataset.originalValue;
    }
  });

  const renderCities = () => {
    const values = cityDirectory?.[stateSelect.value] || [];
    citySelect.innerHTML = '';
    if (!values.length) {
      citySelect.disabled = true;
      citySelect.add(new Option(stateSelect.value === 'Default' ? 'Select a state first' : 'No cities listed', ''));
      return;
    }
    citySelect.disabled = false;
    citySelect.add(new Option('Select City', ''));
    values.forEach((city) => citySelect.add(new Option(city, city)));
    if (citySelect.dataset.selectedCity && values.includes(citySelect.dataset.selectedCity)) {
      citySelect.value = citySelect.dataset.selectedCity;
    }
  };

  stateSelect?.addEventListener('change', () => {
    citySelect.dataset.selectedCity = '';
    if (cityDirectory) renderCities();
  });

  fetch(cityDataUrl)
    .then((response) => {
      if (!response.ok) throw new Error(`City list request failed (${response.status}).`);
      return response.json();
    })
    .then((cities) => {
      cityDirectory = cities;
      renderCities();
    })
    .catch((error) => {
      console.error('Unable to load the Indian state and city list.', error);
      citySelect.disabled = true;
      citySelect.innerHTML = '';
      citySelect.add(new Option('City list could not be loaded', ''));
    });

  form.querySelectorAll('input[name="quality"]').forEach((radio) => {
    radio.addEventListener('change', () => {
      if (!rateInput.dataset.custom) rateInput.value = String(qualityRates[radio.value] || 1500);
    });
  });
  rateInput?.addEventListener('input', () => {
    rateInput.dataset.custom = 'true';
  });
})();
