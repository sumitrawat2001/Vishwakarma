(() => {
  const root = document.getElementById('admin-estimator-app');
  if (!root) return;
  const showMessage = (text, error = false) => {
    const node = document.getElementById('admin-price-message');
    node.hidden = false;
    node.className = `estimator-alert ${error ? 'error' : 'success'}`;
    node.textContent = text;
  };
  const send = async (url, payload) => {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Unable to save changes.');
    return data;
  };

  const catalogForm = document.getElementById('admin-material-catalog-form');
  catalogForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(catalogForm).entries());
    try {
      await send('/api/admin/material-catalog', data);
      showMessage('Material added to the catalogue. You can now enter sourced location rates for it.');
      window.setTimeout(() => window.location.reload(), 600);
    } catch (error) {
      showMessage(error.message, true);
    }
  });

  const priceForm = document.getElementById('admin-price-form');
  priceForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(priceForm);
    const rates = {};
    priceForm.querySelectorAll('[data-official-rate]').forEach((input) => {
      if (input.value !== '') rates[input.dataset.officialRate] = Number(input.value);
    });
    try {
      await send('/api/admin/material-prices', {
        level: form.get('level'),
        country: form.get('country'),
        state: form.get('state'),
        district: form.get('district'),
        locality: form.get('locality'),
        source: form.get('source'),
        rates,
      });
      showMessage('Sourced location rates saved and added to update history.');
      window.setTimeout(() => window.location.reload(), 600);
    } catch (error) {
      showMessage(error.message, true);
    }
  });

  const locationForm = document.getElementById('admin-location-form');
  locationForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(locationForm).entries());
    try {
      await send('/api/admin/material-locations', data);
      showMessage('Location added to the estimator directory.');
      window.setTimeout(() => window.location.reload(), 600);
    } catch (error) {
      showMessage(error.message, true);
    }
  });

  const settingsForm = document.getElementById('admin-estimator-settings-form');
  settingsForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const values = new FormData(settingsForm);
    const payload = {
      wastage_percent: Number(values.get('wastage_percent')),
      dry_volume_factor: Number(values.get('dry_volume_factor')),
      water_cement_ratio: Number(values.get('water_cement_ratio')),
      mix_ratios: {},
    };
    ['M10', 'M15', 'M20'].forEach((grade) => {
      payload.mix_ratios[grade] = {};
      ['cement', 'sand', 'aggregate'].forEach((material) => {
        payload.mix_ratios[grade][material] = Number(values.get(`ratio_${grade}_${material}`));
      });
    });
    try {
      await send('/api/admin/material-estimation-settings', payload);
      showMessage('Estimator defaults and nominal ratios saved.');
    } catch (error) {
      showMessage(error.message, true);
    }
  });

  const rateLevel = priceForm.elements.namedItem('level');
  const rateState = priceForm.elements.namedItem('state');
  const district = priceForm.elements.namedItem('district');
  const locality = priceForm.elements.namedItem('locality');
  const requiredByLevel = () => {
    rateState.required = rateLevel.value !== 'country';
    district.required = ['district', 'locality'].includes(rateLevel.value);
    locality.required = rateLevel.value === 'locality';
  };
  rateLevel.addEventListener('change', requiredByLevel);
  requiredByLevel();

  const locationLevel = locationForm.elements.namedItem('level');
  const locationDistrict = locationForm.elements.namedItem('district');
  const locationRequired = () => {
    locationDistrict.required = locationLevel.value === 'locality';
    locationForm.elements.namedItem('state').required = ['district', 'locality'].includes(locationLevel.value);
  };
  locationLevel.addEventListener('change', locationRequired);
  locationRequired();
})();
