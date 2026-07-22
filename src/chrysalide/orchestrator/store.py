import os
import uuid
import json
import sqlite3
import aiosqlite
from typing import List, Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel
from chrysalide.models import JobConfig

class JobRecord(BaseModel):
    job_id: str
    status: str
    created_at: str
    result: Optional[Dict[str, Any]] = None

class JobStore:
    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            db_path = os.getenv("CHRYSALIDE_STORE_PATH", os.path.expanduser("~/.chrysalide/jobs.db"))
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_sync()
        
    def _init_sync(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    repo_path TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    async def create_job(self, request: JobConfig) -> str:
        job_id = str(uuid.uuid4())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO jobs (id, repo_path, goal, status)
                VALUES (?, ?, ?, ?)
            ''', (job_id, str(request.repo_path), request.goal, "pending"))
            await db.commit()
        return job_id
        
    async def get_job(self, job_id: str) -> Optional[JobRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                
                result_data = None
                if row["result"]:
                    try:
                        result_data = json.loads(row["result"])
                    except:
                        pass
                        
                return JobRecord(
                    job_id=row["id"],
                    status=row["status"],
                    created_at=row["created_at"],
                    result=result_data
                )
                
    async def list_jobs(self) -> List[JobRecord]:
        jobs = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM jobs ORDER BY created_at DESC') as cursor:
                async for row in cursor:
                    jobs.append(JobRecord(
                        job_id=row["id"],
                        status=row["status"],
                        created_at=row["created_at"]
                    ))
        return jobs

    async def update_job(self, job_id: str, status: str, result: Optional[Dict[str, Any]] = None):
        query = 'UPDATE jobs SET status = ?, updated_at = CURRENT_TIMESTAMP'
        params: List[Any] = [status]
        
        if result is not None:
            query += ', result = ?'
            params.append(json.dumps(result))
            
        query += ' WHERE id = ?'
        params.append(job_id)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, tuple(params))
            await db.commit()
