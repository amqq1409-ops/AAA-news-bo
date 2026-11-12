# دليل ملخصات التغطية الإعلامية

ينشئ `MediaIntelligenceAnalyzer` ملخصًا وصفيًا من الأخبار الموجودة في قاعدة البيانات أو من قائمة مقالات:

```python
from data_store import ArticleStore
from intelligence_analyzer import MediaIntelligenceAnalyzer

report = MediaIntelligenceAnalyzer(store=ArticleStore("data/news.db")).generate_intelligence_report()
comparisons = MediaIntelligenceAnalyzer(articles).comparative_analysis()
patterns = MediaIntelligenceAnalyzer(articles).pattern_detection()
```

يتضمن التقرير حجم العينة، الأسواق التي ظهرت فيها أخبار، الموضوعات ومصادرها، إشارات العناوين السلبية، ومجموعات التشابه المرشحة. تقسيمات الأسواق (الأسواق المتقدمة والشرق الأوسط وBRICS والاتحاد الأوروبي) هي تجميعات تحليلية وليست مواقف رسمية أو إجماعًا وطنيًا.

## قراءة النتائج

- أعداد المقالات تقيس ما جمعه البوت، لا إجمالي ما نشرته الصحافة.
- مؤشرات المشاعر قائمة على كلمات مفتاحية في العنوان وباللغات التي تغطيها القوائم الصغيرة داخل الكود.
- `near_term_outlook` لا يقدم توقعًا عند غياب سلسلة زمنية مناسبة؛ لا يستخدم النظام نموذج تنبؤ.
- أنماط المصادر والموضوعات قد تتأثر بتكوين المصادر وإعدادات البحث وتكرار إعادة النشر.
- تحليل التمويل معلّم `not_assessed` لأن البيانات لا تتضمن أدلة موثوقة عن الملكية أو التمويل.

استخدم الإشارات لاختيار أخبار لمراجعتها، لا كحقائق عن نوايا أو مواقف جهات أو دول.
