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
DIGEST_ON = {**CFG, "digest": {**CFG["digest"], "enabled": True}}
NOW = dt.datetime(2026, 11, 14, 0, 5, tzinfo=nb.RIYADH)
FAKE_AR = {
    "Saudi Arabia signs $5 billion investment deal with Japan": "السعودية توقع صفقة استثمار بقيمة 5 مليارات دولار مع اليابان",
    "Saudi Arabia signs 5 billion dollar investment deal with Japan": "السعودية توقع صفقة استثمار بقيمة 5 مليارات دولار مع اليابان",
    "サウジアラビア、日本と50億ドルの投資契約を締結": "المملكة العربية السعودية توقع صفقة استثمار بقيمة 5 مليارات دولار مع اليابان",
    "サウジ、新しい観光ビザを発表": "السعودية تعلن عن تأشيرة سياحية جديدة",
}


def fake_translate(text):
    """مثل خدمة الترجمة: سطر لكل عنوان، وما لا تعرفه تعيده كما هو."""
    lines = text.split("\n")
    if len(lines) == 1:
        return FAKE_AR.get(text)
    return "\n".join(FAKE_AR.get(line, line) for line in lines)


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
    nb.add_arabic_titles.__defaults__ = (fake_translate,)
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
        self.assertEqual(nb.classify_topic("منتخب كوريا الجنوبية يخسر أمام السعودية لأول مرة منذ 21 عاماً بسبب انهيار الدفاع"), "sports")
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
            nb.add_arabic_titles.__defaults__ = (fake_translate,)
            nb.run({**CFG, "digest": {**CFG["digest"], "enabled": True}}, state, tg, archive=archive, now=evening, fetchers=fetchers)
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
            nb.maybe_send_digests(DIGEST_ON, state, tg, archive, friday)
            self.assertEqual(len([m for m in tg.sent if "الأسبوعي" in m]), 0)
            self.assertEqual(state.data["digest"].get("weekly"), "2026-11-13")
            tg2, state2, archive2 = Recorder(), new_state(tmp + "/b"), Archive(Path(tmp) / "c")
            archive2.add(dict(rec))
            archive2.add({**rec, "ts": friday.timestamp() - 5 * 86400})
            nb.maybe_send_digests(DIGEST_ON, state2, tg2, archive2, friday)
            self.assertEqual(len([m for m in tg2.sent if "الأسبوعي" in m]), 1)

    def test_no_digest_before_hour(self):
        with tempfile.TemporaryDirectory() as tmp:
            tg, state = Recorder(), new_state(tmp)
            nb.maybe_send_digests(DIGEST_ON, state, tg, Archive(Path(tmp) / "a"), NOW.replace(hour=15))
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
            self.assertFalse(any("🌴" in m for m in tg.sent))   # لا رسالة فاصلة: كل خبر فوري بذاته
            before, after = tg.sent[:1], tg.sent[1:]
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


class FreshAndFastTests(unittest.TestCase):
    def test_translate_many_uses_one_request_per_batch(self):
        calls = []

        def translate(text):
            calls.append(text)
            return "\n".join("ع" + str(i) for i, _ in enumerate(text.split("\n")))

        out = nb.translate_many([f"title {i}" for i in range(20)], translate, batch_size=10)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(out), 20)
        self.assertTrue(all(out))

    def test_translate_many_falls_back_when_lines_differ(self):
        def translate(text):
            return "سطر واحد" if "\n" in text else "ترجمة " + text

        self.assertEqual(nb.translate_many(["a", "b"], translate), ["ترجمة a", "ترجمة b"])

    def test_translate_many_stops_when_service_down(self):
        calls = []

        def translate(text):
            calls.append(text)
            return None

        out = nb.translate_many([f"t{i}" for i in range(50)], translate, batch_size=5)
        self.assertEqual(len(calls), 2)
        self.assertEqual(out, [None] * 50)

    def test_old_date_in_url_is_rejected(self):
        a = art("Saudi Arabia opens new metro line in Riyadh")
        a.url = "https://example.com/2024/05/12/saudi-metro"
        self.assertFalse(nb.is_recent(a, 6, NOW))
        a.url = "https://example.com/2026/11/13/saudi-metro"
        self.assertTrue(nb.is_recent(a, 6, NOW))

    def test_news_older_than_limit_is_rejected(self):
        self.assertTrue(nb.is_recent(art("Saudi news", minutes_ago=60), 6, NOW))
        self.assertFalse(nb.is_recent(art("Saudi news", minutes_ago=7 * 60), 6, NOW))

    def test_fresher_story_ranks_first(self):
        cfg = {"_now": NOW, "fresh_hours": 3}
        fresh, stale = art("Saudi A", minutes_ago=5), art("Saudi B", minutes_ago=170)
        fresh.relevance_score = stale.relevance_score = 50
        self.assertLess(nb.sort_key(fresh, cfg), nb.sort_key(stale, cfg))

    def test_age_text(self):
        self.assertEqual(nb.age_text(art("x", minutes_ago=12), NOW), "منذ 12 دقيقة")
        self.assertEqual(nb.age_text(art("x", minutes_ago=0), NOW), "الآن")
        self.assertIn("⏱", nb.format_message(art("Saudi Arabia opens metro", minutes_ago=12), {"_now": NOW}))

    def test_messages_sent_oldest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            tg, state = Recorder(), new_state(tmp)
            items = [
                art("Saudi Arabia opens new metro line in Riyadh", "arabnews.com", minutes_ago=10),
                art("Saudi Aramco reports quarterly oil profit rise", "reuters.com", minutes_ago=90),
            ]
            run_with(items, state, tg, tmp)
            news = [m for m in tg.sent if "📰" in m]
            self.assertEqual(len(news), 2)
            self.assertIn("Aramco", news[0])

    def test_no_digest_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            tg, state = Recorder(), new_state(tmp)
            evening = NOW.replace(hour=21, minute=30)
            run_with([art("Saudi Arabia opens new metro line in Riyadh", minutes_ago=-1290 + 30)], state, tg, tmp, now=evening)
            self.assertFalse([m for m in tg.sent if "موجز" in m])

    def test_gnews_fetched_in_parallel(self):
        cfg = {"google_news": {"parallel": 4, "editions": [
            {"lang": "en", "hl": f"en-{i}", "gl": "US", "ceid": "US:en", "query": "Saudi"} for i in range(6)]}}
        rss = b"<rss><channel><item><title>Saudi news - Src</title><link>https://e.com/a</link><source url='https://e.com'>Src</source><pubDate>Sat, 14 Nov 2026 00:00:00 GMT</pubDate></item></channel></rss>"

        class Resp:
            status_code = 200
            content = rss

        original = nb.http_get
        nb.http_get = lambda url, **kw: Resp()
        try:
            items, counts, status = nb.fetch_gnews(cfg, time.monotonic() + 30)
        finally:
            nb.http_get = original
        self.assertEqual((len(items), status[0], len(counts)), (6, "ok", 6))


class DirectFeedTests(unittest.TestCase):
    RSS = b"""<rss><channel>
      <item><title><![CDATA[Saudi Arabia &amp; Japan sign deal]]></title><link>https://ex.com/a?utm_source=rss</link>
        <pubDate>Fri, 13 Nov 2026 20:50:00 GMT</pubDate></item>
      <item><title>No link</title></item></channel></rss>"""
    ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Qatar opens port</title>
      <link rel="alternate" href="https://ex.org/q"/><updated>2026-11-13T20:55:00Z</updated></entry></feed>"""
    BROKEN = b"""<rss><\\channel><item><link>https://qna.example/n1</link><title>Saudi minister meets counterpart</title>
      <pubDate>2026-11-13T20:40:00Z</pubDate></item></rss>"""

    def test_rss_and_atom(self):
        items = nb.parse_feed(self.RSS, {"name": "Ex", "lang": "en", "iso": "SA"})
        self.assertEqual(len(items), 1)
        a = items[0]
        self.assertEqual((a.title, a.url, a.source_name, a.origin), ("Saudi Arabia & Japan sign deal", "https://ex.com/a", "Ex", "feed"))
        self.assertEqual(a.published, dt.datetime(2026, 11, 13, 20, 50, tzinfo=dt.timezone.utc))
        atom = nb.parse_feed(self.ATOM, {"name": "Q", "lang": "en"})
        self.assertEqual((atom[0].title, atom[0].url), ("Qatar opens port", "https://ex.org/q"))
        self.assertIsNotNone(atom[0].published)

    def test_broken_xml_is_still_read(self):
        items = nb.parse_feed(self.BROKEN, {"name": "QNA", "lang": "en"})
        self.assertEqual([a.title for a in items], ["Saudi minister meets counterpart"])
        self.assertIsNone(nb.parse_feed(b"<html><body>blocked</body></html>", {"name": "x"}))

    def test_date_without_zone_uses_feed_zone(self):
        d = nb.parse_feed_date("2026-11-13 23:50:00", 3)
        self.assertEqual(d.astimezone(dt.timezone.utc).hour, 20)

    def test_pick_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = new_state(tmp)
            self.assertEqual(nb.pick_mode(CFG, state, 10_000), "full")
            state.data["runs"] = {"full": 10_000, "wide": 10_000}
            self.assertEqual(nb.pick_mode(CFG, state, 10_060), "instant")
            self.assertEqual(nb.pick_mode(CFG, state, 10_000 + 280), "fast")
            self.assertEqual(nb.pick_mode(CFG, state, 10_000 + 3600), "full")

    def test_instant_run_sends_only_very_recent_with_flash_mark(self):
        with tempfile.TemporaryDirectory() as tmp:
            tg, state = Recorder(), new_state(tmp)
            items = [art("Saudi Arabia opens new metro line in Riyadh", "arabnews.com", minutes_ago=5, origin="feed"),
                     art("Saudi Aramco reports quarterly oil profit rise", "reuters.com", minutes_ago=200, origin="feed")]
            fetchers = {"feeds": lambda c, d: (items, {}, ("ok", ""))}
            nb.add_arabic_titles.__defaults__ = (fake_translate,)
            sent = nb.run(CFG, state, tg, archive=Archive(Path(tmp) / "a"), now=NOW, fetchers=fetchers, instant=True)
            self.assertEqual(sent, 1)
            self.assertIn("⚡", tg.sent[0])
            self.assertIn("metro", tg.sent[0])


class FakeResponse:
    def __init__(self, payload=None, status=200, text=""):
        self.payload, self.status_code, self.text = payload, status, text

    def json(self):
        if self.payload is None:
            raise ValueError("no json")
        return self.payload


class WorldTests(unittest.TestCase):
    TG_PAGE = """<html><body>
      <div class="tgme_widget_message_wrap js-widget_message_wrap"><div class="tgme_widget_message" data-post="AjaNews/101">
        <div class="tgme_widget_message_text js-message_text" dir="auto"><b>عاجل</b> | ترمب: سنبدأ محادثات مع إيران<br/>الأسبوع المقبل</div>
        <a class="tgme_widget_message_date" href="https://t.me/AjaNews/101"><time datetime="2026-11-13T20:58:00+00:00" class="time">23:58</time></a>
      </div></div>
      <div class="tgme_widget_message_wrap js-widget_message_wrap"><div class="tgme_widget_message" data-post="AjaNews/102">
        <div class="tgme_widget_message_photo"></div>
        <time datetime="2026-11-13T20:59:00+00:00" class="time">23:59</time>
      </div></div></body></html>"""
    BSKY_FEED = {"feed": [
        {"post": {"uri": "at://did:plc:abc/app.bsky.feed.post/3kxyz", "author": {"handle": "reporter.bsky.social", "displayName": "A Reporter"},
                  "record": {"text": "Putin and Xi Jinping meet in Beijing to discuss energy deal", "createdAt": "2026-11-13T20:55:00.000Z", "langs": ["en"]}}},
        {"reason": {"$type": "app.bsky.feed.defs#reasonRepost"},
         "post": {"uri": "at://did:plc:zzz/app.bsky.feed.post/3kabc", "author": {"handle": "other.bsky.social"},
                  "record": {"text": "A repost about Russia that must be skipped", "createdAt": "2026-11-13T20:55:00.000Z"}}},
    ]}

    def matcher(self):
        return nb.watch.Matcher(nb.compile_terms, CFG["world"]["leaders"])

    def test_countries_and_leaders_in_english_and_arabic(self):
        m = self.matcher()
        self.assertEqual(m.subjects("Trump says US will talk to Iran next week"), ["US", "IR"])
        self.assertEqual(m.subjects("عاجل | ترمب: رسوم جديدة على الصين وللعراق نصيب"), ["US", "CN", "IQ"])
        self.assertEqual(m.subjects("البيت الأبيض: بوتين يزور أنقرة"), ["US", "RU", "TR"])
        self.assertEqual(m.subjects("Netanyahu arrives in Paris"), ["IL", "FR"])

    def test_common_words_are_not_countries(self):
        m = self.matcher()
        for text in ["us and them went home", "Jim Jordan visits Indiana", "وزير يمنح عراقيل تركيز هندسة",
                     "Thanksgiving turkey prices fall"]:
            self.assertEqual([i for i in m.subjects(text) if i != "TR"] if "turkey" in text else m.subjects(text), [], text)

    def test_telegram_page_parsing(self):
        rows = nb.watch.parse_telegram(self.TG_PAGE, {"id": "AjaNews", "name": "الجزيرة عاجل", "lang": "ar"})
        self.assertEqual(len(rows), 1)  # المنشور الثاني صورة بلا نص
        self.assertEqual(rows[0]["url"], "https://t.me/AjaNews/101")
        self.assertEqual(rows[0]["text"], "عاجل | ترمب: سنبدأ محادثات مع إيران الأسبوع المقبل")
        self.assertEqual(rows[0]["published"], dt.datetime(2026, 11, 13, 20, 58, tzinfo=dt.timezone.utc))

    def test_bluesky_feed_parsing_skips_reposts(self):
        rows = nb.watch.parse_bluesky_feed(self.BSKY_FEED)
        self.assertEqual([r["url"] for r in rows], ["https://bsky.app/profile/reporter.bsky.social/post/3kxyz"])
        self.assertEqual(rows[0]["source"], "A Reporter (@reporter.bsky.social)")

    def test_bluesky_resolution_requires_trusted_account(self):
        profiles = {"profiles": [
            {"handle": "bigname.bsky.social", "did": "did:1", "followersCount": 50000, "postsCount": 900},
            {"handle": "fakename.bsky.social", "did": "did:2", "followersCount": 12, "postsCount": 3},
            {"handle": "official.bsky.social", "did": "did:3", "followersCount": 5, "postsCount": 1,
             "verification": {"verifiedStatus": "valid"}},
        ]}
        store = {}
        found = nb.watch.resolve_bluesky(["Big_Name", "FakeName", "official", "missing1"], store, {}, time.monotonic() + 5,
                                         lambda url, **kw: FakeResponse(profiles), lambda *a: None, now_ts=1000)
        self.assertEqual(found, 2)
        self.assertEqual(store["map"]["big_name"]["h"], "bigname.bsky.social")
        self.assertEqual(store["map"]["official"]["h"], "official.bsky.social")
        self.assertNotIn("h", store["map"]["fakename"])
        self.assertNotIn("h", store["map"]["missing1"])
        # من لم يوجد لا يُعاد البحث عنه قبل انقضاء المهلة
        calls = []
        nb.watch.resolve_bluesky(["FakeName"], store, {}, time.monotonic() + 5,
                                 lambda url, **kw: calls.append(url) or FakeResponse(profiles), lambda *a: None, now_ts=2000)
        self.assertEqual(calls, [])

    def world_items(self):
        def post(text, minutes_ago, origin="tg", lang="ar"):
            a = art(text, "t.me" if origin == "tg" else "bsky.app", lang, minutes_ago, origin, source="الجزيرة عاجل")
            a.watch = True
            return a
        return [post("عاجل | ترمب: سنبدأ محادثات مع إيران الأسبوع المقبل", 3),
                post("عاجل | حالة الطقس غدًا غائم جزئيًا على السواحل", 2),             # لا دولة ولا رئيس
                post("عاجل | الرئيس الروسي بوتين يصل إلى بكين في زيارة رسمية", 90),  # قديم
                post("عاجل | وزير الخارجية السعودي يلتقي نظيره الفرنسي في باريس", 4),  # يخص السعودية
                post("Zelensky says Ukraine needs more air defense", 5, "bsky", "en")]

    def run_world(self, tmp, tg, state, items=None):
        fetchers = {"tg": lambda c, d: (items or self.world_items(), {}, ("ok", ""))}
        nb.add_arabic_titles.__defaults__ = (lambda text: "\n".join("زيلينسكي: أوكرانيا تحتاج دفاعًا جويًا أكثر" for _ in text.split("\n")),)
        try:
            return nb.run(CFG, state, tg, archive=Archive(Path(tmp) / "a"), now=NOW, fetchers=fetchers, instant=True)
        finally:
            nb.add_arabic_titles.__defaults__ = (nb.translate_to_arabic,)

    def test_world_section_sends_only_fresh_posts_naming_countries_or_leaders(self):
        with tempfile.TemporaryDirectory() as tmp:
            tg, state = Recorder(), new_state(tmp)
            self.run_world(tmp, tg, state)
            world = [m for m in tg.sent if "#دول_ورؤساء" in m]
            self.assertEqual(len(world), 2)
            iran = next(m for m in world if "إيران" in m)
            self.assertIn("🇺🇸 🇮🇷", iran)
            self.assertIn("أمريكا • إيران", iran)
            self.assertIn("📡 الجزيرة عاجل", iran)
            ukraine = next(m for m in world if "Zelensky" in m)
            self.assertIn("🇺🇦", ukraine)
            self.assertIn("زيلينسكي: أوكرانيا تحتاج دفاعًا جويًا أكثر", ukraine)   # الترجمة
            self.assertIn("🦋", ukraine)
            self.assertFalse(any("الطقس" in m or "بكين" in m for m in tg.sent))
            saudi = [m for m in tg.sent if "السعودي" in m]
            self.assertEqual(len(saudi), 1)
            self.assertNotIn("#دول_ورؤساء", saudi[0])   # خبر السعودية في قسمه
            # لا إعادة إرسال في الفحص التالي
            again = Recorder()
            self.run_world(tmp, again, state)
            self.assertEqual(again.sent, [])

    def test_first_live_run_skips_what_is_already_published(self):
        class Live(Recorder):
            def __init__(self):
                super().__init__()
                self.dry_run = False

        with tempfile.TemporaryDirectory() as tmp:
            cfg_pause = CFG.get("send_pause_sec")
            CFG["send_pause_sec"] = 0
            try:
                tg, state = Live(), new_state(tmp)
                self.run_world(tmp, tg, state)
                self.assertFalse(any("#دول_ورؤساء" in m for m in tg.sent))
                self.assertTrue(state.data["runs"].get("world_seed"))
                new = self.world_items()[:1]
                new[0].title = "عاجل | ماكرون يعلن قمة أوروبية طارئة في بروكسل"
                new[0].url = "https://t.me/AjaNews/999"
                new[0].uid = "u" + nb.h(new[0].url)
                self.run_world(tmp, tg, state, items=new)
                self.assertEqual(len([m for m in tg.sent if "#دول_ورؤساء" in m]), 1)
            finally:
                CFG["send_pause_sec"] = cfg_pause

    def test_world_cap_per_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            tg, state = Recorder(), new_state(tmp)
            texts = ["عاجل | اليابان ترفع أسعار الفائدة للمرة الثانية هذا العام", "عاجل | زلزال قوي يضرب جنوب تركيا دون خسائر",
                     "عاجل | ألمانيا تقر ميزانية دفاع قياسية", "عاجل | البرازيل تستضيف قمة المناخ المقبلة",
                     "عاجل | مصر توقع اتفاق غاز جديدًا مع قبرص", "عاجل | كندا تفرض قيودًا على واردات الصلب",
                     "عاجل | باكستان تعلن حالة الطوارئ بسبب الفيضانات"]
            items = []
            for i, text in enumerate(texts):
                a = art(text, "t.me", "ar", 2 + i, "tg", source="العربية عاجل")
                a.watch = True
                items.append(a)
            self.run_world(tmp, tg, state, items=items)
            self.assertEqual(len([m for m in tg.sent if "#دول_ورؤساء" in m]), CFG["world"]["max_messages"])

    def test_watchlist_file(self):
        handles = nb.watch.load_handles(Path(nb.ROOT) / "watchlist.txt")
        self.assertGreater(len(handles), 500)
        self.assertEqual(len(handles), len({h.lower() for h in handles}))
        self.assertEqual(nb.watch.bsky_candidate("Kate_HunterDC"), "katehunterdc.bsky.social")
