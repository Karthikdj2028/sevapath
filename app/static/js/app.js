/**
 * SevaPath Client-Side Utilities
 * Vanilla JavaScript (No heavy frameworks)
 */

document.addEventListener("DOMContentLoaded", function () {
  // 1. Live Public Service Search Filter
  const searchInput = document.getElementById("serviceSearchInput");
  const serviceCards = document.querySelectorAll(".service-card-col");
  const noResultsAlert = document.getElementById("noServicesAlert");

  if (searchInput && serviceCards.length > 0) {
    searchInput.addEventListener("input", function (e) {
      const query = e.target.value.toLowerCase().trim();
      let visibleCount = 0;

      serviceCards.forEach(function (cardCol) {
        const title = cardCol.getAttribute("data-title") || "";
        const desc = cardCol.getAttribute("data-desc") || "";
        const dept = cardCol.getAttribute("data-dept") || "";
        const combined = (title + " " + desc + " " + dept).toLowerCase();

        if (combined.includes(query)) {
          cardCol.style.display = "";
          visibleCount++;
        } else {
          cardCol.style.display = "none";
        }
      });

      if (noResultsAlert) {
        noResultsAlert.style.display = visibleCount === 0 ? "block" : "none";
      }
    });
  }

  // 2. Smooth Scroll to Services if requested
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get("scroll") === "services") {
    const servicesSection = document.getElementById("services-section");
    if (servicesSection) {
      servicesSection.scrollIntoView({ behavior: "smooth" });
    }
  }
});
