import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getEvalRun } from "@/api/opencompass";
import { useI18n } from "@/hooks/useI18n";

interface Props {
  projectId: string | undefined;
  runId: string;
}

export function ComparisonView({ projectId, runId }: Props) {
  const { t } = useI18n();
  const [perDataset, setPerDataset] = useState<Record<string, Record<string, number>>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!projectId || !runId) return;
    setLoading(true);
    setError("");
    getEvalRun(projectId, runId)
      .then((res) => {
        setPerDataset(res.viz?.per_dataset ?? {});
      })
      .catch((e: unknown) => {
        const err = e as { message?: string };
        setPerDataset({});
        setError(err?.message ?? t("oc.err_load_failed"));
      })
      .finally(() => setLoading(false));
  }, [projectId, runId]);

  const models = useMemo(() => Object.keys(perDataset), [perDataset]);
  const chartRows = useMemo(() => {
    const datasetSet = new Set<string>();
    for (const model of models) {
      Object.keys(perDataset[model] ?? {}).forEach((ds) => datasetSet.add(ds));
    }
    const datasets = Array.from(datasetSet);
    return datasets.map((dataset) => {
      const row: Record<string, number | string> = { dataset };
      for (const model of models) {
        row[model] = Number(perDataset[model]?.[dataset] ?? 0);
      }
      return row;
    });
  }, [models, perDataset]);

  if (loading) {
    return <div className="text-[var(--vs-fg-muted)] text-[12px] py-4 text-center">{t("oc.loading_comparison")}</div>;
  }
  if (error) {
    return <div className="text-[#f48771] text-[12px] py-4 text-center">{error}</div>;
  }
  if (!models.length || !chartRows.length) {
    return (
      <div className="text-[var(--vs-fg-muted)] text-[12px] py-4 text-center">
        {t("oc.no_comparison_run", { run: runId })}
      </div>
    );
  }

  const colors = ["#3794ff", "#c586c0", "#4ec9b0", "#dcb67a", "#f48771"];

  return (
    <div className="space-y-3">
      <div className="text-[12px] text-[var(--vs-fg-muted)]">
        {t("oc.model_count_label", { count: models.length })} · {t("oc.dataset_count_label", { count: chartRows.length })}
      </div>
      <div style={{ width: "100%", height: 320 }}>
        <ResponsiveContainer>
          <BarChart data={chartRows} margin={{ top: 8, right: 10, left: 6, bottom: 8 }}>
            <CartesianGrid stroke="var(--vs-border)" strokeDasharray="3 3" />
            <XAxis dataKey="dataset" stroke="var(--vs-fg-subtle)" fontSize={11} />
            <YAxis
              stroke="var(--vs-fg-subtle)"
              fontSize={11}
              domain={[0, 100]}
              tickFormatter={(v) => `${v}%`}
              width={46}
            />
            <Tooltip
              formatter={(value: number) => [`${Number(value).toFixed(2)}%`, t("oc.metric_accuracy")]}
              contentStyle={{ backgroundColor: "var(--vs-sidebar)", border: "1px solid #3c3c3c", fontSize: 11 }}
            />
            <Legend />
            {models.map((model, idx) => (
              <Bar key={model} dataKey={model} fill={colors[idx % colors.length]} radius={[3, 3, 0, 0]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
