const form = document.querySelector("#search-form");
const status = document.querySelector("#status");
const results = document.querySelector("#results");

function safeArticleURL(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  status.textContent = "جارٍ البحث…";
  results.replaceChildren();
  try {
    const params = new URLSearchParams(new FormData(form));
    const response = await fetch(`/api/search?${params}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "تعذر تنفيذ البحث");
    status.textContent = `عدد النتائج: ${data.total}`;
    data.results.forEach((article) => {
      const item = document.createElement("article");
      item.className = "panel article";
      const heading = document.createElement("h2");
      const url = safeArticleURL(article.url);
      if (url) {
        const link = document.createElement("a");
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = article.title || "بدون عنوان";
        heading.append(link);
      } else {
        heading.textContent = article.title || "بدون عنوان";
      }
      const details = document.createElement("p");
      details.className = "muted";
      details.textContent = [article.source_name, article.country_ar, article.lang, article.topic,
        article.sentiment.label].filter(Boolean).join(" · ");
      item.append(heading, details);
      results.append(item);
    });
  } catch (error) {
    status.textContent = error.message;
  }
});
