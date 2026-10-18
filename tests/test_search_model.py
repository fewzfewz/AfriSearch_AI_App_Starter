"""Choosing the search model: per-model settings and indexes built with another model."""
import pytest

from conftest import SOLAR_GUIDE, upload


@pytest.fixture
def search_model(app_env, monkeypatch):
    """Lets a test call set_embedder(); the original settings come back afterwards."""
    main, fake = app_env
    for name in ("EMBEDDER_ID", "QUERY_PREFIX", "PASSAGE_PREFIX", "MIN_SCORE", "INDEX_VERSION"):
        monkeypatch.setattr(main, name, getattr(main, name))
    for name in ("AFRISEARCH_QUERY_PREFIX", "AFRISEARCH_PASSAGE_PREFIX", "AFRISEARCH_MIN_SCORE"):
        monkeypatch.delenv(name, raising=False)

    def use(model_id):
        main.set_embedder(model_id)
        main.embedder = fake  # set_embedder() drops the loaded model; keep the fake one

    return use


def test_e5_models_get_prefixes_and_their_own_cutoff(search_model, app_env):
    main, _ = app_env
    search_model("intfloat/multilingual-e5-small")
    assert (main.QUERY_PREFIX, main.PASSAGE_PREFIX) == ("query: ", "passage: ")
    assert main.MIN_SCORE == 0.75
    assert "intfloat/multilingual-e5-small" in main.INDEX_VERSION


def test_other_models_get_no_prefixes(search_model, app_env):
    main, _ = app_env
    search_model("sentence-transformers/all-MiniLM-L6-v2")
    assert (main.QUERY_PREFIX, main.PASSAGE_PREFIX) == ("", "")
    assert main.MIN_SCORE == 0.2


def test_settings_can_be_overridden_with_environment_variables(search_model, app_env, monkeypatch):
    main, _ = app_env
    monkeypatch.setenv("AFRISEARCH_MIN_SCORE", "0.5")
    monkeypatch.setenv("AFRISEARCH_QUERY_PREFIX", "Q: ")
    search_model("intfloat/multilingual-e5-small")
    assert main.MIN_SCORE == 0.5
    assert main.QUERY_PREFIX == "Q: "


def test_prefixes_are_added_when_embedding(client, search_model, app_env):
    main, fake = app_env
    search_model("intfloat/multilingual-e5-small")
    main.MIN_SCORE = 0.0  # fake embedder scale
    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    assert fake.texts and all(text.startswith("passage: ") for text in fake.texts)

    fake.texts.clear()
    main.retrieve("How often should panels be cleaned?")
    assert fake.texts == ["query: How often should panels be cleaned?"]


def test_changing_the_model_hides_old_chunks_until_reindexed(client, search_model, app_env, fake_model):
    main, _ = app_env
    search_model("sentence-transformers/all-MiniLM-L6-v2")
    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    question = {"question": "How often should solar panels be cleaned?"}
    assert client.post("/ask", json=question).status_code == 200

    search_model("intfloat/multilingual-e5-small")
    main.MIN_SCORE = 0.2  # fake embedder scale
    documents = client.get("/documents").json()
    assert documents["stale_documents"] == 1
    assert documents["embedder"] == "intfloat/multilingual-e5-small"
    assert main.retrieve(question["question"]) == []  # old vectors are never compared
    response = client.post("/ask", json=question)
    assert response.status_code == 409
    assert "Re-index" in response.json()["detail"]

    result = client.post("/documents/index").json()  # re-embeds the stale document
    assert result["new_documents"] == ["guide.txt"]
    assert client.get("/documents").json()["stale_documents"] == 0
    assert client.post("/ask", json=question).status_code == 200
