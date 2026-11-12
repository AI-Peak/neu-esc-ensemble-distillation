import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.text_network import build_network
from tests.support import TestOnlyRegistry
from services.worker import Worker


def test_build_network_basic():
    items = [
        {"id": "1", "text": "Cổng đăng ký học phần rất chậm và báo lỗi liên tục."},
        {"id": "2", "text": "Đăng ký học phần gặp lỗi cổng, sinh viên không vào được."},
        {"id": "3", "text": "Giảng viên nhiệt tình, bài giảng dễ hiểu."},
        {"id": "4", "text": "Thầy cô rất nhiệt tình và hỗ trợ sinh viên chu đáo."},
    ]
    net = build_network(items, max_nodes=20, min_df=1)
    assert net["total_nodes"] > 0
    assert net["total_edges"] >= 0
    assert len(net["communities"]) > 0

    # Verify node structure
    for node in net["nodes"]:
        assert "id" in node
        assert "label" in node
        assert "count" in node
        assert "community" in node
        assert "x" in node
        assert "y" in node
        assert len(node["item_ids"]) > 0

    # Verify community structure
    for comm in net["communities"]:
        assert "id" in comm
        assert "label" in comm
        assert "color" in comm
        assert "count" in comm


def test_network_endpoint(tmp_path):
    registry = TestOnlyRegistry()
    app = create_app(tmp_path, registry)
    client = TestClient(app)

    # Create dataset
    ds = client.post(
        "/api/v1/datasets",
        json={
            "name": "Bộ thử nghiệm mạng từ",
            "profile": "neu",
            "items": [
                {"text": "Cổng đăng ký học phần báo lỗi."},
                {"text": "Đăng ký học phần rất chậm."},
                {"text": "Giảng viên nhiệt tình."},
            ],
        },
    ).json()
    ds_id = ds["id"]

    # Fetch network
    res = client.get(f"/api/v1/datasets/{ds_id}/network")
    assert res.status_code == 200
    data = res.json()
    assert data["dataset_id"] == ds_id
    assert "scope_token" in data
    assert "nodes" in data
    assert "edges" in data
    assert "communities" in data


def _network(client, worker, ds_id, **params):
    first=client.get(f'/api/v1/datasets/{ds_id}/network',params=params)
    assert first.status_code==200,first.text
    for _ in range(20):
        value=client.get(f'/api/v1/datasets/{ds_id}/network',params=params).json()
        if value['status'] in ('completed','failed'):
            return value
        worker.run_once()
    raise AssertionError('Network did not finish')


def test_network_membership_population_snapshot_and_pagination(tmp_path):
    app=create_app(tmp_path,TestOnlyRegistry());c=TestClient(app)
    worker=Worker(tmp_path,app.state.registry)
    ds=c.post('/api/v1/datasets',json=dict(name='Network invariant test',profile='neu',
        items=[dict(text='Wifi thư viện chậm nhưng nhân viên nhiệt tình.') for _ in range(31)])).json()['id']
    empty=_network(c,worker,ds)
    assert empty['scope_item_count']==31 and empty['source_item_count']==0 and empty['nodes']==[]
    c.post('/api/v1/analysis-runs',json=dict(dataset_id=ds))
    for _ in range(6): worker.run_once()
    graph=_network(c,worker,ds,label_source='ai')
    node=next(n for n in graph['nodes'] if n['id']=='wifi')
    assert node['count']==31
    endpoint='/api/v1/networks/'+graph['network_id']+'/evidence'
    query=dict(selection_type='node',selection_id='wifi',page_size=10)
    pages=[c.get(endpoint,params=dict(query,page=n)).json() for n in (1,2,3,4)]
    assert [len(p['items']) for p in pages]==[10,10,10,1]
    assert len({r['id'] for p in pages for r in p['items']})==31
    item=pages[0]['items'][0]
    c.patch('/api/v1/items/'+item['id']+'/text',json=dict(text='Thông báo mới.',expected_revision=1))
    stale=c.get(endpoint,params=query)
    assert stale.status_code==409 and stale.json()['code']=='SCOPE_CHANGED'
    new=_network(c,worker,ds,label_source='ai')
    assert new['network_id']!=graph['network_id'] and new['source_item_count']==30
    # A forged selection is rejected even if it names an existing item.
    forged=c.get('/api/v1/networks/'+new['network_id']+'/evidence',params=dict(selection_type='node',selection_id=item['id']))
    assert forged.status_code==422


def test_network_ai_effective_filters_and_worker_scope_conflict(tmp_path):
    registry=TestOnlyRegistry();app=create_app(tmp_path,registry);c=TestClient(app);worker=Worker(tmp_path,registry)
    ds=c.post('/api/v1/datasets',json=dict(name='Partial',profile='neu',items=[dict(text='Wifi thư viện chậm.'),dict(text='Máy tính mới.')])).json()['id']
    rows=c.get(f'/api/v1/datasets/{ds}/items').json()['items']
    c.put('/api/v1/items/'+rows[0]['id']+'/review',json=dict(task='sentiment',status='corrected',label_id=3,expected_revision=1,expected_review_revision=0))
    effective=_network(c,worker,ds,label_source='effective')
    ai=_network(c,worker,ds,label_source='ai')
    assert effective['source_item_count']==1 and ai['source_item_count']==0
    base=_network(c,worker,ds,label_source='effective',q='máy')
    assert base['source_item_count']==0 and base['filter_signature']!=effective['filter_signature']
    queued=c.get(f'/api/v1/datasets/{ds}/network',params=dict(label_source='effective',q='wifi')).json()
    c.patch('/api/v1/items/'+rows[0]['id']+'/text',json=dict(text='Mạng đã thay đổi.',expected_revision=1))
    worker.run_once()
    with app.state.store.connect() as db:
        state=db.execute('SELECT status,error_code FROM network_jobs WHERE id=?',(queued['network_id'],)).fetchone()
        assert tuple(state)==('failed','SCOPE_CHANGED')


def test_network_item_ids_subset_normalization_and_server_evidence_membership(tmp_path):
    registry = TestOnlyRegistry()
    app = create_app(tmp_path, registry)
    client, worker = TestClient(app), Worker(tmp_path, registry)
    dataset = client.post('/api/v1/datasets', json=dict(
        name='Authored subset network fixture', profile='neu',
        items=[dict(text='Wifi thư viện chậm nhưng nhân viên nhiệt tình.') for _ in range(3)]))
    assert dataset.status_code == 201
    dataset_id = dataset.json()['id']
    rows = client.get(f'/api/v1/datasets/{dataset_id}/items').json()['items']
    selected_ids = {rows[0]['id'], rows[1]['id']}
    excluded_id = rows[2]['id']
    assert client.post('/api/v1/analysis-runs', json=dict(dataset_id=dataset_id)).status_code == 202
    worker.run_once()

    full = _network(client, worker, dataset_id, label_source='ai')
    duplicate_reversed = ','.join([rows[1]['id'], rows[0]['id'], rows[1]['id']])
    subset = _network(client, worker, dataset_id, label_source='ai', item_ids=duplicate_reversed)
    equivalent = _network(client, worker, dataset_id, label_source='ai', item_ids=','.join(sorted(selected_ids)))
    assert full['status'] == subset['status'] == equivalent['status'] == 'completed'
    assert subset['network_id'] == equivalent['network_id']
    assert subset['filter_signature'] == equivalent['filter_signature'] != full['filter_signature']
    # Dataset snapshot tokens do not replace the identity of the base filters.
    assert subset['scope_token'] == full['scope_token']
    assert full['scope_item_count'] == full['source_item_count'] == 3
    assert subset['scope_item_count'] == subset['source_item_count'] == 2
    assert next(node for node in full['nodes'] if node['id'] == 'wifi')['count'] == 3
    wifi = next(node for node in subset['nodes'] if node['id'] == 'wifi')
    assert wifi['count'] == 2 and set(wifi['item_ids']) == selected_ids
    for collection in ('nodes', 'edges', 'communities'):
        assert subset[collection]
        assert all(excluded_id not in selection['item_ids'] for selection in subset[collection])

    endpoint = '/api/v1/networks/' + subset['network_id'] + '/evidence'
    for kind, selection in [('node', wifi), ('edge', subset['edges'][0]), ('community', subset['communities'][0])]:
        response = client.get(endpoint, params=dict(selection_type=kind, selection_id=str(selection['id'])))
        assert response.status_code == 200, response.text
        evidence = response.json()
        assert evidence['network_id'] == subset['network_id']
        assert evidence['filter_signature'] == subset['filter_signature']
        assert evidence['total'] == len(selection['item_ids'])
        assert {item['id'] for item in evidence['items']} == set(selection['item_ids']) <= selected_ids
