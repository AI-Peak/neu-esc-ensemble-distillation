import React from "react";
import type { Profile } from "./types";

interface SentimentDistributionProps {
  profile: Profile | null;
  sentimentCounts: Record<number, number>;
  totalEligible: number;
  totalItems?: number;
  selectedSentimentId: number | null;
  onSelectSentiment: (labelId: number | null) => void;
}

const SENTIMENT_COLORS: Record<string, string> = {
  positive: "#39996a",
  negative: "#c76b5d",
  neutral: "#9aa7a0",
  toxic: "#c88c3d",
};

export const SentimentDistribution: React.FC<SentimentDistributionProps> = ({
  profile,
  sentimentCounts,
  totalEligible,
  totalItems,
  selectedSentimentId,
  onSelectSentiment,
}) => {
  if (!profile || totalEligible === 0) {
    return (
      <div className="donut-layout" style={{ justifyContent: "center", padding: "24px" }}>
        <p className="chart-note">Chưa có phản hồi nào được gán nhãn cảm xúc.</p>
      </div>
    );
  }

  // Sentiment definitions from profile
  const labels = profile.sentiment;
  const positiveLabel = labels.find((l) => l.key.toLowerCase() === "positive");
  const negativeLabel = labels.find((l) => l.key.toLowerCase() === "negative");

  const positiveCount = positiveLabel ? sentimentCounts[positiveLabel.id] ?? 0 : 0;
  const negativeCount = negativeLabel ? sentimentCounts[negativeLabel.id] ?? 0 : 0;

  // Net sentiment: 100 * (pos - neg) / total_valid_sentiment
  const netScore = totalEligible > 0 ? (100.0 * (positiveCount - negativeCount)) / totalEligible : 0;
  const formattedNet =
    netScore > 0
      ? `+${netScore.toFixed(1).replace(".", ",")}`
      : netScore < 0
      ? `−${Math.abs(netScore).toFixed(1).replace(".", ",")}`
      : "0,0";

  // SVG Donut calculation
  const radius = 86;
  const circumference = 2 * Math.PI * radius;
  let accumulatedOffset = 0;

  const segments = labels.map((label) => {
    const count = sentimentCounts[label.id] ?? 0;
    const fraction = totalEligible > 0 ? count / totalEligible : 0;
    const dashLength = Math.max(0, fraction * circumference - 2);
    const offset = accumulatedOffset;
    accumulatedOffset += fraction * circumference;
    const color = SENTIMENT_COLORS[label.key.toLowerCase()] ?? "#7a8984";
    const percent = (fraction * 100).toFixed(1).replace(".", ",");
    const isSelected = selectedSentimentId === label.id;

    return {
      label,
      count,
      fraction,
      dashLength,
      offset,
      color,
      percent,
      isSelected,
    };
  });

  return (
    <div className="donut-layout">
      <div className="donut-container">
        <svg
          id="sentiment-donut"
          viewBox="0 0 224 224"
          role="group"
          aria-label={`Phân bố cảm xúc của ${totalEligible} phản hồi`}
        >
          {segments.map((seg) => {
            if (seg.fraction <= 0) return null;
            return (
              <circle
                key={seg.label.id}
                cx="112"
                cy="112"
                r={radius}
                stroke={seg.color}
                strokeDasharray={`${seg.dashLength} ${circumference}`}
                strokeDashoffset={-seg.offset}
                className={`donut-segment ${seg.isSelected ? "selected" : ""}`}
                role="button"
                tabIndex={0}
                aria-label={`${seg.label.name}: ${seg.count} phản hồi (${seg.percent}%)`}
                aria-pressed={seg.isSelected}
                onKeyDown={(event) => {
                  if (["Enter", " "].includes(event.key)) {
                    event.preventDefault();
                    onSelectSentiment(seg.isSelected ? null : seg.label.id);
                  }
                }}
                style={{
                  strokeWidth: seg.isSelected ? 23 : 18,
                  opacity: selectedSentimentId !== null && !seg.isSelected ? 0.45 : 1.0,
                }}
                onClick={() =>
                  onSelectSentiment(seg.isSelected ? null : seg.label.id)
                }
              >
                <title>{`${seg.label.name}: ${seg.count} phản hồi (${seg.percent}%)`}</title>
              </circle>
            );
          })}
        </svg>
        <div className="donut-center">
          <strong id="net-sentiment">{formattedNet}</strong>
          <span>Net sentiment</span>
        </div>
      </div>
      {totalItems !== undefined && totalEligible < totalItems && (
        <p className="sr-only">Có nhãn cảm xúc: {totalEligible} / {totalItems} phản hồi.</p>
      )}

      <div
        id="distribution-legend"
        className="distribution-legend"
        aria-label="Chọn cảm xúc để xem phản hồi"
      >
        {segments.map((seg) => (
          <button
            type="button"
            key={seg.label.id}
            className="legend-button"
            data-sentiment={seg.label.key}
            aria-pressed={seg.isSelected}
            onClick={() =>
              onSelectSentiment(seg.isSelected ? null : seg.label.id)
            }
          >
            <i className="dot" style={{ background: seg.color }} />
            <span>{seg.label.name}</span>
            <strong>{seg.percent}%</strong>
            <small>{seg.count} phản hồi</small>
          </button>
        ))}
      </div>
    </div>
  );
};
