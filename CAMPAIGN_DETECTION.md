# رصد أنماط التغطية المتشابهة

تستخدم `CampaignDetector` تشابه مفردات العناوين، تقارب تواريخ النشر، واختلاف أسواق التغطية لاستخراج مجموعات تستحق مراجعة بشرية:

```python
from campaign_detector import CampaignDetector

detector = CampaignDetector(articles)
candidates = detector.detect_coordinated_campaigns()
topic_distribution = detector.detect_bias_patterns()
vocabulary_changes = detector.detect_narrative_shifts()
```

المخرجات ترصد **تشابهًا أو تركّزًا في البيانات المجموعة فقط**. إعادة نشر الخبر نفسه، أو وكالات الأنباء، أو فلاتر البحث قد تنتج أنماطًا مشابهة. لا تثبت هذه النتائج تنسيقًا مقصودًا، أو تحيزًا تحريريًا، أو تغيرًا في رواية رسمية، أو تمويلًا مشتركًا. لا يحتوي مصدر البيانات الحالي على معلومات موثقة عن الملكية أو التمويل.

`severity` و`confidence_score` درجتان إرشاديتان ناتجتان عن تشابه العناوين وتوزعها على الأسواق؛ لا تمثلان احتمالية إحصائية معايرة. راجع المقالات الأصلية والتواريخ والمصادر قبل أي استنتاج أو إجراء.
