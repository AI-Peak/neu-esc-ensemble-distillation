import React, { useState } from "react";
import type { NetworkResponse, NetworkNode } from "./types";

interface TermNetworkProps {
  network: NetworkResponse | null;
  loading: boolean;
  onFilterEvidence: (type: "node" | "edge" | "community", id: string, label: string) => void;
}

export const TermNetwork: React.FC<TermNetworkProps> = ({
  network,
  loading,
  onFilterEvidence,
}) => {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedCommunityId, setSelectedCommunityId] = useState<number | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="network-surface" role="status" style={{ padding: "40px", textAlign: "center" }}>
        <p className="chart-note">Đang xây dựng mạng đồng xuất hiện từ ngữ...</p>
      </div>
    );
  }

  if (!network || network.nodes.length === 0) {
    return (
      <div className="network-surface" style={{ padding: "40px", textAlign: "center" }}>
        <p className="chart-note">
          Chưa có quan hệ từ ngữ đủ dữ liệu trong các phản hồi có nhãn cảm xúc.
        </p>
      </div>
    );
  }

  const { nodes, edges, communities } = network;
  const nodeMap = new Map<string, NetworkNode>(nodes.map((n) => [n.id, n]));

  // Selected node details
  const selectedNode = selectedNodeId ? nodeMap.get(selectedNodeId) : null;
  const selectedCommunity =
    selectedCommunityId !== null
      ? communities.find((c) => c.id === selectedCommunityId)
      : null;

  const selectedEdge = selectedEdgeId ? edges.find((edge) => edge.id === selectedEdgeId) : null;

  // Max count for scaling node radius
  const maxCount = Math.max(...nodes.map((n) => n.count), 1);
  const getNodeRadius = (count: number) => {
    return 6 + (count / maxCount) * 16;
  };

  const handleSelectNode = (nodeId: string | null) => {
    setSelectedNodeId(nodeId);
    setSelectedCommunityId(null);
    setSelectedEdgeId(null);
  };

  const handleSelectCommunity = (commId: number | null) => {
    setSelectedCommunityId(commId);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
  };

  const handleReset = () => {
    setSelectedNodeId(null);
    setSelectedCommunityId(null);
    setSelectedEdgeId(null);
  };

  const handleShowEvidence = () => {
    if (selectedNode) {
      onFilterEvidence("node", selectedNode.id, `Từ “${selectedNode.label}” (${selectedNode.count} phản hồi)`);
    } else if (selectedCommunity) {
      onFilterEvidence("community", String(selectedCommunity.id), `Nhóm từ “${selectedCommunity.label}” (${selectedCommunity.count} phản hồi)`);
    } else if (selectedEdge) {
      onFilterEvidence("edge", selectedEdge.id, `Liên kết ${nodeMap.get(selectedEdge.source)?.label} – ${nodeMap.get(selectedEdge.target)?.label} (${selectedEdge.weight} phản hồi)`);
    }
  };

  return (
    <div className="network-surface">
      <div className="network-canvas">
        <div className="graph-key">
          <span>Kích thước: số phản hồi</span>
          <span>Liên kết: 5 vị trí token liên tiếp, cùng câu</span>
        </div>

        {/* Mobile dropdown term picker */}
        <label className="mobile-term-picker" htmlFor="mobile-term">
          <span>Chọn cụm từ</span>
          <select
            id="mobile-term"
            value={selectedNodeId || ""}
            onChange={(e) => handleSelectNode(e.target.value || null)}
          >
            <option value="">Tất cả cụm từ ({nodes.length} từ)</option>
            {nodes.map((n) => (
              <option key={n.id} value={n.id}>
                {n.label} ({n.count} phản hồi)
              </option>
            ))}
          </select>
        </label>

        <svg
          id="term-network"
          viewBox="0 0 760 430"
          aria-label="Mạng đồng xuất hiện từ ngữ"
        >
          {/* Edges */}
          {edges.map((e) => {
            const src = nodeMap.get(e.source);
            const tgt = nodeMap.get(e.target);
            if (!src || !tgt) return null;

            const isEdgeActive =
              (selectedNodeId && (e.source === selectedNodeId || e.target === selectedNodeId)) ||
              (selectedCommunityId !== null &&
                src.community === selectedCommunityId &&
                tgt.community === selectedCommunityId);

            const isEdgeDim =
              (selectedNodeId && !isEdgeActive) ||
              (selectedCommunityId !== null && !isEdgeActive);

            let edgeClass = "graph-edge";
            if (isEdgeActive) edgeClass += " active";
            if (isEdgeDim) edgeClass += " dim";

            return (
              <g
                key={e.id}
                className={`graph-edge-button${selectedEdgeId === e.id ? " selected" : ""}`}
                role="button"
                tabIndex={0}
                aria-label={`Liên kết ${src.label} – ${tgt.label}: ${e.weight} phản hồi`}
                aria-pressed={selectedEdgeId === e.id}
                onClick={() => { setSelectedEdgeId(selectedEdgeId === e.id ? null : e.id); setSelectedNodeId(null); setSelectedCommunityId(null); }}
                onKeyDown={(event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); setSelectedEdgeId(selectedEdgeId === e.id ? null : e.id); setSelectedNodeId(null); setSelectedCommunityId(null); } }}
              >
              <line x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y} stroke="transparent" strokeWidth={16} />
              <line
                x1={src.x}
                y1={src.y}
                x2={tgt.x}
                y2={tgt.y}
                className={edgeClass}
                style={{
                  strokeWidth: Math.min(6, 1.2 + (e.weight - 1) * 0.8),
                }}
              />
              </g>
            );
          })}

          {/* Nodes */}
          {nodes.map((n) => {
            const comm = communities[n.community];
            const color = comm?.color ?? "#3d8361";
            const r = getNodeRadius(n.count);

            const isNodeSelected = selectedNodeId === n.id;
            const isNodeInComm =
              selectedCommunityId !== null && n.community === selectedCommunityId;
            const isDim =
              (selectedNodeId && !isNodeSelected && !edges.some(
                (e) =>
                  (e.source === selectedNodeId && e.target === n.id) ||
                  (e.target === selectedNodeId && e.source === n.id)
              )) ||
              (selectedCommunityId !== null && !isNodeInComm);

            let nodeClass = "graph-node";
            if (isNodeSelected || isNodeInComm) nodeClass += " selected";
            if (isDim) nodeClass += " dim";

            return (
              <g
                key={n.id}
                className={nodeClass}
                data-node={n.id}
                role="button"
                tabIndex={0}
                aria-label={`${n.label}: ${n.count} phản hồi`}
                aria-pressed={isNodeSelected}
                onKeyDown={(event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); handleSelectNode(isNodeSelected ? null : n.id); } }}
                transform={`translate(${n.x}, ${n.y})`}
                onClick={() => handleSelectNode(isNodeSelected ? null : n.id)}
                style={{ cursor: "pointer", pointerEvents: "all" }}
              >
                <circle
                  r={r}
                  fill={color}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleSelectNode(isNodeSelected ? null : n.id);
                  }}
                  style={{ cursor: "pointer", pointerEvents: "all" }}
                />
                <text
                  x={0}
                  y={r + 14}
                  textAnchor="middle"
                  style={{
                    fontSize: "14px",
                    fontWeight: isNodeSelected ? 700 : 500,
                  }}
                >
                  {n.label}
                </text>
              </g>
            );
          })}
        </svg>

        <div className="graph-controls">
          <button
            type="button"
            id="network-reset"
            aria-label="Bỏ chọn cụm từ trong mạng"
            onClick={handleReset}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 10a8 8 0 1 1 1 7M4 4v6h6" />
            </svg>
            Bỏ chọn
          </button>
        </div>
      </div>

      <aside className="network-sidebar">
        <h3>Các nhóm từ</h3>
        <div id="community-list" className="community-list">
          {communities.map((c) => {
            const isPressed = selectedCommunityId === c.id;
            return (
              <button
                type="button"
                key={c.id}
                className="community-button"
                aria-pressed={isPressed}
                onClick={() => handleSelectCommunity(isPressed ? null : c.id)}
              >
                <span
                  className="community-swatch"
                  style={{ background: c.color }}
                />
                <div>
                  <strong>{c.label}</strong>
                  <small>{c.count} phản hồi liên quan</small>
                </div>
              </button>
            );
          })}
        </div>

        <div className="network-insight">
          <span className="field-label">
            {selectedNode
              ? "Cụm từ được chọn"
              : selectedCommunity
              ? "Nhóm từ được chọn"
              : "Khám phá chi tiết"}
          </span>
          <strong id="selected-node-label">
            {selectedNode
              ? selectedNode.label
              : selectedCommunity
              ? selectedCommunity.label
              : selectedEdge ? `${nodeMap.get(selectedEdge.source)?.label} – ${nodeMap.get(selectedEdge.target)?.label}` : "Chọn cụm từ, liên kết hoặc nhóm từ"}
          </strong>
          <p id="selected-node-description">
            {selectedNode
              ? `Xuất hiện trong ${selectedNode.count} phản hồi.`
              : selectedCommunity
              ? `Bao gồm ${selectedCommunity.members.length} từ ngữ trong ${selectedCommunity.count} phản hồi.`
              : selectedEdge ? `${selectedEdge.weight} phản hồi có quan hệ này.` : "Chọn trên mạng hoặc dùng bàn phím để xem phản hồi liên quan."}
          </p>
          {(selectedNode || selectedCommunity || selectedEdge) && (
            <button
              type="button"
              id="show-node-evidence"
              className="text-action"
              onClick={handleShowEvidence}
            >
              Xem {selectedNode?.count ?? selectedCommunity?.count ?? selectedEdge?.weight} phản hồi liên quan{" "}
              <span aria-hidden="true">↗</span>
            </button>
          )}
        </div>

        <p className="network-note">Dùng {network.source_item_count} / {network.scope_item_count} phản hồi có nhãn trong phạm vi. </p>
        <p className="network-note">
          Nhóm màu là các thành phần liên thông của mạng, tách biệt với nhãn cảm xúc và chủ đề.
        </p>
      </aside>
    </div>
  );
};
