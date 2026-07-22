from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from typing import List, Optional, Union, Dict
from pydantic import BaseModel


class Budget(BaseModel):
    """Modèle représentant le budget d'un job."""
    max_iterations: int = 15
    max_wall_time_min: int = 30
    max_tokens_total: int = 500000


class JobConfig(BaseModel):
    """Configuration d'un job."""
    goal: str
    repo_path: str
    base_branch: str = 'main'
    constraints: List[str] = []
    budget: Budget = Budget()
    provider_override: Optional[str] = None
    allow_network: bool = False


class JobStatus(StrEnum):
    """Statut d'un job."""
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    DONE = 'DONE'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'
    ESCALATED = 'ESCALATED'


class JobProgress(BaseModel):
    """Progression d'un job."""
    current_iteration: int = 0
    max_iterations: int = 15
    current_phase: str = ''
    wall_time_sec: float = 0.0


class FindingType(StrEnum):
    """Type de découverte."""
    PLAN = 'PLAN'
    FILE_WRITE = 'FILE_WRITE'
    FILE_READ = 'FILE_READ'
    COMMAND_RUN = 'COMMAND_RUN'
    DECISION = 'DECISION'
    CORRECTION_HYPOTHESIS = 'CORRECTION_HYPOTHESIS'
    NOTE = 'NOTE'
    VALIDATION_SUCCESS = 'VALIDATION_SUCCESS'
    PROVIDER_FALLBACK = 'PROVIDER_FALLBACK'


class Finding(BaseModel):
    """Découverte faite pendant un job."""
    type: FindingType
    timestamp: datetime = datetime.now()
    data: Dict


class FileChanged(BaseModel):
    """Fichier modifié pendant un job."""
    path: str
    action: str  # 'created' | 'modified' | 'deleted'
    lines: int
    hash: str
    size_bytes: int


class CommandExecuted(BaseModel):
    """Commande exécutée pendant un job."""
    phase: str
    iteration: int
    cmd: str
    exit_code: int
    duration_sec: float
    stdout_tail: str
    stderr_tail: str
    truncated: bool = False


class Decision(BaseModel):
    """Décision prise pendant un job."""
    topic: str
    choice: str
    reason: str


class Blocker(BaseModel):
    """Bloqueur rencontré pendant un job."""
    description: str
    resolution: str  # 'resolved' | 'escalated' | 'unresolved'
    detail: str = ''


class TokenUsage(BaseModel):
    """Utilisation des tokens pendant un job."""
    input: int = 0
    output: int = 0
    total: int = 0


class ProviderInfo(BaseModel):
    """Informations sur le fournisseur."""
    name: str
    model: str


class DiffSummary(BaseModel):
    """Résumé des différences de fichiers pendant un job."""
    files: int = 0
    added: int = 0
    removed: int = 0


class ReportError(BaseModel):
    """Erreur dans le rapport."""
    type: str
    message: str
    traceback: str = ''


class ReportPayload(BaseModel):
    """Payload du rapport final."""
    job_id: str
    status: JobStatus
    summary: str
    goal: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    iterations_used: int
    iterations_max: int
    wall_time_sec: float
    tokens_used: TokenUsage
    provider: ProviderInfo
    plan: Optional[str] = None
    files_changed: List[FileChanged] = []
    diff_summary: DiffSummary
    commands_executed: List[CommandExecuted] = []
    decisions: List[Decision] = []
    blockers: List[Blocker] = []
    iteration_log: List[Finding] = []
    sandbox_path: str
    integration_hint: Optional[str] = None
    error: Optional[ReportError] = None


class JobRecord(BaseModel):
    """Enregistrement d'un job."""
    job_id: str
    config: JobConfig
    status: JobStatus
    progress: JobProgress
    created_at: datetime
    updated_at: datetime
    report: Optional[ReportPayload] = None
    sandbox_path: str = ''


class StartTaskResponse(BaseModel):
    """Réponse pour le démarrage d'une tâche."""
    job_id: str


class GetStatusResponse(BaseModel):
    """Réponse pour obtenir le statut d'une tâche."""
    job_id: str
    status: JobStatus
    progress: JobProgress


class GetReportResponse(BaseModel):
    """Réponse pour obtenir le rapport d'une tâche."""
    job_id: str
    report: ReportPayload


class CancelTaskResponse(BaseModel):
    """Réponse pour l'annulation d'une tâche."""
    job_id: str
    status: JobStatus


class ChrysalideError(BaseModel):
    """Erreur dans le système Chrysalide."""
    code: str
    message: str
    details: Dict = {}