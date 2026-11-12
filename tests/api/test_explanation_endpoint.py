"""The retired endpoint cannot reactivate an outbound provider via legacy config."""
from fastapi.testclient import TestClient
import pytest

from services.api.main import create_app
from tests.support import TestOnlyRegistry


class NeverProvider:
    calls = 0

    async def explain(self, context):
        self.calls += 1
        raise AssertionError('The retired provider must never be called')


@pytest.mark.parametrize('legacy_kwarg', ['explanation_provider', 'explanation_service', None])
def test_explanation_is_gone_even_with_legacy_configuration(tmp_path, monkeypatch, legacy_kwarg):
    # Synthetic values only. Invalid old timeout must not be parsed at startup.
    monkeypatch.setenv('FEEDBACK_EXPLANATION_BASE_URL', 'https://unused.invalid')
    monkeypatch.setenv('FEEDBACK_EXPLANATION_API_KEY', 'synthetic-unused-value')
    monkeypatch.setenv('FEEDBACK_EXPLANATION_MODEL', 'unused-model')
    monkeypatch.setenv('FEEDBACK_EXPLANATION_TIMEOUT_SECONDS', 'invalid-obsolete-setting')
    provider = NeverProvider()
    kwargs = {legacy_kwarg: provider} if legacy_kwarg else {}
    with TestClient(create_app(tmp_path, registry=TestOnlyRegistry(), **kwargs)) as client:
        response = client.post('/api/v1/quick-analysis/retired-source/explanation',
                               json={'source_prediction_id': 'retired-prediction'})
        assert response.status_code == 410, response.text
        assert response.json()['code'] == 'EXPLANATION_DISABLED'
        assert 'reading' not in response.json()
        assert 'synthetic-unused-value' not in response.text
        assert provider.calls == 0
        assert client.get('/api/v1/health').status_code == 200


def test_retired_endpoint_preserves_origin_protection(tmp_path):
    with TestClient(create_app(tmp_path, registry=TestOnlyRegistry())) as client:
        response = client.post('/api/v1/quick-analysis/old/explanation',
                               json={'source_prediction_id': 'old'},
                               headers={'Origin': 'https://external.invalid'})
        assert response.status_code == 403
        assert response.json()['code'] == 'FORBIDDEN_ORIGIN'
