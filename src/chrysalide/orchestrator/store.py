import os
import uuid
import json
import sqlite3
import aiosqlite
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timezone
from chrysalide.models import JobConfig, JobRecord, JobStatus, JobProgress, ReportPayload

def get_current_time():
    return datetime.now(timezone.utc).isoformat()

class JobStore:
    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            db_path = os.getenv("CHRYSALIDE_STORE_PATH", "~/.chrysalide/jobs.db")
        self.db_path = Path(os.path.expanduser(db_path)).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_sync()
        
    def _init_sync(self):
        with sqlite3.connect(self.db_path) as conn:
            # We recreate or alter the table to match the new schema. 
            # In a real app we'd use migrations, but for this dev stage we can just drop it if it's the old schema
            # Let's try to fetch columns and if it's old, drop it.
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(jobs)")
            columns = [c[1] for c in cursor.fetchall()]
            if columns and "config" not in columns:
                conn.execute("DROP TABLE jobs")
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    config TEXT NOT NULL,
                    progress TEXT NOT NULL,
                    report TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            ''')
            conn.commit()

    async def create_job(self, request: JobConfig) -> str:
        job_id = f"chrys_{uuid.uuid4().hex[:12]}"
        now = get_current_time()
        
        progress = JobProgress(current_iteration=0, max_iterations=request.budget.max_iterations, current_phase="", wall_time_sec=0.0)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO jobs (id, status, config, progress, report, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (job_id, JobStatus.PENDING, request.model_dump_json(), progress.model_dump_json(), None, now, now))
            await db.commit()
        return job_id
        
    async def get_job(self, job_id: str) -> Optional[JobRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                
                config = JobConfig.model_validate_json(row["config"])
                progress = JobProgress.model_validate_json(row["progress"])
                report = ReportPayload.model_validate_json(row["report"]) if row["report"] else None
                
                return JobRecord(
                    job_id=row["id"],
                    config=config,
                    status=JobStatus(row["status"]),
                    progress=progress,
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                    report=report
                )

    async def list_jobs(self) -> List[JobRecord]:
        jobs = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM jobs ORDER BY created_at DESC') as cursor:
                async for row in cursor:
                    config = JobConfig.model_validate_json(row["config"])
                    progress = JobProgress.model_validate_json(row["progress"])
                    report = ReportPayload.model_validate_json(row["report"]) if row["report"] else None
                    jobs.append(JobRecord(
                        job_id=row["id"],
                        config=config,
                        status=JobStatus(row["status"]),
                        progress=progress,
                        created_at=datetime.fromisoformat(row["created_at"]),
                        updated_at=datetime.fromisoformat(row["updated_at"]),
                        report=report
                    ))
        return jobs

    async def update_job(self, job_id: str, status: JobStatus):
        now = get_current_time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?', (status, now, job_id))
            await db.commit()

    async def update_progress(self, job_id: str, progress: JobProgress):
        now = get_current_time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE jobs SET progress = ?, updated_at = ? WHERE id = ?', (progress.model_dump_json(), now, job_id))
            await db.commit()
            
    async def update_report(self, job_id: str, report: ReportPayload):
        now = get_current_time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE jobs SET report = ?, updated_at = ? WHERE id = ?', (report.model_dump_json(), now, job_id))
            await db.commit()
