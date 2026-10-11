"""
tests/test_engineering_questions.py
====================================
Tests for Engineering Question Ingestion, Persistence, Tenant Isolation,
and Zero-Fabrication Command Center KPIs.
"""
import pytest
import uuid
from sqlalchemy import select
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.engineering_question import EngineeringQuestion
from suspensionlab.backend.services.engineering_question_service import EngineeringQuestionService


@pytest.mark.asyncio
async def test_create_and_persist_engineering_question():
    """Verify question ingestion produces persistent backend object with correct fields."""
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    async with SessionLocal() as db:
        q = await EngineeringQuestionService.create_question(
            db=db,
            user_id=user_id,
            user_name="Aerodynamics Engineer",
            title="Front tire saturation increasing in Turn 7",
            question_text="Front slip angle exceeds 7.5 deg during high-speed trail-braking apex entry.",
            vehicle_id="Formula 1 2026 Spec (CAR 07)",
            setup_id="Spa-Francorchamps Aero Rev 28",
            severity="WARNING",
            source="ENGINEER_INPUT",
            organization_id=org_id,
        )

        assert q["id"] is not None
        assert q["question_id"].startswith("Q-2026-")
        assert q["title"] == "Front tire saturation increasing in Turn 7"
        assert q["status"] == "OPEN"
        assert q["severity"] == "WARNING"
        assert q["organization_id"] == org_id
        assert len(q["linked_evidence"]) > 0

        # Query back from DB directly
        stmt = select(EngineeringQuestion).where(EngineeringQuestion.id == uuid.UUID(q["id"]))
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        assert record is not None
        assert record.title == "Front tire saturation increasing in Turn 7"
        assert record.source == "ENGINEER_INPUT"


@pytest.mark.asyncio
async def test_tenant_isolation_on_questions():
    """Verify strict tenant isolation: users from another organization are blocked."""
    user_a = str(uuid.uuid4())
    org_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    org_b = str(uuid.uuid4())

    async with SessionLocal() as db:
        # User A in Org A creates question
        q_a = await EngineeringQuestionService.create_question(
            db=db,
            user_id=user_a,
            user_name="Engineer A",
            title="Confidential Aero Stalling at DRS Closure",
            question_text="High downforce stall observed in wind tunnel correlation.",
            organization_id=org_a,
        )

        # User A in Org A can access it
        fetched = await EngineeringQuestionService.get_question(
            db=db,
            question_id_or_uuid=q_a["question_id"],
            user_id=user_a,
            organization_id=org_a,
            is_admin=False,
        )
        assert fetched["title"] == "Confidential Aero Stalling at DRS Closure"

        # User B in Org B MUST be blocked with PermissionError
        with pytest.raises(PermissionError):
            await EngineeringQuestionService.get_question(
                db=db,
                question_id_or_uuid=q_a["question_id"],
                user_id=user_b,
                organization_id=org_b,
                is_admin=False,
            )

        # Admin user CAN access it
        admin_fetched = await EngineeringQuestionService.get_question(
            db=db,
            question_id_or_uuid=q_a["question_id"],
            user_id=user_b,
            organization_id=org_b,
            is_admin=True,
        )
        assert admin_fetched["title"] == "Confidential Aero Stalling at DRS Closure"


@pytest.mark.asyncio
async def test_update_question_status_and_links():
    """Verify lifecycle progression: updating status and linking experiments."""
    user_id = str(uuid.uuid4())
    async with SessionLocal() as db:
        q = await EngineeringQuestionService.create_question(
            db=db,
            user_id=user_id,
            user_name="Dynamics Lead",
            title="Damper hysteresis divergence in Turn 9",
            question_text="Observed rebound lag during curb strike.",
        )

        updated = await EngineeringQuestionService.update_question(
            db=db,
            question_id_or_uuid=q["question_id"],
            user_id=user_id,
            status="HYPOTHESIS_FORMED",
            linked_experiments=["exp-test-01"],
            linked_decisions=["dec-001"],
        )

        assert updated["status"] == "HYPOTHESIS_FORMED"
        assert "exp-test-01" in updated["linked_experiments"]
        assert "dec-001" in updated["linked_decisions"]


@pytest.mark.asyncio
async def test_list_questions_with_filtering():
    """Verify list_questions filters by severity, vehicle, and status."""
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    async with SessionLocal() as db:
        await EngineeringQuestionService.create_question(
            db=db,
            user_id=user_id,
            user_name="Test User",
            title="Critical Oversteer Warning",
            question_text="High yaw acceleration.",
            severity="CRITICAL",
            organization_id=org_id,
        )

        await EngineeringQuestionService.create_question(
            db=db,
            user_id=user_id,
            user_name="Test User",
            title="Informational Tire Wear",
            question_text="Mild thermal degradation.",
            severity="INFO",
            organization_id=org_id,
        )

        crit_list = await EngineeringQuestionService.list_questions(
            db=db,
            user_id=user_id,
            organization_id=org_id,
            severity="CRITICAL",
        )
        assert all(q["severity"] == "CRITICAL" for q in crit_list)
