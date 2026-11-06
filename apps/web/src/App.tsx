import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, post } from "./api";
import type { Dataset, Profile } from "./types";
import { date } from "./types";
import { Badge, Empty, ErrorNotice, Loading, Modal } from "./ui";
import { ImportDataset } from "./ImportDataset";
import { Workspace } from "./Workspace";
import { QuickAnalysis } from "./QuickAnalysis";
export type Notify = (text: string, error?: boolean) => void;
export default function App() {
  const client = useQueryClient();
  const [route, setRoute] = useState(location.hash.slice(1) || "/");
  const [quick, setQuick] = useState(false);
  const [message, setMessage] = useState<{
    text: string;
    error: boolean;
  } | null>(null);
  const profiles = useQuery({
    queryKey: ["profiles"],
    queryFn: () => api<Profile[]>("/profiles"),
    refetchInterval: 15000,
  });
  const datasets = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api<Dataset[]>("/datasets"),
  });
  useEffect(() => {
    const update = () => setRoute(location.hash.slice(1) || "/");
    addEventListener("hashchange", update);
    return () => removeEventListener("hashchange", update);
  }, []);
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(
      () => setMessage(null),
      message.error ? 15000 : 6500,
    );
    return () => clearTimeout(timer);
  }, [message]);
  const notify: Notify = (text, error = false) => setMessage({ text, error });
  const navigate = (path: string) => {
    location.hash = path;
    setMessage(null);
  };
  const selected = datasets.data?.find((d) => route === `/datasets/${d.id}`);
  const [search, setSearch] = useState("");
  const [manage, setManage] = useState<{
    dataset: Dataset;
    mode: "rename" | "copy" | "delete";
  } | null>(null);
  const [name, setName] = useState("");
  const [copyProfile, setCopyProfile] = useState("");
  const [busy, setBusy] = useState(false);
  const openManage = (dataset: Dataset, mode: "rename" | "copy" | "delete") => {
    setManage({ dataset, mode });
    setName(mode === "copy" ? `${dataset.name} (bản sao)` : dataset.name);
    setCopyProfile(dataset.profile);
  };
  async function saveManage() {
    if (!manage) return;
    setBusy(true);
    try {
      if (manage.mode === "delete") {
        await api(`/datasets/${manage.dataset.id}`, { method: "DELETE" });
        if (selected?.id === manage.dataset.id) navigate("/");
        notify("Đã xóa bộ phản hồi.");
      } else if (manage.mode === "rename") {
        await api(`/datasets/${manage.dataset.id}`, {
          method: "PATCH",
          body: JSON.stringify({ name: name.trim() }),
        });
        notify("Đã đổi tên bộ phản hồi.");
      } else {
        const created = await post<Dataset>(
          `/datasets/${manage.dataset.id}/copy`,
          { name: name.trim(), profile: copyProfile },
        );
        navigate(`/datasets/${created.id}`);
        notify("Đã sao chép văn bản và metadata sang bộ phản hồi mới.");
      }
      await client.invalidateQueries({ queryKey: ["datasets"] });
      setManage(null);
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <a
        className="skip-link"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main")?.focus();
        }}
      >
        Đến nội dung chính
      </a>
      <div className="app-shell">
        <aside className="sidebar">
          <a className="brand" href="#/" aria-label="NEU-ESC · Bộ phản hồi">
            <span className="brand-mark" aria-hidden="true">
              N
            </span>
            <span>
              NEU-ESC<small>Không gian phản hồi</small>
            </span>
          </a>
          <nav aria-label="Điều hướng chính">
            <a
              className={
                route === "/" ||
                route.startsWith("/datasets") ||
                route === "/new"
                  ? "selected"
                  : ""
              }
              href="#/"
            >
              <span aria-hidden="true">▤</span>Bộ phản hồi
            </a>
            <button onClick={() => setQuick(true)}>
              <span aria-hidden="true">⌁</span>Thử một câu
            </button>
            <a
              className={route === "/research" ? "selected" : ""}
              href="#/research"
            >
              <span aria-hidden="true">▥</span>Báo cáo nghiên cứu
            </a>
            <a className={route === "/help" ? "selected" : ""} href="#/help">
              <span aria-hidden="true">ⓘ</span>Trạng thái & hướng dẫn
            </a>
          </nav>
          <div className="sidebar-footer">
            <span className="local-dot" />
            Lưu trên máy của bạn
            <small>Văn bản và kết quả được lưu local.</small>
          </div>
        </aside>
        <div className="main-shell">
          <header className="topbar">
            <span>
              {selected
                ? "Bộ phản hồi / " + selected.name
                : route === "/new"
                  ? "Bộ phản hồi / Tạo mới"
                  : route === "/research"
                    ? "Báo cáo nghiên cứu"
                    : route === "/help"
                      ? "Trạng thái & hướng dẫn"
                      : "Bộ phản hồi"}
            </span>
            <span className="top-meta">NEU · UIT</span>
          </header>
          <main id="main" tabIndex={-1}>
            {profiles.isError ? (
              <ErrorNotice
                error={profiles.error}
                retry={() => void profiles.refetch()}
              />
            ) : profiles.isPending ? (
              <Loading text="Đang tải hệ nhãn…" />
            ) : route === "/new" ? (
              <ImportDataset
                profiles={profiles.data}
                onCancel={() => navigate("/")}
                onCreated={async (d) => {
                  await client.invalidateQueries({ queryKey: ["datasets"] });
                  navigate(`/datasets/${d.id}`);
                  notify(
                    d.skipped_count
                      ? `Đã nhập ${d.item_count} phản hồi và bỏ qua ${d.skipped_count} dòng lỗi.`
                      : "Đã nhập dữ liệu. Bạn có thể bắt đầu phân tích hoặc rà soát thủ công.",
                  );
                }}
              />
            ) : route === "/research" ? (
              <Research />
            ) : route === "/help" ? (
              <Help profiles={profiles.data} />
            ) : selected ? (
              <Workspace
                key={selected.id}
                dataset={selected}
                profile={profiles.data.find((p) => p.id === selected.profile)!}
                notify={notify}
                onManage={(mode) => openManage(selected, mode)}
              />
            ) : datasets.isError ? (
              <ErrorNotice
                error={datasets.error}
                retry={() => void datasets.refetch()}
              />
            ) : datasets.isPending ? (
              <Loading />
            ) : route.startsWith("/datasets/") ? (
              <Empty title="Không tìm thấy bộ phản hồi">
                <p>Bộ phản hồi này đã bị xóa hoặc đường dẫn không còn đúng.</p>
                <a className="button" href="#/">
                  Về danh sách
                </a>
              </Empty>
            ) : (
              <>
                <div className="page-heading">
                  <div>
                    <h1>Bộ phản hồi</h1>
                    <p>
                      Nhập dữ liệu, phân tích và rà soát trong cùng một nơi.
                    </p>
                  </div>
                  <button
                    className="primary"
                    data-testid="create-dataset"
                    onClick={() => navigate("/new")}
                  >
                    ＋ Tạo bộ phản hồi
                  </button>
                </div>
                {datasets.data.length === 0 ? (
                  <Empty title="Bắt đầu với bộ phản hồi đầu tiên">
                    <p>
                      Nhập tệp CSV hoặc dán các phản hồi tiếng Việt. Chọn hệ
                      nhãn phù hợp, kiểm tra dữ liệu rồi phân tích khi model sẵn
                      sàng.
                    </p>
                    <div className="inline-actions">
                      <button
                        className="primary"
                        onClick={() => navigate("/new")}
                      >
                        Tạo bộ phản hồi
                      </button>
                      <button onClick={() => setQuick(true)}>
                        Thử một câu
                      </button>
                    </div>
                    <p className="muted small">
                      Bạn vẫn có thể nhập và rà soát thủ công khi chưa cài
                      model.
                    </p>
                  </Empty>
                ) : (
                  <>
                    <div className="list-toolbar">
                      <label className="search">
                        <span className="sr-only">Tìm bộ phản hồi</span>
                        <input
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                          placeholder="Tìm theo tên bộ phản hồi…"
                        />
                      </label>
                      <span className="muted">
                        {datasets.data.length} bộ phản hồi
                      </span>
                    </div>
                    <div className="dataset-list">
                      {datasets.data
                        .filter((d) =>
                          d.name
                            .toLocaleLowerCase("vi")
                            .includes(search.toLocaleLowerCase("vi")),
                        )
                        .map((d) => (
                          <article className="dataset-row" key={d.id}>
                            <div className="dataset-icon" aria-hidden="true">
                              ▤
                            </div>
                            <div className="dataset-main">
                              <h2>
                                <a href={`#/datasets/${d.id}`}>{d.name}</a>
                              </h2>
                              <p>
                                {
                                  profiles.data.find((p) => p.id === d.profile)
                                    ?.name
                                }{" "}
                                <span aria-hidden="true">·</span> Nhập{" "}
                                {date(d.created_at)}
                              </p>
                            </div>
                            <div className="dataset-count">
                              <strong>
                                {d.item_count.toLocaleString("vi")}
                              </strong>
                              <span>phản hồi</span>
                            </div>
                            <div className="dataset-progress">
                              <span>
                                {d.processed_count}/{d.item_count} đã phân tích
                              </span>
                              <progress
                                value={d.processed_count}
                                max={d.item_count || 1}
                                aria-label={`Đã phân tích ${d.processed_count} trong ${d.item_count}`}
                              />
                              <small>
                                {d.reviewed_count} đã rà soát ·{" "}
                                {d.partial_review_count} một phần
                              </small>
                            </div>
                            <div className="row-actions">
                              <button
                                className="quiet"
                                aria-label={`Đổi tên ${d.name}`}
                                onClick={() => openManage(d, "rename")}
                              >
                                Đổi tên
                              </button>
                              <button
                                className="quiet"
                                aria-label={`Sao chép ${d.name}`}
                                onClick={() => openManage(d, "copy")}
                              >
                                Sao chép
                              </button>
                              <button
                                className="quiet danger-text"
                                aria-label={`Xóa ${d.name}`}
                                onClick={() => openManage(d, "delete")}
                              >
                                Xóa
                              </button>
                            </div>
                          </article>
                        ))}
                    </div>
                    {!datasets.data.some((d) =>
                      d.name.toLowerCase().includes(search.toLowerCase()),
                    ) && (
                      <p className="empty-inline">
                        Không có bộ phản hồi khớp với tên này.
                      </p>
                    )}
                  </>
                )}
              </>
            )}
          </main>
          <footer className="main-footer">
            NEU-ESC Feedback Workspace{" "}
            <span>
              Dự đoán hỗ trợ việc rà soát. Nhãn người duyệt được lưu riêng.
            </span>
          </footer>
        </div>
      </div>
      {message && (
        <div
          className={`toast ${message.error ? "error" : ""}`}
          role={message.error ? "alert" : "status"}
        >
          <span>{message.text}</span>
          <button
            className="icon-button"
            aria-label="Đóng thông báo"
            onClick={() => setMessage(null)}
          >
            ×
          </button>
        </div>
      )}
      {quick && profiles.data && (
        <QuickAnalysis
          profiles={profiles.data}
          datasets={datasets.data ?? []}
          onClose={() => setQuick(false)}
          notify={notify}
        />
      )}{" "}
      {manage && (
        <Modal
          title={
            manage.mode === "delete"
              ? "Xóa bộ phản hồi?"
              : manage.mode === "copy"
                ? "Sao chép bộ phản hồi"
                : "Đổi tên bộ phản hồi"
          }
          onClose={() => !busy && setManage(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void saveManage();
            }}
          >
            {manage.mode === "delete" ? (
              <p>
                Toàn bộ văn bản, kết quả và lịch sử rà soát của{" "}
                <strong>{manage.dataset.name}</strong> sẽ bị xóa. Thao tác này
                không thể hoàn tác.
              </p>
            ) : (
              <label>
                Tên bộ phản hồi
                <input
                  autoFocus
                  required
                  maxLength={160}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
            )}
            {manage.mode === "copy" && (
              <>
                <label>
                  Loại nội dung
                  <select
                    value={copyProfile}
                    onChange={(e) => setCopyProfile(e.target.value)}
                  >
                    {profiles.data?.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="muted">
                  Chỉ sao chép văn bản và metadata. Bộ mới dùng hệ nhãn đã chọn;
                  không mang theo dự đoán, nhãn tham chiếu hoặc nhãn đã duyệt.
                </p>
              </>
            )}
            <div className="dialog-actions">
              <button
                type="button"
                onClick={() => setManage(null)}
                disabled={busy}
              >
                Hủy
              </button>
              <button
                className={manage.mode === "delete" ? "danger" : "primary"}
                disabled={busy || (manage.mode !== "delete" && !name.trim())}
              >
                {busy
                  ? "Đang lưu…"
                  : manage.mode === "delete"
                    ? "Xóa vĩnh viễn"
                    : manage.mode === "copy"
                      ? "Tạo bản sao"
                      : "Lưu tên"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
function Research() {
  const result = useQuery({
    queryKey: ["research"],
    queryFn: () =>
      api<{
        rows: {
          dataset: string;
          backbone: string;
          setup: string;
          task: string;
          metric: string;
          mean: number;
          std: number;
          seeds: number;
          source: string;
        }[];
        note: string;
      }>("/research/summary"),
  });
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Báo cáo nghiên cứu</h1>
          <p>Bằng chứng thực nghiệm lịch sử từ báo cáo của dự án.</p>
        </div>
        <Badge>Tham khảo</Badge>
      </div>
      <div className="notice">
        Kết quả trung bình qua các seed không bảo đảm chất lượng của một câu
        hoặc model đang cài trên máy.
      </div>
      {result.isPending ? (
        <Loading />
      ) : result.isError ? (
        <ErrorNotice error={result.error} />
      ) : (
        <>
          <p>{result.data.note}</p>
          {result.data.rows.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {[
                      "Dataset",
                      "Backbone",
                      "Thiết lập",
                      "Tác vụ",
                      "Chỉ số",
                      "Trung bình",
                      "Độ lệch chuẩn",
                      "Số seed",
                      "Nguồn",
                    ].map((h) => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.data.rows.map((r, i) => (
                    <tr key={i}>
                      <td>{r.dataset}</td>
                      <td>{r.backbone}</td>
                      <td>{r.setup}</td>
                      <td>
                        {r.task === "sentiment"
                          ? "Cảm xúc"
                          : r.task === "topic"
                            ? "Chủ đề"
                            : r.task}
                      </td>
                      <td>
                        {r.metric.toLowerCase().includes("f1")
                          ? "Macro-F1"
                          : r.metric.toLowerCase().includes("acc")
                            ? "Accuracy"
                            : r.metric}
                      </td>
                      <td>
                        {r.mean.toLocaleString("vi-VN", {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                        %
                      </td>
                      <td>
                        ±{" "}
                        {r.std.toLocaleString("vi-VN", {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                        %
                      </td>
                      <td>{r.seeds}</td>
                      <td className="small">{r.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="Chưa có số liệu được xác minh">
              <p>Báo cáo sẽ xuất hiện khi có nguồn thực nghiệm phù hợp.</p>
            </Empty>
          )}
        </>
      )}
    </>
  );
}
function Help({ profiles }: { profiles: Profile[] }) {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () =>
      api<{ status: string; worker: { alive: boolean }; runtime: unknown }>(
        "/health",
      ),
    refetchInterval: 15000,
  });
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Trạng thái & hướng dẫn</h1>
          <p>Chuẩn bị dữ liệu và kiểm tra model trước khi phân tích.</p>
        </div>
      </div>
      <section className="section">
        <h2>Hệ thống local</h2>
        {health.isPending ? (
          <Loading />
        ) : health.isError ? (
          <ErrorNotice error={health.error} />
        ) : (
          <p>
            API: {health.data.status} · Worker:{" "}
            <Badge tone={health.data.worker.alive ? "success" : "warning"}>
              {health.data.worker.alive ? "Đang hoạt động" : "Chưa hoạt động"}
            </Badge>
          </p>
        )}
        {profiles.map((p) => (
          <div className="model-row" key={p.id}>
            <div>
              <h3>{p.name}</h3>
              <p>{p.description}</p>
              <details>
                <summary>Xem hệ nhãn</summary>
                <p>Cảm xúc: {p.sentiment.map((l) => l.name).join(", ")}.</p>
                <p>Chủ đề: {p.topic.map((l) => l.name).join(", ")}.</p>
              </details>
            </div>
            <div>
              <Badge tone={p.model.available ? "success" : "warning"}>
                {p.model.available ? "Model sẵn sàng" : "Chưa có model"}
              </Badge>
              <p className="small muted">
                {p.model.available
                  ? `${p.model.model_id} · ${p.model.model_version}`
                  : "Cần cài bộ model hợp lệ để phân tích."}
              </p>
              {!p.model.available && p.model.reason && (
                <details>
                  <summary>Chi tiết kỹ thuật</summary>
                  <p className="technical-reason small">{p.model.reason}</p>
                </details>
              )}
            </div>
          </div>
        ))}
      </section>
      <section className="section prose">
        <h2>Chuẩn bị CSV</h2>
        <p>
          Dùng UTF-8 (có hoặc không có BOM), tối đa 5 MB và 500 phản hồi. Mỗi
          phản hồi dài tối đa 5.000 ký tự. Chọn đúng cột văn bản ở bước xem
          trước. Phản hồi có dấu xuống dòng phải được đặt trong ô CSV có dấu
          ngoặc kép.
        </p>
        <p>
          Dán văn bản: mỗi dòng không trống là một phản hồi. Dòng trùng được giữ
          vì có thể đến từ nhiều người khác nhau.
        </p>
        <h2>Hiểu nguồn nhãn</h2>
        <p>
          Nhãn AI là dự đoán gốc. Nhãn đã duyệt do bạn xác nhận hoặc sửa độc lập
          cho cảm xúc và chủ đề. Nhãn tham chiếu chỉ được lưu khi bạn xác nhận
          nguồn và ánh xạ rõ ràng lúc nhập CSV.
        </p>
        <p>
          “Nhãn hiệu lực” dùng nhãn đã duyệt nếu có, còn lại dùng AI theo từng
          tác vụ. Tham chiếu không tự trở thành nhãn hiệu lực. Sửa văn bản tạo
          phiên bản mới và không sao chép nhãn cũ.
        </p>
        <h2>Điểm mô hình & rà soát</h2>
        <p>
          Điểm mô hình là softmax chưa hiệu chuẩn, không phải xác suất dự đoán
          đúng. Hàng chờ cần rà soát gồm câu chưa duyệt đủ hai tác vụ, lỗi, cắt
          ngắn hoặc điểm cao nhất dưới 0,6. Đây là quy tắc hỗ trợ, không phát
          hiện mọi lỗi.
        </p>
        <p>
          Model có thể cắt phản hồi dài theo giới hạn token. Dấu cảnh báo cho
          biết model chưa đọc toàn bộ văn bản. Việc sửa nhãn được lưu riêng và
          không tự huấn luyện lại model.
        </p>
        <h2>Lưu trữ</h2>
        <p>
          Bộ phản hồi được lưu bền ở máy chạy API. Thử một câu được lưu tạm và
          dọn sau 15 phút kể từ khi tác vụ kết thúc. Xuất CSV tạo bản chụp cố
          định với văn bản, dự đoán, tham chiếu, nhãn duyệt và phiên bản model
          tách riêng.
        </p>
      </section>
    </>
  );
}
