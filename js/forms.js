// js/forms.js
const API_BASE = "https://homes.mdilworth.com";
// Cloudflare Turnstile test site key. Replace with your real site key in production.
const TURNSTILE_SITE_KEY = "0x4AAAAAADjFN8arfytMmafT";
const TURNSTILE_SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

let _turnstileScriptPromise = null;

function getSubmitButton(form) {
  return form.querySelector('button[type="submit"]');
}

function setSubmitEnabled(form, enabled) {
  const btn = getSubmitButton(form);
  if (!btn) return;
  btn.disabled = !enabled;
}

function ensureSecurityStateEl(form) {
  let el = form.querySelector('.security-state');
  if (el) return el;
  el = document.createElement('div');
  el.className = 'security-state small text-muted mt-2';
  const slot = form.querySelector('.turnstile-slot');
  if (slot) {
    slot.insertAdjacentElement('afterend', el);
  } else {
    form.appendChild(el);
  }
  return el;
}

function setSecurityState(form, message, isError = false) {
  const el = ensureSecurityStateEl(form);
  el.textContent = message;
  el.classList.toggle('text-danger', isError);
  el.classList.toggle('text-muted', !isError);
}

function ensureHumanConfirm(form) {
  let wrapper = form.querySelector('.human-confirm-wrap');
  if (wrapper) return wrapper.querySelector('.human-confirm');

  wrapper = document.createElement('div');
  wrapper.className = 'human-confirm-wrap form-check my-2';

  const input = document.createElement('input');
  input.type = 'checkbox';
  input.className = 'form-check-input human-confirm';
  input.id = `${form.id || 'form'}-human-confirm`;

  const label = document.createElement('label');
  label.className = 'form-check-label';
  label.setAttribute('for', input.id);
  label.textContent = 'I completed the security check';

  wrapper.appendChild(input);
  wrapper.appendChild(label);

  const slot = form.querySelector('.turnstile-slot');
  if (slot) {
    slot.insertAdjacentElement('afterend', wrapper);
  } else {
    form.appendChild(wrapper);
  }

  return input;
}

function isHumanConfirmed(form) {
  const input = form.querySelector('.human-confirm');
  return Boolean(input?.checked);
}

function ensureTurnstileScript() {
  if (window.turnstile) return Promise.resolve();
  if (_turnstileScriptPromise) return _turnstileScriptPromise;

  _turnstileScriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-turnstile="1"]');
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("turnstile-load-failed")));
      return;
    }
    const script = document.createElement("script");
    script.src = TURNSTILE_SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.dataset.turnstile = "1";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("turnstile-load-failed"));
    document.head.appendChild(script);
  });

  return _turnstileScriptPromise;
}

function ensureTurnstileWidget(form) {
  if (!window.turnstile) throw new Error("turnstile-not-ready");

  if (form.dataset.turnstileWidgetId) {
    return form.dataset.turnstileWidgetId;
  }

  let container = form.querySelector(".turnstile-slot");
  if (!container) {
    container = document.createElement("div");
    container.className = "turnstile-slot my-3";
    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn?.parentElement) {
      submitBtn.parentElement.parentElement.insertBefore(container, submitBtn.parentElement);
    } else {
      form.appendChild(container);
    }
  }

  const confirmInput = ensureHumanConfirm(form);
  if (!confirmInput.dataset.bound) {
    confirmInput.addEventListener('change', () => {
      const hasToken = Boolean(form.dataset.turnstileToken);
      setSubmitEnabled(form, hasToken && isHumanConfirmed(form));
      if (hasToken && isHumanConfirmed(form)) {
        setSecurityState(form, "Security check passed.");
      }
    });
    confirmInput.dataset.bound = '1';
  }

  const widgetId = window.turnstile.render(container, {
    sitekey: TURNSTILE_SITE_KEY,
    theme: "light",
    appearance: "always",
    callback: (token) => {
      form.dataset.turnstileToken = token || "";
      setSubmitEnabled(form, Boolean(token) && isHumanConfirmed(form));
      if (token) {
        setSecurityState(form, isHumanConfirmed(form) ? "Security check passed." : "Check the confirmation box to enable submit.");
      } else {
        setSecurityState(form, "Complete the security check and confirm to enable submit.", true);
      }
    },
    "expired-callback": () => {
      form.dataset.turnstileToken = "";
      setSubmitEnabled(form, false);
      setSecurityState(form, "Security check expired. Please verify again.", true);
    },
    "error-callback": () => {
      form.dataset.turnstileToken = "";
      setSubmitEnabled(form, false);
      setSecurityState(form, "Security check failed to load. Refresh and try again.", true);
    }
  });
  form.dataset.turnstileWidgetId = String(widgetId);
  form.dataset.turnstileToken = "";
  const confirm = form.querySelector('.human-confirm');
  if (confirm) confirm.checked = false;
  setSubmitEnabled(form, false);
  setSecurityState(form, "Complete the security check and confirm to enable submit.");
  return String(widgetId);
}

function showAlert(el, message, type) {
  el.classList.remove("d-none", "alert-success", "alert-danger");
  el.classList.add("alert-" + type);
  el.textContent = message;
}

async function submitForm(url, payload, alertEl, btn) {
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Sending...";
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("Server error");
    showAlert(alertEl, "Thanks for reaching out! I will follow up shortly.", "success");
    return true;
  } catch {
    showAlert(alertEl, "Something went wrong. Please call (919) 721-1111 instead.", "danger");
    return false;
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const leadForm = document.getElementById("lead-form");
  const contactForm = document.getElementById("contact-form");
  const videoForm = document.getElementById("video-form");

  const formsWithTurnstile = [leadForm, contactForm, videoForm].filter(Boolean);
  if (formsWithTurnstile.length > 0) {
    ensureTurnstileScript()
      .then(() => {
        formsWithTurnstile.forEach((form) => {
          try {
            ensureTurnstileWidget(form);
          } catch (err) {
            console.warn("Turnstile widget render failed", err);
          }
        });
      })
      .catch(() => {
        console.warn("Turnstile script failed to load");
      });
  }

  if (leadForm) {
    leadForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const alertEl = document.getElementById("form-alert");
      const btn = leadForm.querySelector('button[type="submit"]');
      const payload = {
        interest: document.getElementById("interest")?.value,
        location: document.getElementById("location")?.value.trim(),
        propertyType: document.getElementById("propertyType")?.value,
        priceRange: document.getElementById("priceRange")?.value.trim(),
        name: document.getElementById("name")?.value.trim(),
        email: document.getElementById("email")?.value.trim(),
        phone: document.getElementById("phone")?.value.trim(),
        message: document.getElementById("message")?.value.trim()
      };
      if (!payload.interest || !payload.location || !payload.name || !payload.email) {
        showAlert(alertEl, "Please fill in the required fields.", "danger");
        return;
      }

      try {
        await ensureTurnstileScript();
        const widgetId = ensureTurnstileWidget(leadForm);
        const token = leadForm.dataset.turnstileToken || window.turnstile.getResponse(widgetId);
        if (!isHumanConfirmed(leadForm)) {
          showAlert(alertEl, "Please check the confirmation box before submitting.", "danger");
          return;
        }
        if (!token) {
          showAlert(alertEl, "Please complete the Turnstile check.", "danger");
          return;
        }
        payload.turnstileToken = token;
      } catch {
        showAlert(alertEl, "Security check unavailable. Please try again.", "danger");
        return;
      }

      if (await submitForm(`${API_BASE}/api/lead`, payload, alertEl, btn)) {
        leadForm.reset();
        if (window.turnstile && leadForm.dataset.turnstileWidgetId) {
          window.turnstile.reset(leadForm.dataset.turnstileWidgetId);
        }
        leadForm.dataset.turnstileToken = "";
        const confirm = leadForm.querySelector('.human-confirm');
        if (confirm) confirm.checked = false;
        setSubmitEnabled(leadForm, false);
        setSecurityState(leadForm, "Complete the security check and confirm to enable submit.");
      }
    });
  }

  if (contactForm) {
    contactForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const alertEl = document.getElementById("contact-alert");
      const btn = contactForm.querySelector('button[type="submit"]');
      const payload = {
        name: document.getElementById("contactName")?.value.trim(),
        email: document.getElementById("contactEmail")?.value.trim(),
        phone: document.getElementById("contactPhone")?.value.trim(),
        message: document.getElementById("contactMessage")?.value.trim()
      };
      if (!payload.name || !payload.email || !payload.message) {
        showAlert(alertEl, "Please complete all required fields.", "danger");
        return;
      }

      try {
        await ensureTurnstileScript();
        const widgetId = ensureTurnstileWidget(contactForm);
        const token = contactForm.dataset.turnstileToken || window.turnstile.getResponse(widgetId);
        if (!isHumanConfirmed(contactForm)) {
          showAlert(alertEl, "Please check the confirmation box before submitting.", "danger");
          return;
        }
        if (!token) {
          showAlert(alertEl, "Please complete the Turnstile check.", "danger");
          return;
        }
        payload.turnstileToken = token;
      } catch {
        showAlert(alertEl, "Security check unavailable. Please try again.", "danger");
        return;
      }

      if (await submitForm(`${API_BASE}/api/contact`, payload, alertEl, btn)) {
        contactForm.reset();
        if (window.turnstile && contactForm.dataset.turnstileWidgetId) {
          window.turnstile.reset(contactForm.dataset.turnstileWidgetId);
        }
        contactForm.dataset.turnstileToken = "";
        const confirm = contactForm.querySelector('.human-confirm');
        if (confirm) confirm.checked = false;
        setSubmitEnabled(contactForm, false);
        setSecurityState(contactForm, "Complete the security check and confirm to enable submit.");
      }
    });
  }

  if (videoForm) {
    videoForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const alertEl = document.getElementById("video-form-alert");
      const btn = videoForm.querySelector('button[type="submit"]');
      const payload = {
        name: document.getElementById("vidName")?.value.trim(),
        email: document.getElementById("vidEmail")?.value.trim(),
        phone: document.getElementById("vidPhone")?.value.trim(),
        source: "video-page"
      };
      if (!payload.name || !payload.email) {
        showAlert(alertEl, "Please enter your name and email.", "danger");
        return;
      }

      try {
        await ensureTurnstileScript();
        const widgetId = ensureTurnstileWidget(videoForm);
        const token = videoForm.dataset.turnstileToken || window.turnstile.getResponse(widgetId);
        if (!isHumanConfirmed(videoForm)) {
          showAlert(alertEl, "Please check the confirmation box before submitting.", "danger");
          return;
        }
        if (!token) {
          showAlert(alertEl, "Please complete the Turnstile check.", "danger");
          return;
        }
        payload.turnstileToken = token;
      } catch {
        showAlert(alertEl, "Security check unavailable. Please try again.", "danger");
        return;
      }

      if (await submitForm(`${API_BASE}/api/contact`, payload, alertEl, btn)) {
        videoForm.reset();
        if (window.turnstile && videoForm.dataset.turnstileWidgetId) {
          window.turnstile.reset(videoForm.dataset.turnstileWidgetId);
        }
        videoForm.dataset.turnstileToken = "";
        const confirm = videoForm.querySelector('.human-confirm');
        if (confirm) confirm.checked = false;
        setSubmitEnabled(videoForm, false);
        setSecurityState(videoForm, "Complete the security check and confirm to enable submit.");
      }
    });
  }
});
