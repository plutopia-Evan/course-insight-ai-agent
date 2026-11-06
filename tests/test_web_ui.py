from io import BytesIO
import pandas as pd
from fastapi.testclient import TestClient
from api.main_api import app


def test_online_page_and_example_are_public_but_analysis_is_protected(monkeypatch):
    monkeypatch.setenv('SERVICE_API_KEY', 'local-ui-test')
    with TestClient(app) as client:
        response = client.get('/app')
        assert response.status_code == 200
        assert 'text/html' in response.headers['content-type']
        assert '生成课程复盘' in response.text
        assert 'localStorage' not in response.text
        assert 'local-ui-test' not in response.text
        assert 'no-store' in response.headers['cache-control']
        example = client.get('/app/example')
        frame = pd.read_excel(BytesIO(example.content))
        assert frame['学员编号'].str.startswith('DEMO').all()
        result = client.post('/analysis/batch', files={'files': ('合成示例课程_第01期.xlsx', example.content)})
        assert result.status_code == 401
