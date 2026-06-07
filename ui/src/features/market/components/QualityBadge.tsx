import { StatusBadge } from "@/shared/ui/StatusBadge";

export function QualityBadge({ status }: { status: string | undefined }) {
  let tone: "positive" | "negative" | "warning" | "muted" = "muted";
  if (status === "ok") {
    tone = "positive";
  } else if (status === "partial" || status === "stale") {
    tone = "warning";
  } else if (status === "unavailable") {
    tone = "negative";
  }
  return <StatusBadge label={status || "unknown"} tone={tone} />;
}
