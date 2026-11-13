"""اختبارات آلية للبوت ببيانات مصطنعة (لا تحتاج إنترنت).  التشغيل:  python -m unittest discover tests"""
import datetime as dt
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "X_BEARER_TOKEN"):
    os.environ.pop(_k, None)

import yaml

import ai
import geo
import news_bot as nb
from archive import Archive, build_digest

CFG = yaml.safe_load((Path(nb.ROOT) / "config.yaml").read_text("utf-8"))
NOW = dt.datetime(2026, 11, 14, 0, 5, tzinfo=nb.RIYADH)
FAKE_AR = {
    "Saudi Arabia signs $5 billion investment deal with Japan": "السعودية توقع صفقة استثمار بقيمة 5 مليارات دولار مع اليابان",
    "Saudi Arabia signs 5 billion dollar investment deal with Japan": "السعودية توقع صفقة استثمار بقيمة 5 مليارات دولار مع اليابان",
    "サウジアラビア、日本と50億ドルの投資契約を締結": "المملكة العربية السعودية توقع صفقة استثمار بقيمة 5 مليارات دولار مع اليابان",
    "サウジ、新しい観光ビザを発表": "السعودية تعلن عن تأشيرة سياحية جديدة",
}


def art(title, domain="example.com", lang="en", minutes_ago=30, origin="gdelt", country="", source=None):
    published = NOW - dt.timedelta(minutes=minutes_ago)
    a = nb.Article(title, f"https://{domain}/{nb.h(title)}", domain, source or domain, lang, "", published, origin, True)
    nb.resolve_geo(a, hint_name=country, prefer_domain=False)
    return a


class Recorder(nb.Telegram):
    def __init__(self):
        self.dry_run = True
        self.sent = []

    def send_text(self, text, preview=False):
        self.sent.append(text)
        return True


def new_state(tmp):
    return nb.State(Path(tmp) / "state.json")


def run_with(articles, state, tg, tmp, statuses=None, cfg=None, now=NOW):
    statuses = statuses or {}
    fetchers = {
        "gnews": lambda c, d: (articles, {}, statuses.get("gnews", ("ok", ""))),
        "gdelt": lambda c, d: ([], {}, statuses.get("gdelt", ("ok", ""))),
        "x": lambda c, d: ([], {}, statuses.get("x", ("skip", ""))),
    }
    original = nb.translate_to_arabic
    nb.add_arabic_titles.__defaults__ = (lambda t: FAKE_AR.get(t),)
    try:
        return nb.run(cfg or CFG, state, tg, archive=Archive(Path(tmp) / "archive"), now=now, fetchers=fetchers)
    finally:
        nb.add_arabic_titles.__defaults__ = (original,)


class TopicTests(unittest.TestCase):
    def test_saudi_is_not_technology(self):
        # كان "ai" داخل كلمة "saudi" يصنّف كل عنوان إنجليزي تقنيةً
        self.assertEqual(nb.classify_topic("Saudi Arabia hosts regional talks with Iran minister"), "politics")
        self.assertNotEqual(nb.classify_topic("Saudi Arabia weather update"), "technology")

    def test_hotel_is_not_art(self):
        self.assertEqual(nb.classify_topic("افتتاح فندق جديد في العلا لاستقبال السياح"), "tourism")

    def test_translated_title_gives_topic(self):
        a = art("サウジ、新しい観光ビザを発表", "nikkei.com", "ja")
        a.title_ar = FAKE_AR[a.title]
        self.assertEqual(nb.classify_topic(a.all_text()), "tourism")

    def test_common_topics(self):
        self.assertEqual(nb.classify_topic("أرامكو ترفع أسعار النفط الخام لآسيا"), "energy")
        self.assertEqual(nb.classify_topic("السعودية تعلن ميزانية 2027 بإنفاق قياسي على المشاريع"), "economy")
        self.assertEqual(nb.classify_topic("Saudi Arabia and Kenya sign labour agreement"), "economy")
        self.assertEqual(nb.classify_topic("Al Hilal beat Al Nassr in Saudi Pro League match"), "sports")
        self.assertEqual(nb.classify_topic("Pilgrims arrive in Makkah for Umrah"), "religion")
        self.assertEqual(nb.classify_topic("Saudi Arabia to build AI data center with chips"), "technology")


class RecencyTests(unittest.TestCase):
    def test_article_before_midnight_is_kept(self):
        a = art("Saudi news", minutes_ago=10)  # نُشر 23:55 واكتُشف 00:05
        self.assertTrue(nb.is_recent(a, 24, NOW))

    def test_old_article_dropped(self):
        self.assertFalse(nb.is_recent(art("Saudi news", minutes_ago=25 * 60), 24, NOW))


class GeoTests(unittest.TestCase):
    def test_lookup(self):
        self.assertEqual(geo.by_name("Japan")[2], "east_asia")
        self.assertEqual(geo.by_domain("asahi.co.jp")[1], "اليابان")
        self.assertEqual(geo.by_domain("bbc.co.uk")[0], "GB")
        self.assertIsNone(geo.by_domain("reuters.com"))
        self.assertEqual(geo.by_iso("ke")[2], "africa")

    def test_gnews_uses_real_source_domain(self):
        xml = b"""<rss><channel><item><title>Saudi Aramco profit rises - Reuters</title>
        <link>https://news.google.com/rss/articles/abc</link><pubDate>Fri, 13 Nov 2026 20:00:00 GMT</pubDate>
        <source url="https://www.reuters.com">Reuters</source></item></channel></rss>"""
        items = nb.parse_gnews_rss(xml, {"lang": "en", "gl": "KE", "country_ar": "كينيا"})
        self.assertEqual(items[0].domain, "reuters.com")
        self.assertEqual(items[0].source_score, 120)
        self.assertEqual(items[0].title, "Saudi Aramco profit rises")
        self.assertEqual(items[0].region, "africa")

    def test_all_gnews_editions_have_region(self):
        for ed in CFG["google_news"]["editions"]:
            self.assertIsNotNone(geo.by_iso(ed["gl"]), ed)


class DedupeTests(unittest.TestCase):
    def test_same_story_merged_across_sources_and_languages(self):
        with tempfile.TemporaryDirectory() as tmp:
            tg, state = Recorder(), new_state(tmp)
            items = [
                art("Saudi Arabia signs $5 billion investment deal with Japan", "reuters.com", country="United Kingdom", source="Reuters"),
                art("Saudi Arabia signs 5 billion dollar investment deal with Japan", "bloomberg.com", source="Bloomberg"),
                art("サウジアラビア、日本と50億ドルの投資契約を締結", "nikkei.com", "ja", country="Japan", source="Nikkei"),
                art("Saudi Arabia opens new metro line in Riyadh", "arabnews.com", country="Saudi Arabia"),
            ]
            sent = run_with(items, state, tg, tmp)
            self.assertEqual(sent, 2)
            merged = next(m for m in tg.sent if "Reuters" in m)
            self.assertIn("نشره أيضًا", merged)
            self.assertIn("Bloomberg", merged)
            self.assertIn("Nikkei", merged)
            for item in items:
                self.assertTrue(state.seen_article(item))

    def test_story_not_repeated_in_later_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            tg, state = Recorder(), new_state(tmp)
            run_with([art("Saudi Arabia signs $5 billion investment deal with Japan", "reuters.com")], state, tg, tmp)
            later = art("サウジアラビア、日本と50億ドルの投資契約を締結", "nikkei.com", "ja", country="Japan")
            self.assertEqual(run_with([later], state, tg, tmp), 0)
            self.assertTrue(state.seen_article(later))

    def test_different_stories_not_merged(self):
        a = art("Saudi Arabia signs investment deal with Japan")
        b = art("Saudi Arabia cuts oil output after OPEC meeting")
        for x in (a, b):
            x.tok_orig = nb.story_tokens(x.title, "en")
        self.assertLess(nb.similarity(a, b), 0.6)


class SelectionTests(unittest.TestCase):
    def _articles(self):
        items = [art(f"Saudi Arabia economy report number {i} about banks", "cnn.com", "en", country="United States") for i in range(12)]
        items += [art(f"Informe {i} sobre Arabia Saudita y el petroleo", "elpais.com", "es", country="Spain") for i in range(4)]
        items += [art("Saudi Arabia and Kenya sign labour agreement", "nation.africa", "en", country="Kenya")]
        items += [art("Saudi Arabia and Kazakhstan discuss wheat exports", "inform.kz", "en", country="Kazakhstan")]
        pats = nb.compile_terms(CFG["title_must_match_any"])
        for a in items:
            a.title_ar = a.title
            a.relevance_score = nb.compute_relevance(a, pats)
            a.tok_orig = nb.story_tokens(a.title, a.lang)
        return items

    def test_language_caps_and_region_quota(self):
        cfg = nb.apply_saudi_focus(dict(CFG))
        chosen = nb.select_clusters(self._articles(), cfg)
        langs = [a.lang for a in chosen]
        self.assertLessEqual(langs.count("es"), 2)
        self.assertLessEqual(len(chosen), cfg["max_messages_per_run"])
        regions = {a.region for a in chosen}
        self.assertIn("africa", regions)       # ما كان ليظهر لولا حصة المناطق
        self.assertIn("central_asia", regions)
        # حصة المناطق لا تُحسب ضد حد اللغة إلا لما بعدها: الإنجليزية 6 + خبرا الحصة
        self.assertGreaterEqual(langs.count("en"), 6)

    def test_weak_term_alone_is_dropped_but_other_scripts_pass(self):
        cfg = nb.apply_saudi_focus(dict(CFG))
        pats = nb.compile_terms(cfg["title_must_match_any"])
        weak = art("Thousands register for hajj lottery in Indonesia", "smallblog.id", "en", minutes_ago=200)
        japanese = art("サウジ、新しい観光ビザを発表", "smallblog.jp", "ja")
        for a in (weak, japanese):
            a.title_ar = FAKE_AR.get(a.title)
        kept = nb.score_and_focus([weak, japanese], cfg, pats, NOW)
        self.assertEqual([a.title for a in kept], [japanese.title])


class MessageTests(unittest.TestCase):
    def test_message_has_tags_region_and_escaping(self):
        a = art("Saudi <b>Aramco</b> & Toyota sign hydrogen deal", "asahi.co.jp", "en", country="Japan", source="Asahi")
        a.title_ar, a.translated = "أرامكو السعودية وتويوتا توقعان صفقة هيدروجين", True
        a.topic, a.summary, a.tone = "energy", "ملخص من جملتين.", "positive"
        msg = nb.format_message(a, CFG)
        self.assertIn("#طاقة #اليابان #شرق_آسيا", msg)
        self.assertIn("🇯🇵 اليابان — شرق آسيا", msg)
        self.assertIn("📝 ملخص من جملتين.", msg)
        self.assertIn("أرامكو 🟢<u>السعودية</u> وتويوتا", msg)
        self.assertIn("🟢 النبرة: إيجابي", msg)
        self.assertIn("&lt;b&gt;Aramco&lt;/b&gt; &amp;", msg)
        self.assertLess(len(msg), 4096)

    def test_saudi_word_highlight(self):
        out = nb.highlight_saudi("ولي العهد السعودي يبحث مع وزير سعودي مستقبل السعودية")
        self.assertEqual(out.count("🟢"), 1)          # الدائرة الخضراء مرة واحدة
        self.assertEqual(out.count("<u>"), 3)          # والخط تحت كل ورود
        self.assertIn("🟢<u>السعودي</u>", out)
        self.assertEqual(nb.highlight_saudi("أخبار قطر"), "أخبار قطر")

    def test_flags(self):
        self.assertEqual(geo.flag("sa"), "🇸🇦")
        self.assertEqual(geo.flag_for_name("كينيا"), "🇰🇪")
        self.assertEqual(geo.flag(""), "")
        unknown = art("Saudi Arabia news item", "example.com")
        self.assertIn("🏛 example.com", nb.format_message(unknown, CFG))

    def test_hashtag(self):
        self.assertEqual(nb.hashtag("عُمان"), "#عمان")
        self.assertEqual(nb.hashtag("جنوب أفريقيا"), "#جنوب_أفريقيا")
        self.assertEqual(nb.hashtag(""), "")


class HealthTests(unittest.TestCase):
    def test_alert_once_then_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            tg, state = Recorder(), new_state(tmp)
            t0 = 1_000_000
            fail = {"gdelt": ("fail", "HTTP 429"), "gnews": ("ok", ""), "x": ("skip", "")}
            nb.check_health(fail, CFG, state, tg, t0)
            nb.check_health(fail, CFG, state, tg, t0 + 2 * 3600)
            self.assertEqual(tg.sent, [])                      # أقل من 3 ساعات: لا تنبيه
            nb.check_health(fail, CFG, state, tg, t0 + 3.5 * 3600)
            nb.check_health(fail, CFG, state, tg, t0 + 5 * 3600)
            self.assertEqual(len(tg.sent), 1)                  # تنبيه واحد فقط
            self.assertIn("GDELT", tg.sent[0])
            self.assertIn("HTTP 429", tg.sent[0])
            nb.check_health({"gdelt": ("ok", "")}, CFG, state, tg, t0 + 6 * 3600)
            self.assertEqual(len(tg.sent), 2)
            self.assertIn("عاد", tg.sent[1])


class DigestAndArchiveTests(unittest.TestCase):
    def test_archive_roundtrip_and_digest_once_per_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            tg, state = Recorder(), new_state(tmp)
            evening = dt.datetime.now(nb.RIYADH).replace(hour=21, minute=10)
            items = [
                art("Saudi Arabia signs $5 billion investment deal with Japan", "reuters.com", country="United Kingdom"),
                art("Saudi Arabia and Kenya sign labour agreement", "nation.africa", country="Kenya"),
            ]
            for a in items:
                a.published = evening - dt.timedelta(minutes=20)
            archive = Archive(Path(tmp) / "archive")
            fetchers = {"gnews": lambda c, d: (items, {}, ("ok", ""))}
            nb.add_arabic_titles.__defaults__ = (lambda t: FAKE_AR.get(t),)
            nb.run(CFG, state, tg, archive=archive, now=evening, fetchers=fetchers)
            archive.save()
            digests = [m for m in tg.sent if "موجز اليوم" in m]
            self.assertEqual(len(digests), 1)
            self.assertIn("حسب المنطقة", digests[0])
            self.assertIn("أفريقيا 1", digests[0])
            files = list((Path(tmp) / "archive").glob("*.jsonl"))
            self.assertEqual(len(files), 1)
            self.assertEqual(len(files[0].read_text("utf-8").splitlines()), 2)
            before = len(tg.sent)
            nb.run(CFG, state, tg, archive=archive, now=evening + dt.timedelta(minutes=10), fetchers={"gnews": lambda c, d: ([], {}, ("ok", ""))})
            self.assertEqual(len([m for m in tg.sent[before:] if "موجز اليوم" in m]), 0)

    def test_weekly_digest_waits_for_a_full_week(self):
        with tempfile.TemporaryDirectory() as tmp:
            friday = dt.datetime(2026, 11, 13, 21, 30, tzinfo=nb.RIYADH)
            rec = {"ts": friday.timestamp() - 600, "title": "t", "url": "https://e.com", "origin": "gnews", "score": 50}
            tg, state, archive = Recorder(), new_state(tmp), Archive(Path(tmp) / "a")
            archive.add(dict(rec))
            nb.maybe_send_digests(CFG, state, tg, archive, friday)
            self.assertEqual(len([m for m in tg.sent if "الأسبوعي" in m]), 0)
            self.assertEqual(state.data["digest"].get("weekly"), "2026-11-13")
            tg2, state2, archive2 = Recorder(), new_state(tmp + "/b"), Archive(Path(tmp) / "c")
            archive2.add(dict(rec))
            archive2.add({**rec, "ts": friday.timestamp() - 5 * 86400})
            nb.maybe_send_digests(CFG, state2, tg2, archive2, friday)
            self.assertEqual(len([m for m in tg2.sent if "الأسبوعي" in m]), 1)

    def test_no_digest_before_hour(self):
        with tempfile.TemporaryDirectory() as tmp:
            tg, state = Recorder(), new_state(tmp)
            nb.maybe_send_digests(CFG, state, tg, Archive(Path(tmp) / "a"), NOW.replace(hour=15))
            self.assertEqual(tg.sent, [])

    def test_digest_text_limits(self):
        recs = [{"ts": time.time(), "title": "T" * 300, "title_ar": "خبر " * 60, "url": "https://e.com/" + "x" * 200,
                 "source": "S", "region": "europe", "topic": "economy", "tone": "critical", "score": i, "origin": "gnews",
                 "country": "فرنسا", "also": 2} for i in range(40)]
        text = build_digest(recs, "موجز", 10, nb.TOPIC_LABELS, geo.REGIONS_AR, ai.TONES)
        self.assertLess(len(text), 4096)
        self.assertIn("أكثر المناطق نقدًا", text)


class AITests(unittest.TestCase):
    def test_disabled_without_key(self):
        e = ai.AIEnricher(CFG, {}, "2026-11-14", list(nb.TOPIC_LABELS))
        self.assertFalse(e.available())
        self.assertIsNone(e.enrich("t", "s", "https://e.com", "e.com"))

    def test_daily_cap_and_parsing(self):
        os.environ["GEMINI_API_KEY"] = "test"
        try:
            data = {"ai": {"day": "2026-11-14", "calls": 300}}
            self.assertFalse(ai.AIEnricher(CFG, data, "2026-11-14", list(nb.TOPIC_LABELS)).available())
            self.assertTrue(ai.AIEnricher(CFG, data, "2026-11-15", list(nb.TOPIC_LABELS)).available())  # يوم جديد
        finally:
            os.environ.pop("GEMINI_API_KEY")
        self.assertEqual(ai.parse_json_object('```json\n{"tone": "neutral"}\n```'), {"tone": "neutral"})
        self.assertIsNone(ai.parse_json_object("no json here"))

    def test_enrich_validates_answer_and_needs_text_for_summary(self):
        os.environ["ANTHROPIC_API_KEY"] = "test"
        try:
            e = ai.AIEnricher(CFG, {}, "2026-11-14", list(nb.TOPIC_LABELS))
            e._anthropic = lambda prompt: '{"title_ar": "عنوان", "summary_ar": "ملخص مختلق", "tone": "angry", "topic": "energy"}'
            out = e.enrich("Title", "Src", "https://news.google.com/rss/articles/x", "news.google.com")
            self.assertEqual(out["summary_ar"], "")     # لا نص للخبر => لا ملخص
            self.assertEqual(out["tone"], "")           # قيمة غير معروفة تُهمل
            self.assertEqual(out["topic"], "energy")
        finally:
            os.environ.pop("ANTHROPIC_API_KEY")

    def test_model_choice_and_text_extraction(self):
        models = [{"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
                  {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                  {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
                  {"name": "models/gemini-3.5-flash-image", "supportedGenerationMethods": ["generateContent"]}]
        self.assertEqual(ai.choose_gemini_model(models), "gemini-3.5-flash-lite")
        page = "<html><script>x()</script><p>" + "جملة طويلة من نص الخبر عن السعودية. " * 12 + "</p><p>short</p></html>"
        self.assertIn("السعودية", ai.extract_text(page))
        self.assertEqual(ai.extract_text("<p>قصير</p>"), "")


class TitleFilterTests(unittest.TestCase):
    PATS = nb.compile_terms(CFG["title_must_match_any"])

    def test_matches_in_many_languages(self):
        for title in ["السعودية تعلن ميزانية 2027", "وزير سعودي يزور طوكيو", "ولي العهد يستقبل وفدًا في الرياض",
                      "Saudis welcome new visa rules", "サウジアラビア、新しい観光ビザを発表", "中国与沙特签署能源协议",
                      "사우디아라비아와 한국 정상회담", "Саудовская Аравия сократит добычу", "L'Arabie saoudite investit",
                      "บริษัทไทยลงทุนในซาอุดีอาระเบีย", "Suudi Arabistan'dan yeni karar", "סיכום ביקור בסעודיה",
                      "عربستان سعودی و ایران", "Arabia Saudyjska kupuje"]:
            self.assertTrue(nb.title_matches(title, self.PATS), title)

    def test_rejects_unrelated(self):
        for title in ["ارتفاع أسعار الألمنيوم عالميًا", "Ksar el Kebir festival opens", "Egypt and Jordan sign deal",
                      "وزارة الرياضة تعلن جدول الدوري", "مهرجان الحجارة القديمة"]:
            self.assertFalse(nb.title_matches(title, self.PATS), title)


class ConfigTests(unittest.TestCase):
    def test_x_handles_valid(self):
        import re
        for handle in CFG["x"]["accounts"]:
            self.assertRegex(handle, r"^[A-Za-z0-9_]{1,15}$")

    def test_state_keeps_old_file_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"sent": {"uabc": 1}, "warned": {"noresults": "2026-10-25"}}', "utf-8")
            state = nb.State(path)
            self.assertTrue(state.seen("uabc"))
            self.assertEqual(state.data["stories"], [])
            state.save()


if __name__ == "__main__":
    unittest.main()


class GulfTests(unittest.TestCase):
    def test_subjects_in_many_languages(self):
        cases = [("UAE and India sign trade pact", "en", ["AE"]), ("Dubaï accueille un sommet sur l'IA", "fr", ["AE"]),
                 ("قطر والكويت توقعان اتفاقية غاز", "ar", ["QA", "KW"]), ("البحرين تستضيف القمة الخليجية", "ar", ["BH"]),
                 ("سلطنة عمان تعلن ميزانية 2027", "ar", ["OM"]), ("الوفد العماني يصل طوكيو", "ar", ["OM"]),
                 ("カタール、LNG増産を発表", "ja", ["QA"]), ("科威特宣布新投资计划", "zh", ["KW"]),
                 ("Катар и Оман обсудили поставки газа", "ru", ["QA", "OM"]), ("Katar'da yeni dönem", "tr", ["QA"]),
                 ("BAE ile anlaşma imzalandı", "tr", ["AE"]), ("Bahrein acoge el Gran Premio", "es", ["BH"]),
                 ("Oman opens new port in Duqm", "en", ["OM"]), ("אבו דאבי משקיעה בישראל", "he", ["AE"])]
        for title, lang, expected in cases:
            self.assertEqual(nb.GULF.subjects(title, lang), expected, title)

    def test_other_meanings_rejected(self):
        for title, lang in [("Oman kodin ostaminen kallistuu", "fi"), ("Katar sienny: jak leczyć", "pl"),
                            ("ملك الأردن يفتتح مشروعًا في عمان", "ar"), ("Arsenal win at Emirates Stadium", "en"),
                            ("Governo de Santa Catarina anuncia obras", "pt"), ("Woman wins award in Roman city", "en"),
                            ("Операция по удалению катаракты", "ru"), ("My bae is the best", "en")]:
            self.assertEqual(nb.GULF.subjects(title, lang), [], title)

    def test_every_gnews_edition_has_gulf_query_or_is_skipped(self):
        import gulf
        missing = sorted({ed["lang"] for ed in CFG["google_news"]["editions"] if not gulf.query_for(ed)})
        self.assertEqual(missing, ["am"])  # الأمهرية فقط بلا صيغة بحث خليجية

    def test_separate_batch_with_country_cap_and_saudi_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            tg, state = Recorder(), new_state(tmp)
            items = [art("Saudi Arabia and Qatar sign rail link deal", "reuters.com", source="Reuters"),
                     art("Kuwait approves new airport terminal budget", "kuna.net.kw", country="Kuwait"),
                     art("Oman opens new port in Duqm", "timesofoman.com", country="Oman")]
            uae = ["Dubai announces new tower downtown", "UAE central bank holds interest rates", "Abu Dhabi fund buys stake in airline",
                   "Sharjah book fair draws record visitors", "Emirati astronaut returns from space station", "Dubai airport traffic hits record"]
            items += [art(t, f"site{i}.ae", country="United Arab Emirates") for i, t in enumerate(uae)]
            run_with(items, state, tg, tmp)
            sep = next(i for i, m in enumerate(tg.sent) if "أخبار الخليج" in m and "🌴" in m)
            before, after = tg.sent[:sep], tg.sent[sep + 1:]
            self.assertEqual(len(before), 1)
            self.assertIn("خبر عن 🟢 السعودية", before[0])   # خبر السعودية وقطر في قسم السعودية
            self.assertTrue(all("خبر خليجي —" in m for m in after))
            self.assertEqual(sum("خبر خليجي — الإمارات" in m for m in after), 3)   # حد الدولة الواحدة
            self.assertEqual(sum("#أخبار_الكويت" in m for m in after), 1)
            self.assertEqual(sum("#أخبار_عمان" in m for m in after), 1)
            self.assertTrue(all("#الخليج" in m for m in after))

    def test_no_separator_when_no_gulf_news_and_can_disable(self):
        with tempfile.TemporaryDirectory() as tmp:
            tg, state = Recorder(), new_state(tmp)
            run_with([art("Saudi Arabia opens new metro line in Riyadh", "arabnews.com")], state, tg, tmp)
            self.assertFalse(any("أخبار الخليج" in m for m in tg.sent))
            tg2, state2 = Recorder(), new_state(tmp + "/x")
            off = {**CFG, "gulf": {"enabled": False}}
            run_with([art("Kuwait approves new airport terminal budget", "kuna.net.kw")], state2, tg2, tmp, cfg=off)
            self.assertEqual(tg2.sent, [])

    def test_gulf_digest_is_separate(self):
        recs = [{"ts": time.time(), "title": "a", "url": "https://e.com/1", "origin": "gnews", "score": 60, "section": "gulf", "subject": "QA"},
                {"ts": time.time(), "title": "b", "url": "https://e.com/2", "origin": "gnews", "score": 60}]
        import gulf
        text = build_digest([r for r in recs if r.get("section") == "gulf"], "موجز الخليج", 10, nb.TOPIC_LABELS, geo.REGIONS_AR, ai.TONES, gulf.NAMES_AR)
        self.assertIn("حسب الدولة", text)
        self.assertIn("قطر 1", text)
        self.assertIn("عدد ما نُشر: 1", text)
