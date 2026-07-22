import os
import uuid
import json
import sqlite3
import aiosqlite
import pytest
from unittest import mock
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from chrysalide.models import JobConfig
from chrysalide.orchestrator.store import JobStore, JobRecord

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
        assert len(job_id) > 0

    @pytest.mark.asyncio
    async def test_create_job_inserts_record(self, job_store, job_config):
        job_id = await job_store.create_job(job_config)
        async with aiosqlite.connect(job_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row["id"] == job_id
                assert row["repo_path"] == job_config.repo_path
                assert row["goal"] == job_config.goal
                assert row["status"] == "pending"

class TestJobStoreGetJob:
    @pytest.mark.asyncio
    async def test_get_job_returns_correct_record(self, job_store, job_config):
        job_id = await job_store.create_job(job_config)
        job_record = await job_store.get_job(job_id)
        assert job_record is not None
        assert job_record.job_id == job_id
        assert job_record.status == "pending"
        assert job_record.result is None

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
        await job_store.update_job(job_id, "completed")
        job_record = await job_store.get_job(job_id)
        assert job_record.status == "completed"

    @pytest.mark.asyncio
    async def test_update_job_updates_result(self, job_store, job_config):
        job_id = await job_store.create_job(job_config)
        result = {"key": "value"}
        await job_store.update_job(job_id, "completed", result)
        job_record = await job_store.get_job(job_id)
        assert job_record.result == result

    @pytest.mark.asyncio
    async def test_update_job_with_invalid_id_does_not_throw(self, job_store):
        await job_store.update_job("non-existent-id", "completed")
        job_record = await job_store.get_job("non-existent-id")
        assert job_record is None