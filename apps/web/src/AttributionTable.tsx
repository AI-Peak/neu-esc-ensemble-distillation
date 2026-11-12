import React, { useState, useMemo } from "react";
import type { AttributionResponse } from "./types";
import { HighlightedFeedback } from "./HighlightedFeedback";

interface AttributionTableProps {
  rawText: string;
  attribution: AttributionResponse;
  targetLabelName?: string;
}

export const AttributionTable: React.FC<AttributionTableProps> = ({
  rawText,
  attribution,
  targetLabelName = "",
}) => {
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [showAllGroups, setShowAllGroups] = useState<boolean>(false);

  const { groups, aggregate, method } = attribution;
  const targetKind = method?.target.kind ?? "polarity_margin";
  const isPolarity = targetKind === "polarity_margin";

  // Compute maximum absolute contribution across all individual groups for gauge meter denominator
  const maxAbsWeight = useMemo(() => {
    if (!groups.length) return 1.0;
    const max = Math.max(...groups.map((g) => Math.abs(g.contribution)));
    return max > 0 ? max : 1.0;
  }, [groups]);

  // Group display logic:
  // If groups > 6 and not showAllGroups, pick top 6 groups by absolute weight,
  // then sort them by their appearance order in the sentence.
  const { visibleGroups, hiddenGroups, hiddenSum } = useMemo(() => {
    if (groups.length <= 6 || showAllGroups) {
      const sortedByPos = [...groups].sort((a, b) => a.start_utf16 - b.start_utf16);
      return { visibleGroups: sortedByPos, hiddenGroups: [], hiddenSum: 0 };
    }

    const sortedByAbs = [...groups].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
    const top6 = sortedByAbs.slice(0, 6);
    const top6Set = new Set(top6.map((g) => g.id));
    const remaining = groups.filter((g) => !top6Set.has(g.id));
    const sumRemaining = remaining.reduce((acc, g) => acc + g.contribution, 0);

    const top6InOrder = top6.sort((a, b) => a.start_utf16 - b.start_utf16);
    return { visibleGroups: top6InOrder, hiddenGroups: remaining, hiddenSum: sumRemaining };
  }, [groups, showAllGroups]);

  const hasRemaining = hiddenGroups.length > 0;
  const rowCount = visibleGroups.length + (hasRemaining ? 1 : 0);

  // Completed payloads are validated before this component is mounted.
  if (!aggregate || !method) return null;
  const totalValue = aggregate.total_contribution;
  const baselineValue = aggregate.baseline_value;
  const targetValue = aggregate.target_output;
  const residual = aggregate.additivity_residual;

  const formatNumber = (val: number, forceSign = false) => {
    const formatted = Math.abs(val).toFixed(1).replace(".", ",");
    if (val > 0) return forceSign ? `+${formatted}` : formatted;
    if (val < 0) return `−${formatted}`;
    return "0,0";
  };

  const formattedTotal = formatNumber(totalValue, totalValue > 0);

  // Meter width percentage
  const getMeterPercent = (contrib: number) => {
    const ratio = Math.abs(contrib) / maxAbsWeight;
    return Math.min(100, Math.max(0, ratio * 100));
  };

  // Determine weight header label based on target
  const weightHeader = isPolarity
    ? "Trọng số cảm xúc"
    : "Trọng số";

  return (
    <div id="attribution-content" className="attribution-surface">
      <table className="attribution-table">
        <caption className="sr-only">
          Đóng góp của các cụm từ vào điểm dự đoán phân tích
        </caption>
        <colgroup>
          <col className="col-feedback" />
          <col className="col-phrase" />
          <col className="col-weight" />
          <col className="col-total" />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">
              Phản hồi
              <span className="reference-label">Consumer comment</span>
            </th>
            <th scope="col">
              Từ quan trọng
              <span className="reference-label">Meaningful words</span>
            </th>
            <th scope="col">
              {weightHeader}
              <span className="reference-label">
                {isPolarity ? "Sentiment weight" : `cho nhãn ${targetLabelName}`}
              </span>
            </th>
            <th scope="col">
              Tổng đóng góp
              <span className="reference-label">Tổng các trọng số</span>
            </th>
          </tr>
        </thead>
        <tbody style={{ "--analysis-rows": rowCount } as React.CSSProperties}>
          <tr className="compact-table-labels">
            <td role="columnheader">Từ quan trọng</td>
            <td role="columnheader">Trọng số</td>
          </tr>
          {visibleGroups.map((group, index) => {
            const isSelected = selectedGroupId === group.id;
            const isPos = group.contribution > 0;
            const isNeg = group.contribution < 0;

            let weightTextClass = "weight-cell";
            let phraseClass = "phrase-button";

            if (isPolarity) {
              if (isPos) {
                weightTextClass += " positive-text";
                phraseClass += " positive-text";
              } else if (isNeg) {
                weightTextClass += " negative-text";
                phraseClass += " negative-text";
              }
            } else {
              // Neutral or Toxic: use blue / amber
              if (isPos) {
                weightTextClass += " label-increase-text";
                phraseClass += " label-increase-text";
              } else if (isNeg) {
                weightTextClass += " label-decrease-text";
                phraseClass += " label-decrease-text";
              }
            }

            return (
              <tr
                key={group.id}
                className={`attribution-row ${isSelected ? "selected" : ""}`}
                data-row={group.id}
              >
                {/* Rowspan column 1 for the original cell */}
                {index === 0 && (
                  <td className="original-cell" rowSpan={rowCount}>
                    <HighlightedFeedback
                      text={rawText}
                      groups={visibleGroups}
                      selectedGroupId={selectedGroupId}
                      onSelectGroup={setSelectedGroupId}
                      targetKind={targetKind}
                      targetLabelName={targetLabelName}
                    />
                  </td>
                )}

                <td className="phrase-cell">
                  <button
                    type="button"
                    className={phraseClass}
                    data-term={group.id}
                    aria-pressed={isSelected}
                    onClick={() =>
                      setSelectedGroupId(isSelected ? null : group.id)
                    }
                  >
                    <i className="direction-icon" aria-hidden="true">
                      {isPos ? "+" : isNeg ? "−" : ""}
                    </i>
                    {group.text}
                  </button>
                </td>

                <td className={weightTextClass}>
                  <span>{formatNumber(group.contribution, true)}</span>
                  <span className="weight-meter">
                    <i style={{ width: `${getMeterPercent(group.contribution)}%` }}></i>
                  </span>
                </td>

                {/* Rowspan column 4 for the total cell */}
                {index === 0 && (
                  <td className="total-cell" rowSpan={rowCount}>
                    <span className="total-sign">
                      {formattedTotal}
                    </span>
                    <span className="total-unit">điểm phần trăm</span>
                  </td>
                )}
              </tr>
            );
          })}

          {/* Remaining row if some groups were hidden */}
          {hasRemaining && (
            <tr className="attribution-row remaining-row">
              <td className="phrase-cell">
                <span className="remaining-label">
                  Các từ còn lại ({hiddenGroups.length} từ)
                </span>
                <button
                  type="button"
                  className="button-plain text-action"
                  style={{ fontSize: "0.875rem", padding: "2px 6px" }}
                  onClick={() => setShowAllGroups(true)}
                >
                  Xem đủ
                </button>
              </td>
              <td className="weight-cell muted-text">
                <span>{formatNumber(hiddenSum, true)}</span>
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {showAllGroups && groups.length > 6 && (
        <div style={{ padding: "8px 20px", textAlign: "right" }}>
          <button
            type="button"
            className="button-plain"
            style={{ fontSize: "0.875rem" }}
            onClick={() => setShowAllGroups(false)}
          >
            Thu gọn lại 6 từ chính
          </button>
        </div>
      )}

      <div className="calculation-footer">
        <span className="weight-unit-note">
          Đơn vị trọng số: điểm phần trăm ·
          {isPolarity
            ? " Đang xem: cân bằng tích cực/tiêu cực"
            : ` Đang xem: đóng góp cho nhãn ${targetLabelName || "dự đoán"}`}
        </span>

        <details className="method-details">
          <summary>
            Cách tính tổng <span aria-hidden="true">+</span>
          </summary>
          <div>
            <strong>
              Điểm nền ({formatNumber(baselineValue, true)}) + Tổng đóng góp (
              {formattedTotal}) = {formatNumber(targetValue)} điểm %
            </strong>
            <p>
              Tổng đóng góp là tổng các trọng số trong bảng. Cộng với điểm nền sẽ
              đạt điểm mục tiêu của mô hình trước khi làm tròn.
            </p>
            <p>
              Ước lượng Permutation Shapley cục bộ ({method.completed_permutations} hoán vị,
              FP32 CPU eval). Sai số cộng dồn: {" "}
              {residual <= 1e-6 ? "0,0000" : residual.toExponential(2)}.
            </p>
            <p>Thanh đo so độ lớn từng nhóm với nhóm mạnh nhất. Số được làm tròn khi hiển thị.
              Kết quả phụ thuộc cách nhóm và điểm nền khi che token, không phải kết luận nhân quả.</p>
          </div>
        </details>
      </div>
    </div>
  );
};
