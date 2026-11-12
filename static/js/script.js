(() => {
  const countdowns = document.querySelectorAll("[data-countdown]");

  function updateCountdowns() {
    const now = Date.now();
    countdowns.forEach((element) => {
      const expiry = new Date(element.dataset.countdown).getTime();
      const remaining = expiry - now;
      if (!Number.isFinite(expiry) || remaining <= 0) {
        element.textContent = "Expired";
        element.classList.add("text-danger");
        return;
      }

      const totalMinutes = Math.floor(remaining / 60000);
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;
      const label =
        hours > 0
          ? `${hours}h ${minutes}m left`
          : `${Math.max(1, minutes)}m left`;
      element.textContent = label;
      element.classList.toggle("urgent", remaining <= 60 * 60 * 1000);
    });
  }

  updateCountdowns();
  window.setInterval(updateCountdowns, 30000);

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  const mapElement = document.getElementById("food-map");
  const markers = window.mealBridgeMapMarkers || [];
  if (mapElement && window.L) {
    const map = window.L.map(mapElement, { scrollWheelZoom: false });
    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);

    if (markers.length) {
      const bounds = [];
      markers.forEach((item) => {
        const point = [item.lat, item.lon];
        bounds.push(point);
        const link = document.createElement("a");
        link.href = item.url;
        link.textContent = item.name;
        link.className = "map-popup-link";
        const address = document.createElement("div");
        address.textContent = item.address;
        address.className = "small text-secondary mt-1";
        const content = document.createElement("div");
        content.append(link, address);
        window.L.marker(point).addTo(map).bindPopup(content);
      });
      map.fitBounds(bounds, { padding: [28, 28], maxZoom: 14 });
    } else {
      map.setView([21.04655, 76.05938], 12);
      mapElement.classList.add("map-muted");
    }
  }
})();
