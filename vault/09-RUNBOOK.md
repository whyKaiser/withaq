# تشغيل مختبر وثاق

1. نفّذ bootstrap من README عند البداية أو تغيّر lock.
2. شغّل `python scripts/init_lab.py` مرة أولى، ثم `docker compose -f compose.dev.yml up -d --wait db`.
3. شغّل `python scripts/lab.py --postgres --packets`. خمس عمليات خدمات؛ worker وgateway لا يستلمان DB credentials؛ PEP broker وحده يستدعي Docker.
4. افتح `http://127.0.0.1:8000` وانسخ token من `data/local-access.txt`، دون وضعه في Git أو VITE_*.
5. اتبع `docs/JUDGES.md`. الحالة QUEUED قبول للعمل وليست نجاحًا. LAB_CONFIRMED تجربة حزم مؤقتة؛ SIMULATED_CONFIRMED محاكاة فقط.
6. Ctrl+C يوقف الخدمات التابعة. أوقف DB بـ`docker compose -f compose.dev.yml stop` إن أردت. لا تستخدم `down -v` للحفاظ على الحالة.

بدون Docker: `python scripts/lab.py` يشغّل SQLite وأربع خدمات؛ تطبيق الحزم غير متاح. `serve.py` اسم تشغيل متوافق يشغّل الخدمات نفسها.

| العلامة | الخطوة |
|---|---|
| 401 / ROLE_DENIED | رمز صحيح وهوية operator للتعديل؛ لا تستخدم هوية خدمة في اللوحة |
| STALE_SNAPSHOT | راجع الحالة المحدثة وأعد الإجراء؛ لا تتجاوز revision |
| ROOT_REVOKED / ARTIFACT_NOT_ACTIVE | الحارس يمنع المصدر؛ الاستعادة بهوية جديدة وجذور مستقلة |
| UNKNOWN / INFEASIBLE | لا تطبيق؛ راجع دليل النموذج والفرضيات |
| LEASED ثم انتهاء العامل | المحاولة التالية تزيد fence؛ القديمة لا تستطيع نشر نتيجة |
| OUTCOME_UNKNOWN | لا resend أعمى؛ تصالح مع المزود قبل إجراء مستقل |
| PACKET_LAB_NOT_CONFIGURED | استخدم --packets مع Docker يعمل، أو اختر simulation |
| UNSUPPORTED_PACKET_MODEL | الرسم لا يطابق lab المعلن؛ لا توسع التغطية بالادعاء |
| PACKET_TRIAL_FAILED | راجع تشغيل lab منفصلًا؛ الحالة ليست تأكيد احتواء |
| 503 ready | افحص DB، Alembic head والهوية/السياسة؛ live وحده غير كافٍ |
| انقطاع اتصال اللوحة | البيانات الظاهرة آخر قراءة؛ الخدمة عند عودتها تعيد polling |
| npm ECONNRESET | أعد ci أو استخدم cache مطابقًا للlock؛ لا تعطل TLS |

## استعادة البيانات

`python scripts/restore_qualification.py` اختبار آمن في قاعدتين جديدتين مؤقتتين. لا يكتب فوق قاعدة الفريق. يثبت رفض ledger معدل، وتطبيق حاجز أحدث من dump قبل resume، وحفظ outbox ومنع قراءة المخرج القديم.

الاستعادة التشغيلية تحتاج اختيار أحدث ledger موثوق خارج قاعدة البيانات وتطبيقه قبل فتح القراءات/الخدمات، مع حفظ مفتاح تحقق مستقل. النسخ الآلي خارج المضيف وسلطة freshness غير منفذين بعد. مجرد نسخ dump قد يعيد صلاحيات قديمة؛ لا تصف dump وحده كاستعادة مؤهلة.

`data/` والرموز والنسخ غير العامة لا تُنشر. لا يمس bootstrap بيانات قائمة؛ الحاويات المخصصة لقياس الحزم لا تربط مجلدات المضيف أو Docker socket ولا تتصل بالشبكة الخارجية.
