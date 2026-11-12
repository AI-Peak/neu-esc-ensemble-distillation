import React from "react";
import type { AttributionGroup } from "./types";

interface HighlightedFeedbackProps {
  text: string;
  groups: AttributionGroup[];
  selectedGroupId: string | null;
  onSelectGroup: (groupId: string | null) => void;
  targetKind?: "polarity_margin" | "label_score";
  targetLabelName?: string;
}

export const HighlightedFeedback: React.FC<HighlightedFeedbackProps> = ({
  text,
  groups,
  selectedGroupId,
  onSelectGroup,
  targetKind = "polarity_margin",
  targetLabelName = "",
}) => {
  // Sort groups by start_utf16
  const sortedGroups = [...groups].sort((a, b) => a.start_utf16 - b.start_utf16);

  // Render raw text interleaved with group buttons
  const elements: React.ReactNode[] = [];
  let lastUtf16 = 0;

  // Helper to slice text using UTF-16 offsets
  const sliceUtf16 = (start: number, end: number) => {
    // UTF-16 string slicing works directly with String.prototype.slice
    return text.slice(start, end);
  };

  sortedGroups.forEach((group, idx) => {
    if (group.start_utf16 > lastUtf16) {
      elements.push(
        <React.Fragment key={`plain-${idx}`}>
          {sliceUtf16(lastUtf16, group.start_utf16)}
        </React.Fragment>
      );
    }

    const isSelected = selectedGroupId === group.id;
    const isPolarity = targetKind === "polarity_margin";
    const isPositive = group.contribution > 0;
    const isNegative = group.contribution < 0;

    let markClass = "word-mark";
    if (isPolarity) {
      if (isPositive) markClass += " positive-mark";
      else if (isNegative) markClass += " negative-mark";
    } else {
      // label_score
      if (isPositive) markClass += " label-increase-mark";
      else if (isNegative) markClass += " label-decrease-mark";
    }

    elements.push(
      <button
        type="button"
        key={group.id}
        className={markClass}
        data-term={group.id}
        aria-pressed={isSelected}
        onClick={() => onSelectGroup(isSelected ? null : group.id)}
      >
        {sliceUtf16(group.start_utf16, group.end_utf16)}
      </button>
    );

    lastUtf16 = group.end_utf16;
  });

  if (lastUtf16 < text.length) {
    elements.push(
      <React.Fragment key="plain-end">
        {sliceUtf16(lastUtf16, text.length)}
      </React.Fragment>
    );
  }

  // Selected group details description
  const selectedGroup = groups.find((g) => g.id === selectedGroupId);
  let detailText = "Chọn cụm từ để đối chiếu với bảng.";
  if (selectedGroup) {
    const formattedSign =
      selectedGroup.contribution > 0
        ? `+${selectedGroup.contribution.toFixed(1).replace(".", ",")}`
        : `${selectedGroup.contribution.toFixed(1).replace(".", ",")}`;
    if (targetKind === "polarity_margin") {
      const direction = selectedGroup.contribution > 0 ? "nghiêng tích cực" : selectedGroup.contribution < 0 ? "nghiêng tiêu cực" : "không đổi điểm";
      detailText = `“${selectedGroup.text}” · ${formattedSign} điểm % · ${direction}`;
    } else {
      const direction = selectedGroup.contribution > 0 ? `tăng điểm ${targetLabelName}` : selectedGroup.contribution < 0 ? `giảm điểm ${targetLabelName}` : `không đổi điểm ${targetLabelName}`;
      detailText = `“${selectedGroup.text}” · ${formattedSign} điểm % · ${direction}`;
    }
  }

  return (
    <div className="quote-container">
      <div className="quote-text" style={{ whiteSpace: "pre-wrap" }}>
        {elements}
      </div>
      <div className="selection-detail" id="selection-detail" role="status">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="m8 13 5-5m-7 7-1 1a4 4 0 0 1-6-6l3-3a4 4 0 0 1 6 0m0 0 1-1a4 4 0 0 1 6 6l-3 3a4 4 0 0 1-6 0"
            transform="translate(5 1)"
          />
        </svg>
        <span>{detailText}</span>
      </div>
    </div>
  );
};
