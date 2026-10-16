from fastapi.testclient import TestClient

from app.main import app
from app.routes.ui import INPUT_FOLDER_ENV_VAR

client = TestClient(app)


def _input_folder_tag(html: str) -> str:
    start = html.index('<input id="input-folder"')
    return html[start : html.index("/>", start)]


def test_index_does_not_prefill_a_machine_specific_input_folder(monkeypatch) -> None:
    monkeypatch.delenv(INPUT_FOLDER_ENV_VAR, raising=False)

    response = client.get("/")

    assert response.status_code == 200
    assert 'value=""' in _input_folder_tag(response.text)
    assert "/Users/" not in response.text


def test_index_prefills_the_input_folder_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv(INPUT_FOLDER_ENV_VAR, "~/clip-art/bundle-01")

    response = client.get("/")

    assert 'value="~/clip-art/bundle-01"' in _input_folder_tag(response.text)
