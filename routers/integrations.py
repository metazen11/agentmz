"""Routers for Integration CRUD operations."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import (
    Project,
    Task,
    TaskNode,
    IntegrationProvider,
    IntegrationCredential,
    ProjectIntegration,
    TaskExternalLink,
)
from routers.tasks import get_task_or_404

router = APIRouter()

class IntegrationProviderResponse(BaseModel):
    id: int
    name: str
    display_name: str
    auth_type: str
    enabled: bool
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class IntegrationCredentialCreate(BaseModel):
    provider_id: int
    name: str
    token: str  # Plaintext token (will be encrypted before storage)


class IntegrationCredentialResponse(BaseModel):
    id: int
    provider_id: int
    provider_name: Optional[str] = None
    provider_display_name: Optional[str] = None
    name: str
    is_valid: bool
    last_verified_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ProjectIntegrationCreate(BaseModel):
    project_id: int
    credential_id: int
    external_project_id: str
    external_project_name: Optional[str] = None
    sync_direction: str = "import"


class ProjectIntegrationResponse(BaseModel):
    id: int
    project_id: int
    project_name: Optional[str] = None
    credential_id: int
    external_project_id: str
    external_project_name: Optional[str]
    sync_direction: str
    last_synced_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class TaskImportRequest(BaseModel):
    integration_id: int
    task_ids: List[str]  # External task IDs to import
    include_subtasks: bool = True
    include_attachments: bool = False


class TaskExportRequest(BaseModel):
    integration_id: int

def _get_credential_or_404(credential_id: int, db: Session) -> IntegrationCredential:
    credential = (
        db.query(IntegrationCredential)
        .filter(IntegrationCredential.id == credential_id)
        .first()
    )
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    return credential


def _get_integration_or_404(integration_id: int, db: Session) -> ProjectIntegration:
    integration = (
        db.query(ProjectIntegration)
        .filter(ProjectIntegration.id == integration_id)
        .first()
    )
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    return integration


@router.get("/integrations/providers", response_model=List[IntegrationProviderResponse])
def list_integration_providers(db: Session = Depends(get_db)):
    """List all available integration providers."""
    return (
        db.query(IntegrationProvider)
        .filter(IntegrationProvider.enabled == True)
        .order_by(IntegrationProvider.name.asc())
        .all()
    )


@router.get("/integrations/providers/{provider_id}", response_model=IntegrationProviderResponse)
def get_integration_provider(provider_id: int, db: Session = Depends(get_db)):
    """Get a single integration provider by ID."""
    provider = (
        db.query(IntegrationProvider)
        .filter(IntegrationProvider.id == provider_id)
        .first()
    )
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


@router.post("/integrations/credentials", response_model=IntegrationCredentialResponse)
def create_integration_credential(
    payload: IntegrationCredentialCreate,
    db: Session = Depends(get_db),
):
    """Store a new integration credential (encrypts token before storage)."""
    from integrations.encryption import encrypt_token, is_encryption_configured
    from integrations.providers import get_provider

    # Verify provider exists
    provider = (
        db.query(IntegrationProvider)
        .filter(IntegrationProvider.id == payload.provider_id)
        .first()
    )
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Check encryption is configured
    if not is_encryption_configured():
        raise HTTPException(
            status_code=500,
            detail="INTEGRATION_ENCRYPTION_KEY not configured",
        )

    # Encrypt the token
    try:
        encrypted = encrypt_token(payload.token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Encryption failed: {e}")

    # Validate credential with provider
    is_valid = False
    try:
        provider_instance = get_provider(provider.name, payload.token)
        is_valid = provider_instance.validate_credential()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        # Token may still be saved even if validation fails
        is_valid = False

    # Create credential record
    credential = IntegrationCredential(
        provider_id=payload.provider_id,
        name=payload.name,
        encrypted_token=encrypted,
        is_valid=is_valid,
        last_verified_at=datetime.utcnow() if is_valid else None,
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)

    return credential


@router.get("/integrations/credentials", response_model=List[IntegrationCredentialResponse])
def list_integration_credentials(db: Session = Depends(get_db)):
    """List all stored integration credentials."""
    return (
        db.query(IntegrationCredential)
        .order_by(IntegrationCredential.created_at.desc())
        .all()
    )


@router.get("/integrations/credentials/{credential_id}", response_model=IntegrationCredentialResponse)
def get_integration_credential(credential_id: int, db: Session = Depends(get_db)):
    """Get a single integration credential."""
    return _get_credential_or_404(credential_id, db)


@router.delete("/integrations/credentials/{credential_id}")
def delete_integration_credential(credential_id: int, db: Session = Depends(get_db)):
    """Delete an integration credential and all related mappings."""
    credential = _get_credential_or_404(credential_id, db)
    db.delete(credential)
    db.commit()
    return {"deleted": True, "credential_id": credential_id}


@router.post("/integrations/credentials/{credential_id}/validate")
def validate_integration_credential(credential_id: int, db: Session = Depends(get_db)):
    """Re-validate an existing credential."""
    from integrations.encryption import decrypt_token
    from integrations.providers import get_provider

    credential = _get_credential_or_404(credential_id, db)

    try:
        token = decrypt_token(credential.encrypted_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Decryption failed: {e}")

    try:
        provider_instance = get_provider(credential.provider.name, token)
        is_valid = provider_instance.validate_credential()
    except Exception as e:
        is_valid = False

    credential.is_valid = is_valid
    credential.last_verified_at = datetime.utcnow()
    db.commit()
    db.refresh(credential)

    return {
        "credential_id": credential_id,
        "is_valid": is_valid,
        "last_verified_at": credential.last_verified_at.isoformat(),
    }


@router.get("/integrations/credentials/{credential_id}/projects")
def list_external_projects(credential_id: int, db: Session = Depends(get_db)):
    """List external projects accessible via this credential."""
    from integrations.encryption import decrypt_token
    from integrations.providers import get_provider

    credential = _get_credential_or_404(credential_id, db)

    try:
        token = decrypt_token(credential.encrypted_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Decryption failed: {e}")

    try:
        provider_instance = get_provider(credential.provider.name, token)
        projects = provider_instance.list_projects()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {e}")

    return {
        "credential_id": credential_id,
        "provider": credential.provider.name,
        "projects": [
            {
                "external_id": p.external_id,
                "name": p.name,
                "external_url": p.external_url,
                "metadata": p.metadata,
            }
            for p in projects
        ],
    }


@router.post("/integrations/project-mapping", response_model=ProjectIntegrationResponse)
def create_project_integration(
    payload: ProjectIntegrationCreate,
    db: Session = Depends(get_db),
):
    """Link a local project to an external project."""
    # Verify local project exists
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Local project not found")

    # Verify credential exists
    credential = _get_credential_or_404(payload.credential_id, db)

    # Check for duplicate mapping
    existing = (
        db.query(ProjectIntegration)
        .filter(
            ProjectIntegration.project_id == payload.project_id,
            ProjectIntegration.credential_id == payload.credential_id,
            ProjectIntegration.external_project_id == payload.external_project_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="This mapping already exists")

    integration = ProjectIntegration(
        project_id=payload.project_id,
        credential_id=payload.credential_id,
        external_project_id=payload.external_project_id,
        external_project_name=payload.external_project_name,
        sync_direction=payload.sync_direction,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)

    return integration


@router.get("/integrations/project-mappings", response_model=List[ProjectIntegrationResponse])
def list_project_integrations(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """List all project integrations, optionally filtered by project."""
    query = db.query(ProjectIntegration)
    if project_id is not None:
        query = query.filter(ProjectIntegration.project_id == project_id)
    return query.order_by(ProjectIntegration.created_at.desc()).all()


@router.get("/integrations/project-mappings/{integration_id}", response_model=ProjectIntegrationResponse)
def get_project_integration(integration_id: int, db: Session = Depends(get_db)):
    """Get a single project integration."""
    return _get_integration_or_404(integration_id, db)


@router.delete("/integrations/project-mappings/{integration_id}")
def delete_project_integration(integration_id: int, db: Session = Depends(get_db)):
    """Delete a project integration and all task links."""
    integration = _get_integration_or_404(integration_id, db)
    db.delete(integration)
    db.commit()
    return {"deleted": True, "integration_id": integration_id}


@router.get("/integrations/{integration_id}/tasks")
def list_external_tasks(integration_id: int, db: Session = Depends(get_db)):
    """List tasks from the external project for import selection."""
    from integrations.encryption import decrypt_token
    from integrations.providers import get_provider

    integration = _get_integration_or_404(integration_id, db)
    credential = integration.credential

    try:
        token = decrypt_token(credential.encrypted_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Decryption failed: {e}")

    try:
        provider_instance = get_provider(credential.provider.name, token)
        tasks = provider_instance.list_tasks(integration.external_project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {e}")

    # Check which tasks are already imported
    imported_ids = set(
        db.query(TaskExternalLink.external_task_id)
        .filter(TaskExternalLink.integration_id == integration_id)
        .all()
    )
    imported_ids = {t[0] for t in imported_ids}

    return {
        "integration_id": integration_id,
        "external_project_id": integration.external_project_id,
        "tasks": [
            {
                "external_id": t.external_id,
                "title": t.title,
                "description": t.description,
                "completed": t.completed,
                "external_url": t.external_url,
                "already_imported": t.external_id in imported_ids,
            }
            for t in tasks
        ],
    }


@router.post("/integrations/import")
def import_external_tasks(payload: TaskImportRequest, db: Session = Depends(get_db)):
    """Import selected tasks from an external project."""
    from integrations.encryption import decrypt_token
    from integrations.providers import get_provider
    import hashlib

    integration = _get_integration_or_404(payload.integration_id, db)
    credential = integration.credential

    try:
        token = decrypt_token(credential.encrypted_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Decryption failed: {e}")

    try:
        provider_instance = get_provider(credential.provider.name, token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Get default node for imported tasks
    default_node = db.query(TaskNode).filter(TaskNode.name == "dev").first()
    if not default_node:
        raise HTTPException(status_code=500, detail="Default node 'dev' not configured")

    imported_tasks = []
    skipped_tasks = []

    def import_task(external_task, parent_id: Optional[int] = None) -> Optional[Task]:
        """Import a single task and optionally its subtasks."""
        # Check if already imported
        existing = (
            db.query(TaskExternalLink)
            .filter(
                TaskExternalLink.integration_id == integration.id,
                TaskExternalLink.external_task_id == external_task.external_id,
            )
            .first()
        )
        if existing:
            skipped_tasks.append(external_task.external_id)
            return None

        # Create local task
        status = "done" if external_task.completed else "backlog"
        task = Task(
            project_id=integration.project_id,
            parent_id=parent_id,
            node_id=default_node.id,
            title=external_task.title,
            description=external_task.description,
            status=status,
        )
        db.add(task)
        db.flush()

        # Create external link
        sync_hash = hashlib.sha256(
            f"{external_task.title}:{external_task.description}:{external_task.completed}".encode()
        ).hexdigest()[:16]

        link = TaskExternalLink(
            task_id=task.id,
            integration_id=integration.id,
            external_task_id=external_task.external_id,
            external_url=external_task.external_url,
            sync_status="synced",
            sync_hash=sync_hash,
        )
        db.add(link)

        imported_tasks.append({
            "task_id": task.id,
            "external_id": external_task.external_id,
            "title": task.title,
        })

        # Import subtasks if requested
        if payload.include_subtasks and external_task.subtasks:
            for subtask in external_task.subtasks:
                import_task(subtask, parent_id=task.id)

        return task

    # Import each selected task
    for external_id in payload.task_ids:
        try:
            external_task = provider_instance.get_task(
                external_id,
                include_subtasks=payload.include_subtasks,
            )
            import_task(external_task)
        except Exception as e:
            skipped_tasks.append(f"{external_id} (error: {e})")

    # Update integration sync timestamp
    integration.last_synced_at = datetime.utcnow()
    db.commit()

    return {
        "success": True,
        "integration_id": integration.id,
        "imported_count": len(imported_tasks),
        "skipped_count": len(skipped_tasks),
        "imported_tasks": imported_tasks,
        "skipped_tasks": skipped_tasks,
    }

@router.post("/tasks/{task_id}/export")
def export_external_task(task_id: int, payload: TaskExportRequest, db: Session = Depends(get_db)):
    """Export a local task to an external provider."""
    from integrations.encryption import decrypt_token
    from integrations.providers import get_provider
    import hashlib

    # 1. Get local task
    task = get_task_or_404(task_id, db)

    # 2. Get integration and credential
    integration = _get_integration_or_404(payload.integration_id, db)
    credential = integration.credential

    # 3. Validate project match
    if task.project_id != integration.project_id:
        raise HTTPException(
            status_code=400,
            detail="Task project does not match integration project",
        )
    # 4. Check if already exported
    existing_link = (
        db.query(TaskExternalLink)
        .filter(
            TaskExternalLink.task_id == task_id,
            TaskExternalLink.integration_id == integration.id,
        )
        .first()
    )
    if existing_link:
        raise HTTPException(
            status_code=400,
            detail=f"Task already linked to external ID: {existing_link.external_task_id}",
        )

    # 5. Get provider and token
    try:
        token = decrypt_token(credential.encrypted_token)
        provider_instance = get_provider(credential.provider.name, token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize provider: {e}")

    # 6. Call export method
    try:
        exported_task = provider_instance.export_task(
            title=task.title,
            description=task.description or "",
            completed=task.status == "done",
            external_project_id=integration.external_project_id,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error on export: {e}")

    # 7. Create external link
    sync_hash = hashlib.sha256(
        f"{exported_task.title}:{exported_task.description}:{exported_task.completed}".encode()
    ).hexdigest()[:16]

    link = TaskExternalLink(
        task_id=task.id,
        integration_id=integration.id,
        external_task_id=exported_task.external_id,
        external_url=exported_task.external_url,
        sync_status="synced",
        sync_hash=sync_hash,
    )
    db.add(link)

    integration.last_synced_at = datetime.utcnow()
    db.commit()

    return {
        "success": True,
        "task_id": task.id,
        "external_task": {
            "external_id": exported_task.external_id,
            "title": exported_task.title,
            "external_url": exported_task.external_url,
        },
    }
