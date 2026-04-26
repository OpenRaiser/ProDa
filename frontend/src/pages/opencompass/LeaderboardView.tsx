import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getEvalRun } from "@/api/opencompass";
import { useI18n } from "@/hooks/useI18n";
import type { LeaderboardRow } from "@/types";

interface Props {
  projectId: string | undefined;
  runId: string;
}

export function LeaderboardView({ projectId, runId }: Props) {
  const { t } = useI18n();
  const [rows, setRows] = useState<LeaderboardRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!projectId || !runId) return;
    setLoading(true);
    setError("");
    getEvalRun(projectId, runId)
      .then((res) => {
        setRows((res.viz?.leaderboard ?? []).slice().sort((a, b) => b.accuracy - a.accuracy));
      })
      .catch((e: unknown) => {
        const err = e as { message?: string };
        setRows([]);
        setError(err?.message ?? t("oc.err_load_failed"));
      })
      .finally(() => setLoading(false));
  }, [projectId, runId]);

  const best = useMemo(() => (rows.length ? rows[0] : null), [rows]);

  if (loading) {
    return <div className="text-[var(--vs-fg-muted)] text-[12px] py-4 text-center">{t("oc.loading_leaderboard")}</div>;
  }
  if (error) {
    return <div className="text-[#f48771] text-[12px] py-4 text-center">{error}</div>;
  }
  if (!rows.length) {
    return (
      <div className="text-[var(--vs-fg-muted)] text-[12px] py-4 text-center">
        {t("oc.no_leaderboard_run", { run: runId })}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {best && (
        <div className="text-[12px] text-[var(--vs-fg)]">
          {t("oc.best_model_label")}:{" "}
          <span className="text-[var(--vs-fg-strong)]">{best.model}</span> · {best.accuracy.toFixed(2)}%
        </div>
      )}
      <div style={{ width: "100%", height: 280 }}>
        <ResponsiveContainer>
          <BarChart data={rows} margin={{ top: 6, right: 10, left: 8, bottom: 22 }}>
            <CartesianGrid stroke="var(--vs-border)" strokeDasharray="3 3" />
            <XAxis
              dataKey="model"
              stroke="var(--vs-fg-subtle)"
              fontSize={11}
              angle={-12}
              textAnchor="end"
              interval={0}
              height={60}
            />
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
            <Bar dataKey="accuracy" fill="var(--vs-accent)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
