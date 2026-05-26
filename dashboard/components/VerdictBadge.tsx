import type { Verdict } from "@/lib/mockData";

interface VerdictBadgeProps {
  verdict: Verdict;
  size?: "sm" | "md" | "lg";
}

const verdictConfig: Record<Verdict, { label: string; bg: string; text: string; dot: string }> = {
  PASS: {
    label: "PASS",
    bg: "rgba(0, 229, 160, 0.12)",
    text: "#00E5A0",
    dot: "#00E5A0",
  },
  KILL: {
    label: "KILL",
    bg: "rgba(255, 68, 68, 0.12)",
    text: "#FF4444",
    dot: "#FF4444",
  },
  ITERATE: {
    label: "ITERATE",
    bg: "rgba(255, 184, 0, 0.12)",
    text: "#FFB800",
    dot: "#FFB800",
  },
};

export default function VerdictBadge({ verdict, size = "md" }: VerdictBadgeProps) {
  const config = verdictConfig[verdict];
  const sizeClass = size === "sm" ? "text-xs px-2 py-0.5" : size === "lg" ? "text-base px-4 py-1.5" : "text-sm px-2.5 py-1";

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-semibold rounded-full ${sizeClass}`}
      style={{ backgroundColor: config.bg, color: config.text }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
        style={{ backgroundColor: config.dot }}
      />
      {config.label}
    </span>
  );
}
