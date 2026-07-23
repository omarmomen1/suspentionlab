from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from typing import Dict, Any, List

router = APIRouter(prefix="/scim/v2", tags=["SCIM"])

class SCIMUser(BaseModel):
    schemas: List[str] = ["urn:ietf:params:scim:schemas:core:2.0:User"]
    userName: str
    name: Dict[str, str]
    emails: List[Dict[str, Any]]
    active: bool = True

@router.get("/Users", response_model=Dict[str, Any])
async def get_scim_users():
    """Placeholder for SCIM user provisioning directory GET"""
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": 0,
        "Resources": [],
        "startIndex": 1,
        "itemsPerPage": 100
    }

@router.post("/Users", response_model=Dict[str, Any])
async def create_scim_user(user: SCIMUser):
    """Placeholder for SCIM user provisioning directory POST"""
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": "scim_stub_id",
        "userName": user.userName,
        "active": user.active
    }
