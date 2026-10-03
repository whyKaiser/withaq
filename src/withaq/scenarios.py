from .models import Action, Contract, Edge, Hypothesis, Snapshot


def edge(source: str, target: str) -> Edge:
    return Edge(source=source, target=target)


def scenarios() -> dict[str, Snapshot]:
    attack = (edge("G", "P"), edge("G", "X"), edge("X", "P"))
    functions = (edge("G", "M"), edge("G", "A"))
    contracts = (
        Contract(id="FC1", name="Monitoring", source="G", target="M"),
        Contract(id="FC2", name="Alert delivery", source="G", target="A"),
    )
    baseline = Hypothesis(id="declared", attack_edges=attack, function_edges=functions, contracts=contracts)
    base = Snapshot(
        id="separable", title="احتواء مع استمرار الوظائف",
        description="مساران للهجوم، ووظيفتا مراقبة وتنبيه مستقلتان عنهما.",
        nodes=("G", "X", "P", "M", "A"), attack_sources=("G",), protected_targets=("P",),
        actions=(
            Action(id="a", label="Block G–P", cost=1, blocks=(attack[0],)),
            Action(id="b", label="Block G–X", cost=1, blocks=(attack[1],)),
            Action(id="c", label="Isolate G", cost=1, blocks=(attack[0], attack[1], *functions)),
            Action(id="d", label="Block X–P", cost=2, blocks=(attack[2],)),
        ), hypotheses=(baseline,),
    )
    shared = baseline.model_copy(update={
        "function_edges": (*functions, attack[0]),
        "contracts": (*contracts, Contract(id="FC3", name="Shared critical channel", source="G", target="P")),
    })
    alternative = baseline.model_copy(update={
        "id": "relay-is-critical", "function_edges": (*functions, attack[1]),
        "contracts": (*contracts, Contract(id="FC3", name="Relay dependency", source="G", target="X")),
    })
    late = baseline.model_copy(update={"contracts": (
        contracts[0], contracts[1].model_copy(update={"observed_latencies_s": (0.1, 0.1, 2.5)})
    )})
    variants = [base,
        base.model_copy(update={"id": "shared-channel", "title": "تعارض لا يسمح بالاحتواء", "description": "القناة G–P مطلوبة للهجوم ووظيفة حرجة معًا؛ لا حل ضمن الإجراءات المحددة.", "hypotheses": (shared,)}),
        base.model_copy(update={"id": "bounded-dependency", "title": "اعتماد إضافي معلوم", "description": "تُفحص فرضيتان؛ قد تكون G–X حرجة، فيلزم اختيار مختلف.", "hypotheses": (baseline, alternative)}),
        base.model_copy(update={"id": "unknown-evidence", "title": "أدلة غير مكتملة", "description": "الاعتمادات غير محصورة؛ النتيجة UNKNOWN ولا يُنفّذ احتواء آلي.", "evidence_complete": False}),
        base.model_copy(update={"id": "late-alert", "title": "تنبيه يتجاوز حد الوظيفة", "description": "تنبيه اصطناعي واحد يتأخر 2.5 ثانية؛ المتوسط لا يخفي فشله.", "hypotheses": (late,)}),
        base.model_copy(update={"id": "unavailable-action", "title": "إجراء غير قابل للتنفيذ", "description": "الإجراء b غير متاح للمحاكي؛ ابحث عن بديل قابل للتطبيق.", "actions": tuple(a.model_copy(update={"enforceable": False}) if a.id == "b" else a for a in base.actions)}),
    ]
    return {item.id: item for item in variants}
