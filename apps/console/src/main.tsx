import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { EngineConsole } from "./EngineConsole";

type Edge = { source: string; target: string };
type Scenario = {
  id: string;
  title: string;
  description: string;
  hypotheses: { attack_edges: Edge[]; function_edges: Edge[] }[];
  actions: { id: string; blocks: Edge[] }[];
};
type Artifact = {
  id: string;
  roots: Record<string, number>;
  parents: string[];
  status: string;
};
type Disclosure = {
  id: string;
  payload_hash: string;
  status: string;
  reason: string | null;
  payload?: string;
};
type Run = {
  id: string;
  version: number;
  mode: string;
  scenario: string;
  policy: string;
  snapshot: Scenario;
  plan: {
    status: string;
    actions: string[];
    cost: number;
    examined: number;
    feasible_count: number;
    reason: string;
  };
  validation: {
    accepted: boolean;
    reasons: string[];
    attack_blocked: boolean;
    contracts: Record<string, boolean | null>;
  };
  enforcement: string;
  artifacts: Artifact[];
  roots: Record<string, { status: string; version: number }>;
  events: {
    seq: number;
    at: string;
    kind: string;
    details: Record<string, unknown>;
  }[];
  disclosures: Record<string, Disclosure>;
  command_result?: { status?: string; reason?: string; request?: Disclosure };
};

function App() {
  const [token, setToken] = useState("");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenario, setScenario] = useState("separable");
  const [policy, setPolicy] = useState("mfsc");
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [artifact, setArtifact] = useState("T2");
  const [extra, setExtra] = useState("");
  const [disclosure, setDisclosure] = useState<Disclosure | null>(null);
  const [notice, setNotice] = useState("");
  const [english, setEnglish] = useState(false);
  const t = (ar: string, en: string) => (english ? en : ar);
  async function api(path: string, body?: unknown) {
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body === undefined
          ? {}
          : {
              "Content-Type": "application/json",
              "Idempotency-Key": crypto.randomUUID(),
            }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail),
      );
    return data;
  }
  async function act(operation: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await operation();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function command(action: string, body: Record<string, unknown> = {}) {
    if (!run) return;
    const result: Run = await api(`/v1/demo/runs/${run.id}/${action}`, {
      expected_version: run.version,
      ...body,
    });
    setRun(result);
    if (result.command_result?.request)
      setDisclosure(result.command_result.request);
    if (result.command_result?.status)
      setNotice(
        `${result.command_result.status}${result.command_result.reason ? ` · ${result.command_result.reason}` : ""}`,
      );
    if (
      !result.command_result?.request &&
      disclosure &&
      result.disclosures[disclosure.id]
    ) {
      const current = result.disclosures[disclosure.id];
      setDisclosure({
        ...disclosure,
        ...current,
        payload: current.status === "BLOCKED" ? undefined : disclosure.payload,
      });
    }
  }
  function exportRun() {
    if (!run) return;
    const blob = new Blob([JSON.stringify(run, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `withaq-${run.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }
  const selected = scenarios.find((s) => s.id === scenario);
  return (
    <div className="shell" dir={english ? "ltr" : "rtl"}>
      <header>
        <a className="brand" href="/" aria-label="WITHAQ home">
          <span className="brand-mark">و</span>
          <span>
            وثاق <small>WITHAQ</small>
          </span>
        </a>
        <div className="header-end">
          <span className="badge">{t("مختبر وثاق", "WITHAQ lab")} · v0.2</span>
          <button className="quiet" onClick={() => setEnglish(!english)}>
            {english ? "العربية" : "English"}
          </button>
          <a
            href="https://github.com/whyKaiser/withaq"
            target="_blank"
            rel="noreferrer"
          >
            GitHub ↗
          </a>
        </div>
      </header>
      <section className="hero">
        <div>
          <p className="eyebrow">CONTAIN · VERIFY · RECOVER</p>
          <h1>
            {t(
              "احمِ الوظيفة. واضبط أثر البيانات.",
              "Protect the function. Govern the data.",
            )}
          </h1>
          <p>
            {t(
              "استكشف كيف يختار وثاق احتواء الحادث، ويتحقق من كل وظيفة حرجة، ثم يمنع استخدام المصدر المسحوب ويعيد البناء من بديل مسموح.",
              "Explore bounded containment, independent checks, source revocation and recovery from approved alternatives.",
            )}
          </p>
        </div>
        <div className="mode-note">
          <strong>{t("محاكاة قابلة للفحص", "Inspectable simulation")}</strong>
          <span>
            {t(
              "بيانات اصطناعية فقط. قياس الحزم في مختبر معزول عند تفعيله؛ دون تعديل شبكة المضيف أو إرسال لمزود خارجي. الرسم لا يثبت صحة قراءة الحساس.",
              "Synthetic data only. Optional isolated packet trials; no host network changes or external sends. Graph connectivity does not establish sensor truth.",
            )}
          </span>
        </div>
      </section>
      {!scenarios.length ? (
        <section className="panel login">
          <p className="eyebrow">LOCAL DEVELOPMENT</p>
          <h2>{t("الدخول إلى المختبر", "Enter the lab")}</h2>
          <p>
            {t(
              "انسخ رمز التشغيل من data/local-access.txt. يبقى الرمز في ذاكرة هذه الصفحة فقط.",
              "Copy the operator token from data/local-access.txt. It stays only in this page’s memory.",
            )}
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void act(async () => setScenarios(await api("/v1/scenarios")));
            }}
          >
            <label htmlFor="token">
              {t("رمز التشغيل المحلي", "Local operator token")}
            </label>
            <div className="inline">
              <input
                id="token"
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="off"
                required
              />
              <button disabled={busy || !token}>{t("دخول", "Enter")}</button>
            </div>
          </form>
        </section>
      ) : (
        <>
          <EngineConsole token={token} english={english} />
          <div className="sandbox-heading">
            <p className="eyebrow">FINITE MODEL EXPLORER</p>
            <h2>
              {t("استكشاف المثال العلمي", "Explore the scientific model")}
            </h2>
            <p>
              {t(
                "الأداة التالية تشرح السيناريوهات المحددة بصورة تفاعلية؛ المحرك التشغيلي أعلاه يحفظ المهام والبيانات العامة.",
                "The explorer below explains bounded scenarios interactively; the operational engine above persists general state and jobs.",
              )}
            </p>
          </div>
          <section className="panel controls">
            <div>
              <label htmlFor="scenario">
                {t("01 / سيناريو الحادث", "01 / Incident scenario")}
              </label>
              <select
                id="scenario"
                disabled={busy}
                value={scenario}
                onChange={(e) => setScenario(e.target.value)}
              >
                {scenarios.map((s) => (
                  <option key={s.id} value={s.id}>
                    {english ? s.id : s.title}
                  </option>
                ))}
              </select>
              <p className="muted">
                {english ? selected?.id : selected?.description}
              </p>
            </div>
            <div>
              <label htmlFor="policy">
                {t("سياسة الاستجابة", "Response policy")}
              </label>
              <select
                id="policy"
                value={policy}
                disabled={busy}
                onChange={(e) => setPolicy(e.target.value)}
              >
                <option value="mfsc">WITHAQ / MFSC</option>
                <option value="quarantine">
                  {t("عزل كامل — للمقارنة", "Full quarantine — comparison")}
                </option>
                <option value="single-block">
                  {t(
                    "حجب مسار واحد — للمقارنة",
                    "Single-path block — comparison",
                  )}
                </option>
              </select>
            </div>
            <button
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  setRun(await api("/v1/demo/runs", { scenario, policy }));
                  setDisclosure(null);
                })
              }
            >
              {busy
                ? t("جارٍ الحساب…", "Computing…")
                : t("إنشاء تجربة", "Create experiment")}
            </button>
          </section>
          {run && (
            <>
              <div className="section-heading">
                <h2>
                  {t("02 / القرار والتحقق", "02 / Decision and validation")}
                </h2>
                <button className="quiet" disabled={busy} onClick={exportRun}>
                  {t("تصدير الدليل JSON", "Export JSON evidence")}
                </button>
              </div>
              <div className="metrics">
                <div>
                  <span>{t("حالة البحث", "Solver status")}</span>
                  <strong>{run.plan.status}</strong>
                </div>
                <div>
                  <span>{t("الإجراءات المختارة", "Selected actions")}</span>
                  <strong>{run.plan.actions.join(" + ") || "—"}</strong>
                </div>
                <div>
                  <span>{t("الكلفة في النموذج", "Model cost")}</span>
                  <strong>
                    {["OPTIMAL", "FEASIBLE"].includes(run.plan.status)
                      ? run.plan.cost
                      : "—"}
                  </strong>
                </div>
                <div>
                  <span>{t("المرشحون المفحوصون", "Candidates checked")}</span>
                  <strong>{run.plan.examined}</strong>
                </div>
              </div>
              <div className="two-columns">
                <section className="panel graph-panel">
                  <div className="panel-heading">
                    <h3>
                      {t("مسارات الهجوم والوظائف", "Attack and function paths")}
                    </h3>
                    <span className="badge">
                      {run.enforcement === "SIMULATED_CONFIRMED"
                        ? "APPLIED · SIMULATED"
                        : "MODEL"}
                    </span>
                  </div>
                  <Graph run={run} />
                  <p className="legend">
                    <span className="red-dot" />
                    {t("مسار هجوم", "Attack path")}
                    <span className="green-dot" />
                    {t("وظيفة مطلوبة", "Required function")}
                    <span>
                      ×{" "}
                      {t("حجب محاكى بعد التطبيق", "Simulated deny after apply")}
                    </span>
                  </p>
                </section>
                <section className="panel">
                  <h3>
                    {t(
                      "تحقق مستقل لكل وظيفة",
                      "Independent per-function validation",
                    )}
                  </h3>
                  <p
                    className={
                      run.validation.accepted ? "verdict good" : "verdict bad"
                    }
                  >
                    {run.validation.accepted
                      ? t(
                          "مقبول داخل النموذج المحدد",
                          "Accepted within this model",
                        )
                      : t("مرفوض أو غير محسوم", "Rejected or unknown")}
                  </p>
                  <div className="contract">
                    <span>
                      {t(
                        "الوصول إلى الهدف المحمي داخل النموذج",
                        "Protected-target reachability in this model",
                      )}
                    </span>
                    <span
                      className={
                        run.validation.attack_blocked
                          ? "status active"
                          : "status revoked"
                      }
                    >
                      {run.validation.attack_blocked ? "BLOCKED" : "REACHABLE"}
                    </span>
                  </div>
                  {Object.entries(run.validation.contracts).map(
                    ([id, pass]) => (
                      <div className="contract" key={id}>
                        <code>{id}</code>
                        <span
                          className={pass ? "status active" : "status held"}
                        >
                          {pass ? "PASS" : pass === null ? "UNKNOWN" : "FAIL"}
                        </span>
                      </div>
                    ),
                  )}
                  <p className="muted">
                    {t(
                      "الفحص يستخدم أدلة اصطناعية معلنة؛ لا يمثل قياسات حزم شبكة حقيقية.",
                      "Checks use declared synthetic evidence, not real packet measurements.",
                    )}
                  </p>
                  <details>
                    <summary>{t("أسباب القرار", "Decision reasons")}</summary>
                    <p dir="ltr">{run.plan.reason}</p>
                    <ul dir="ltr">
                      {run.validation.reasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  </details>
                  <button
                    disabled={
                      busy ||
                      !run.validation.accepted ||
                      run.enforcement === "SIMULATED_CONFIRMED"
                    }
                    onClick={() => void act(() => command("apply"))}
                  >
                    {t(
                      "اعتماد وتطبيق داخل المحاكاة",
                      "Authorize simulated application",
                    )}
                  </button>
                </section>
              </div>
              <div className="section-heading">
                <h2>
                  {t(
                    "03 / أثر المصدر والاستعادة",
                    "03 / Source impact and recovery",
                  )}
                </h2>
                <span className="badge">MAHW</span>
              </div>
              <section className="panel">
                <div className="roots">
                  {Object.entries(run.roots).map(([id, r]) => (
                    <div key={id}>
                      <strong>{id}</strong>
                      <span
                        className={`status ${r.status === "ACTIVE" ? "active" : "revoked"}`}
                      >
                        {r.status}
                      </span>
                      <small>v{r.version}</small>
                    </div>
                  ))}
                </div>
                <div className="artifact-grid">
                  {run.artifacts.map((a) => (
                    <article key={a.id}>
                      <div>
                        <h3>{a.id}</h3>
                        <span className={`status ${a.status.toLowerCase()}`}>
                          {a.status}
                        </span>
                      </div>
                      <p>
                        {t("المصادر", "Roots")}:{" "}
                        {Object.keys(a.roots).join(", ") ||
                          t("غير مثبتة", "Unknown")}
                      </p>
                      <small>
                        {a.parents.length
                          ? `${t("مشتق من", "Derived from")}: ${a.parents.join(", ")}`
                          : t(
                              "مصدر مستقل أو غير مثبت",
                              "Independent or unknown lineage",
                            )}
                      </small>
                    </article>
                  ))}
                </div>
                <div className="actions">
                  <button
                    className="danger"
                    disabled={busy || run.roots.S1.status === "REVOKED"}
                    onClick={() => void act(() => command("revoke"))}
                  >
                    {t("سحب صلاحية S1", "Revoke S1")}
                  </button>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => void act(() => command("complete-late"))}
                  >
                    {t("فحص نتيجة معالجة متأخرة", "Check late model result")}
                  </button>
                  <button
                    disabled={
                      busy ||
                      run.roots.S1.status !== "REVOKED" ||
                      run.artifacts.some((a) => a.id === "T2b")
                    }
                    onClick={() => void act(() => command("recover"))}
                  >
                    {t("إعادة بناء T2b من S2", "Rebuild T2b from S2")}
                  </button>
                </div>
                <p className="muted">
                  {t(
                    "السحب يمنع الاستخدام الجديد؛ لا يسترجع بيانات سبق إرسالها. C-D يبقى معلقًا لأن سلسلة مصادره غير مثبتة.",
                    "Revocation blocks new use; it cannot recall previously sent bytes. C-D stays held because its lineage is unknown.",
                  )}
                </p>
              </section>
              <div className="section-heading">
                <h2>{t("04 / بوابة الإفصاح", "04 / Disclosure gateway")}</h2>
                <span className="badge">MOCK PROVIDER</span>
              </div>
              <section className="panel">
                <div className="disclosure-form">
                  <div>
                    <label htmlFor="artifact">{t("المخرج", "Artifact")}</label>
                    <select
                      id="artifact"
                      value={artifact}
                      onChange={(e) => setArtifact(e.target.value)}
                    >
                      {run.artifacts.map((a) => (
                        <option key={a.id}>{a.id}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="extra">
                      {t(
                        "نص اصطناعي إضافي للفحص",
                        "Extra synthetic text for inspection",
                      )}
                    </label>
                    <input
                      id="extra"
                      placeholder="national_id=TEST"
                      value={extra}
                      onChange={(e) => setExtra(e.target.value)}
                    />
                  </div>
                  <button
                    disabled={busy}
                    onClick={() =>
                      void act(() =>
                        command("inspect", { artifact, extra_text: extra }),
                      )
                    }
                  >
                    {t("فحص قبل الإفصاح", "Inspect disclosure")}
                  </button>
                </div>
                <p className="muted" dir="ltr">
                  mock://review · account: demo · purpose: competition-demo
                </p>
                {disclosure && (
                  <div className="disclosure-result">
                    <strong>{disclosure.status}</strong>
                    <p>
                      {disclosure.reason ||
                        t(
                          "يتطلب اعتماد نفس المحتوى والوجهة والغرض.",
                          "Approval is bound to identical bytes, destination and purpose.",
                        )}
                    </p>
                    {disclosure.payload && <pre>{disclosure.payload}</pre>}
                    <code className="hash">
                      SHA-256: {disclosure.payload_hash}
                    </code>
                    <div className="actions">
                      <button
                        disabled={
                          busy || disclosure.status !== "REVIEW_REQUIRED"
                        }
                        onClick={() =>
                          void act(() =>
                            command("egress/approve", {
                              request_id: disclosure.id,
                              payload_hash: disclosure.payload_hash,
                            }),
                          )
                        }
                      >
                        {t("اعتماد المحتوى المعروض", "Approve displayed bytes")}
                      </button>
                      <button
                        disabled={busy || disclosure.status !== "APPROVED"}
                        onClick={() =>
                          void act(() =>
                            command("egress/dispatch", {
                              request_id: disclosure.id,
                              payload_hash: disclosure.payload_hash,
                            }),
                          )
                        }
                      >
                        {t("إرسال محاكى", "Simulate dispatch")}
                      </button>
                      <button
                        className="secondary"
                        disabled={busy || disclosure.status !== "APPROVED"}
                        onClick={() =>
                          void act(() =>
                            command("egress/dispatch", {
                              request_id: disclosure.id,
                              payload_hash: disclosure.payload_hash,
                              lose_response: true,
                            }),
                          )
                        }
                      >
                        {t("محاكاة فقد الرد", "Simulate lost response")}
                      </button>
                    </div>
                  </div>
                )}
              </section>
              <div className="section-heading">
                <h2>{t("05 / سجل الأدلة", "05 / Evidence trace")}</h2>
                <span className="mono">
                  {run.id.slice(0, 8)} · v{run.version}
                </span>
              </div>
              <section className="panel">
                <ol className="timeline">
                  {[...run.events].reverse().map((e) => (
                    <li key={e.seq}>
                      <span className="sequence">
                        {String(e.seq).padStart(2, "0")}
                      </span>
                      <div>
                        <strong>{e.kind}</strong>
                        <p>{JSON.stringify(e.details)}</p>
                      </div>
                      <time>
                        {new Date(e.at).toLocaleTimeString(
                          english ? "en-GB" : "ar-SA",
                        )}
                      </time>
                    </li>
                  ))}
                </ol>
              </section>
            </>
          )}
        </>
      )}
      {error && (
        <div className="toast error" role="alert">
          <strong>{t("لم تكتمل العملية", "Operation rejected")}</strong>
          <span dir="ltr">{error}</span>
          <button className="quiet" onClick={() => setError("")}>
            ×
          </button>
        </div>
      )}
      {notice && (
        <div className="toast" role="status">
          <span dir="ltr">{notice}</span>
          <button className="quiet" onClick={() => setNotice("")}>
            ×
          </button>
        </div>
      )}
      <footer>
        <strong>WITHAQ / وثاق</strong>
        <span>
          {t(
            "نموذج برمجي تجريبي · ليس نظام تشغيل أمني معتمدًا",
            "Experimental software prototype · not a certified security system",
          )}
        </span>
        <a href="https://github.com/whyKaiser/withaq/tree/main/vault">
          {t("سياق المشروع وخطة الفريق", "Project context and team plan")} ↗
        </a>
      </footer>
    </div>
  );
}

function Graph({ run }: { run: Run }) {
  const positions: Record<string, [number, number]> = {
    G: [80, 140],
    X: [275, 50],
    P: [475, 140],
    M: [205, 270],
    A: [405, 270],
  };
  const hypothesis = run.snapshot.hypotheses[0];
  const denied =
    run.enforcement === "SIMULATED_CONFIRMED"
      ? run.snapshot.actions
          .filter((a) => run.plan.actions.includes(a.id))
          .flatMap((a) => a.blocks)
      : [];
  const edges = [
    ...hypothesis.attack_edges.map((e) => ({ ...e, attack: true })),
    ...hypothesis.function_edges.map((e) => ({ ...e, attack: false })),
  ];
  return (
    <svg
      className="network"
      viewBox="0 0 560 340"
      role="img"
      aria-label="Synthetic network: gateway, relay, protected target, monitor and alerts"
    >
      <defs>
        <marker
          id="arrow"
          markerWidth="7"
          markerHeight="7"
          refX="5"
          refY="3.5"
          orient="auto"
        >
          <path d="M0,0 L7,3.5 L0,7" fill="context-stroke" />
        </marker>
      </defs>
      {edges.map((e, i) => {
        const a = positions[e.source],
          b = positions[e.target];
        const blocked = denied.some(
          (d) => d.source === e.source && d.target === e.target,
        );
        return (
          <g key={i}>
            <line
              x1={a[0]}
              y1={a[1]}
              x2={b[0]}
              y2={b[1]}
              stroke={e.attack ? "#c76551" : "#2b8478"}
              strokeWidth="2"
              strokeDasharray={blocked ? "3 7" : e.attack ? "8 5" : undefined}
              opacity={blocked ? 0.45 : 1}
              markerEnd="url(#arrow)"
            />
            {blocked && (
              <text
                x={(a[0] + b[0]) / 2}
                y={(a[1] + b[1]) / 2 - 10}
                textAnchor="middle"
                fill="#b04f3d"
                fontSize="25"
              >
                ×
              </text>
            )}
          </g>
        );
      })}
      {Object.entries(positions).map(([id, [x, y]]) => (
        <g key={id}>
          <rect
            x={x - 48}
            y={y - 28}
            width="96"
            height="62"
            rx="12"
            fill={id === "P" ? "#fcebe5" : "#e4f0ea"}
            stroke={id === "P" ? "#e0aa9c" : "#bfd4cc"}
          />
          <text
            x={x}
            y={y - 3}
            textAnchor="middle"
            fontSize="20"
            fontWeight="700"
            fill="#143f3b"
          >
            {id}
          </text>
          <text
            x={x}
            y={y + 18}
            textAnchor="middle"
            fontSize="11"
            fill="#45675f"
          >
            {
              {
                G: "Gateway",
                X: "Relay",
                P: "Protected",
                M: "Monitor",
                A: "Alerts",
              }[id]
            }
          </text>
        </g>
      ))}
    </svg>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
