import { useId } from "react";
import type { AttributionResponse, Profile } from "./types";
import { contributionDistribution } from "./contributionShares";

type Props = {
  // The same validated, generation-owned snapshot consumed by AttributionTable.
  attribution: AttributionResponse | null;
  profile: Profile;
  loading: boolean;
  error: string | null;
};

export function ContributionDistribution({ attribution, profile, loading, error }: Props) {
  const descriptionId = useId();
  if (loading) return <p className="contribution-state chart-note" role="status">Đang tính tỷ trọng đóng góp…</p>;
  if (error) return <p className="contribution-state chart-note" role="status">{error}</p>;
  if (!attribution) return <p className="contribution-state chart-note">Phân tích văn bản để xem tỷ trọng đóng góp.</p>;

  let shares;
  try { shares = contributionDistribution(attribution.groups); }
  catch (cause) { return <p className="contribution-state chart-note" role="alert">{(cause as Error).message}</p>; }
  if (!shares) return <p className="contribution-state chart-note" role="status">Chưa có đóng góp khác 0 để tính tỷ trọng.</p>;
  const target = attribution.method!.target;
  const polarity = target.kind === "polarity_margin";
  const label = target.kind === "label_score"
    ? profile.sentiment.find((candidate) => candidate.id === target.label_id)?.name : "";
  const labels = polarity ? ["Nghiêng tích cực", "Nghiêng tiêu cực"] : [`Tăng điểm ${label}`, `Giảm điểm ${label}`];
  const colors = polarity ? ["#39996a", "#c76b5d"] : ["#417caa", "#b45309"];
  const circumference = 2 * Math.PI * 86;
  const description = shares.map((share, index) => `${labels[index]}: ${share.percent}%${share.negligible ? " (dưới 0,05% trước làm tròn)" : ""}`).join("; ");

  return <>
    <div className="donut-layout contribution-layout" data-attribution-id={attribution.attribution_id}>
      <div className="donut-container">
        <svg id="contribution-donut" viewBox="0 0 224 224" role="img"
          aria-label="Tỷ trọng đóng góp của cụm từ" aria-describedby={descriptionId}>
          <desc id={descriptionId}>{description}. Tính theo độ lớn đóng góp vào mục tiêu của mô hình.</desc>
          {shares.map((share, index) => share.fraction > 0 && <circle key={index}
            cx="112" cy="112" r="86" fill="none" strokeWidth="18" stroke={colors[index]}
            strokeDasharray={`${share.fraction * circumference} ${circumference}`}
            strokeDashoffset={index === 0 ? 0 : -shares[0].fraction * circumference}
            data-direction={index === 0 ? "increase" : "decrease"}>
            <title>{labels[index]}: {share.percent}%</title>
          </circle>)}
        </svg>
        <div className="donut-center contribution-center" aria-hidden="true"><span>Đóng góp<br />từ ngữ</span></div>
      </div>
      <ul id="contribution-legend" className="distribution-legend contribution-legend" aria-label="Hai chiều đóng góp">
        {shares.map((share, index) => <li key={index} data-direction={index === 0 ? "increase" : "decrease"}>
          <i className="dot" style={{ background: colors[index] }} aria-hidden="true" />
          <span>{labels[index]}</span><strong>{share.percent}%</strong>
          {share.negligible && <small>Dưới 0,05% trước làm tròn</small>}
        </li>)}
      </ul>
    </div>
    <p className="chart-note">Tỷ trọng tính theo độ lớn đóng góp của các cụm từ, không phải tỷ lệ từ hay xác suất cảm xúc.</p>
  </>;
}
