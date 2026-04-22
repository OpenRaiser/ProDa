interface Props {
  projectId: string | undefined;
  runId: string;
}

export function ComparisonView({ projectId, runId }: Props) {
  return (
    <div className="text-[var(--vs-fg-muted)] text-[12px] py-4 text-center">
      Comparison — run: {runId}
    </div>
  );
}
