import type { Filters, Profile, Summary } from "./types";
import { activeJob, labelName } from "./types";
import { Badge } from "./ui";

const runStatusLabel: Record<string, string> = {
  queued: "Đang chờ",
  pending: "Đang chờ",
  running: "Đang phân tích",
  loading_model: "Đang nạp model",
  completed: "Hoàn tất",
  failed: "Có lỗi",
  cancelled: "Đã hủy",
  cancelling: "Đang hủy",
  interrupted: "Bị gián đoạn",
  partial: "Hoàn tất một phần",
  completed_with_errors: "Hoàn tất, có dòng lỗi",
};

export function TopicAttention({
  summary,
  profile,
  sentimentFilter,
  labelSource,
  running,
  onSelectTopicNegative,
}: {
  summary: Summary;
  profile: Profile;
  sentimentFilter: string;
  labelSource: Filters["label_source"];
  running: boolean;
  onSelectTopicNegative: (topicId: number, negativeLabelId: number) => void;
}) {
  const { attention } = summary;
  const isRunActive =
    running || (summary.run_status != null && activeJob(summary.run_status));
  const hasAbnormalRunStatus =
    summary.run_status != null &&
    summary.run_status !== "completed" &&
    !activeJob(summary.run_status);
  const unprocessedCount = Math.max(
    0,
    summary.total - summary.processed - summary.errors,
  );
  const hasUnprocessed = summary.total > 0 && unprocessedCount > 0;
  const showIncompleteNotice =
    isRunActive ||
    hasAbnormalRunStatus ||
    summary.errors > 0 ||
    (hasUnprocessed &&
      (summary.run_status !== null ||
        (attention.topics.length > 0 &&
          attention.eligible_count < attention.filtered_count)));

  const statusBadgeText = isRunActive
    ? "Kết quả tạm thời"
    : summary.run_status != null && summary.run_status !== "completed"
      ? (runStatusLabel[summary.run_status] ?? summary.run_status)
      : showIncompleteNotice
        ? "Kết quả một phần"
        : null;

  const showToxicColumn = attention.toxic_label_id !== null;
  const hasAnyNegative = attention.topics.some((row) => row.negative_count > 0);
  const hasMissingLabels =
    attention.missing_topic_count > 0 ||
    attention.missing_sentiment_with_topic_count > 0;

  return (
    <section className="attention-section" aria-labelledby="attention-heading">
      <div className="section-heading attention-header">
        <div>
          <h2 id="attention-heading">Chủ đề cần chú ý</h2>
          <p className="muted small">
            Tỷ lệ trong phạm vi bộ lọc hiện tại. Nguồn nhãn đang dùng:{" "}
            <strong>
              {labelSource === "ai"
                ? "Chỉ dự đoán AI gốc"
                : "Đã duyệt nếu có, còn lại AI"}
            </strong>
            .
          </p>
        </div>
        {statusBadgeText && <Badge tone="warning">{statusBadgeText}</Badge>}
      </div>

      {sentimentFilter !== "" && (
        <div className="notice warning small" role="status">
          <strong>
            Đang lọc cảm xúc; tỷ lệ không mô tả toàn bộ bộ phản hồi.
          </strong>
        </div>
      )}

      {showIncompleteNotice && (
        <div
          className={
            summary.errors > 0 || hasAbnormalRunStatus
              ? "notice warning small"
              : "notice small"
          }
          role="status"
        >
          <span>
            {isRunActive
              ? "Phiên phân tích đang chạy:"
              : summary.run_status != null && summary.run_status !== "completed"
                ? `Lần phân tích hiện ở trạng thái “${runStatusLabel[summary.run_status] ?? summary.run_status}”:`
                : "Phạm vi đang xem chưa hoàn tất đầy đủ:"}{" "}
            <strong>{attention.eligible_count}</strong>/{attention.filtered_count}{" "}
            dòng có đủ hai nhãn · {summary.processed}/{summary.total} dòng đã
            phân tích
            {summary.errors > 0 ? ` · ${summary.errors} dòng lỗi` : ""}
            {unprocessedCount > 0 ? ` · ${unprocessedCount} dòng chưa xử lý` : ""}
            .
          </span>
        </div>
      )}

      {attention.filtered_count > 0 && (
        <p className="muted small attention-denominator">
          Mẫu số: {attention.eligible_count}/{attention.filtered_count} dòng có
          đủ cả chủ đề và cảm xúc
          {attention.missing_topic_count > 0 &&
            ` · ${attention.missing_topic_count} dòng thiếu chủ đề`}
          {attention.missing_sentiment_with_topic_count > 0 &&
            ` · ${attention.missing_sentiment_with_topic_count} dòng có chủ đề nhưng thiếu cảm xúc`}
          {hasMissingLabels &&
            ". Nhãn tham chiếu không tự tính vào nguồn đang chọn"}
          .
        </p>
      )}

      <p className="muted small attention-rules">
        Sắp xếp giảm dần theo số phản hồi Tiêu cực (hòa theo số dòng có đủ hai
        nhãn, rồi mã chủ đề). Nhóm có n &lt; {attention.small_sample_threshold}{" "}
        gắn “Ít dữ liệu” (quy ước hiển thị, chưa phải kiểm định thống kê).
        {showToxicColumn &&
          " Nhãn Toxic được đếm tách riêng, không cộng vào Tiêu cực."}
      </p>

      {attention.topics.length === 0 ? (
        <div className="notice small">
          Chưa đủ nhãn để tính theo chủ đề. Chạy phân tích hoặc duyệt nhãn thủ
          công.
        </div>
      ) : (
        <>
          {!hasAnyNegative && (
            <div className="notice small" role="status">
              Chưa có phản hồi gán nhãn Tiêu cực trong phạm vi đang xem.
            </div>
          )}
          <div className="table-scroll attention-table">
            <table>
              <thead>
                <tr>
                  <th>Chủ đề</th>
                  <th className="num">Tiêu cực</th>
                  <th className="num">Có đủ hai nhãn</th>
                  <th className="num">Tỷ lệ tiêu cực</th>
                  {showToxicColumn && <th className="num">Toxic</th>}
                  <th className="action-col">Xem phản hồi</th>
                </tr>
              </thead>
              <tbody>
                {attention.topics.map((row) => {
                  const topicName = labelName(profile, "topic", row.topic_id);
                  const rateText =
                    row.negative_rate === null || row.eligible_count === 0
                      ? "—"
                      : `${row.negative_count}/${row.eligible_count} · ${(
                          row.negative_rate * 100
                        ).toLocaleString("vi-VN", {
                          minimumFractionDigits: 1,
                          maximumFractionDigits: 1,
                        })}%`;
                  return (
                    <tr key={row.topic_id}>
                      <td data-label="Chủ đề">
                        <div className="attention-topic-cell">
                          <span className="attention-topic-name">
                            {topicName}
                          </span>
                          {row.small_sample && (
                            <Badge tone="warning">Ít dữ liệu</Badge>
                          )}
                        </div>
                      </td>
                      <td className="num" data-label="Tiêu cực">
                        <span>{row.negative_count}</span>
                      </td>
                      <td className="num" data-label="Có đủ hai nhãn">
                        <span className="attention-eligible-value">
                          <span>{row.eligible_count}</span>
                          {row.missing_sentiment_count > 0 && (
                            <span className="muted small attention-missing-note">
                              (thiếu cảm xúc: {row.missing_sentiment_count})
                            </span>
                          )}
                        </span>
                      </td>
                      <td className="num" data-label="Tỷ lệ tiêu cực">
                        <span>{rateText}</span>
                      </td>
                      {showToxicColumn && (
                        <td className="num" data-label="Toxic">
                          <span>{row.toxic_count ?? 0}</span>
                        </td>
                      )}
                      <td className="action-col" data-label="Xem phản hồi">
                        <button
                          type="button"
                          className="attention-evidence-btn"
                          disabled={row.negative_count === 0}
                          aria-label={`Xem ${row.negative_count} phản hồi tiêu cực của chủ đề ${topicName}`}
                          onClick={() =>
                            onSelectTopicNegative(
                              row.topic_id,
                              attention.negative_label_id,
                            )
                          }
                        >
                          Xem {row.negative_count} phản hồi tiêu cực
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
