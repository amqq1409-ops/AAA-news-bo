async function renderList(endpoint, elementId, format) {
  const response = await fetch(endpoint);
  if (!response.ok) throw new Error("تعذر تحميل التحليلات");
  const data = await response.json();
  const items = format(data);
  const list = document.createElement("ul");
  list.className = "data-list";
  items.forEach((text) => {
    const row = document.createElement("li");
    row.textContent = text;
    list.append(row);
  });
  document.querySelector(`#${elementId}`).append(list);
}

async function loadAnalytics() {
  const status = document.querySelector("#status");
  try {
    await Promise.all([
      renderList("/api/trends", "trends", (data) =>
        [...data.data.map((item) => `${item.date}: ${item.count} خبر`),
          `تقدير اليوم التالي: ${data.forecast_next_day} خبر`]),
      renderList("/api/sources", "sources", (items) =>
        items.slice(0, 20).map((item) => `${item.label}: ${item.count} خبر · تقييم ${item.average_score ?? "غير متاح"}`)),
      renderList("/api/sentiment", "topics-sentiment", (data) =>
        Object.entries(data.by_topic).map(([topic, counts]) =>
          `${topic}: إيجابي ${counts.positive || 0} · سلبي ${counts.negative || 0} · محايد ${counts.neutral || 0}`)),
    ]);
    status.textContent = "";
  } catch (error) {
    status.textContent = error.message;
  }
}
loadAnalytics();
