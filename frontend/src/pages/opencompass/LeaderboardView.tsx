interface Props {
  projectId: string | undefined;
  runId: string;
}

export function LeaderboardView({ projectId, runId }: Props) {
  return (
    <div className="text-[var(--vs-fg-muted)] text-[12px] py-4 text-center">
      Leaderboard — run: {runId}
    </div>
  );
}
