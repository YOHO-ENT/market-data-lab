export function MetricCard({
  label,
  value,
  mono,
}: {
  label: string;
  value: string | number;
  mono?: boolean;
}) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${mono ? "mono" : ""}`}>{value}</div>
    </div>
  );
}
