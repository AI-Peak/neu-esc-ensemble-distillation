import React, { useState, useMemo } from "react";
import type { AttributionResponse } from "./types";
import { HighlightedFeedback } from "./HighlightedFeedback";

interface AttributionTableProps {
  rawText: string;
  attribution: AttributionResponse;
  targetLabelName?: string;
}

export const AttributionTable: React.FC<AttributionTableProps> = ({ rawText, attribution, targetLabelName = "" }) => {
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [showAllGroups, setShowAllGroups] = useState(false);
  const { groups, aggregate, method } = attribution;
  const targetKind = method?.target.kind ?? "polarity_margin";
  const isPolarity = targetKind === "polarity_margin";
  // The full snapshot owns the scale, totals and top-six selection at every size.
  const { ordered, topIds, maxAbsWeight } = useMemo(() => ({
    ordered: [...groups].sort((a, b) => a.start_utf16 - b.start_utf16),
    topIds: new Set([...groups].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
      .slice(0, 6).map(g => g.id)),
    maxAbsWeight: Math.max(...groups.map(g => Math.abs(g.contribution))) || 1,
  }), [groups]);
  const visibleGroups = showAllGroups ? ordered : ordered.filter(g => topIds.has(g.id));
  const hiddenGroups = ordered.filter(g => !topIds.has(g.id));
  const hiddenSum = hiddenGroups.reduce((sum, g) => sum + g.contribution, 0);
  const midpoint = Math.ceil(visibleGroups.length / 2);
  const columns = [visibleGroups.slice(0, midpoint), visibleGroups.slice(midpoint)];
  const collapse = () => {
    if (selectedGroupId && !topIds.has(selectedGroupId)) setSelectedGroupId(null);
    setShowAllGroups(false);
  };
  // Only validated completed payloads reach this component.
  if (!aggregate || !method) return null;
  const { total_contribution: totalValue, baseline_value: baselineValue,
    target_output: targetValue, additivity_residual: residual } = aggregate;
  const formatNumber = (val: number, forceSign = false) => {
    const formatted = Math.abs(val).toFixed(1).replace(".", ",");
    return val > 0 ? (forceSign ? `+${formatted}` : formatted) : val < 0 ? `−${formatted}` : "0,0";
  };
  const formattedTotal = formatNumber(totalValue, true);

  return (
    <div id="attribution-content" className="attribution-surface">
      <HighlightedFeedback text={rawText} groups={visibleGroups} selectedGroupId={selectedGroupId}
        onSelectGroup={setSelectedGroupId} targetKind={targetKind} targetLabelName={targetLabelName} />
      <div className="contribution-list-heading">
        <span className="weight-unit-note">
          Đơn vị: điểm phần trăm · {isPolarity ? "Đang xem: cân bằng tích cực/tiêu cực"
            : `Đang xem: đóng góp cho nhãn ${targetLabelName || "dự đoán"}`}
        </span>
        {showAllGroups && groups.length > 6 && (
          <button type="button" className="button-plain" aria-controls="phrase-contributions" aria-expanded={true} onClick={collapse}>Thu gọn</button>
        )}
      </div>
      <div id="phrase-contributions" className="contribution-columns" role="group" aria-label="Đóng góp của các cụm từ">
        {columns.map((column, index) => (
          <ul className="contribution-column" key={index}>
            {column.map(group => {
              const selected = selectedGroupId === group.id;
              const tone = group.contribution === 0 ? "zero-text" : isPolarity
                ? (group.contribution > 0 ? "positive-text" : "negative-text")
                : (group.contribution > 0 ? "label-increase-text" : "label-decrease-text");
              return (
                <li key={group.id} className={`attribution-row ${selected ? "selected" : ""}`} data-row={group.id}>
                  <button type="button" className={`phrase-button ${tone}`} data-term={group.id}
                    aria-pressed={selected} onClick={() => setSelectedGroupId(selected ? null : group.id)}>
                    <span className="phrase-text">{group.text}</span>
                    <span className="weight-meter" aria-hidden="true"><i style={{ width: `${Math.min(100, Math.abs(group.contribution) / maxAbsWeight * 100)}%` }} /></span>
                    <span className="contribution-value">{formatNumber(group.contribution, true)}<span className="sr-only"> điểm phần trăm</span></span>
                  </button>
                </li>
              );
            })}
          </ul>
        ))}
      </div>
      {!showAllGroups && hiddenGroups.length > 0 && (
        <div className="remaining-row">
          <span>Các cụm từ còn lại ({hiddenGroups.length}): <strong>{formatNumber(hiddenSum, true)}</strong> điểm phần trăm</span>
          <button type="button" className="button-plain" aria-controls="phrase-contributions" aria-expanded={false} onClick={() => setShowAllGroups(true)}>
            Xem tất cả {groups.length} cụm từ
          </button>
        </div>
      )}
      <div className="calculation-footer">
        <p className="contribution-total">Tổng đóng góp: <strong className="total-sign">{formattedTotal}</strong> điểm phần trăm</p>
        {showAllGroups && groups.length > 6 && (
          <button type="button" className="button-plain collapse-action" aria-controls="phrase-contributions" aria-expanded={true} onClick={collapse}>Thu gọn</button>
        )}
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
              Tổng đóng góp là tổng các trọng số trong toàn bộ danh sách. Cộng với điểm nền sẽ
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
