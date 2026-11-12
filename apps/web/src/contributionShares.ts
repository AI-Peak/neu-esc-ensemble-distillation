import type { AttributionGroup } from "./types";

// Only original groups belong here. The table's “Các từ còn lại” is a display
// aggregate, and baseline/target output are not contributions.
export function contributionDistribution(groups: AttributionGroup[]) {
  if (!groups.length || groups.some((group) => !Number.isFinite(group.contribution))) {
    throw new Error("Đóng góp không hợp lệ để tính tỷ trọng.");
  }
  const scale = Math.max(...groups.map((group) => Math.abs(group.contribution)));
  if (scale === 0) return null;
  // Scale before summing: even subnormal values and a P+N above Number.MAX_VALUE
  // yield finite ratios. This does not change the signed contributions or D.
  let positive = 0;
  let negative = 0;
  for (const { contribution } of groups) {
    if (contribution > 0) positive += contribution / scale;
    else negative -= contribution / scale;
  }
  const mass = positive + negative;
  const fractions = [positive / mass, negative / mass];
  // Round one side and use its integer complement: displayed tenths sum to 100%.
  const positiveTenths = Math.round(fractions[0] * 1000);
  const tenths = [positiveTenths, 1000 - positiveTenths];
  return fractions.map((fraction, index) => ({
    fraction,
    percent: (tenths[index] / 10).toFixed(1).replace(".", ","),
    negligible: fraction > 0 && tenths[index] === 0,
  }));
}
