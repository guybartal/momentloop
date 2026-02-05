from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.photo import Photo
from app.models.project import Project
from app.models.user import User
from app.models.video import Export
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.storage import storage_service

router = APIRouter()


@router.get("/", response_model=list[ProjectListResponse])
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all projects for the current user."""
    # Subquery to get main export thumbnail (is_main=True) or latest ready export for each project
    # Priority: is_main first, then created_at desc
    # PostgreSQL DISTINCT ON requires ORDER BY to start with the DISTINCT ON column
    main_export_subquery = (
        select(
            Export.project_id,
            Export.thumbnail_path,
        )
        .where(Export.status == "ready")
        .distinct(Export.project_id)
        .order_by(Export.project_id, Export.is_main.desc(), Export.created_at.desc())
        .subquery()
    )

    # Get projects with photo count and main/latest export thumbnail
    result = await db.execute(
        select(
            Project,
            func.count(Photo.id).label("photo_count"),
            main_export_subquery.c.thumbnail_path,
        )
        .outerjoin(Photo, Project.id == Photo.project_id)
        .outerjoin(main_export_subquery, Project.id == main_export_subquery.c.project_id)
        .where(Project.user_id == current_user.id)
        .group_by(Project.id, main_export_subquery.c.thumbnail_path)
        .order_by(Project.created_at.desc())
    )

    projects = []
    for row in result.all():
        project = row[0]
        photo_count = row[1]
        thumbnail_path = row[2]
        projects.append(
            ProjectListResponse(
                id=project.id,
                name=project.name,
                style=project.style,
                status=project.status,
                created_at=project.created_at,
                updated_at=project.updated_at,
                photo_count=photo_count,
                thumbnail_url=storage_service.get_url(thumbnail_path) if thumbnail_path else None,
            )
        )

    return projects


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new project."""
    project = Project(
        name=project_data.name,
        user_id=current_user.id,
        status="draft",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific project."""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project_data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a project."""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if project_data.name is not None:
        project.name = project_data.name
    if project_data.style is not None:
        project.style = project_data.style
    if project_data.style_prompt is not None:
        project.style_prompt = project_data.style_prompt
    if project_data.status is not None:
        project.status = project_data.status

    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project."""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    await db.delete(project)
    await db.commit()
