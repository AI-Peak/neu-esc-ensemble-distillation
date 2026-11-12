"""Deterministic word co-occurrence network extraction for Vietnamese feedback.

Extracts meaningful compound terms, windowed co-occurrences, deterministic community
clusters, and evidence memberships without LLMs.
"""
from __future__ import annotations

import collections
import math
import re
from typing import Any
import unicodedata

STOPWORDS_V1 = {
    "và", "hoặc", "nhưng", "thì", "mà", "là", "của", "ở", "tại", "trong", "cho",
    "với", "để", "do", "vì", "nếu", "các", "những", "một", "này", "đó", "kia",
    "có", "được", "bị", "ra", "vào", "lên", "xuống", "đến", "tới", "về", "theo",
    "qua", "lại", "rất", "quá", "lắm", "nhiều", "ít", "đã", "đang", "sẽ", "cũng",
    "vẫn", "cứ", "chỉ", "thôi", "ạ", "nhé", "nha", "nào", "gì", "ai", "đâu",
    "sao", "thế", "vậy", "rồi", "khi", "lúc", "từ", "hơn", "như", "nhất", "luôn",
    "từng", "vừa", "mới", "hãy", "chớ", "đừng", "cả", "mọi", "mỗi", "nên", "phải",
    "thấy", "biết", "nghĩ", "cho_rằng", "cảm_thấy", "em", "mình", "bạn", "ạ"
}
STOPWORDS_V2 = STOPWORDS_V1 - {'không', 'chẳng', 'chưa', 'đừng', 'chớ'}
NETWORK_VERSION = 'cooccurrence-v2'

COMMUNITY_COLORS = [
    "#3d8361",  # Dark Teal / Forest
    "#34749f",  # Blue
    "#a65d3f",  # Terracotta / Amber
    "#7e57c2",  # Purple
    "#5c6bc0",  # Indigo
    "#8d6e63",  # Brown
]


def clean_tokens(sentence: str) -> list[str]:
    """Compatibility helper; graph windows use positioned_tokens instead."""
    return [term for _, term in positioned_tokens(sentence)]


def positioned_tokens(sentence: str) -> list[tuple[int, str]]:
    """Keep the original segmented-token index before removing stopwords."""
    import underthesea
    segmented = underthesea.word_tokenize(sentence, format="text")
    tokens = segmented.split()
    valid = []
    for index, t in enumerate(tokens):
        clean = unicodedata.normalize('NFC', t).casefold()
        # Drop pure punctuation or single-character tokens.
        if not any(unicodedata.category(ch)[0] in ('L', 'N') for ch in clean):
            continue
        if len(clean) <= 1:
            continue
        if clean in STOPWORDS_V2:
            continue
        valid.append((index, clean))
    return valid


def build_network(
    items: list[dict],
    max_nodes: int = 40,
    min_df: int = 1,
    window_size: int = 5,
    max_edges: int = 120,
) -> dict[str, Any]:
    """Build a deterministic co-occurrence network from a list of feedback items.

    Each item is a dict with at least 'id' and 'text'.
    """
    if (any(type(value) is not int for value in (max_nodes, min_df, window_size, max_edges))
            or not 1 <= max_nodes <= 60 or not 1 <= min_df or not 2 <= window_size <= 20
            or not 1 <= max_edges <= 150):
        raise ValueError('Network limits are invalid')
    node_items = collections.defaultdict(set)
    edge_items = collections.defaultdict(set)
    source_ids = set()

    for item in items:
        item_id = str(item.get("id", ""))
        text = str(item.get("text", ""))
        if not text.strip():
            continue
        if not item_id:
            raise ValueError('Network items require a stable ID')
        source_ids.add(item_id)

        # Split sentences
        sentences = re.split(r"[.!?\n\r]+", text)
        item_seen_terms = set()
        item_seen_edges = set()

        for s in sentences:
            if not s.strip():
                continue
            terms = positioned_tokens(s)
            for _, t in terms:
                item_seen_terms.add(t)

            # Windowed co-occurrence
            n = len(terms)
            for i in range(n):
                position1, t1 = terms[i]
                for j in range(i + 1, n):
                    position2, t2 = terms[j]
                    if position2 - position1 >= window_size:
                        break
                    if t1 != t2:
                        edge = (min(t1, t2), max(t1, t2))
                        item_seen_edges.add(edge)

        for t in item_seen_terms:
            node_items[t].add(item_id)
        for e in item_seen_edges:
            edge_items[e].add(item_id)

    # Filter nodes by document frequency
    sorted_nodes = sorted(
        [t for t, ids in node_items.items() if len(ids) >= min_df],
        key=lambda t: (-len(node_items[t]), t),
    )
    selected_nodes = sorted_nodes[:max_nodes]
    selected_set = set(selected_nodes)

    # Filter edges between selected nodes
    filtered_edges = {}
    for (t1, t2), ids in sorted(edge_items.items(), key=lambda entry: (-len(entry[1]), entry[0])):
        if t1 in selected_set and t2 in selected_set:
            filtered_edges[(t1, t2)] = ids
            if len(filtered_edges) >= max_edges:
                break
    # A graph without supported relations has an honest empty state. Isolated
    # terms do not imply relationships, and would otherwise clutter the canvas.
    linked = {term for edge in filtered_edges for term in edge}
    selected_nodes = [term for term in selected_nodes if term in linked]

    # Adjacency for community detection
    adj = collections.defaultdict(set)
    for t1, t2 in filtered_edges:
        adj[t1].add(t2)
        adj[t2].add(t1)

    # Deterministic connected components, with no modularity optimization.
    visited = set()
    raw_communities = []
    for node in selected_nodes:
        if node not in visited:
            comp = []
            queue = [node]
            visited.add(node)
            while queue:
                curr = queue.pop(0)
                comp.append(curr)
                # Sort neighbors for deterministic traversal
                for neighbor in sorted(adj[curr]):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            raw_communities.append(sorted(comp, key=lambda term: (-len(node_items[term]), term)))

    # Sort communities by size descending
    raw_communities.sort(key=lambda c: (-len(c), tuple(c)))

    # Assign community IDs and build community objects
    community_for_node = {}
    community_list = []
    for c_idx, members in enumerate(raw_communities):
        # 2-3 most frequent representative terms
        rep_terms = sorted(members, key=lambda t: (-len(node_items[t]), t))[:3]
        label = " · ".join(t.replace("_", " ") for t in rep_terms)
        color = COMMUNITY_COLORS[c_idx % len(COMMUNITY_COLORS)]

        # Unique items belonging to any member in this community
        comm_item_ids = set()
        for m in members:
            community_for_node[m] = c_idx
            comm_item_ids.update(node_items[m])

        community_list.append({
            "id": c_idx,
            "label": label,
            "color": color,
            "count": len(comm_item_ids),
            "members": members,
            "item_ids": sorted(comm_item_ids),
        })

    # Layout nodes deterministically on a 760x430 canvas
    # Group nodes by community in concentric/radial clusters
    node_objects = []
    width, height = 760, 430
    num_comms = max(1, len(community_list))

    for c_info in community_list:
        c_idx = c_info["id"]
        members = c_info["members"]
        # Center of community
        angle_c = (2 * math.pi * c_idx) / num_comms
        cx = width / 2 + (width * 0.28) * math.cos(angle_c) if num_comms > 1 else width / 2
        cy = height / 2 + (height * 0.28) * math.sin(angle_c) if num_comms > 1 else height / 2

        for m_idx, term in enumerate(members):
            # A deterministic sunflower fills the available area. The former
            # 25/45/65px circles stacked dozens of labels in a tiny center.
            angle_m = m_idx * math.pi * (3 - math.sqrt(5))
            radial = math.sqrt((m_idx + .5) / len(members))
            radius_x = width * .38 if num_comms == 1 else min(150, width * .30 / math.sqrt(num_comms))
            radius_y = height * .34 if num_comms == 1 else min(100, height * .28 / math.sqrt(num_comms))
            x = cx + radius_x * radial * math.cos(angle_m)
            y = cy + radius_y * radial * math.sin(angle_m)
            # Bound inside canvas
            x = max(40.0, min(width - 40.0, x))
            y = max(40.0, min(height - 40.0, y))

            term_ids = sorted(node_items[term])
            node_objects.append({
                "id": term,
                "label": term.replace("_", " "),
                "count": len(term_ids),
                "community": c_idx,
                "x": round(x, 1),
                "y": round(y, 1),
                "item_ids": term_ids,
            })

    edge_objects = []
    for (t1, t2), ids in sorted(filtered_edges.items(), key=lambda e: (-len(e[1]), e[0])):
        edge_objects.append({
            'id': t1 + '::' + t2,
            "source": t1,
            "target": t2,
            "weight": len(ids),
            "item_ids": sorted(ids),
        })

    return {
        'network_version': NETWORK_VERSION,
        'params': {'window_size': window_size, 'max_distance': window_size - 1,
                   'window_unit': 'segmented_token_positions', 'sentence_boundaries': 'punctuation_or_linebreak',
                   'stopwords_version': 'v2', 'community_method': 'connected_components',
                   'layout_method': 'deterministic_sunflower_v2',
                   'max_nodes': max_nodes, 'max_edges': max_edges, 'min_df': min_df},
        "nodes": node_objects,
        "edges": edge_objects,
        "communities": community_list,
        "total_nodes": len(node_objects),
        "total_edges": len(edge_objects),
        "source_item_count": len(source_ids),
    }
