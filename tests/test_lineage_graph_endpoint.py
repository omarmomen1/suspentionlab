"""
tests/test_lineage_graph_endpoint.py
Tests for the real backend engineering lineage graph endpoint GET /api/v1/runs/lineage/graph.
"""
import pytest

@pytest.mark.asyncio
async def test_lineage_graph_endpoint_authenticated(authenticated_client):
    response = await authenticated_client.get("/api/v1/runs/lineage/graph?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert "total_nodes" in data
    assert "total_edges" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)
    assert data["total_nodes"] == len(data["nodes"])
    assert data["total_edges"] == len(data["edges"])

    # If any nodes exist in db, check schema
    if data["nodes"]:
        node = data["nodes"][0]
        assert "id" in node
        assert "type" in node
        assert "label" in node
        assert "status" in node

    # If any edges exist, check schema
    if data["edges"]:
        edge = data["edges"][0]
        assert "id" in edge
        assert "source" in edge
        assert "target" in edge
        assert "relationship" in edge


@pytest.mark.asyncio
async def test_lineage_graph_unauthenticated(client):
    response = await client.get("/api/v1/runs/lineage/graph")
    assert response.status_code == 401
