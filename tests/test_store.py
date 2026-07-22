import os
import sqlite3
import aiosqlite
import pytest
from pathlib import Path
from chrysalide.models import JobConfig, JobStatus, JobProgress, ReportPayload, TokenUsage, ProviderInfo, DiffSummary
from chrysalide.orchestrator.store import JobStore
import json
from datetime import datetime, timezone

@pytest.fixture
def mock_db_path(tmp_path):
    return tmp_path / "test_jobs.db"

@pytest.fixture
def job_store(mock_db_path):
    return JobStore(db_path=str(mock_db_path))

@pytest.fixture
def job_config():
    return JobConfig(repo_path="https://example.com/repo.git", goal="test-goal")

class TestJobStoreInitialization:
    def test_initialization_creates_db_file(self, mock_db_path):
        JobStore(db_path=str(mock_db_path))
        assert mock_db_path.exists()

    def test_initialization_creates_db_structure(self, mock_db_path):
        JobStore(db_path=str(mock_db_path))
        with sqlite3.connect(mock_db_path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
            assert cursor.fetchone() is not None

class TestJobStoreCreateJob:
    @pytest.mark.asyncio
    async def test_create_job_returns_job_id(self, job_store, job_config):
        job_id = await job_store.create_job(job_config)
        assert isinstance(job_id, str)
        assert job_id.startswith("chrys_")

    @pytest.mark.asyncio
    async def test_create_job_inserts_record(self, job_store, job_config):
        job_id = await job_store.create_job(job_config)
        async with aiosqlite.connect(job_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row["id"] == job_id
                assert row["status"] == JobStatus.PENDING
                
                config = json.loads(row["config"])
                assert config["repo_path"] == job_config.repo_path

class TestJobStoreGetJob:
    @pytest.mark.asyncio
    async def test_get_job_returns_correct_record(self, job_store, job_config):
        job_id = await job_store.create_job(job_config)
        job_record = await job_store.get_job(job_id)
        assert job_record is not None
        assert job_record.job_id == job_id
        assert job_record.status == JobStatus.PENDING
        assert job_record.report is None
        assert job_record.progress.current_iteration == 0

    @pytest.mark.asyncio
    async def test_get_job_returns_none_for_invalid_id(self, job_store):
        job_record = await job_store.get_job("non-existent-id")
        assert job_record is None

class TestJobStoreListJobs:
    @pytest.mark.asyncio
    async def test_list_jobs_returns_all_jobs(self, job_store, job_config):
        job_id1 = await job_store.create_job(job_config)
        job_id2 = await job_store.create_job(job_config)
        jobs = await job_store.list_jobs()
        assert len(jobs) == 2
        job_ids = [job.job_id for job in jobs]
        assert job_id1 in job_ids
        assert job_id2 in job_ids

class TestJobStoreUpdateJob:
    @pytest.mark.asyncio
    async def test_update_job_updates_status(self, job_store, job_config):
        job_id = await job_store.create_job(job_config)
        await job_store.update_job(job_id, JobStatus.DONE)
        job_record = await job_store.get_job(job_id)
        assert job_record.status == JobStatus.DONE

    @pytest.mark.asyncio
    async def test_update_job_updates_progress(self, job_store, job_config):
        job_id = await job_store.create_job(job_config)
        progress = JobProgress(current_iteration=5, max_iterations=10, current_phase="ACT", wall_time_sec=120)
        await job_store.update_progress(job_id, progress)
        job_record = await job_store.get_job(job_id)
        assert job_record.progress.current_iteration == 5

    @pytest.mark.asyncio
    async def test_update_job_updates_report(self, job_store, job_config):
        job_id = await job_store.create_job(job_config)
        report = ReportPayload(
            job_id=job_id,
            status=JobStatus.DONE,
            summary="Test summary",
            goal=job_config.goal,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            iterations_used=1,
            iterations_max=15,
            wall_time_sec=1.0,
            tokens_used=TokenUsage(),
            provider=ProviderInfo(name="test", model="test"),
            diff_summary=DiffSummary(),
            sandbox_path="/tmp"
        )
        await job_store.update_report(job_id, report)
        job_record = await job_store.get_job(job_id)
        assert job_record.report is not None
        assert job_record.report.summary == "Test summary"

    @pytest.mark.asyncio
    async def test_update_job_with_invalid_id_does_not_throw(self, job_store):
        await job_store.update_job("non-existent-id", JobStatus.DONE)
        job_record = await job_store.get_job("non-existent-id")
        assert job_record is None