"""Network mechanics only; no model predictions or live dataset are involved."""
import json
import os
from pathlib import Path
import subprocess
import sys

from services.text_network import build_network


def test_window_uses_positions_before_filtering_stopwords():
    network = build_network([{'id': 'i', 'text': 'Wifi ở trong các phòng thì vẫn cứ bị chậm.'}])
    assert not any({edge['source'], edge['target']} == {'wifi', 'chậm'} for edge in network['edges'])


def test_five_token_window_means_max_distance_four(monkeypatch):
    import underthesea
    monkeypatch.setattr(underthesea, 'word_tokenize', lambda text, format: text)
    network = build_network([{'id': 'i', 'text': 'wifi rất quá ở trong chậm'}])
    assert not any({edge['source'], edge['target']} == {'wifi', 'chậm'} for edge in network['edges'])
    close = build_network([{'id': 'i', 'text': 'wifi rất quá ở chậm'}])
    assert any({edge['source'], edge['target']} == {'wifi', 'chậm'} for edge in close['edges'])


def test_network_metadata_is_honest_and_limits_edges():
    network = build_network([{'id': 'i', 'text': 'wifi học_phí giảng_viên dịch_vụ thư_viện tốt nhanh chậm sạch tiện'}])
    assert network['network_version'] == 'cooccurrence-v2'
    assert network['params']['community_method'] == 'connected_components'
    assert network['params']['max_distance'] == 4
    assert len(network['edges']) <= 120


def test_membership_is_per_feedback_and_community_count_is_union(monkeypatch):
    import services.text_network as module
    monkeypatch.setattr(module, 'positioned_tokens', lambda text: list(enumerate(text.split())))
    items = [{'id': 'a', 'text': 'wifi chậm wifi chậm'},
             {'id': 'b', 'text': 'wifi tốt'}, {'id': 'c', 'text': 'thư_viện tốt'}]
    network = build_network(items)
    nodes = {node['id']: node for node in network['nodes']}
    edge = next(edge for edge in network['edges'] if {edge['source'], edge['target']} == {'wifi', 'chậm'})
    assert edge['weight'] == 1 and edge['item_ids'] == ['a']
    assert nodes['wifi']['count'] == 2 and nodes['wifi']['item_ids'] == ['a', 'b']
    assert len(network['communities']) == 1
    community = network['communities'][0]
    assert community['count'] == 3 and community['item_ids'] == ['a', 'b', 'c']
    for edge in network['edges']:
        assert edge['id'] == edge['source'] + '::' + edge['target']
        assert set(edge['item_ids']) <= set(nodes[edge['source']]['item_ids']) & set(nodes[edge['target']]['item_ids'])


def test_never_connects_across_sentences_or_feedback(monkeypatch):
    import services.text_network as module
    monkeypatch.setattr(module, 'positioned_tokens', lambda text: list(enumerate(text.split())))
    network = build_network([{'id': 'a', 'text': 'wifi. chậm! học_phí\n cao'}, {'id': 'b', 'text': 'tốt'}])
    assert network['source_item_count'] == 2
    assert network['nodes'] == network['edges'] == network['communities'] == []


def test_node_edge_limits_preserve_membership_counts_and_repeatability(monkeypatch):
    import services.text_network as module
    monkeypatch.setattr(module, 'positioned_tokens', lambda text: list(enumerate(text.split())))
    text = ' '.join(f'term{i:02}' for i in range(60))
    items = [{'id': str(i), 'text': text} for i in range(3)]
    graph = build_network(items, max_nodes=40, max_edges=12, window_size=20)
    assert len(graph['nodes']) <= 40 and len(graph['edges']) == 12
    assert all(edge['weight'] == 3 and edge['item_ids'] == ['0', '1', '2'] for edge in graph['edges'])
    assert graph == build_network(list(reversed(items)), max_nodes=40, max_edges=12, window_size=20)
    for community in graph['communities']:
        assert community['count'] == 3


def test_hash_randomization_cannot_change_graph_layout_or_ties():
    script = """
import json
import services.text_network as module
module.positioned_tokens = lambda text: list(enumerate(text.split()))
items = [{'id': str(i), 'text': ' '.join(set(['wifi', 'chậm', 'giảng_viên', 'học_phí']))} for i in range(3)]
# Fix authored raw order; only internal set/dict order may vary.
for item in items: item['text'] = 'wifi chậm giảng_viên học_phí'
print(json.dumps(module.build_network(items), sort_keys=True))
"""
    root = Path(__file__).resolve().parents[1]
    outputs = []
    for seed in ('1', '72'):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONIOENCODING='utf-8')
        outputs.append(subprocess.check_output([sys.executable, '-c', script], cwd=root, env=env))
    assert outputs[0] == outputs[1]


def test_api_can_import_network_metadata_without_loading_nlp_or_encoder():
    script = "import sys; import services.text_network; assert not {'torch', 'transformers', 'underthesea'} & set(sys.modules)"
    subprocess.run([sys.executable, '-c', script], check=True, cwd=Path(__file__).resolve().parents[1])
