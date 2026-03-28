// js/components.js
// Shared site chrome - include on every page

const SITE_NAME = "Matt Dilworth, REALTOR\u00ae";
const PHONE     = "(919) 721-1111";
const PHONE_TEL = "tel:+19197211111";
const EMAIL     = "matt@mdilworth.com";
const ADDRESS   = "304 N Horner Blvd, Sanford, NC 27330";
const SOCIAL = {
  facebook:  "https://facebook.com/MattDilworthRealtor",
  x:         "https://twitter.com/RealtorMattD",
  instagram: "https://instagram.com/MattDilworthRealtor",
  linkedin:  "https://linkedin.com/in/mattdilworthrealtor"
};

const NAV_ITEMS = [
  { label: "Home",          href: "/" },
  { label: "List with Us",  href: "/list-with-us.html" },
  { label: "Find a Home",   href: "/find-a-home.html" },
  { label: "Services",      href: "/services.html" },
  { label: "Testimonials",  href: "/testimonials.html" },
  { label: "Blog",          href: "/blog.html" },
  { label: "About Me",      href: "/about.html" },
  { label: "Contact",       href: "/contact.html" },
  { label: "Videos",        href: "/videos.html" }
];

function currentPage() {
  const p = window.location.pathname;
  if (p === "/" || p === "/index.html") return "/";
  return p;
}

function renderTopBar(el) {
  el.innerHTML = `
    <div class="top-bar">
      <div class="container d-flex justify-content-between align-items-center flex-wrap">
        <div>CALL ME TODAY: <a href="${PHONE_TEL}" class="fw-semibold">${PHONE}</a></div>
        <div class="d-flex gap-3">
          <a href="${SOCIAL.facebook}" target="_blank" rel="noopener">Facebook</a>
          <a href="${SOCIAL.x}" target="_blank" rel="noopener">X</a>
          <a href="${SOCIAL.instagram}" target="_blank" rel="noopener">Instagram</a>
          <a href="${SOCIAL.linkedin}" target="_blank" rel="noopener">LinkedIn</a>
        </div>
      </div>
    </div>`;
}

function renderNav(el) {
  const cur = currentPage();
  const items = NAV_ITEMS.map(n =>
    `<li class="nav-item"><a class="nav-link ${n.href === cur ? 'active fw-semibold' : ''}" href="${n.href}">${n.label}</a></li>`
  ).join("");

  el.innerHTML = `
    <nav class="navbar navbar-expand-lg navbar-light bg-white border-bottom sticky-top">
      <div class="container">
        <a class="navbar-brand" href="/">${SITE_NAME}</a>
        <a href="/contact.html" class="btn btn-primary d-none d-lg-inline-block ms-auto me-3">GET IN TOUCH</a>
        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#mainNav"
                aria-controls="mainNav" aria-expanded="false" aria-label="Toggle navigation">
          <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="mainNav">
          <ul class="navbar-nav ms-auto mb-2 mb-lg-0">${items}</ul>
        </div>
      </div>
    </nav>`;
}

function renderCtaBand(el) {
  el.innerHTML = `
    <section class="cta-band text-center">
      <div class="container">
        <h2 class="h3 mb-2">Ready to buy or sell a property?</h2>
        <p class="mb-3">Call me today at <a href="${PHONE_TEL}" class="fw-bold">${PHONE}</a></p>
        <a href="/contact.html" class="btn btn-light btn-lg">Get in touch</a>
      </div>
    </section>`;
}

function renderFooter(el) {
  el.innerHTML = `
    <footer class="site-footer">
      <div class="container">
        <div class="row g-4 mb-3">
          <div class="col-md-4">
            <h5 class="text-white mb-2">Location</h5>
            <p class="small mb-0">${ADDRESS}</p>
          </div>
          <div class="col-md-4">
            <h5 class="text-white mb-2">Contact</h5>
            <p class="small mb-1"><a href="${PHONE_TEL}">${PHONE}</a></p>
            <p class="small mb-0"><a href="mailto:${EMAIL}">${EMAIL}</a></p>
          </div>
          <div class="col-md-4">
            <h5 class="text-white mb-2">Connect</h5>
            <div class="d-flex gap-3 mb-2">
              <a href="${SOCIAL.facebook}" target="_blank" rel="noopener">Facebook</a>
              <a href="${SOCIAL.x}" target="_blank" rel="noopener">X</a>
              <a href="${SOCIAL.instagram}" target="_blank" rel="noopener">Instagram</a>
              <a href="${SOCIAL.linkedin}" target="_blank" rel="noopener">LinkedIn</a>
            </div>
          </div>
        </div>
        <hr class="border-secondary">
        <div class="row">
          <div class="col-md-8">
            <p class="small mb-0">
              I am committed to maintaining an accessible website. If you have difficulty accessing
              content or have questions about accessibility, please
              <a href="/contact.html">contact me</a>.
            </p>
          </div>
          <div class="col-md-4 text-md-end">
            <p class="small mb-0">&copy; <span id="footer-year"></span> Matt Dilworth. All rights reserved.</p>
          </div>
        </div>
      </div>
    </footer>`;
  document.getElementById("footer-year").textContent = new Date().getFullYear();
}

// Auto-init on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => {
  const tb = document.getElementById("top-bar");
  const nv = document.getElementById("site-nav");
  const ct = document.getElementById("cta-band");
  const ft = document.getElementById("site-footer");
  if (tb) renderTopBar(tb);
  if (nv) renderNav(nv);
  if (ct) renderCtaBand(ct);
  if (ft) renderFooter(ft);
});
