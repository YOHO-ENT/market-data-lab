export function StatusBadge({
  label,
  tone = "muted",
}: {
  label: string;
  tone?: "positive" | "negative" | "warning" | "muted";
}) {
  return <span className={`status-badge is-${tone}`}>{label}</span>;
}
