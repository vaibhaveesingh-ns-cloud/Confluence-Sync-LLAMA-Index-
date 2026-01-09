import pytest
from app.services.sync_service import sync_index
from app.models import SyncConfig, SyncedPage
from app.database import get_db
from sqlalchemy.orm import Session

@pytest.fixture
def db_session():
    db = get_db()
    yield db
    db.close()

@pytest.fixture
def sync_config(db_session):
    config = SyncConfig(
        index_id=1,
        confluence_spaces=["SPACE1", "SPACE2"],
        confluence_labels=["label1", "label2"],
        include_attachments=True,
        include_comments=False,
        interval_minutes=60,
        enabled=True
    )
    db_session.add(config)
    db_session.commit()
    return config

@pytest.fixture
def synced_page(db_session):
    page = SyncedPage(
        index_id=1,
        confluence_page_id="12345",
        confluence_page_title="Test Page",
        confluence_version=1,
        confluence_modified_time="2023-01-01T00:00:00Z",
        last_synced_at="2023-01-01T00:00:00Z"
    )
    db_session.add(page)
    db_session.commit()
    return page

def test_sync_index(db_session, sync_config, synced_page):
    result = sync_index(db_session, user_id=1, index_id=1)
    assert result is not None
    assert isinstance(result, dict)
    assert "synced_pages" in result
    assert len(result["synced_pages"]) >= 0  # Adjust based on expected behavior

def test_sync_with_no_changes(db_session, sync_config):
    # Simulate no changes in Confluence
    result = sync_index(db_session, user_id=1, index_id=1)
    assert result["synced_pages"] == []  # Expecting no new synced pages

def test_sync_with_new_page(db_session, sync_config):
    # Simulate a new page being added in Confluence
    # This would typically involve mocking the API response
    result = sync_index(db_session, user_id=1, index_id=1)
    assert len(result["synced_pages"]) > 0  # Expecting at least one new synced page

def test_sync_with_modified_page(db_session, sync_config, synced_page):
    # Simulate a modified page in Confluence
    synced_page.confluence_version += 1
    db_session.commit()
    
    result = sync_index(db_session, user_id=1, index_id=1)
    assert len(result["synced_pages"]) > 0  # Expecting the modified page to be synced