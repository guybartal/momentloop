"""Tests for project endpoints."""

import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_list_projects_unauthenticated(client: AsyncClient):
    """Test that listing projects requires authentication."""
    response = await client.get("/api/projects")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_projects_empty(client: AsyncClient, auth_headers: dict):
    """Test listing projects when user has none."""
    response = await client.get("/api/projects", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient, auth_headers: dict):
    """Test creating a new project."""
    response = await client.post(
        "/api/projects",
        json={"name": "Test Project"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Project"
    assert data["status"] == "draft"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient, auth_headers: dict):
    """Test getting a specific project."""
    # First create a project
    create_response = await client.post(
        "/api/projects",
        json={"name": "Get Test Project"},
        headers=auth_headers,
    )
    project_id = create_response.json()["id"]

    # Then get it
    response = await client.get(f"/api/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Get Test Project"
    assert data["id"] == project_id


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient, auth_headers: dict):
    """Test updating a project."""
    # Create a project
    create_response = await client.post(
        "/api/projects",
        json={"name": "Update Test"},
        headers=auth_headers,
    )
    project_id = create_response.json()["id"]

    # Update it
    response = await client.put(
        f"/api/projects/{project_id}",
        json={"name": "Updated Name", "style": "ghibli"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["style"] == "ghibli"


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient, auth_headers: dict):
    """Test deleting a project."""
    # Create a project
    create_response = await client.post(
        "/api/projects",
        json={"name": "Delete Test"},
        headers=auth_headers,
    )
    project_id = create_response.json()["id"]

    # Delete it
    response = await client.delete(f"/api/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 204

    # Verify it's gone
    get_response = await client.get(f"/api/projects/{project_id}", headers=auth_headers)
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_get_project_not_found(client: AsyncClient, auth_headers: dict):
    """Test getting a non-existent project."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/api/projects/{fake_id}", headers=auth_headers)
    assert response.status_code == 404
