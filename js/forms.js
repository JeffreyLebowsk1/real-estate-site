// js/forms.js
const API_BASE = "https://homes.mdilworth.com";

function showAlert(el, message, type) {
  el.classList.remove("d-none", "alert-success", "alert-danger");
  el.classList.add("alert-" + type);
  el.textContent = message;
}

async function submitForm(url, payload, alertEl, btn, originalText) {
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
      if (await submitForm(`${API_BASE}/api/lead`, payload, alertEl, btn, "Submit request")) {
        leadForm.reset();
      }
    });
  }

  const contactForm = document.getElementById("contact-form");
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
      if (await submitForm(`${API_BASE}/api/contact`, payload, alertEl, btn, "Send message")) {
        contactForm.reset();
      }
    });
  }

  const videoForm = document.getElementById("video-form");
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
      if (await submitForm(`${API_BASE}/api/contact`, payload, alertEl, btn, "Submit")) {
        videoForm.reset();
      }
    });
  }
});
