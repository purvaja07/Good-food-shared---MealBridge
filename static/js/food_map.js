(() => {
  const root = document.getElementById("mealbridge-food-map");
  const mapElement = document.getElementById("food-rescue-map");
  if (!root || !mapElement || !window.L) return;

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const listElement = document.getElementById("map-food-list");
  const errorElement = document.getElementById("map-error");
  const countElement = document.getElementById("map-result-count");
  const locationStatus = document.getElementById("map-location-status");
  const searchElement = document.getElementById("map-search");
  const categoryElement = document.getElementById("map-category");
  const quantityElement = document.getElementById("map-quantity");
  const capacityElement = document.getElementById("map-capacity");
  const addressSearchButton = document.getElementById("search-address");
  const isNgo = root.dataset.userRole === "ngo";
  const defaultArea = { lat: 21.04655, lon: 76.05938 };
  const savedLocation = {
    lat: Number(root.dataset.userLat),
    lon: Number(root.dataset.userLon),
  };
  const isIndiaLocation =
    savedLocation.lat >= 6 &&
    savedLocation.lat <= 38 &&
    savedLocation.lon >= 68 &&
    savedLocation.lon <= 98;
  const hasSavedLocation =
    root.dataset.userLat !== "" &&
    root.dataset.userLon !== "" &&
    isIndiaLocation &&
    Number.isFinite(savedLocation.lat) &&
    Number.isFinite(savedLocation.lon);
  const map = window.L.map(mapElement, { scrollWheelZoom: false }).setView(
    [hasSavedLocation ? savedLocation.lat : defaultArea.lat, hasSavedLocation ? savedLocation.lon : defaultArea.lon],
    hasSavedLocation ? 13 : 12,
  );
  const foodLayer = window.L.layerGroup().addTo(map);
  const ngoLayer = window.L.layerGroup().addTo(map);
  let userMarker;
  let routeLayer;
  let donations = [];
  let nearby = [];
  let organizations = [];
  let currentLocation = hasSavedLocation ? savedLocation : null;
  let searchCenter = currentLocation || defaultArea;
  let radius = 20;
  let activeDonation = null;
  let searchTimer;
  let searchLocationLabel = "";

  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);

  function makeIcon(kind) {
    const symbol = kind === "ngo" ? "bi-people-fill" : kind === "user" ? "bi-crosshair" : "bi-basket2-fill";
    return window.L.divIcon({
      className: "",
      html: `<span class="food-marker food-marker-${kind}"><i class="bi ${symbol}"></i></span>`,
      iconSize: [36, 44],
      iconAnchor: [18, 40],
      popupAnchor: [0, -37],
    });
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function formatExpiry(expiry) {
    const remaining = new Date(expiry).getTime() - Date.now();
    if (!Number.isFinite(remaining) || remaining <= 0) return "Expired";
    const minutes = Math.floor(remaining / 60000);
    const hours = Math.floor(minutes / 60);
    return hours ? `${hours}h ${minutes % 60}m left` : `${Math.max(1, minutes)}m left`;
  }

  function foodPopup(item, match) {
    const card = element("div", "map-popup");
    const heading = element("div", "map-popup-heading");
    heading.append(
      element("strong", "", item.donor_name),
      element("span", "map-popup-category", item.category),
    );
    card.append(heading, element("h3", "map-popup-title", item.food_name));
    const facts = element("div", "map-popup-facts");
    facts.append(
      element("span", "", `${item.quantity} portions available`),
      element("span", "", `About ${item.meals} meals`),
      element("span", "", `Prepared ${new Date(item.preparation_time).toLocaleString()}`),
    );
    const countdown = element("span", "map-popup-expiry");
    countdown.dataset.countdown = item.expiry_time;
    countdown.textContent = formatExpiry(item.expiry_time);
    if (new Date(item.expiry_time).getTime() - Date.now() < 60 * 60 * 1000) {
      countdown.classList.add("urgent");
    }
    facts.append(countdown);
    card.append(facts, element("p", "map-popup-address", item.pickup_address));

    if (match) {
      card.append(
        element(
          "p",
          "map-popup-distance",
          `${match.distance_km.toFixed(1)} km away · about ${match.estimated_travel_minutes} min by road estimate`,
        ),
      );
    }

    const actions = element("div", "map-popup-actions");
    const route = element("button", "btn btn-sm btn-outline-success", "Show route");
    route.type = "button";
    route.addEventListener("click", () => showRoute(item));
    if (isNgo) {
      const request = element("button", "btn btn-sm btn-success", "Request food");
      request.type = "button";
      request.disabled = root.dataset.userVerified !== "true";
      request.title = request.disabled ? "Your NGO account must be verified first." : "";
      request.addEventListener("click", () => openRequest(item));
      actions.append(request, route);
    } else {
      actions.append(route);
    }
    card.append(actions);
    return card;
  }

  function openRequest(item) {
    if (root.dataset.userVerified !== "true") {
      showError("Your NGO must be verified before requesting food.");
      return;
    }
    activeDonation = item;
    document.getElementById("request-donation-id").value = item.id;
    document.getElementById("request-food-summary").textContent =
      `${item.food_name} from ${item.donor_name} · ${item.quantity} portions available`;
    const quantity = document.getElementById("request-quantity");
    quantity.min = "1";
    quantity.max = String(item.quantity);
    quantity.value = String(
      Math.min(
        item.recommended_quantity || item.quantity,
        Number(capacityElement.value) || item.quantity,
      ),
    );
    const pickupTime = document.getElementById("request-pickup-time");
    pickupTime.min = localDateTimeValue(new Date(Date.now() + 5 * 60000));
    pickupTime.max = localDateTimeValue(new Date(item.expiry_time));
    pickupTime.value = pickupTime.min;
    document.getElementById("request-notes").value = "";
    document.getElementById("request-form-error").hidden = true;
    window.bootstrap.Modal.getOrCreateInstance(
      document.getElementById("mapRequestModal"),
    ).show();
  }

  function localDateTimeValue(date) {
    const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return localDate.toISOString().slice(0, 16);
  }

  function showError(message) {
    errorElement.textContent = message;
    errorElement.hidden = false;
  }

  function clearError() {
    errorElement.textContent = "";
    errorElement.hidden = true;
  }

  function matchesSearch(item) {
    const query = searchElement.value.trim().toLowerCase();
    const category = categoryElement.value;
    if (category && item.category_id && String(item.category_id) !== category) return false;
    if (!query) return true;
    return [
      item.food_name,
      item.category,
      item.pickup_address,
      item.donor_name,
      item.description,
    ].some((value) => String(value || "").toLowerCase().includes(query));
  }

  function renderList() {
    const source = searchCenter ? nearby : donations;
    const results = source.filter(matchesSearch);
    listElement.replaceChildren();
    countElement.textContent = `${results.length} ${results.length === 1 ? "match" : "matches"}`;

    if (!results.length) {
      listElement.append(
        element(
          "div",
          "empty-state map-empty-state",
          searchCenter
            ? "No safe, nearby matches for these filters. Try a wider distance or check back later."
            : "No located food donations yet. Allow location access or add coordinates to your NGO profile.",
        ),
      );
      return;
    }

    const matchById = new Map(nearby.map((item) => [item.id, item]));
    results.forEach((item) => {
      const match = matchById.get(item.id);
      const card = element("article", "map-food-card");
      if (item.image_url) {
        const image = element("img", "map-food-image");
        image.src = item.image_url;
        image.alt = item.food_name;
        image.loading = "lazy";
        card.append(image);
      }

      const content = element("div", "map-food-card-content");
      const top = element("div", "d-flex justify-content-between align-items-start gap-2");
      top.append(
        element("span", "category-pill", item.category),
        element("span", "map-availability-badge", "Available"),
        element("span", "map-expiry-badge", formatExpiry(item.expiry_time)),
      );
      const heading = element("h2", "h6 mt-2 mb-1", item.food_name);
      const organization = element("p", "small text-secondary mb-2", item.donor_name);
      const address = element("p", "map-food-address", item.pickup_address);
      const facts = element(
        "p",
        "map-food-facts",
        `${item.quantity} portions · ${item.meals} meals${match ? ` · collect up to ${match.recommended_quantity} · ${match.distance_km.toFixed(1)} km away` : ""}`,
      );
      const actions = element("div", "d-flex gap-2 mt-3");
      const focus = element("button", "btn btn-sm btn-outline-success flex-fill", "View on map");
      focus.type = "button";
      focus.addEventListener("click", () => {
        map.setView([item.latitude, item.longitude], 15);
        const marker = foodLayer.getLayers().find((layer) => layer.options.donationId === item.id);
        if (marker) marker.openPopup();
        if (currentLocation) showRoute(item);
      });
      actions.append(focus);
      if (isNgo) {
        const request = element("button", "btn btn-sm btn-success flex-fill", "Request food");
        request.type = "button";
        request.disabled = root.dataset.userVerified !== "true";
        request.title = request.disabled ? "Your NGO account must be verified first." : "";
        request.addEventListener("click", () => openRequest(item));
        actions.append(request);
      }
      content.append(top, heading, organization, address, facts, actions);
      card.append(content);
      listElement.append(card);
    });
  }

  function renderMarkers() {
    foodLayer.clearLayers();
    ngoLayer.clearLayers();
    const matchById = new Map(nearby.map((item) => [item.id, item]));

    donations.forEach((item) => {
      const marker = window.L.marker([item.latitude, item.longitude], {
        icon: makeIcon("food"),
        donationId: item.id,
      });
      marker.bindPopup(foodPopup(item, matchById.get(item.id)), { maxWidth: 330 });
      marker.addTo(foodLayer);
    });

    organizations.forEach((ngo) => {
      const marker = window.L.marker([ngo.latitude, ngo.longitude], {
        icon: makeIcon(ngo.is_current_user ? "user" : "ngo"),
      });
      marker.bindPopup(
        element(
          "div",
          "",
          `${ngo.name}${ngo.address ? ` · ${ngo.address}` : ""}${ngo.is_current_user ? " (your organization)" : ""}`,
        ),
      );
      marker.addTo(ngoLayer);
    });

    if (currentLocation) {
      if (userMarker) map.removeLayer(userMarker);
      userMarker = window.L.marker([currentLocation.lat, currentLocation.lon], {
        icon: makeIcon("user"),
        zIndexOffset: 1000,
      })
        .bindPopup(searchLocationLabel || "Your current location")
        .addTo(map);
    }
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.method && options.method !== "GET" ? { "X-CSRF-Token": csrfToken } : {}),
        ...options.headers,
      },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The request could not be completed.");
    return data;
  }

  function buildNearbyUrl() {
    if (!searchCenter) return null;
    const params = new URLSearchParams({
      lat: String(searchCenter.lat),
      lon: String(searchCenter.lon),
      radius_km: String(radius),
      needed_quantity: String(Math.max(1, Number(quantityElement.value) || 1)),
      capacity: String(Math.max(1, Number(capacityElement.value) || 50)),
    });
    if (categoryElement.value) params.set("category", categoryElement.value);
    return `/api/donations/nearby?${params}`;
  }

  async function refreshResults() {
    clearError();
    listElement.replaceChildren(
      element("div", "map-loading", "Updating nearby food…"),
    );
    try {
      const params = new URLSearchParams();
      if (categoryElement.value) params.set("category", categoryElement.value);
      const [donationData, ngoData] = await Promise.all([
        fetchJson(`/api/donations?${params}`),
        fetchJson("/api/ngos"),
      ]);
      donations = donationData.donations;
      organizations = ngoData.ngos;
      nearby = [];

      const nearbyUrl = buildNearbyUrl();
      if (nearbyUrl) {
        const nearbyData = await fetchJson(nearbyUrl);
        nearby = nearbyData.donations;
        document.getElementById("map-matching-note").textContent =
          `${nearbyData.matching_note} ${
            currentLocation
              ? "Distances use your saved or shared location."
              : "Showing Muktainagar, Jalgaon; search an address or allow location access for distance matching."
          }`;
        document.getElementById("map-matching-note").hidden = false;
      } else {
        document.getElementById("map-matching-note").hidden = true;
      }
      renderList();
      renderMarkers();
    } catch (error) {
      showError(error.message);
      listElement.replaceChildren(
        element("div", "empty-state map-empty-state", "Could not load food matches. Please try again."),
      );
    }
  }

  async function showRoute(item) {
    if (!currentLocation) {
      showError("Share your location to get pickup directions.");
      return;
    }
    clearError();
    const summary = document.getElementById("route-summary");
    summary.hidden = false;
    document.getElementById("route-distance").textContent = "Finding a road route…";
    document.getElementById("route-time").textContent = "";
    document.getElementById("external-directions").removeAttribute("href");
    const externalUrl = new URL("https://www.google.com/maps/dir/");
    externalUrl.searchParams.set(
      "api",
      "1",
    );
    externalUrl.searchParams.set(
      "origin",
      `${currentLocation.lat},${currentLocation.lon}`,
    );
    externalUrl.searchParams.set(
      "destination",
      `${item.latitude},${item.longitude}`,
    );
    document.getElementById("external-directions").href = externalUrl.toString();

    try {
      const url =
        "https://router.project-osrm.org/route/v1/driving/" +
        `${currentLocation.lon},${currentLocation.lat};${item.longitude},${item.latitude}` +
        "?overview=full&geometries=geojson&steps=false";
      const response = await fetch(url);
      if (!response.ok) throw new Error("The routing service is temporarily unavailable.");
      const data = await response.json();
      if (data.code !== "Ok" || !data.routes?.length) {
        throw new Error("No road route was found. Use the external directions link.");
      }
      const route = data.routes[0];
      if (routeLayer) map.removeLayer(routeLayer);
      routeLayer = window.L.geoJSON(route.geometry, {
        style: { color: "#198754", weight: 5, opacity: 0.82 },
      }).addTo(map);
      map.fitBounds(routeLayer.getBounds(), { padding: [36, 36] });
      document.getElementById("route-distance").textContent =
        `${(route.distance / 1000).toFixed(1)} km route`;
      document.getElementById("route-time").textContent =
        `${Math.max(1, Math.round(route.duration / 60))} min estimated drive`;
    } catch (error) {
      document.getElementById("route-distance").textContent =
        "Road route unavailable";
      document.getElementById("route-time").textContent = error.message;
    }
  }

  async function searchAddress() {
    const query = searchElement.value.trim();
    if (!query) {
      showError("Enter an Indian address, town, or district to find it on the map.");
      searchElement.focus();
      return;
    }

    clearError();
    addressSearchButton.disabled = true;
    addressSearchButton.innerHTML =
      '<span class="spinner-border spinner-border-sm" role="status" aria-label="Searching"></span>';
    locationStatus.textContent = `Searching India for “${query}”…`;
    try {
      const result = await fetchJson(`/api/geocode?q=${encodeURIComponent(query)}`);
      currentLocation = {
        lat: result.latitude,
        lon: result.longitude,
      };
      searchCenter = currentLocation;
      searchLocationLabel = result.display_name;
      locationStatus.textContent = result.display_name;
      map.setView([currentLocation.lat, currentLocation.lon], 14);
      renderMarkers();
      await refreshResults();
    } catch (error) {
      locationStatus.textContent = "Address search did not find a location";
      showError(error.message);
    } finally {
      addressSearchButton.disabled = false;
      addressSearchButton.innerHTML = '<i class="bi bi-geo-alt"></i>';
    }
  }

  function useLocation(position) {
    currentLocation = {
      lat: position.coords.latitude,
      lon: position.coords.longitude,
    };
    searchLocationLabel = "";
    searchCenter = currentLocation;
    locationStatus.textContent = "Using your current location";
    map.setView([currentLocation.lat, currentLocation.lon], 13);
    refreshResults();
  }

  function locateUser() {
    if (!navigator.geolocation) {
      locationStatus.textContent = currentLocation
        ? "Using your saved organization location"
        : "Showing Muktainagar, Jalgaon, Maharashtra";
      return;
    }
    locationStatus.textContent = "Requesting location permission…";
    navigator.geolocation.getCurrentPosition(
      useLocation,
      () => {
        if (hasSavedLocation) {
          useLocation({
            coords: {
              latitude: savedLocation.lat,
              longitude: savedLocation.lon,
            },
          });
          locationStatus.textContent = "Using your saved organization location";
        } else {
          currentLocation = null;
          searchLocationLabel = "";
          searchCenter = defaultArea;
          locationStatus.textContent =
            "Showing Muktainagar, Jalgaon, Maharashtra · allow location for exact distance";
          refreshResults();
        }
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  }

  document.querySelectorAll("[data-radius]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-radius]").forEach((option) => {
        option.classList.remove("active");
        option.setAttribute("aria-pressed", "false");
      });
      button.classList.add("active");
      button.setAttribute("aria-pressed", "true");
      radius = Number(button.dataset.radius);
      refreshResults();
    });
  });
  searchElement.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(refreshResults, 250);
  });
  searchElement.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      searchAddress();
    }
  });
  addressSearchButton.addEventListener("click", searchAddress);
  [categoryElement, quantityElement, capacityElement].forEach((field) => {
    field.addEventListener("change", refreshResults);
  });
  document.getElementById("refresh-map").addEventListener("click", refreshResults);
  document.getElementById("locate-me").addEventListener("click", locateUser);
  document.getElementById("clear-route").addEventListener("click", () => {
    if (routeLayer) map.removeLayer(routeLayer);
    routeLayer = null;
    document.getElementById("route-summary").hidden = true;
  });

  document.getElementById("map-request-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!activeDonation) return;
    const errorElement = document.getElementById("request-form-error");
    const submitButton = document.getElementById("submit-map-request");
    errorElement.hidden = true;
    submitButton.disabled = true;
    try {
      const result = await fetchJson("/api/pickup/request", {
        method: "POST",
        body: JSON.stringify({
          donation_id: Number(document.getElementById("request-donation-id").value),
          quantity: Number(document.getElementById("request-quantity").value),
          pickup_date: new Date(
            document.getElementById("request-pickup-time").value,
          ).toISOString(),
          notes: document.getElementById("request-notes").value.trim(),
        }),
      });
      window.bootstrap.Modal.getOrCreateInstance(
        document.getElementById("mapRequestModal"),
      ).hide();
      errorElement.textContent =
        `${result.message} Track the status in your NGO dashboard.`;
      errorElement.className = "alert alert-success mx-3 my-2 py-2 small";
      errorElement.hidden = false;
      window.setTimeout(() => {
        errorElement.hidden = true;
      }, 7000);
      await refreshResults();
    } catch (error) {
      errorElement.classList.remove("alert-success");
      errorElement.classList.add("alert-danger");
      errorElement.textContent = error.message;
      errorElement.hidden = false;
    } finally {
      submitButton.disabled = false;
    }
  });

  refreshResults();
  renderMarkers();
  locationStatus.textContent = currentLocation
    ? "Using your saved organization location"
    : "Showing Muktainagar, Jalgaon, Maharashtra · select My location for exact distance";
  window.setInterval(() => {
    document.querySelectorAll("[data-countdown]").forEach((item) => {
      item.textContent = formatExpiry(item.dataset.countdown);
      item.classList.toggle(
        "urgent",
        new Date(item.dataset.countdown).getTime() - Date.now() < 60 * 60 * 1000,
      );
    });
  }, 30000);
})();
