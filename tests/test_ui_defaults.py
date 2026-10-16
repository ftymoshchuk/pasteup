import re

from fastapi.testclient import TestClient

from pasteup.main import app
from pasteup.routes.ui import INPUT_FOLDER_ENV_VAR

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


def test_static_assets_are_served_from_the_installed_package() -> None:
    assert client.get("/static/js/app.js").status_code == 200
    assert client.get("/static/css/styles.css").status_code == 200
    assert client.get("/static/favicon.svg").status_code == 200


def test_index_is_titled_pasteup() -> None:
    html = client.get("/").text

    assert "<title>Pasteup</title>" in html
    assert "<h1>Pasteup</h1>" in html


def test_fonts_are_bundled_so_the_page_works_offline() -> None:
    for font in ("caveat-latin-700.woff2", "patrick-hand-latin-400.woff2"):
        response = client.get(f"/static/fonts/{font}")

        assert response.status_code == 200
        assert response.content[:4] == b"wOF2"


def test_the_page_loads_nothing_from_other_sites() -> None:
    html = client.get("/").text
    css = client.get("/static/css/styles.css").text

    for reference in re.findall(r'(?:src|href)=["\']?([^"\'\s>]*)', html):
        assert reference.startswith(("/", "#")) and not reference.startswith("//"), reference
    for reference in re.findall(r'url\(\s*["\']?([^"\')\s]*)', css):
        assert reference.startswith(("../", "data:", "#")), reference
