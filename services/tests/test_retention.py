import pytest
from siteproof import retention


def test_active_job_must_be_cancelled_before_deletion(monkeypatch):
    monkeypatch.setattr(retention.db, "get_job", lambda *args: {"status": "capturing"})
    with pytest.raises(ValueError, match="Cancel"):
        retention.delete_job("tenant", "job")


def test_missing_foreign_job_is_not_deleted(monkeypatch):
    monkeypatch.setattr(retention.db, "get_job", lambda *args: None)
    with pytest.raises(LookupError):
        retention.delete_job("tenant", "foreign-job")
