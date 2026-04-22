interface Props {
  projectId: string | undefined;
  runId: string;
}

export function SamplesView({ projectId, runId }: Props) {
  return (
    <div className="text-[var(--vs-fg-muted)] text-[12px] py-4 text-center">
      Samples — run: {runId}
    </div>
  );
}
