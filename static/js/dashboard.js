async function getJSON(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error("تعذر تحميل البيانات");
  return response.json();
}

function listRows(items, labelKey = "label") {
  const list = document.createElement("ul");
  list.className = "data-list";
  items.forEach((item) => {
    const row = document.createElement("li");
    row.textContent = `${item[labelKey] || "غير محدد"} (${item.count})`;
    list.append(row);
  });
  return list;
}

async function loadDashboard() {
  const status = document.querySelector("#status");
  try {
    const [stats, sentiment] = await Promise.all([
      getJSON("/api/stats"),
      getJSON("/api/sentiment"),
    ]);
    const cards = [
      ["إجمالي الأخبار", stats.total_articles],
      ["الأخبار خلال 24 ساعة", stats.recent_articles],
      ["المصادر النشطة", stats.active_sources],
      ["الدول المغطاة", stats.countries_covered],
      ["اللغات المغطاة", stats.languages_covered],
    ];
    const container = document.querySelector("#stats");
    cards.forEach(([label, value]) => {
      const card = document.createElement("article");
      card.className = "card";
      const strong = document.createElement("strong");
      strong.textContent = value;
      const caption = document.createElement("span");
      caption.textContent = label;
      card.append(strong, caption);
      container.append(card);
    });
    const sentiments = Object.entries(sentiment.distribution).map(([label, values]) => ({
      label: { positive: "إيجابي", negative: "سلبي", neutral: "محايد" }[label],
      count: `${values.percentage}%`,
    }));
    document.querySelector("#sentiment").append(listRows(sentiments));
    document.querySelector("#topics").append(listRows(stats.by_topic || []));
    status.textContent = stats.total_articles ? "" : "لا توجد أخبار في قاعدة البيانات بعد.";
  } catch (error) {
    status.textContent = error.message;
  }
}

loadDashboard();
