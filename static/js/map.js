async function loadCountries() {
  const status = document.querySelector("#status");
  const panel = document.querySelector("#countries");
  try {
    const response = await fetch("/api/countries");
    if (!response.ok) throw new Error("تعذر تحميل توزيع الدول");
    const countries = await response.json();
    if (!countries.length) {
      status.textContent = "لا تتوفر بيانات دول حالياً.";
      return;
    }
    const centers = {
      US: [39.8, -98.6], GB: [55.4, -3.4], FR: [46.2, 2.2], AE: [24.2, 53.8],
      EG: [26.8, 30.8], SA: [23.9, 45.1], DE: [51.2, 10.4], IN: [21.1, 78.0],
      CN: [35.9, 104.2], JP: [36.2, 138.3], RU: [61.5, 105.3], BR: [-10.8, -52.9],
      CA: [56.1, -106.3], AU: [-25.3, 133.8], IT: [41.9, 12.6], ES: [40.5, -3.7],
      TR: [38.9, 35.2], IL: [31.0, 34.9], QA: [25.3, 51.2], KW: [29.3, 47.5],
      BH: [26.0, 50.6], OM: [21.5, 55.9], JO: [30.6, 36.2], LB: [33.9, 35.9],
      PK: [30.4, 69.3], KR: [36.5, 127.9], SG: [1.3, 103.8], ID: [-0.8, 113.9],
      ZA: [-29.0, 24.0], NG: [9.1, 8.7], KE: [0.2, 37.9], MX: [23.6, -102.5],
      NL: [52.1, 5.3], BE: [50.5, 4.5], CH: [46.8, 8.2], SE: [60.1, 18.6],
      NO: [60.5, 8.5], UA: [48.4, 31.2], IR: [32.4, 53.7], IQ: [33.2, 43.7],
      MA: [31.8, -7.1], TN: [33.9, 9.5], DZ: [28.0, 1.7], NZ: [-40.9, 174.9],
    };
    const map = window.L && L.map("world-map").setView([24, 15], 2);
    if (map) {
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 10,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(map);
      const max = Math.max(...countries.map((item) => item.count));
      countries.forEach((item) => {
        const coordinates = centers[String(item.label).toUpperCase()];
        if (!coordinates) return;
        const popup = document.createElement("span");
        popup.textContent = `${item.label}: ${item.count}`;
        L.circleMarker(coordinates, {
          radius: 5 + 12 * Math.sqrt(item.count / max),
          color: "#075985",
          fillColor: "#0e9aa7",
          fillOpacity: 0.7,
        }).bindPopup(popup).addTo(map);
      });
    }
    const renderList = () => {
      const filter = document.querySelector("#country-filter").value.trim().toLocaleLowerCase();
      const descending = document.querySelector("#country-sort").dataset.descending !== "false";
      const filtered = countries.filter((item) => String(item.label).toLocaleLowerCase().includes(filter));
      filtered.sort((left, right) => descending
        ? right.count - left.count : left.count - right.count);
      const max = Math.max(1, ...countries.map((item) => item.count));
      const list = document.createElement("ul");
      list.className = "data-list";
      filtered.forEach((item) => {
        const row = document.createElement("li");
        const label = document.createElement("div");
        label.textContent = `${item.label} (${item.count})`;
        const bar = document.createElement("div");
        bar.className = "bar";
        const fill = document.createElement("span");
        fill.style.width = `${Math.max(2, item.count / max * 100)}%`;
        bar.append(fill);
        row.append(label, bar);
        list.append(row);
      });
      panel.replaceChildren(list);
    };
    document.querySelector("#country-filter").addEventListener("input", renderList);
    document.querySelector("#country-sort").addEventListener("click", (event) => {
      const button = event.currentTarget;
      button.dataset.descending = button.dataset.descending === "false" ? "true" : "false";
      button.textContent = button.dataset.descending === "true"
        ? "ترتيب: الأكثر أخباراً" : "ترتيب: الأقل أخباراً";
      renderList();
    });
    renderList();
    status.textContent = "";
  } catch (error) {
    status.textContent = error.message;
  }
}
loadCountries();
