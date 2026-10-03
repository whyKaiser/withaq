# Backlog واحد للفريق — 3 أكتوبر 2026

المالك البشري يختاره الفريق. REVIEW يعني تنفيذًا وفحوصات محلية دون مراجعة مستقلة أو تشغيل عضو آخر. PARTIAL يعني جزءًا محددًا منفذًا مع شروط خروج متبقية. لا velocity أو مساهمات بشرية مخترعة.

| ID | المهمة | أولوية | نقاط | Sprint المخطط | الحالة 0.2 | المتبقي |
|---|---|---|---:|---|---|---|
| WQ-001 | Repo عام + vault | P0 | 2 | S01 | REVIEW | مراجعة عضو |
| WQ-002 | locks/bootstrap/CI | P0 | 3 | S01 | PARTIAL | OAuth workflow + تشغيل عضو ثانٍ |
| WQ-003 | MFSC وحالات البحث وoracle | P0 | 3 | S01 | REVIEW | مراجعة مستقلة للمنطق |
| WQ-004 | validator مستقل | P0 | 3 | S01 | REVIEW | توسيع corpus وتعقيب مراجع |
| WQ-005 | fixture barriers | P0 | 3 | S01 | REVIEW | تاريخي؛ المحرك العام في 009 |
| WQ-006 | exact approval وunknown mock | P0 | 3 | S01 | REVIEW | مزود حقيقي خارج نطاق العرض الحالي |
| WQ-007 | Console ثنائية اللغة | P0 | 5 | S01 | REVIEW | usability/reproduction مستقل |
| WQ-008 | PostgreSQL/Alembic | P0 | 8 | S02 | REVIEW | قيود/أدوار نشر مؤسسية؛ ADR-007 |
| WQ-009 | lineage عام وcycles/closure | P0 | 5 | S02 | REVIEW | object storage وتصنيف دفعات المصادر |
| WQ-010 | APIs للعقود/الأجهزة/المصادر | P1 | 5 | S02 | PARTIAL | lifecycle/owner/AND/OR وإسناد الحوادث للدفعات |
| WQ-011 | outbox/lease/fencing/restart | P0 | 8 | S03 | REVIEW | limits/operations طويلة المدة |
| WQ-012 | races بين عمليتين | P0 | 5 | S03 | REVIEW | ضغط موسع ومراجعة البروتوكول |
| WQ-013 | فصل الخدمات وهويات مقيدة | P0 | 5 | S03 | PARTIAL | فصل صلاحيات الشبكة ومنع worker egress في النشر |
| WQ-014 | إفصاح عربي/إنجليزي وsanitization | P1 | 5 | S03 | PARTIAL | corpus أوسع؛ لا DLP عام |
| WQ-015 | تكامل UI مع APIs العامة | P0 | 5 | S04 | REVIEW | نموذج إدارة عقود عام وتعدد مدخلات في الشاشة |
| WQ-016 | اختبارات متصفح آلية | P0 | 3 | S04 | READY | فحص يدوي منفذ؛ suite آلية متبقية |
| WQ-017 | نتائج مقارنة خام | P1 | 5 | S04 | REVIEW | 300 إعداد model-only؛ مراجعة المنهجية |
| WQ-018 | PEP/nftables مختبر معزول | P1 | 8 | S04/لاحق | PARTIAL | حاوية مؤقتة ناجحة؛ VM/PEP دائم متبقٍ |
| WQ-019 | probes new/established/function | P1 | 8 | S04/لاحق | PARTIAL | G/X/P/M/A مقاس؛ topologies/faults إضافية |
| WQ-020 | restore/barrier/outbox | P0 | 5 | S04 | PARTIAL | pg_restore مؤهل؛ ledger replication/freshness مؤسسي متبقٍ |
| WQ-021 | تشغيل عضو ثانٍ وتسجيل عرض | P0 | 3 | S05 | READY | يحتاج عضوًا فعليًا؛ غير منفذ بمساعدة Codex |
| WQ-022 | Release ودليل حكام | P0 | 2 | S05 | REVIEW | إصدار مختبر؛ human review قبل final qualification |
| WQ-023 | حسابات/أدوار/رخصة | P1 | 1 | S01 | WAITING_TEAM | اختيار بشري؛ الأسماء مثبتة في TEAM |
| WQ-024 | رابط حكام ونشر تلقائي | P0 | 5 | S04 | PARTIAL | العزل والحاوية والفحوص جاهزة؛ تفعيل Render وفحص الرابط العام جاريان |

الترتيب المنجز تقنيًا سبق تواريخ S02–S04 المخططة. هذا لا يدعي انعقاد Sprint review أو مساهمات/ساعات بشرية. اعتماديات التنفيذ: 008 قبل 009/011؛ 009/011 قبل 012/013؛ 015 قبل 021.

OAuth الحالي لا يستطيع إنشاء GitHub Actions workflows؛ القالب محفوظ في `docs/ci`. ليس عائقًا لبناء المشروع أو نشر مصدره وأدلته.
