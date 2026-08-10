"""End-to-end test of the whole application on Groq.

Boots the real FastAPI app against a temporary SQLite database and temporary
storage folders, with a fake Groq chat/vision client but the *real* local
embedding backend and the real ChromaDB store. Exercises:

    setup -> login -> upload -> OCR -> AI metadata -> vectorise
          -> list -> semantic search -> RAG -> tags -> health
"""
import json
import shutil
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ADMIN = {
    "username": "e2e_admin",
    "email": "e2e@example.com",
    "password": "S3cure-Passw0rd!",
    "full_name": "E2E Admin",
}

INVOICE_TEXT = """City Utilities Sampletown Ltd
Invoice No. 2025-0042
Invoice date: 2025-01-15

Dear Sir or Madam,

we are billing you for the electricity supplied in the period
2024-12-01 to 2024-12-31.

Consumption: 412 kWh
Net amount: 118.40 EUR
Value added tax 19%: 22.50 EUR
Total amount: 140.90 EUR

Payable by 2025-02-15 to the account given below.
"""

AI_METADATA = {
    "title": "2025-01-15_invoice_CityUtilitiesSampletown_Electricity_Bill_December",
    "document_type": "invoice",
    "date": "2025-01-15",
    "sender": "CityUtilitiesSampletown",
    "tax_relevant": True,
    "tags": ["Electricity", "Energy", "Utilities"],
    "summary": "Electricity invoice from City Utilities Sampletown for 140.90 EUR covering December 2024.",
}

RAG_ANSWER = (
    "## Answer\n\nThe total amount is **140.90 EUR** ([Doc1])."
)


class FakeGroqClient:
    """Stands in for the Groq API: returns metadata JSON, then RAG prose."""

    def __init__(self):
        self.requests = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.requests.append(kwargs)
        prompt = json.dumps(kwargs.get("messages", []))

        if "NAMING CONVENTION" in prompt or "extract the metadata" in prompt:
            content = json.dumps(AI_METADATA)
        elif "QUESTION:" in prompt or "cite your sources" in prompt:
            content = RAG_ANSWER
        else:
            content = "ok"

        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    """A fully isolated running application."""
    data_dir = tmp_path / "data"
    for sub in ("staging", "storage", "logs", "backups", "chroma"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)

    # The rate limiter keeps per-IP counters in a process-wide middleware
    # instance, so repeated logins across tests would trip the 5-per-5-minutes
    # login limit. Rate limiting itself is covered by test_rate_limiting.py.
    from app.middleware.rate_limit_middleware import RateLimitMiddleware

    monkeypatch.setattr(
        RateLimitMiddleware, "is_rate_limited", lambda self, *a, **k: (False, None)
    )

    monkeypatch.setenv("DOCUMENT_MANAGER_ENV_FILE", "")
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_e2e_test_key")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("OCR_ENGINE", "auto")
    monkeypatch.setenv("DATA_FOLDER", str(data_dir))
    monkeypatch.setenv("STAGING_FOLDER", str(data_dir / "staging"))
    monkeypatch.setenv("STORAGE_FOLDER", str(data_dir / "storage"))
    monkeypatch.setenv("LOGS_FOLDER", str(data_dir / "logs"))
    monkeypatch.setenv("BACKUP_FOLDER", str(data_dir / "backups"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-e2e-runs-only")
    monkeypatch.setenv("CHROMA_COLLECTION_NAME", "e2e_documents")

    from app import database as db_module
    from app.config import reset_settings

    reset_settings()

    # Point the ORM at a throwaway database.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'e2e.db'}", connect_args={"check_same_thread": False}
    )
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)

    from app.models import Base

    Base.metadata.create_all(bind=engine)

    # Reset the ChromaDB singleton so it persists into the temp folder.
    from app.services import vector_db_service as vdb

    vdb.VectorDBService._instance = None
    vdb.VectorDBService._client = None
    vdb.VectorDBService._collection = None

    # Route chat/vision to the fake client; embeddings stay real and local.
    fake_client = FakeGroqClient()
    from app.services.ai_client_factory import AIClientFactory

    monkeypatch.setattr(
        AIClientFactory, "create_client", staticmethod(lambda db=None: fake_client)
    )

    import app.main as main_module
    from app.database import get_db

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    main_module.app.dependency_overrides[get_db] = override_get_db

    # No context manager: skip lifespan so the file watcher / schedulers stay off.
    client = TestClient(main_module.app)

    yield SimpleNamespace(
        client=client,
        session_factory=TestSession,
        data_dir=data_dir,
        fake_client=fake_client,
    )

    main_module.app.dependency_overrides.clear()
    vdb.VectorDBService._instance = None
    vdb.VectorDBService._client = None
    vdb.VectorDBService._collection = None
    reset_settings()
    shutil.rmtree(tmp_path, ignore_errors=True)


def csrf(client) -> dict:
    """Fetch a CSRF token and return it as request headers."""
    response = client.get("/api/csrf-token")
    token = response.json().get("csrf_token")
    return {"X-CSRF-Token": token} if token else {}


@pytest.fixture
def authed(app_env):
    """An app with an admin account created and logged in."""
    client = app_env.client

    status = client.get("/api/auth/setup/check")
    assert status.status_code == 200
    assert status.json()["setup_complete"] is False

    created = client.post("/api/auth/setup/initial-user", json=ADMIN)
    assert created.status_code == 200, created.text

    login = client.post(
        "/api/auth/login",
        json={"username": ADMIN["username"], "password": ADMIN["password"]},
    )
    assert login.status_code == 200, login.text
    assert "session_token" in login.cookies or client.cookies.get("session_token")

    return app_env


def process_staging_now(app_env):
    """Run the real ingestion pipeline over everything in staging.

    Returns document ids; ORM instances would be detached once the session
    closes, so callers re-query inside their own session.
    """
    from app.services.document_processor import DocumentProcessor

    staged = [p for p in (app_env.data_dir / "staging").iterdir() if p.is_file()]
    assert staged, "expected at least one staged file"

    ids = []
    with app_env.session_factory() as db:
        processor = DocumentProcessor(db)
        for path in staged:
            document = processor.process_file(path, db)
            assert document is not None, f"processing returned nothing for {path.name}"
            ids.append(document.id)
    return ids


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_setup_and_login(authed):
    client = authed.client

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == ADMIN["username"]
    assert me.json()["is_admin"] is True

    session = client.get("/api/auth/check-session")
    assert session.status_code == 200
    assert session.json()["valid"] is True


def test_initial_setup_cannot_run_twice(authed):
    again = authed.client.post("/api/auth/setup/initial-user", json=ADMIN)
    assert again.status_code == 400


def test_unauthenticated_requests_are_rejected(app_env):
    fresh = TestClient(app_env.client.app)
    response = fresh.get("/api/documents/")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------
def test_full_document_pipeline(authed):
    client = authed.client

    upload = client.post(
        "/api/documents/upload",
        files={"file": ("electricity_bill.txt", INVOICE_TEXT.encode("utf-8"), "text/plain")},
        headers=csrf(client),
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["status"] == "uploaded"

    document_ids = process_staging_now(authed)
    assert len(document_ids) == 1

    with authed.session_factory() as db:
        from app.models import Document

        document = db.query(Document).filter(Document.id == document_ids[0]).one()

        # OCR (plain-text read), AI metadata and vectorisation all completed.
        assert document.ocr_status == "completed"
        assert document.ai_status == "completed"
        assert document.vector_status == "completed"
        assert "Total amount" in document.full_text

        assert document.title == AI_METADATA["title"]
        assert document.is_tax_relevant is True
        assert document.correspondent.name == "CityUtilitiesSampletown"
        assert document.doctype.name == "invoice"
        assert {t.name for t in document.tags} == set(AI_METADATA["tags"])

    # The file was filed under {correspondent}/{date}/ in storage.
    stored = authed.data_dir / "storage" / "CityUtilitiesSampletown" / "2025-01-15"
    assert stored.is_dir()
    assert any(stored.iterdir())

    # And it is visible through the API.
    listing = client.get("/api/documents/")
    assert listing.status_code == 200
    payload = listing.json()
    assert len(payload) == 1
    assert payload[0]["title"] == AI_METADATA["title"]
    assert payload[0]["summary"] == AI_METADATA["summary"]


def test_duplicate_upload_is_detected(authed):
    client = authed.client
    for _ in range(2):
        client.post(
            "/api/documents/upload",
            files={"file": ("dup.txt", INVOICE_TEXT.encode("utf-8"), "text/plain")},
            headers=csrf(client),
        )

    process_staging_now(authed)

    with authed.session_factory() as db:
        from app.models import Document

        assert db.query(Document).count() == 1


def test_extraction_prompt_targets_the_configured_groq_model(authed):
    client = authed.client
    client.post(
        "/api/documents/upload",
        files={"file": ("r.txt", INVOICE_TEXT.encode("utf-8"), "text/plain")},
        headers=csrf(client),
    )
    process_staging_now(authed)

    extraction = next(
        r for r in authed.fake_client.requests if "NAMING CONVENTION" in json.dumps(r["messages"])
    )
    assert extraction["model"] == "openai/gpt-oss-120b"
    assert extraction["max_completion_tokens"] > 0
    assert extraction["reasoning_effort"] == "medium"
    assert extraction["response_format"]["type"] == "json_schema"


# ---------------------------------------------------------------------------
# Search and RAG
# ---------------------------------------------------------------------------
@pytest.fixture
def ingested(authed):
    client = authed.client
    client.post(
        "/api/documents/upload",
        files={"file": ("electricity_bill.txt", INVOICE_TEXT.encode("utf-8"), "text/plain")},
        headers=csrf(client),
    )
    process_staging_now(authed)
    return authed


def test_semantic_search_finds_the_document(ingested):
    client = ingested.client

    response = client.post(
        "/api/search/",
        json={"query": "How much is my electricity bill?", "limit": 10},
        headers=csrf(client),
    )
    assert response.status_code == 200, response.text

    result = response.json()
    assert result["total_count"] >= 1
    assert result["documents"][0]["title"] == AI_METADATA["title"]


def test_full_text_search_finds_the_document(ingested):
    client = ingested.client

    response = client.post(
        "/api/search/",
        json={"query": "Sampletown", "limit": 10, "use_semantic_search": False},
        headers=csrf(client),
    )
    assert response.status_code == 200
    assert response.json()["total_count"] >= 1


def test_search_suggestions(ingested):
    response = ingested.client.get("/api/search/suggestions", params={"q": "City"})
    assert response.status_code == 200

    suggestions = response.json()
    assert "CityUtilitiesSampletown" in suggestions["correspondents"]


def test_rag_answer_cites_sources(ingested):
    client = ingested.client

    response = client.post(
        "/api/search/rag",
        json={"question": "What is the total amount?", "max_documents": 5},
        headers=csrf(client),
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    assert "140.90" in payload["answer"]
    assert "[Doc1]" in payload["answer"]
    assert len(payload["sources"]) >= 1
    assert payload["confidence"] > 0


def test_vector_stats_reports_the_indexed_document(ingested):
    response = ingested.client.get("/api/search/vector-stats")
    assert response.status_code == 200
    assert response.json()["document_count"] >= 1


# ---------------------------------------------------------------------------
# Document CRUD and tags (the endpoints that used to reference DocumentTag)
# ---------------------------------------------------------------------------
def test_tag_add_and_remove_roundtrip(ingested):
    client = ingested.client
    document_id = client.get("/api/documents/").json()[0]["id"]

    created = client.post(
        f"/api/documents/{document_id}/tags",
        json={"tag_name": "Important"},
        headers=csrf(client),
    )
    assert created.status_code == 200, created.text
    tag_id = created.json()["tag_id"]

    duplicate = client.post(
        f"/api/documents/{document_id}/tags",
        json={"tag_name": "Important"},
        headers=csrf(client),
    )
    assert duplicate.status_code == 400

    removed = client.delete(
        f"/api/documents/{document_id}/tags/{tag_id}", headers=csrf(client)
    )
    assert removed.status_code == 200

    re_added = client.post(
        f"/api/documents/{document_id}/tags/{tag_id}", headers=csrf(client)
    )
    assert re_added.status_code == 200

    detail = client.get(f"/api/documents/{document_id}").json()
    assert "Important" in {t["name"] for t in detail["tags"]}


def test_document_update_and_notes(ingested):
    client = ingested.client
    document_id = client.get("/api/documents/").json()[0]["id"]

    updated = client.put(
        f"/api/documents/{document_id}",
        json={"title": "New Title", "is_tax_relevant": False},
        headers=csrf(client),
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "New Title"

    notes = client.put(
        f"/api/documents/{document_id}/notes",
        json={"notes": "Checked on 2025-02-01."},
        headers=csrf(client),
    )
    assert notes.status_code == 200
    assert client.get(f"/api/documents/{document_id}/notes").json()["notes"] == "Checked on 2025-02-01."


def test_document_download_and_view_tracking(ingested):
    client = ingested.client
    document_id = client.get("/api/documents/").json()[0]["id"]

    download = client.get(f"/api/documents/{document_id}/download")
    assert download.status_code == 200
    assert b"Total amount" in download.content

    view = client.post(f"/api/documents/{document_id}/view", headers=csrf(client))
    assert view.status_code == 200
    assert view.json()["view_count"] == 1


def test_reprocess_vector_endpoint(ingested):
    """Regression: this used to call a non-existent _create_embeddings()."""
    client = ingested.client
    document_id = client.get("/api/documents/").json()[0]["id"]

    response = client.post(
        f"/api/documents/{document_id}/reprocess-vector", headers=csrf(client)
    )
    assert response.status_code == 200, response.text
    assert response.json()["vector_status"] == "completed"


def test_reprocess_ocr_endpoint(ingested):
    """Regression: this used to call a non-existent _process_ocr()."""
    client = ingested.client
    document_id = client.get("/api/documents/").json()[0]["id"]

    response = client.post(
        f"/api/documents/{document_id}/reprocess-ocr", headers=csrf(client)
    )
    assert response.status_code == 200, response.text
    assert response.json()["characters_extracted"] > 0


def test_document_stats(ingested):
    response = ingested.client.get("/api/documents/stats/overview")
    assert response.status_code == 200
    assert response.json()["total_documents"] == 1


# ---------------------------------------------------------------------------
# Taxonomy endpoints
# ---------------------------------------------------------------------------
def test_correspondents_doctypes_and_tags_are_listed(ingested):
    client = ingested.client

    correspondents = client.get("/api/correspondents/").json()
    assert any(c["name"] == "CityUtilitiesSampletown" for c in correspondents)
    assert all("document_count" in c for c in correspondents)

    doctypes = client.get("/api/doctypes/").json()
    assert any(d["name"] == "invoice" for d in doctypes)

    tags = client.get("/api/tags/").json()
    assert {"Electricity", "Energy", "Utilities"}.issubset({t["name"] for t in tags})


def test_correspondent_in_use_cannot_be_deleted(ingested):
    client = ingested.client
    correspondent = client.get("/api/correspondents/").json()[0]

    response = client.delete(
        f"/api/correspondents/{correspondent['id']}", headers=csrf(client)
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Settings and health
# ---------------------------------------------------------------------------
def test_settings_report_groq_configuration(authed):
    response = authed.client.get("/api/settings/models")
    assert response.status_code == 200, response.text

    effective = response.json()["effective"]
    assert effective["provider"] == "groq"
    assert effective["chat_model"] == "openai/gpt-oss-120b"
    assert effective["vision_model"] == "qwen/qwen3.6-27b"
    assert effective["embedding_provider"] == "local"
    assert effective["embedding_dimensions"] == 384


def test_ai_connection_test_endpoint(authed):
    response = authed.client.post("/api/settings/test/ai", headers=csrf(authed.client))
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["provider"] == "groq"
    assert payload["model"] == "openai/gpt-oss-120b"


def test_extended_settings_expose_groq_fields(authed):
    response = authed.client.get("/api/settings/extended")
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["ai_provider"] == "groq"
    assert payload["vision_model"] == "qwen/qwen3.6-27b"
    assert payload["embedding_provider"] == "local"
    assert payload["ocr_engine"] == "auto"


def test_settings_export_endpoint_is_valid(authed):
    """Regression: this endpoint used to raise a response-validation error."""
    response = authed.client.get("/api/settings/export")
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["version"] == "1.0"
    assert "exported_at" in payload
    assert isinstance(payload["settings"], dict)


def test_health_reports_groq_and_local_embeddings(authed):
    response = authed.client.get("/api/health/")
    assert response.status_code == 200, response.text

    services = response.json()["services"]
    assert services["database"]["status"] == "healthy"
    assert services["ai_service"]["details"]["provider"] == "groq"
    assert services["embeddings"]["details"]["provider"] == "local"
    assert services["embeddings"]["details"]["dimensions"] == 384
    assert "engine" in services["ocr_service"]["details"]


def test_readiness_probe(authed):
    response = authed.client.get("/api/health/readiness")
    assert response.status_code == 200
    assert response.json()["checks"]["database"]["ready"] is True
