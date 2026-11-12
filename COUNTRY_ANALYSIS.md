# تحليل التغطية حسب الدولة

يوفر `CountryCoverageTracker` ملخصًا للأخبار المخزنة أو المقدمة مباشرة، يشمل حجم التغطية وحصتها والموضوعات والمصادر الأكثر ظهورًا. تقبل الفئة قائمة مقالات أو `ArticleStore`:

```python
from country_coverage_tracker import CountryCoverageTracker
from data_store import ArticleStore

store = ArticleStore("data/news.db")
tracker = CountryCoverageTracker(store=store)
coverage = tracker.analyze_coverage_by_country()
comparison = tracker.compare_countries("US", "GB")
groups = tracker.get_sensitive_countries()
```

تستخدم رموز الدولة الموجودة في المقال إن توفرت، وإلا تستعين باسم السوق/الدولة المحفوظ. قد يمثل هذا الاسم سوق إصدار Google News، وليس بلد ملكية الصحيفة أو موقعها. لا تُستنتج جنسية المصدر من نطاقه.

عند إضافة جداول التحليل لأول مرة إلى قاعدة بيانات موجودة، يحفظ `ArticleStore` نسخة احتياطية بجانبها بامتداد `.bak` قبل إنشاء الجداول. لا تُحذف أو تُعدّل جداول المقالات القديمة.

الاتجاه يقارن عدد المقالات المرصودة في آخر 30 يومًا بالـ30 يومًا السابقة. وتُحسب الإشارات الإيجابية والسلبية من مفردات محدودة في العنوان، لذلك فهي مؤشرات أولية وليست تحليل مشاعر لغويًا أو حكمًا على موقف دولة. افحص تغطية اللغات والمصادر وحجم العينة قبل إجراء المقارنات.

`get_sensitive_countries()` يحافظ على الاسم المطلوب للتوافق، لكن نتائج الفئات (`negative_focus` و`positive_focus` و`neutral`) تصف توزيع مفردات العناوين فقط، ولا تصنف دولة أو شعبًا على أنه سلبي أو إيجابي.
