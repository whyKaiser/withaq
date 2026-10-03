# S02 — سلطة الحالة

4 أكتوبر 2026. الحالة: PLANNED. البطاقات WQ-008/009/010. المالك: غير مسند.

الهدف: نقل ثوابت الحالة من aggregate محلي إلى مخطط PostgreSQL واضح، مع migrations قابلة للإعادة وroot closure حقيقي.

الاعتماد: S01 قابل للتشغيل. القبول: قاعدة فارغة تبلغ migration head، قيود FK/version، role 403 وstale 409، منع cycles وunknown roots، عدم رجوع REVOKED إلى ACTIVE، واختبارات مقارنة مع fixture الأساس.

مخرج المراجعة: PR وأدلة migration واختبارات lineage. إذا لم ينجز، يبقى عرض SQLite موسومًا ولا يسمى PostgreSQL جاهزًا.
