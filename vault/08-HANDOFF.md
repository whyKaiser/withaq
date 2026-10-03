# التسليم ونقطة الاستئناف — 3 أكتوبر 2026

نسخة 0.2: حالة عامة في PostgreSQL وثلاث migrations، lineage/manifests/MAHW، outbox وfencing، validator/gateway منفصلان، disclosure بأربع قرارات، console عامة، packet broker مربوط بزر التطبيق، benchmark واستعادة مؤهلة في المختبر.

## التحقق المنفذ

- `python scripts/verify_postgres.py`: 78 ناجحًا في آخر تشغيل؛ حالات engine نفسها على SQLite وPostgreSQL. مصدر الاختبارات يسجل أي إضافات بعد هذا الرقم؛ تحديث نتيجة الإصدار النهائية في evidence.
- `tests/test_processes.py`: قتل عامل MODEL فعليًا وإعادة تشغيله؛ fence 2، مخرج واحد؛ اتصال worker بالمتحقق المستقل؛ بوابة منفصلة وOUTCOME_UNKNOWN دون إعادة عمياء.
- `npm --prefix apps/console run build`: TypeScript وVite ناجحان.
- `python scripts/packet_lab.py`: ثمانية checks ناجحة؛ حجب مباشر/relay واتصال قائم، خمس عينات لكل وظيفة، denies لا تفتح تلقائيًا خلال فحص غياب rule installer.
- اللوحة على PostgreSQL: خطة `{a,b}`؛ زر packet-lab أعاد LAB_CONFIRMED مع MEASURED PASS لكل عقد وreceipt موقّع؛ approve/dispatch أعاد MOCK_SENT.
- سحب GUI أثناء مهمة MODEL بعد LEASED: ROOT_REVOKED ثم REJECTED عند publication؛ السحب قبل النشر موثق بالأوقات في أحداث التجربة. تجربة أخرى سُحبت بعد النشر؛ مخرجها صار REVOKED، ولا تُحسب كاختبار نشر متأخر.
- `python scripts/benchmark.py`: 300 إعداد model-only. MFSC: 30 OPTIMAL، 20 INFEASIBLE، 10 UNKNOWN من 60 تكوينًا. المقارنة لا تدعي تفوقًا ميدانيًا.
- `python scripts/restore_qualification.py`: سبعة checks ناجحة في PostgreSQL؛ dump أقدم من السحب، ledger أحدث موثق، الحاجز قبل resume.

أدلة الإصدار وsource commits في `docs/evidence/README.md`. نتائج 0.1 محفوظة كأدلة تاريخية فقط. تحديث vault لا يعني مراجعة بشرية أو تشغيل عضو ثانٍ. تحذير TestClient/httpx upstream معروف ولا يغيّر نجاح الفحص.

الأدلة الخام أُعيد إنتاجها من المصدر النظيف `c70d693fad024a08bdeb3018b7e22c9d47ffbc1a`. بعد تثبيت المصدر وإعادة تشغيل الخدمات، أعادت الواجهة قياس خطتي `a+b` و`a+d`؛ كلاهما LAB_CONFIRMED، وكل عقد حرج MEASURED PASS. تصدير الحالة يحتفظ بالتاريخ السابق أيضًا؛ commit التصدير لا يثبت نسخة كود كل مهمة تاريخية.

## نقاط الاستئناف

راجع `docs/POSTER-TRACEABILITY.md` والبطاقات المتبقية. الأولوية: مراجعة عضو وتشغيله المستقل قبل 8 أكتوبر، ثم اختبار متصفح آلي وإدارة العقود والاعتماديات، ثم عزل خروج الخدمات والتشغيل طويل المدة ودفعات مصادر الأجهزة. لا تخلط LAB_CONFIRMED مع PEP دائم أو استضافة عامة.

GitHub Actions غير مفعّل: OAuth رفض كتابة workflow. القالب في `docs/ci`. لم توسع الصلاحيات تلقائيًا ولم تنشر أسرار التشغيل.

## قالب تسليم كل تغيير

```text
التاريخ / العضو / البطاقة / الفرع:
ما تغير ولماذا:
الواجهات أو القرارات المتأثرة:
الفحوصات ونتيجتها:
raw evidence / PR / commit:
المتبقي والعوائق:
الخطوة التالية:
```
