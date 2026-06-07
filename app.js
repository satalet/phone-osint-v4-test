// ══════════════════════════════════════════
//   Phone OSINT v4 — Landing Page JS
// ══════════════════════════════════════════

// ── Copy code buttons ──
function copyCode(btn) {
  const code = btn.nextElementSibling.innerText;
  navigator.clipboard.writeText(code).then(() => {
    btn.textContent = '✔ تم';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = 'نسخ';
      btn.classList.remove('copied');
    }, 2000);
  });
}

// ── Terminal typewriter animation ──
document.addEventListener('DOMContentLoaded', () => {
  const lines = document.querySelectorAll('.t-line');
  lines.forEach((line, i) => {
    line.style.opacity = '0';
    line.style.transform = 'translateX(8px)';
    line.style.transition = 'opacity .3s, transform .3s';
    setTimeout(() => {
      line.style.opacity = '1';
      line.style.transform = 'translateX(0)';
    }, 300 + i * 60);
  });

  // ── Intersection observer for feature cards ──
  const cards = document.querySelectorAll('.feature-card, .step');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  cards.forEach((card, i) => {
    card.style.opacity = '0';
    card.style.transform = 'translateY(24px)';
    card.style.transition = `opacity .5s ${i * 0.08}s ease, transform .5s ${i * 0.08}s ease`;
    observer.observe(card);
  });
});
