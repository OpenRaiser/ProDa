import { useEffect, useMemo, useState } from "react";
import { getAnnotations, getRunSamples, putAnnotation } from "@/api/opencompass";
import { useI18n } from "@/hooks/useI18n";
import type { EvalSampleRow, SampleAnnotation } from "@/types";

interface Props {
  projectId: string | undefined;
  runId: string;
}

type SummaryRow = {
  model: string;
  total: number;
  pass: number;
  fail: number;
  accuracy: number;
};

export function SamplesView({ projectId, runId }: Props) {
  const { t } = useI18n();
  const [rows, setRows] = useState<EvalSampleRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [model, setModel] = useState("");
  const [subject, setSubject] = useState("");
  const [qtype, setQtype] = useState("");
  const [onlyFail, setOnlyFail] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const [annotations, setAnnotations] = useState<SampleAnnotation[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [annIssue, setAnnIssue] = useState<"concept_gap" | "capability_deficit" | "unlabeled">("unlabeled");
  const [annNote, setAnnNote] = useState("");
  const [annSaving, setAnnSaving] = useState(false);

  useEffect(() => {
    if (!projectId || !runId) return;
    setLoading(true);
    setError("");
    Promise.all([
      getRunSamples(projectId, runId, { limit: 5000, offset: 0 }),
      getAnnotations(projectId, runId),
    ])
      .then(([res, ann]) => {
        setRows(res.rows ?? []);
        setTotal(res.total ?? 0);
        setAnnotations(ann ?? []);
      })
      .catch((e: unknown) => {
        const err = e as { message?: string };
        setRows([]);
        setTotal(0);
        setAnnotations([]);
        setError(err?.message ?? "load failed");
      })
      .finally(() => setLoading(false));
  }, [projectId, runId]);

  useEffect(() => {
    setPage(1);
  }, [model, subject, qtype, onlyFail]);

  const modelOptions = useMemo(
    () => Array.from(new Set(rows.map((r) => String(r.model || "")).filter(Boolean))).sort(),
    [rows]
  );
  const subjectOptions = useMemo(
    () => Array.from(new Set(rows.map((r) => String(r.subject || "")).filter(Boolean))).sort(),
    [rows]
  );
  const qtypeOptions = useMemo(
    () => Array.from(new Set(rows.map((r) => String(r.question_type || "")).filter(Boolean))).sort(),
    [rows]
  );

  const summary = useMemo<SummaryRow[]>(() => {
    const map = new Map<string, SummaryRow>();
    for (const r of rows) {
      const m = String(r.model || "");
      if (!m) continue;
      const item = map.get(m) ?? { model: m, total: 0, pass: 0, fail: 0, accuracy: 0 };
      item.total += 1;
      if (r.pass) item.pass += 1;
      else item.fail += 1;
      map.set(m, item);
    }
    const out = Array.from(map.values()).map((x) => ({
      ...x,
      accuracy: x.total > 0 ? (x.pass / x.total) * 100 : 0,
    }));
    out.sort((a, b) => b.accuracy - a.accuracy);
    return out;
  }, [rows]);

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (model && r.model !== model) return false;
      if (subject && r.subject !== subject) return false;
      if (qtype && r.question_type !== qtype) return false;
      if (onlyFail && r.pass) return false;
      return true;
    });
  }, [rows, model, subject, qtype, onlyFail]);

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pages);
  const pageRows = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, safePage]);

  const annMap = useMemo(() => {
    const map = new Map<string, SampleAnnotation>();
    for (const a of annotations) {
      map.set(`${a.sample_id}::${a.model}`, a);
    }
    return map;
  }, [annotations]);

  const selectedRow = useMemo(
    () =>
      filtered.find(
        (r) => `${r.sample_id}::${r.model}` === selectedKey
      ) ?? null,
    [filtered, selectedKey]
  );

  useEffect(() => {
    if (!selectedRow) {
      setAnnIssue("unlabeled");
      setAnnNote("");
      return;
    }
    const ann = annMap.get(`${selectedRow.sample_id}::${selectedRow.model}`);
    setAnnIssue((ann?.issue_type as "concept_gap" | "capability_deficit" | "unlabeled") ?? "unlabeled");
    setAnnNote(ann?.note ?? "");
  }, [selectedRow, annMap]);

  const saveAnnotation = async () => {
    if (!projectId || !runId || !selectedRow) return;
    setAnnSaving(true);
    try {
      const next = await putAnnotation(projectId, runId, {
        sample_id: selectedRow.sample_id,
        model: selectedRow.model,
        issue_type: annIssue,
        note: annNote,
      });
      setAnnotations(next);
    } finally {
      setAnnSaving(false);
    }
  };

  if (loading) {
    return <div className="text-[var(--vs-fg-muted)] text-[12px] py-4 text-center">{t("oc.samples_loading")}</div>;
  }
  if (error) {
    return <div className="text-[#f48771] text-[12px] py-4 text-center">{error}</div>;
  }
  if (!rows.length) {
    return (
      <div className="text-[var(--vs-fg-muted)] text-[12px] py-4 text-center">
        {t("oc.samples_no_data", { run: runId })}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="vs-card p-3">
        <div className="text-[12px] text-[var(--vs-fg-muted)] mb-2">{t("oc.samples_summary_title")}</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {summary.map((s) => (
            <div key={s.model} className="border border-[var(--vs-border)] rounded px-3 py-2">
              <div className="text-[12px] text-[var(--vs-fg-strong)]">{s.model}</div>
              <div className="text-[11px] text-[var(--vs-fg-muted)] font-mono">
                acc {s.accuracy.toFixed(2)}% · {t("oc.filter_pass")} {s.pass} · {t("oc.filter_fail")} {s.fail} · {t("oc.samples_total_label")} {s.total}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="vs-card p-3">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
          <select className="vs-input" value={model} onChange={(e) => setModel(e.target.value)}>
            <option value="">{t("oc.filter_all_models")}</option>
            {modelOptions.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <select className="vs-input" value={subject} onChange={(e) => setSubject(e.target.value)}>
            <option value="">{t("oc.filter_all_subjects")}</option>
            {subjectOptions.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select className="vs-input" value={qtype} onChange={(e) => setQtype(e.target.value)}>
            <option value="">{t("oc.filter_all_qtypes")}</option>
            {qtypeOptions.map((qt) => (
              <option key={qt} value={qt}>
                {qt}
              </option>
            ))}
          </select>
          <label className="h-[32px] px-2 flex items-center gap-2 text-[12px] text-[var(--vs-fg)]">
            <input
              type="checkbox"
              className="accent-[var(--vs-accent)]"
              checked={onlyFail}
              onChange={(e) => setOnlyFail(e.target.checked)}
            />
            {t("oc.filter_fail")}
          </label>
        </div>
      </div>

      <div className="vs-card overflow-hidden">
        <div className="px-3 py-2 text-[12px] text-[var(--vs-fg-muted)] border-b border-[var(--vs-border)]">
          {t("oc.samples_counter", {
            shown: String(pageRows.length),
            total: String(filtered.length),
            page: String(safePage),
            pages: String(pages),
          })}
          {rows.length < total ? ` · ${t("oc.samples_truncated", { total: String(total) })}` : ""}
        </div>
        <div className="max-h-[420px] overflow-auto">
          <table className="w-full text-[12px] border-collapse">
            <thead className="sticky top-0 bg-[var(--vs-sidebar)]">
              <tr>
                <th className="px-2 py-1 text-left border-b border-[var(--vs-border)]">{t("oc.samples_col_status")}</th>
                <th className="px-2 py-1 text-left border-b border-[var(--vs-border)]">{t("oc.samples_col_model")}</th>
                <th className="px-2 py-1 text-left border-b border-[var(--vs-border)]">{t("oc.samples_col_subject")}</th>
                <th className="px-2 py-1 text-left border-b border-[var(--vs-border)]">{t("oc.samples_col_type")}</th>
                <th className="px-2 py-1 text-left border-b border-[var(--vs-border)]">{t("oc.samples_col_prediction")}</th>
                <th className="px-2 py-1 text-left border-b border-[var(--vs-border)]">{t("oc.samples_col_gold")}</th>
                <th className="px-2 py-1 text-left border-b border-[var(--vs-border)]">{t("oc.samples_col_question")}</th>
                <th className="px-2 py-1 text-left border-b border-[var(--vs-border)]">A</th>
                <th className="px-2 py-1 text-left border-b border-[var(--vs-border)]">B</th>
                <th className="px-2 py-1 text-left border-b border-[var(--vs-border)]">C</th>
                <th className="px-2 py-1 text-left border-b border-[var(--vs-border)]">D</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((r) => {
                const opts = r.options && typeof r.options === "object" ? (r.options as Record<string, unknown>) : {};
                const key = `${r.sample_id}::${r.model}`;
                const ann = annMap.get(key);
                return (
                  <tr
                    key={`${r.model}-${r.sample_id}-${r.idx}`}
                    className="border-b border-[var(--vs-panel)] hover:bg-[var(--vs-hover)] cursor-pointer"
                    onClick={() => setSelectedKey(key)}
                  >
                    <td className="px-2 py-1">{r.pass ? t("oc.filter_pass") : t("oc.filter_fail")}</td>
                    <td className="px-2 py-1 font-mono">{r.model}</td>
                    <td className="px-2 py-1">{r.subject}</td>
                    <td className="px-2 py-1">{r.question_type}</td>
                    <td className="px-2 py-1 font-mono">{r.prediction}</td>
                    <td className="px-2 py-1 font-mono">{r.gold}</td>
                    <td className="px-2 py-1">{r.question}</td>
                    <td className="px-2 py-1">{String(opts.A ?? "")}</td>
                    <td className="px-2 py-1">{String(opts.B ?? "")}</td>
                    <td className="px-2 py-1">{String(opts.C ?? "")}</td>
                    <td className="px-2 py-1">
                      {String(opts.D ?? "")}
                      {ann ? (
                        <span className="ml-2 text-[10px] text-[#c586c0]">[{ann.issue_type}]</span>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="px-3 py-2 border-t border-[var(--vs-border)] flex items-center justify-end gap-2">
          <button
            className="vs-btn-ghost px-2 h-[24px]"
            disabled={safePage <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            {t("oc.samples_prev")}
          </button>
          <span className="text-[11px] text-[var(--vs-fg-muted)] font-mono">
            {safePage}/{pages}
          </span>
          <button
            className="vs-btn-ghost px-2 h-[24px]"
            disabled={safePage >= pages}
            onClick={() => setPage((p) => Math.min(pages, p + 1))}
          >
            {t("oc.samples_next")}
          </button>
        </div>
      </div>

      {selectedRow && (
        <div className="vs-card p-3 space-y-3">
          <div className="text-[12px] text-[var(--vs-fg-strong)]">{t("oc.sample_detail")}</div>
          <div className="text-[12px] text-[var(--vs-fg)]">
            <div className="text-[11px] text-[var(--vs-fg-muted)] mb-1">{t("oc.sample_question")}</div>
            {selectedRow.question}
          </div>
          <div>
            <div className="text-[11px] text-[var(--vs-fg-muted)] mb-1">{t("oc.sample_options")}</div>
            <div className="text-[12px] text-[var(--vs-fg)] leading-[1.45]">
              {formatOptions(selectedRow.options)}
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <div className="text-[12px] font-mono">
              <span className="text-[var(--vs-fg-muted)] mr-2">{t("oc.sample_gold")}:</span>
              <span className="text-[var(--vs-fg)]">{selectedRow.gold}</span>
            </div>
            <div className="text-[12px] font-mono">
              <span className="text-[var(--vs-fg-muted)] mr-2">{t("oc.sample_pred")}:</span>
              <span className="text-[var(--vs-fg)]">{selectedRow.prediction}</span>
            </div>
          </div>

          <div className="border-t border-[var(--vs-border)] pt-3 space-y-2">
            <div className="text-[12px] text-[var(--vs-fg-strong)]">{t("oc.annotate_title")}</div>
            <div className="grid grid-cols-1 md:grid-cols-[220px_1fr_auto] gap-2">
              <select
                className="vs-input"
                value={annIssue}
                onChange={(e) =>
                  setAnnIssue(
                    (e.target.value as "concept_gap" | "capability_deficit" | "unlabeled") ??
                      "unlabeled"
                  )
                }
              >
                <option value="unlabeled">unlabeled</option>
                <option value="concept_gap">concept_gap</option>
                <option value="capability_deficit">capability_deficit</option>
              </select>
              <input
                className="vs-input"
                value={annNote}
                onChange={(e) => setAnnNote(e.target.value)}
                placeholder={t("oc.annotate_note_ph")}
              />
              <button className="vs-btn" onClick={saveAnnotation} disabled={annSaving}>
                {annSaving ? "..." : t("oc.annotate_save")}
              </button>
            </div>
          </div>

          <details>
            <summary className="text-[11px] text-[var(--vs-fg-muted)] cursor-pointer">
              {t("oc.raw_json_title")}
            </summary>
            <pre className="mt-2 p-2 text-[11px] bg-[var(--vs-panel)] border border-[var(--vs-border)] overflow-auto">
              {JSON.stringify(selectedRow, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}

function formatOptions(options: unknown): string {
  if (!options || typeof options !== "object") return "-";
  const dict = options as Record<string, unknown>;
  const rows = ["A", "B", "C", "D"]
    .map((k) => {
      const v = dict[k];
      const s = String(v ?? "").trim();
      return s ? `${k}. ${s}` : "";
    })
    .filter(Boolean);
  return rows.length ? rows.join(" | ") : "-";
}
