/* PIN code → city/area/state/district auto-lookup via India Post API
   Usage: add data-pinlookup to any pincode input
   Optional: data-fill-city="<input-id>"          — auto-fill city text input
             data-fill-state="<input-id>"          — auto-fill state text input
             data-fill-state-select="<select-id>"  — auto-select state <select> by option text
             data-fill-district-select="<select-id>" — auto-select district <select> by option text
*/
(function () {
  var cache = {};

  function lookup(pin, cb) {
    if (cache[pin]) { cb(cache[pin]); return; }
    fetch('/api/pincode/' + pin + '/')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var result = null;
        if (data && data.success) {
          result = { area: data.area, district: data.district, state: data.state };
        }
        cache[pin] = result;
        cb(result);
      })
      .catch(function () { cb(null); });
  }

  function getOrCreateHint(input) {
    var hint = input.parentElement.querySelector('.pin-hint');
    if (!hint) {
      hint = document.createElement('small');
      hint.className = 'pin-hint';
      hint.style.cssText = 'display:block;margin-top:4px;font-size:12px;font-weight:600;min-height:16px';
      input.parentElement.appendChild(hint);
    }
    return hint;
  }

  /* Try to select an option whose text matches `name` (case-insensitive, trimmed).
     Returns true if a match was found. */
  function selectByText(selectEl, name) {
    if (!selectEl || !name) return false;
    var norm = name.trim().toLowerCase();
    var matched = null;
    Array.from(selectEl.options).forEach(function (opt) {
      if (opt.value && opt.text.trim().toLowerCase() === norm) matched = opt;
    });
    if (matched) {
      selectEl.value = matched.value;
      // fire change so dependent listeners (e.g. filterDistricts) run
      selectEl.dispatchEvent(new Event('change'));
      return true;
    }
    return false;
  }

  function initOne(input) {
    if (input._pinInit) return;
    input._pinInit = true;

    var hint           = getOrCreateHint(input);
    var cityId         = input.dataset.fillCity;
    var stateId        = input.dataset.fillState;
    var stateSelectId  = input.dataset.fillStateSelect;
    var distSelectId   = input.dataset.fillDistrictSelect;
    var lastPin        = '';

    function run() {
      var pin = input.value.replace(/\D/g, '');
      if (pin.length !== 6) { lastPin = ''; hint.textContent = ''; return; }
      if (pin === lastPin) return;
      lastPin = pin;
      hint.style.color = '#aaa';
      hint.textContent = '🔍 Looking up…';

      lookup(pin, function (res) {
        if (input.value.replace(/\D/g, '') !== pin) return;
        if (!res) {
          lastPin = '';
          hint.style.color = '#e65100';
          hint.textContent = '⚠️ PIN code not found';
          return;
        }
        hint.style.color = '#2e7d32';
        var parts = res.area !== res.district ? [res.area, res.district, res.state] : [res.district, res.state];
        hint.textContent = '📍 ' + parts.join(', ');

        // Fill city text input
        if (cityId) {
          var cityEl = document.getElementById(cityId);
          if (cityEl) cityEl.value = res.area !== res.district ? res.area + ', ' + res.district : res.district;
        }
        // Fill state text input
        if (stateId) {
          var stateEl = document.getElementById(stateId);
          if (stateEl) stateEl.value = res.state;
        }
        // Auto-select state <select> by text match
        if (stateSelectId) {
          var stateSel = document.getElementById(stateSelectId);
          selectByText(stateSel, res.state);
        }
        // Auto-select district <select> by text match (slight delay lets state filter run first)
        if (distSelectId) {
          setTimeout(function () {
            var distSel = document.getElementById(distSelectId);
            selectByText(distSel, res.district);
          }, 100);
        }
      });
    }

    input.addEventListener('input', run);
    input.addEventListener('blur',  run);
    // run on load if already filled (e.g. edit forms)
    if (input.value.length === 6) run();
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('input[data-pinlookup]').forEach(initOne);
  });

  window.initPinLookup = initOne;
})();
