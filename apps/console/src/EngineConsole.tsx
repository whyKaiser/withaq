import { useCallback, useEffect, useState } from "react";

const checkLabels: Record<string, [string, string]> = {
  attack_paths_exist_before: [
    "وجود مسارات الهجوم قبل الاحتواء",
    "Attack paths present before containment",
  ],
  relay_reaches_protected_before: [
    "وصول المسار الوسيط قبل الاحتواء",
    "Relay reaches protected target before containment",
  ],
  direct_and_relay_blocked_after: [
    "حجب المسارين المباشر والوسيط",
    "Direct and relay paths blocked",
  ],
  existing_session_blocked: [
    "حجب الاتصال القائم قبل الاحتواء",
    "Previously established session blocked",
  ],
  each_monitor_and_alert_event_under_2s: [
    "كل عينة مراقبة وتنبيه ضمن ثانيتين",
    "Every monitor and alert sample within two seconds",
  ],
  controller_absence_keeps_denies: [
    "استمرار الحجب بعد انتهاء مُثبّت القواعد",
    "Denies retained after rule installer exits",
  ],
  quarantine_breaks_functions: [
    "المقارنة: العزل الكامل يوقف الوظائف",
    "Comparison: full quarantine interrupts functions",
  ],
  no_alternate_client_interface: [
    "لا واجهة بديلة للعميل تتجاوز نقطة الإنفاذ",
    "No alternate client interface bypasses the PEP",
  ],
};

type Root = { id: string; label: string; status: string; version: number };
type Artifact = {
  id: string;
  label: string;
  status: string;
  hash: string;
  roots: Record<string, number>;
  parents: string[];
};
type Egress = {
  id: string;
  status: string;
  decision: string;
  reason: string | null;
  binding_hash: string;
  binding: {
    payload_hash: string;
    destination: string;
    account: string;
    purpose: string;
    roots: Record<string, number>;
  };
};
type Plan = {
  id: string;
  status: string;
  candidate: { actions: string[]; cost: number; examined: number } | null;
};
type State = {
  version: number;
  database: string;
  schema: string;
  roots: Root[];
  artifacts: Artifact[];
  plans: Plan[];
  reports: {
    plan_id: string;
    verdict: {
      accepted: boolean;
      reasons: string[];
      contracts: Record<string, boolean | null>;
    };
  }[];
  enforcements: {
    id: string;
    plan_id: string;
    status: string;
    result: {
      receipt?: {
        contracts: Record<string, boolean>;
        evidence: { checks: Record<string, boolean> };
      };
    } | null;
  }[];
  runs: {
    id: string;
    label: string;
    status: string;
    output_id: string | null;
    reason: string | null;
  }[];
  manifests: {
    id: string;
    hash: string;
    sealed: {
      inputs: { artifact_id: string; role: string }[];
      roots: Record<string, number>;
    };
  }[];
  egress: Egress[];
  jobs: {
    id: string;
    kind: string;
    state: string;
    fence: number;
    created_at: number;
  }[];
  events: {
    id: string;
    kind: string;
    at: number;
    details: Record<string, unknown>;
  }[];
};

export function EngineConsole({
  token,
  english,
}: {
  token: string;
  english: boolean;
}) {
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [label, setLabel] = useState("مصدر اصطناعي");
  const [payload, setPayload] = useState(
    "Synthetic temperature reading 23.4 C. Approved test data only.",
  );
  const [input, setInput] = useState("");
  const [role, setRole] = useState("source");
  const [replacement, setReplacement] = useState("");
  const [destination, setDestination] = useState("mock://review");
  const [scenario, setScenario] = useState("separable");
  const [delay, setDelay] = useState(false);
  const [packets, setPackets] = useState(false);
  const [adapter, setAdapter] = useState("simulation");
  const [bytes, setBytes] = useState<{
    id: string;
    kind: "artifact" | "egress";
    value: string;
  } | null>(null);
  const t = (ar: string, en: string) => (english ? en : ar);
  const api = useCallback(
    async (path: string, body?: unknown) => {
      const response = await fetch(path, {
        method: body === undefined ? "GET" : "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "X-Withaq-Demo": "1",
          ...(body === undefined
            ? {}
            : {
                "Content-Type": "application/json",
                "Idempotency-Key": crypto.randomUUID(),
              }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : JSON.stringify(result.detail),
        );
      return result;
    },
    [token],
  );
  const refresh = useCallback(async () => {
    setState(await api("/v1/state"));
  }, [api]);
  useEffect(() => {
    let active = true;
    void api("/v1/capabilities")
      .then((value) => {
        if (active) {
          setPackets(value.packet_lab_configured);
          setAdapter(value.packet_lab_configured ? "packet-lab" : "simulation");
        }
      })
      .catch(() => {});
    const poll = async () => {
      try {
        const value = await api("/v1/state");
        if (active) {
          setState(value);
          setConnectionError("");
        }
      } catch (e) {
        if (active)
          setConnectionError(e instanceof Error ? e.message : String(e));
      }
    };
    void poll();
    const interval = window.setInterval(() => {
      void poll();
    }, 2000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [api]);
  useEffect(() => {
    if (!bytes || !state) return;
    const current =
      bytes.kind === "artifact"
        ? state.artifacts.find((a) => a.id === bytes.id)
        : state.egress.find((a) => a.id === bytes.id);
    if (!current || ["REVOKED", "HELD", "BLOCKED"].includes(current.status))
      setBytes(null);
  }, [state, bytes]);
  async function action(operation: () => Promise<void>) {
    setBusy(true);
    setError("");
    setBytes(null);
    try {
      await operation();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      await refresh().catch(() => {});
    } finally {
      setBusy(false);
    }
  }
  async function mutate(path: string, body: Record<string, unknown> = {}) {
    // Read the current shared revision before a mutation. Server still rejects intervening writes.
    const current: State = await api("/v1/state");
    return api(path, { expected_version: current.version, ...body });
  }
  async function seed() {
    const s1 = await mutate("/v1/roots", { label: "S1 · compromised batch" });
    const s2 = await mutate("/v1/roots", {
      label: "S2 · independent alternative",
    });
    const s3 = await mutate("/v1/roots", { label: "S3 · independent report" });
    const a = await mutate("/v1/artifacts", {
      label: "T1 · monitoring input",
      payload:
        "Synthetic monitoring batch S1: temperature 23.4 C; alert sample A001.",
      root_ids: [s1.id],
    });
    await mutate("/v1/artifacts", {
      label: "S2 · approved rebuild input",
      payload:
        "Independent synthetic batch S2: temperature 23.6 C; alert sample B001.",
      root_ids: [s2.id],
    });
    await mutate("/v1/artifacts", {
      label: "T3 · independent report",
      payload: "Independent synthetic report S3 remains authorized.",
      root_ids: [s3.id],
    });
    await mutate("/v1/artifacts", {
      label: "C-D · unknown lineage",
      payload: "Synthetic unproven source; must remain held.",
    });
    await mutate("/v1/runs", {
      label: "T2 · derived summary",
      inputs: [{ artifact_id: a.id, role: "source" }],
    });
    setInput(a.id);
  }
  async function incident() {
    const scenarios: { id: string; hypotheses: { contracts: unknown[] }[] }[] =
      await api("/v1/scenarios");
    const spec = scenarios.find((s) => s.id === scenario);
    if (!spec) return;
    const device = await mutate("/v1/devices", {
      label: "G · simulated IoT gateway",
      kind: "simulated-gateway",
    });
    for (const contract of spec.hypotheses[0].contracts)
      await mutate("/v1/contracts", { spec: contract });
    const snapshot = await mutate("/v1/snapshots", { spec });
    const created = await mutate("/v1/incidents", {
      device_id: device.id,
      snapshot_id: snapshot.id,
      evidence: { mode: "synthetic", scenario },
    });
    await mutate("/v1/plans", {
      incident_id: created.id,
      snapshot_id: snapshot.id,
    });
  }
  function exportEvidence() {
    if (!state) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(state, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `withaq-engine-v${state.version}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }
  const activeArtifacts =
    state?.artifacts.filter((a) => a.status === "ACTIVE") ?? [];
  const revokedArtifacts =
    state?.artifacts.filter((a) => a.status === "REVOKED") ?? [];
  const tone = (status: string) =>
    [
      "ACTIVE",
      "PUBLISHED",
      "DONE",
      "MOCK_SENT",
      "OPTIMAL",
      "SIMULATED_CONFIRMED",
      "LAB_CONFIRMED",
    ].includes(status)
      ? "pass"
      : ["REVOKED", "REJECTED", "FAILED", "BLOCKED", "INFEASIBLE"].includes(
            status,
          )
        ? "fail"
        : "pending";
  return (
    <section
      className="engine-console"
      aria-label={t("محرك وثاق التشغيلي", "WITHAQ operational engine")}
    >
      <div className="panel engine-heading">
        <div>
          <p className="eyebrow">
            AUTHORITATIVE STATE · DURABLE JOBS · SEALED LINEAGE
          </p>
          <h2>{t("محرك وثاق التشغيلي", "WITHAQ operational engine")}</h2>
          <p>
            {t(
              "مصادر ومخرجات داخل المختبر، مهام منفصلة، وحراس للنسخ الحالية. توليد المحتوى والمزود محاكاة؛ قياس حزم حقيقية متاح في المختبر المعزول عند تفعيله.",
              "Persistent lab state, separate jobs and current-version guards. Content and provider adapters are mock; real packet measurements are available in the isolated lab when enabled.",
            )}
          </p>
        </div>
        <div className="engine-actions">
          <span className="badge">
            {state
              ? `${state.database} · schema ${state.schema} · v${state.version}`
              : t("اتصال…", "Connecting…")}
          </span>
          <button disabled={busy || !state} onClick={() => void action(seed)}>
            {t("إنشاء تجربة كاملة", "Create full experiment")}
          </button>
          <button className="quiet" disabled={!state} onClick={exportEvidence}>
            {t("تنزيل دليل الحالة", "Export state evidence")}
          </button>
        </div>
      </div>
      {connectionError && (
        <div role="alert" className="message error">
          {t(
            "انقطع الاتصال بالمحرك؛ البيانات المعروضة آخر حالة مقروءة.",
            "Engine connection lost; displayed data is the last successful read.",
          )}{" "}
          {connectionError}
        </div>
      )}
      {error && (
        <div role="alert" className="message error">
          {error}{" "}
          {error === "STALE_SNAPSHOT" &&
            t(
              "حدّثنا الحالة المشتركة؛ أعد الإجراء بعد مراجعتها.",
              "Shared state refreshed. Review it before retrying.",
            )}
        </div>
      )}
      {state && (
        <>
          <div className="metrics">
            <article>
              <span>{t("مصادر مسموحة", "Active roots")}</span>
              <strong>
                {state.roots.filter((r) => r.status === "ACTIVE").length}
              </strong>
            </article>
            <article>
              <span>{t("مخرجات مسموحة", "Active artifacts")}</span>
              <strong>{activeArtifacts.length}</strong>
            </article>
            <article>
              <span>{t("مهام معلّقة", "Pending jobs")}</span>
              <strong>
                {
                  state.jobs.filter((j) =>
                    ["QUEUED", "LEASED"].includes(j.state),
                  ).length
                }
              </strong>
            </article>
            <article>
              <span>{t("حواجز سحب", "Revocation barriers")}</span>
              <strong>
                {state.roots.filter((r) => r.status === "REVOKED").length}
              </strong>
            </article>
          </div>
          <div className="engine-grid">
            <section className="panel">
              <p className="eyebrow">01 / FUNCTION-SAFE CONTAINMENT</p>
              <h3>
                {t(
                  "حادث وخطة ومتحقق مستقل",
                  "Incident, plan and independent validator",
                )}
              </h3>
              <label htmlFor="engine-scenario">
                {t("نموذج الحادث", "Incident model")}
              </label>
              <select
                id="engine-scenario"
                value={scenario}
                onChange={(e) => setScenario(e.target.value)}
              >
                {[
                  "separable",
                  "shared-channel",
                  "bounded-dependency",
                  "unknown-evidence",
                  "late-alert",
                  "unavailable-action",
                ].map((id) => (
                  <option key={id}>{id}</option>
                ))}
              </select>
              <button disabled={busy} onClick={() => void action(incident)}>
                {t("سجّل الحادث واطلب خطة", "Record incident and request plan")}
              </button>
              <label htmlFor="apply-adapter">
                {t("طريقة تطبيق الخطة", "Plan application adapter")}
              </label>
              <select
                id="apply-adapter"
                value={adapter}
                onChange={(e) => setAdapter(e.target.value)}
              >
                <option value="simulation">
                  {t("محاكاة القرار", "Decision simulation")}
                </option>
                <option value="packet-lab" disabled={!packets}>
                  {t(
                    "حزم فعلية في مختبر معزول",
                    "Real packets in isolated lab",
                  )}
                </option>
              </select>
              <p className="hint">
                {t(
                  "قياس الحزم يدعم نموذج G/X/P/M/A المحدد فقط. الانتظار لا يعني نجاح التطبيق.",
                  "Packet trials support the declared G/X/P/M/A model only. Queued work is not confirmed enforcement.",
                )}
              </p>
              <div className="record-list">
                {state.plans
                  .slice(-5)
                  .reverse()
                  .map((plan) => {
                    const report = state.reports.find(
                      (r) => r.plan_id === plan.id,
                    );
                    const applied = state.enforcements.find(
                      (e) => e.plan_id === plan.id,
                    );
                    return (
                      <article className="engine-record" key={plan.id}>
                        <span className={`status ${tone(plan.status)}`}>
                          {plan.status}
                        </span>
                        <code>{plan.id.slice(0, 8)}</code>
                        {plan.candidate && (
                          <p>
                            {t("الإجراءات", "Actions")}:{" "}
                            {plan.candidate.actions.join(" + ") || "∅"} ·{" "}
                            {t("الكلفة", "Cost")}:{" "}
                            {["OPTIMAL", "FEASIBLE"].includes(plan.status)
                              ? plan.candidate.cost
                              : "—"}{" "}
                            · {plan.candidate.examined}{" "}
                            {t("مجموعة مفحوصة", "sets examined")}
                          </p>
                        )}
                        {report && (
                          <>
                            <p
                              className={
                                report.verdict.accepted
                                  ? "pass-text"
                                  : "fail-text"
                              }
                            >
                              {report.verdict.accepted
                                ? t("المتحقق وافق", "Validator accepted")
                                : t("المتحقق رفض", "Validator rejected")}
                            </p>
                            {Object.entries(report.verdict.contracts).map(
                              ([id, pass]) => (
                                <p key={id}>
                                  <code>{id}</code> ·{" "}
                                  {pass === null
                                    ? "UNKNOWN"
                                    : pass
                                      ? "PASS"
                                      : "FAIL"}
                                </p>
                              ),
                            )}
                          </>
                        )}
                        {applied ? (
                          <>
                            <p className={`status ${tone(applied.status)}`}>
                              {applied.status}
                            </p>
                            {applied.result?.receipt && (
                              <>
                                <p>
                                  {t(
                                    "تجربة حزم مكتملة على أجهزة اصطناعية داخل حاوية مؤقتة؛ ليست سياسة شبكة مستمرة بعد انتهاء التجربة.",
                                    "Completed packet trial on synthetic devices in a disposable container; rules do not persist beyond the trial.",
                                  )}
                                </p>
                                {Object.entries(
                                  applied.result.receipt.contracts,
                                ).map(([id, pass]) => (
                                  <p key={id}>
                                    <code>{id}</code> ·{" "}
                                    {pass ? "MEASURED PASS" : "FAIL"}
                                  </p>
                                ))}
                                {Object.entries(
                                  applied.result.receipt.evidence.checks,
                                ).map(([id, pass]) => (
                                  <p key={id}>
                                    <span>
                                      {checkLabels[id]
                                        ? t(...checkLabels[id])
                                        : id}
                                    </span>{" "}
                                    ·{" "}
                                    {pass ? t("نجح", "PASS") : t("فشل", "FAIL")}
                                  </p>
                                ))}
                              </>
                            )}
                          </>
                        ) : (
                          <button
                            className="quiet"
                            disabled={busy || !report?.verdict.accepted}
                            onClick={() =>
                              void action(async () => {
                                await mutate(`/v1/plans/${plan.id}/apply`, {
                                  adapter,
                                });
                              })
                            }
                          >
                            {adapter === "packet-lab"
                              ? t(
                                  "تشغيل وقياس الحزم المعزولة",
                                  "Run and measure isolated packets",
                                )
                              : t("تطبيق داخل المحاكي", "Apply in simulator")}
                          </button>
                        )}
                      </article>
                    );
                  })}
              </div>
            </section>
            <section className="panel">
              <p className="eyebrow">02 / SOURCE AUTHORIZATION</p>
              <h3>
                {t(
                  "مصادر عامة وحواجز سحب",
                  "General roots and revocation barriers",
                )}
              </h3>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void action(async () => {
                    const root = await mutate("/v1/roots", { label });
                    const created = await mutate("/v1/artifacts", {
                      label,
                      payload,
                      root_ids: [root.id],
                    });
                    setInput(created.id);
                  });
                }}
              >
                <label htmlFor="source-label">
                  {t("اسم المصدر", "Source label")}
                </label>
                <input
                  id="source-label"
                  value={label}
                  maxLength={120}
                  required
                  onChange={(e) => setLabel(e.target.value)}
                />
                <label htmlFor="source-payload">
                  {t("محتوى اصطناعي فقط", "Synthetic content only")}
                </label>
                <textarea
                  id="source-payload"
                  value={payload}
                  maxLength={16384}
                  required
                  onChange={(e) => setPayload(e.target.value)}
                />
                <button disabled={busy}>
                  {t("إضافة مصدر ومخرج أصلي", "Add root and source artifact")}
                </button>
              </form>
              <div className="record-list">
                {state.roots
                  .slice(-12)
                  .reverse()
                  .map((root) => (
                    <article className="engine-record" key={root.id}>
                      <strong>{root.label}</strong>
                      <span className={`status ${tone(root.status)}`}>
                        {root.status} · v{root.version}
                      </span>
                      <code>{root.id.slice(0, 8)}</code>
                      <button
                        className="quiet"
                        disabled={busy || root.status !== "ACTIVE"}
                        onClick={() =>
                          void action(async () => {
                            await mutate(`/v1/roots/${root.id}/revoke`, {
                              reason:
                                "Synthetic incident: withdraw source authority",
                            });
                          })
                        }
                      >
                        {t("سحب المصدر", "Revoke root")}
                      </button>
                    </article>
                  ))}
              </div>
            </section>
          </div>
          <section className="panel">
            <p className="eyebrow">
              03 / COMPLETE MANIFEST · NEW IDENTITY RECOVERY
            </p>
            <h3>
              {t(
                "التوليد والاستعادة من بديل مستقل",
                "Generation and recovery from independent inputs",
              )}
            </h3>
            <div className="engine-form-grid">
              <div>
                <label htmlFor="engine-input">
                  {t("مدخل مسموح", "Authorized input")}
                </label>
                <select
                  id="engine-input"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                >
                  <option value="">
                    {t("اختر مخرجًا", "Select artifact")}
                  </option>
                  {activeArtifacts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.label} · {a.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="input-role">
                  {t("دور المدخل داخل السياق", "Context input role")}
                </label>
                <select
                  id="input-role"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                >
                  {["source", "system", "history", "tool"].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="replacement">
                  {t(
                    "استبدال مخرج مسحوب — اختياري",
                    "Replace revoked artifact — optional",
                  )}
                </label>
                <select
                  id="replacement"
                  value={replacement}
                  onChange={(e) => setReplacement(e.target.value)}
                >
                  <option value="">{t("توليد جديد", "New generation")}</option>
                  {revokedArtifacts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.label} · {a.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <label className="delay-toggle">
              <input
                type="checkbox"
                checked={delay}
                onChange={(e) => setDelay(e.target.checked)}
              />
              {t(
                "تأخير التوليد 5 ثوانٍ لاختبار السحب أثناء التنفيذ",
                "Delay generation 5 seconds to test mid-run revocation",
              )}
            </label>
            <button
              disabled={busy || !activeArtifacts.some((a) => a.id === input)}
              onClick={() =>
                void action(async () => {
                  await mutate("/v1/runs", {
                    label: replacement
                      ? "T2b · rebuilt from independent inputs"
                      : "Derived summary",
                    task: replacement ? "recovery" : "summary",
                    inputs: [{ artifact_id: input, role }],
                    replacement_for: replacement || null,
                    delay_s: delay ? 5 : 0,
                  });
                })
              }
            >
              {t("ختم المدخلات وتشغيل المهمة", "Seal inputs and start job")}
            </button>
            <p className="hint">
              {t(
                "كل مصدر يدخل المهمة يبقى في جذور المخرج. الاستعادة تنشئ هوية جديدة؛ المصدر المسحوب يبقى مسحوبًا. جودة المخرج هنا فحص حتمي لمحاكي المحتوى.",
                "Every input remains in the output’s roots. Recovery creates a new identity; revoked roots stay revoked. Output quality uses deterministic mock checks.",
              )}
            </p>
            <div className="record-list compact">
              {state.runs
                .slice(-6)
                .reverse()
                .map((run) => (
                  <article className="engine-record" key={run.id}>
                    <strong>{run.label}</strong>
                    <span className={`status ${tone(run.status)}`}>
                      {run.status}
                    </span>
                    {run.reason && <code>{run.reason}</code>}
                    {run.output_id && <code>{run.output_id.slice(0, 8)}</code>}
                  </article>
                ))}
            </div>
          </section>
          <section className="panel">
            <p className="eyebrow">
              04 / IMMUTABLE ARTIFACTS · CURRENT ROOT GUARDS
            </p>
            <h3>{t("التتبّع وحراسة القراءة", "Lineage and guarded reads")}</h3>
            <div className="artifact-grid">
              {state.artifacts
                .slice(-18)
                .reverse()
                .map((a) => (
                  <article className="engine-record" key={a.id}>
                    <strong>{a.label}</strong>
                    <span className={`status ${tone(a.status)}`}>
                      {a.status}
                    </span>
                    <code>{a.id.slice(0, 8)}</code>
                    <p>
                      {t("الجذور", "Roots")}:{" "}
                      {Object.entries(a.roots)
                        .map(
                          ([id, v]) =>
                            `${state.roots.find((r) => r.id === id)?.label ?? id.slice(0, 8)} @${v}`,
                        )
                        .join(", ") || "UNKNOWN"}
                    </p>
                    <p>
                      {t("الآباء", "Parents")}:{" "}
                      {a.parents.map((id) => id.slice(0, 8)).join(", ") || "∅"}
                    </p>
                    <button
                      className="quiet"
                      disabled={busy || a.status !== "ACTIVE"}
                      onClick={() =>
                        void action(async () => {
                          const value = await api(`/v1/artifacts/${a.id}`);
                          setBytes({
                            id: a.id,
                            kind: "artifact",
                            value: value.payload,
                          });
                        })
                      }
                    >
                      {t("قراءة عبر الحارس", "Read through guard")}
                    </button>
                  </article>
                ))}
            </div>
          </section>
          <section className="panel">
            <p className="eyebrow">05 / INSPECT · SANITIZE · APPROVE · ADMIT</p>
            <h3>
              {t("الإفصاح بأربع قرارات", "Four-decision disclosure policy")}
            </h3>
            <div className="inline">
              <select
                aria-label={t("وجهة الإفصاح", "Disclosure destination")}
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
              >
                <option>mock://review</option>
                <option>mock://local</option>
              </select>
              <button
                disabled={busy || !activeArtifacts.some((a) => a.id === input)}
                onClick={() =>
                  void action(async () => {
                    await mutate("/v1/egress/requests", {
                      artifact_id: input,
                      destination,
                      account: "demo",
                      purpose: "competition-demo",
                    });
                  })
                }
              >
                {t("فحص المدخل المختار أعلاه", "Inspect selected input above")}
              </button>
            </div>
            <p className="hint">
              {t(
                "فحص محلي محدد بالعربية والإنجليزية. إزالة معلومات الاتصال تُبقي جذور المصدر. الإرسال mock؛ صفر بايتات لمزود خارجي. القرار OUTCOME_UNKNOWN يمنع الإعادة العمياء.",
                "Bounded Arabic/English local checks. Contact sanitization retains roots. Mock sends contact no external provider. OUTCOME_UNKNOWN forbids blind retries.",
              )}
            </p>
            <div className="record-list">
              {state.egress
                .slice(-8)
                .reverse()
                .map((request) => (
                  <article className="engine-record" key={request.id}>
                    <strong>{request.decision}</strong>
                    <span className={`status ${tone(request.status)}`}>
                      {request.status}
                    </span>
                    <p>
                      {request.binding.destination} · {request.binding.account}{" "}
                      · {request.binding.purpose}
                    </p>
                    <code className="hash">{request.binding.payload_hash}</code>
                    {request.reason && <p>{request.reason}</p>}
                    <div className="inline">
                      <button
                        className="quiet"
                        disabled={busy || request.status === "BLOCKED"}
                        onClick={() =>
                          void action(async () => {
                            const result = await api(
                              `/v1/egress/${request.id}`,
                            );
                            setBytes({
                              id: request.id,
                              kind: "egress",
                              value: result.payload,
                            });
                          })
                        }
                      >
                        {t("مراجعة البايتات", "Review exact bytes")}
                      </button>
                      <button
                        className="quiet"
                        disabled={busy || request.status !== "REVIEW_REQUIRED"}
                        onClick={() =>
                          void action(async () => {
                            await mutate(`/v1/egress/${request.id}/approve`, {
                              binding_hash: request.binding_hash,
                            });
                          })
                        }
                      >
                        {t("اعتماد الطلب المحدد", "Approve exact request")}
                      </button>
                      <button
                        disabled={
                          busy ||
                          !["READY", "APPROVED"].includes(request.status)
                        }
                        onClick={() =>
                          void action(async () => {
                            await mutate(`/v1/egress/${request.id}/dispatch`);
                          })
                        }
                      >
                        {t(
                          "إرسال عبر بوابة mock",
                          "Dispatch through mock gateway",
                        )}
                      </button>
                    </div>
                  </article>
                ))}
            </div>
          </section>
          {bytes && (
            <section className="panel">
              <h3>
                {t("بايتات عبر الحارس الحالي", "Bytes through current guard")}
              </h3>
              <pre className="byte-preview">{bytes.value}</pre>
              <button className="quiet" onClick={() => setBytes(null)}>
                {t("إغلاق", "Close")}
              </button>
            </section>
          )}
          <div className="engine-grid">
            <section className="panel">
              <p className="eyebrow">06 / DURABLE OUTBOX · FENCED ATTEMPTS</p>
              <h3>{t("سجل المهام", "Job ledger")}</h3>
              <div className="record-list compact">
                {state.jobs
                  .slice(-16)
                  .reverse()
                  .map((job) => (
                    <article className="engine-record" key={job.id}>
                      <strong>{job.kind}</strong>
                      <span className={`status ${tone(job.state)}`}>
                        {job.state}
                      </span>
                      <code>{job.id.slice(0, 8)}</code>
                      <p>fence {job.fence}</p>
                    </article>
                  ))}
              </div>
            </section>
            <section className="panel">
              <p className="eyebrow">AUDIT · HASHES ONLY</p>
              <h3>{t("آخر الأدلة", "Recent audit evidence")}</h3>
              <div className="audit engine-audit">
                {state.events
                  .slice(-16)
                  .reverse()
                  .map((event) => (
                    <article key={event.id}>
                      <code>{event.kind}</code>
                      <small>
                        {new Date(event.at * 1000).toLocaleTimeString(
                          english ? "en" : "ar-SA",
                        )}
                      </small>
                      <p>{JSON.stringify(event.details)}</p>
                    </article>
                  ))}
              </div>
            </section>
          </div>
        </>
      )}
    </section>
  );
}
