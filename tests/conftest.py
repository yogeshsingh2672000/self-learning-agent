"""
Pytest configuration and shared fixtures.
Uses SQLite in-memory so tests run without a real PostgreSQL instance.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from api.main import app
from core.database import Base, get_db

# ── In-memory SQLite for tests ────────────────────────────────────────────────
# StaticPool keeps the same connection for all operations in a single-threaded test,
# which is important for in-memory SQLite.

@pytest.fixture(scope="function")
def db_engine():
    """Create a fresh in-memory SQLite engine for this test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Enable foreign keys for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield engine
    
    # Drop all tables after test
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db(db_engine):
    """Fresh DB session per test function."""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_engine,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db: Session):
    """TestClient with DB overridden to use the in-memory SQLite session."""
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

def register_and_login(client: TestClient, email: str = "user@test.com") -> str:
    """Register a user and return a valid Bearer token."""
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Test User"},
    )
    res = client.post(
        "/api/auth/login",
        data={"username": email, "password": "testpass123"},
    )
    return res.json()["access_token"]
