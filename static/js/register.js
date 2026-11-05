// ── Employer type metadata ───────────────────────────────────────────────────
const EMPLOYER_TYPES = [
    'company', 'shop', 'recruiter', 'factory', 'startup',
    'institution', 'ngo', 'hospital', 'hotel',
    'farm', 'individual_employer'
];

const TYPE_META = {
    company:             { label: 'Business',            icon: 'fa-building',      badge: 'blue',   org: 'Business Name',      desc: 'Start Promoting & Hiring' },
    shop:                { label: 'Shop',                 icon: 'fa-store',         badge: 'purple', org: 'Shop Name',          desc: 'Hire the right staff for your shop' },
    recruiter:           { label: 'Recruiter',            icon: 'fa-user-tie',      badge: 'teal',   org: 'Agency Name',        desc: 'Post jobs on behalf of your client companies' },
    factory:             { label: 'Factory',              icon: 'fa-industry',      badge: 'orange', org: 'Factory Name',       desc: 'Hire skilled workers for your factory' },
    startup:             { label: 'Startup',              icon: 'fa-rocket',        badge: 'red',    org: 'Startup Name',       desc: 'Build your startup team from scratch' },
    institution:         { label: 'Institution',          icon: 'fa-university',    badge: 'blue',   org: 'Institution Name',   desc: 'Hire staff for your school, college or institute' },
    ngo:                 { label: 'NGO',                  icon: 'fa-hands-helping', badge: 'green',  org: 'NGO / Trust Name',   desc: 'Hire workers for your social organization' },
    hospital:            { label: 'Hospital',             icon: 'fa-hospital',      badge: 'teal',   org: 'Hospital Name',      desc: 'Hire doctors, nurses & support staff' },
    hotel:               { label: 'Hotel / Restaurant',   icon: 'fa-hotel',         badge: 'gold',   org: 'Hotel / Rest. Name', desc: 'Hire hospitality and kitchen staff' },
    farm:                { label: 'Farm',                  icon: 'fa-leaf',          badge: 'green',  org: 'Farm Name',          desc: 'Hire agricultural and farm workers' },
    individual_employer: { label: 'Individual Employer',  icon: 'fa-user-plus',     badge: 'orange', org: 'Your Full Name',     desc: 'Hire personal, domestic or household staff' },
};

let currentType = '';

// ── Auto-select type from URL ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    const params = new URLSearchParams(window.location.search);
    const type = params.get('type');
    if (type) selectType(type);

    const name    = params.get('name');
    const phone   = params.get('phone');
    const pincode = params.get('pincode');
    if (name || phone || pincode) {
        document.querySelectorAll('.reg-step form').forEach(function (form) {
            if (name)    { var n = form.querySelector('[name="first_name"]'); if (n) n.value = name; }
            if (phone)   { var p = form.querySelector('[name="phone"]');      if (p) p.value = phone; }
            if (pincode) { var c = form.querySelector('[name="pincode"]');    if (c) c.value = pincode; }
        });
    }
});

// ── Type selection ─────────────────────────────────────────────────────────────
function selectType(type) {
    currentType = type;
    document.querySelectorAll('.reg-step').forEach(s => s.classList.add('hidden'));

    if (type === 'individual_employer') {
        // Individual employer has its own lightweight OTP-based form
        document.getElementById('step-individual_employer').classList.remove('hidden');
    } else if (EMPLOYER_TYPES.includes(type)) {
        loadEmployerForm(type);
        document.getElementById('step-employer').classList.remove('hidden');
    } else {
        const step = document.getElementById('step-' + type);
        if (step) step.classList.remove('hidden');
    }
}

// Badge colour → banner background mapping
const BADGE_COLORS = {
    blue:   {bg:'linear-gradient(135deg,#e8f0fe,#dbeafe)', border:'#c5d9f5', icon:'#0a66c2', text:'#0a47a1'},
    purple: {bg:'linear-gradient(135deg,#f3e5f5,#e8d5f5)', border:'#d4b8e8', icon:'#6a1b9a', text:'#4a0e6e'},
    orange: {bg:'linear-gradient(135deg,#fff3e0,#ffe5b4)', border:'#ffcc80', icon:'#e65100', text:'#bf360c'},
    red:    {bg:'linear-gradient(135deg,#fce4ec,#f8c1ce)', border:'#f48fb1', icon:'#c62828', text:'#b71c1c'},
    green:  {bg:'linear-gradient(135deg,#e8f5e9,#c8e6c9)', border:'#a5d6a7', icon:'#2e7d32', text:'#1b5e20'},
    teal:   {bg:'linear-gradient(135deg,#e0f7fa,#b2ebf2)', border:'#80deea', icon:'#00838f', text:'#006064'},
    gold:   {bg:'linear-gradient(135deg,#fff8e1,#ffecb3)', border:'#ffe082', icon:'#f9a825', text:'#e65100'},
};

function loadEmployerForm(type) {
    const m = TYPE_META[type];
    if (!m) return;
    const c = BADGE_COLORS[m.badge] || BADGE_COLORS.blue;

    // Skip phone step — go directly to company details
    var sub1 = document.getElementById('emp-substep1');
    var sub2 = document.getElementById('emp-substep2');
    if (sub1 && sub2) {
        sub1.classList.add('hidden');
        sub2.classList.remove('hidden');
    }

    document.getElementById('emp-user-type-input').value = type;
    const typeLabel = document.getElementById('emp-type-label');
    const typeIcon = document.getElementById('emp-type-icon');
    const typeDescription = document.getElementById('emp-type-desc');
    if (typeLabel) typeLabel.textContent = m.label;
    if (typeIcon) typeIcon.className = 'fas ' + m.icon;
    if (typeDescription) typeDescription.textContent = m.desc;
    document.getElementById('emp-org-label').innerHTML    =
        '<i class="fas ' + m.icon + '"></i> ' + m.org + ' *';
    document.getElementById('emp-org-input').placeholder  = 'Enter ' + m.org.toLowerCase();
    document.getElementById('emp-submit-label').textContent =
        'Create ' + m.label + ' Account';

    // Highlight active pill
    document.querySelectorAll('#empTypePills .ets-pill').forEach(function(p){
        p.classList.toggle('active', p.dataset.type === type);
    });

    // Update banner colours
    var banner = document.getElementById('empTypeBanner');
    var icon   = document.getElementById('etbIcon');
    var label  = document.getElementById('emp-type-badge');
    if (banner) { banner.style.background = c.bg; banner.style.borderColor = c.border; }
    if (icon)   { icon.style.background   = c.icon; }
    if (label)  { label.style.color       = c.text; }
}

function switchEmployerType(type) {
    currentType = type;
    loadEmployerForm(type);
}

function openBusinessRegistration() {
    document.getElementById('regBizBtnWrap').style.display = 'none';
    document.getElementById('regBizForm').style.display = 'block';
    document.getElementById('regBizForm').scrollIntoView({behavior:'smooth', block:'start'});
}
function goBack() {
    const employer = document.getElementById('step-employer');
    const form = document.getElementById('regBizForm');
    if (!employer.classList.contains('hidden') && form.style.display === 'block') {
        form.style.display = 'none';
        document.getElementById('regBizBtnWrap').style.display = 'block';
        employer.scrollIntoView({behavior:'smooth', block:'start'});
        return;
    }
    document.querySelectorAll('.reg-step').forEach(s => s.classList.add('hidden'));
    document.getElementById('step1').classList.remove('hidden');
    currentType = '';
    document.getElementById('step1').scrollIntoView({behavior:'smooth', block:'start'});
}
function registrationBack(event) {
    const selectedStep = document.querySelector('.reg-step:not(.hidden)');
    if (selectedStep && selectedStep.id !== 'step1') {
        event.preventDefault(); goBack(); return false;
    }
    if (history.length > 1 && document.referrer.startsWith(location.origin + '/')) {
        event.preventDefault(); history.back(); return false;
    }
    return true;
}

// ── Inject hidden field helper (used by OTP-based seeker forms) ───────────────
function injectField(form, name, value) {
    let el = form.querySelector('[name="' + name + '"]');
    if (!el) {
        el = document.createElement('input');
        el.type = 'hidden';
        el.name = name;
        form.appendChild(el);
    }
    el.value = value;
}

// ── OTP helpers ───────────────────────────────────────────────────────────────
function regGetCsrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
}

function sendOTP(prefix) {
    var phoneInput = document.getElementById(prefix + 'Phone');
    if (!phoneInput) return;
    var phone = phoneInput.value.trim();

    if (!/^\d{10}$/.test(phone)) {
        alert('Please enter a valid 10-digit mobile number.');
        return;
    }

    var btn = phoneInput.closest('.otp-input-row').querySelector('.otp-btn');
    var errDiv = document.getElementById(prefix + 'PhoneError');
    if (errDiv) errDiv.style.display = 'none';

    btn.textContent = 'Checking…';
    btn.disabled = true;

    // Check if phone already registered
    fetch('/api/check-phone/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': regGetCsrf() },
        body: JSON.stringify({ phone: phone })
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        // Always proceed to next step regardless of whether phone exists
        btn.textContent = 'Continue ✓';
        btn.classList.add('sent');
        btn.disabled = true;
        var sub1 = document.getElementById(prefix + '-substep1');
        var sub2 = document.getElementById(prefix + '-substep2');
        if (sub1 && sub2) {
            sub1.classList.add('hidden');
            sub2.classList.remove('hidden');
        } else {
            var otpBox = document.getElementById(prefix + 'OtpBox');
            if (otpBox) otpBox.classList.add('hidden');
            var badge = document.getElementById(prefix + 'Verified');
            if (badge) badge.classList.remove('hidden');
        }
    })
    .catch(function() {
        btn.textContent = 'Continue';
        btn.disabled = false;
        alert('Network error. Please check your connection and try again.');
    });
}

function otpNext(input) {
    input.value = input.value.replace(/[^0-9]/g, '');
    if (input.value.length === 1) {
        var next = input.nextElementSibling;
        if (next && next.classList.contains('otp-digit')) next.focus();
    }
}

function verifyOTP(prefix) {
    var box    = document.getElementById(prefix + 'OtpBox');
    var digits = box.querySelectorAll('.otp-digit');
    var otp = '';
    digits.forEach(function(d) { otp += d.value; });

    if (otp.length !== 6) {
        alert('Please enter the 6-digit OTP.');
        return;
    }

    var verifyBtn = box.querySelector('.otp-verify-btn');
    if (verifyBtn) { verifyBtn.disabled = true; verifyBtn.textContent = 'Verifying…'; }

    fetch('/api/verify-otp/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': regGetCsrf() },
        body: JSON.stringify({ otp: otp })
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        if (d.success) {
            var sub1 = document.getElementById(prefix + '-substep1');
            var sub2 = document.getElementById(prefix + '-substep2');
            if (sub1 && sub2) {
                sub1.classList.add('hidden');
                sub2.classList.remove('hidden');
            } else {
                box.style.display = 'none';
                var badge = document.getElementById(prefix + 'Verified');
                if (badge) badge.classList.remove('hidden');
            }
        } else {
            if (verifyBtn) { verifyBtn.disabled = false; verifyBtn.textContent = 'Verify OTP'; }
            alert(d.error || 'Wrong OTP. Please try again.');
        }
    })
    .catch(function() {
        if (verifyBtn) { verifyBtn.disabled = false; verifyBtn.textContent = 'Verify OTP'; }
        alert('Network error. Please try again.');
    });
}

// ── Password match check ──────────────────────────────────────────────────────
function checkPasswords(form) {
    const pwd  = form.querySelector('[name="password"]');
    const pwd2 = form.querySelector('[name="password2"], [name="confirm_password"]');
    const err  = form.querySelector('.pwd-error, #emp-pwd-error');
    if (!pwd) return true;
    if (pwd.value.length < 8) {
        pwd.setCustomValidity('Password must contain at least 8 characters.');
        pwd.reportValidity();
        pwd.addEventListener('input', () => pwd.setCustomValidity(''), {once:true});
        return false;
    }
    if (!pwd2) return true;
    if (pwd.value !== pwd2.value) {
        if (err) err.style.display = 'block';
        pwd2.focus();
        return false;
    }
    if (err) err.style.display = 'none';
    return true;
}

// ── AJAX submit for all register forms ───────────────────────────────────────
function regAjaxSubmit(form) {
    if (!checkPasswords(form)) return;

    const btn = form.querySelector('button[type="submit"]');
    let errEl = form.querySelector('.reg-ajax-err');
    if (!errEl) {
        errEl = document.createElement('p');
        errEl.className = 'reg-ajax-err';
        errEl.style.cssText = 'color:#dc2626;background:#fef2f2;border:1px solid #fca5a5;' +
            'border-radius:8px;padding:.6rem .9rem;font-size:.85rem;margin:.75rem 0 0;display:none';
        form.prepend(errEl);
    }
    errEl.style.display = 'none';

    if (btn) {
        btn.disabled    = true;
        btn.dataset.orig = btn.innerHTML;
        btn.innerHTML   = '<i class="fas fa-circle-notch fa-spin"></i> Creating account…';
    }

    var csrfInput   = form.querySelector('[name=csrfmiddlewaretoken]');
    var csrfCookie  = document.cookie.split('; ').filter(function(c){ return c.indexOf('csrftoken=') === 0; })[0];
    var csrf        = (csrfInput ? csrfInput.value : '') || (csrfCookie ? csrfCookie.split('=')[1] : '');

    fetch('/register/process/', {
        method:  'POST',
        headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
        body:    new FormData(form),
    })
        .then(function (r) { return r.json(); })
        .then(function (res) {
            if (res.success) {
                window.location.href = res.redirect;
            } else {
                errEl.textContent = res.error || 'Registration failed. Please try again.';
                errEl.style.display = 'block';
                if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.orig; }
            }
        })
        .catch(function () {
            errEl.textContent = 'Network error. Please check your connection and try again.';
            errEl.style.display = 'block';
            if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.orig || 'Submit'; }
        });
}

// ── Live phone duplicate check (fires as user types, on 10th digit) ──────────
function attachLivePhoneCheck(phoneInputId, errorDivId, otpBtnClass) {
    var inp = document.getElementById(phoneInputId);
    var errDiv = document.getElementById(errorDivId);
    if (!inp) return;

    inp.addEventListener('input', function () {
        var phone = this.value.trim();
        var btn = inp.closest('.otp-input-row') && inp.closest('.otp-input-row').querySelector('.otp-btn');

        // Clear error & re-enable button until we know
        errDiv.style.display = 'none';
        if (btn) btn.disabled = false;

        if (!/^\d{10}$/.test(phone)) return; // wait for full 10 digits

        fetch('/api/check-phone/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': regGetCsrf() },
            body: JSON.stringify({ phone: phone })
        })
        .then(function (r) { return r.json(); })
        .then(function (d) {
            errDiv.style.display = 'none';
            if (btn) btn.disabled = false;
        })
        .catch(function () { /* silent — sendOTP will catch it */ });
    });
}

// ── Password live-check (employer form) ───────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    // Attach live phone check to employer form
    attachLivePhoneCheck('empPhone', 'empPhoneError');

    var p1 = document.getElementById('emp-pwd');
    var p2 = document.getElementById('emp-pwd2');
    var er = document.getElementById('emp-pwd-error');
    if (p1 && p2 && er) {
        p2.addEventListener('input', function () {
            er.style.display = (p1.value && p2.value && p1.value !== p2.value) ? 'block' : 'none';
        });
    }
});

// ── Intercept ALL register forms — document-level delegation ──────────────────
// Fires after onsubmit attribute (field injection), so FormData picks up injected fields.
document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || !form.action || form.action.indexOf('/register/process/') === -1) return;
    e.preventDefault();
    regAjaxSubmit(form);
});
