"""Admin assistance reuses role-authorized handlers; it never switches login sessions."""
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from app.api import editorial as e, publication as p
from app.api.auth import require_admin, require_csrf
from app.models import User, Submission, EditorAssignment, ReviewAssignment, ReviewerProfile, AuditEvent, Article, Issue, Role
from app.services.workflow_progress import load_editorial_summaries, public_progress

router = APIRouter(prefix="/api/v1/admin/manuscripts", tags=["admin workflow assistance"])
Admin = Annotated[User, Depends(require_admin)]
class ConflictInput(e.StrictModel):
    clear: bool

def conflict_action(assignment_id, payload, db, actor):
    return e.resolve_review_conflict(assignment_id, payload.clear, db, actor)

ACTIONS = {
    "cancel_review": (e.CancelReviewInput, e.cancel_review, "editor_review"),
    "resolve_conflict": (ConflictInput, conflict_action, "editor_review"),
    "assign_editor": (e.AssignEditorInput, e.assign_editor, "paper"),
    "transition": (e.TransitionInput, e.transition_submission, "paper"),
    "invite_reviewer": (e.ReviewerInviteInput, e.invite_reviewer, "paper"),
    "review_response": (e.ReviewResponseInput, e.respond_to_review_invitation, "review"),
    "review_report": (e.ReviewReportInput, e.submit_review_report, "review"),
    "decision": (e.DecisionInput, e.make_editorial_decision, "paper"),
    "production": (p.ArticleInput, p.create_production_article, "paper"),
    "verify_license": (p.VerifyValueInput, p.verify_article_license, "article"),
    "verify_doi": (p.VerifyDoiInput, p.verify_article_doi, "article"),
    "assign_issue": (p.ArticleIssueInput, p.assign_article_to_issue, "article"),
    "schedule_issue": (p.IssueScheduleInput, p.schedule_issue, "issue"),
}

def records(db, paper):
    editors = db.scalars(select(EditorAssignment).where(EditorAssignment.submission_id == paper.id, EditorAssignment.is_active.is_(True))).all()
    reviews = db.scalars(select(ReviewAssignment).where(ReviewAssignment.submission_id == paper.id)).all()
    article = db.scalar(select(Article).where(Article.submission_id == paper.id))
    return editors, reviews, article

def snapshot(db, paper):
    editors, reviews, article = records(db, paper)
    targets = [str(paper.id)] + [str(r.id) for r in reviews] + ([str(article.id), str(article.issue_id)] if article else [])
    events = db.scalars(select(AuditEvent.id).where(AuditEvent.target_id.in_(targets), AuditEvent.event_type != "admin.case_viewed").order_by(AuditEvent.id)).all()
    value = [paper.status, [(str(x.id), x.can_make_decisions) for x in editors], [(str(x.id), x.status, x.conflict_status) for x in reviews], [str(x) for x in events]]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

def choices(db, paper):
    editors, reviews, article = records(db, paper)
    result = []
    for user in db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.display_name)):
        roles = e._roles(user)
        if "site_admin" in roles: continue
        actions = []
        if "editor_in_chief" in roles and paper.status not in {"published", "declined", "withdrawn"}: actions.append("assign_editor")
        assignment = next((x for x in editors if x.editor_id == user.id), None)
        if assignment and roles & e.EDITOR_ROLES:
            current_reviews = [r for r in reviews if r.round_number == e.current_review_round(db, paper.id)]
            if paper.status in {"editorial_screening", "reviewer_invitation", "under_review"}:
                if any(r.status in {"invited", "accepted", "conflict_reported"} for r in current_reviews): actions.append("cancel_review")
                if any(r.status == "conflict_reported" for r in current_reviews): actions.append("resolve_conflict")
            if e.manual_transitions(paper): actions.append("transition")
            if paper.status in {"editorial_screening", "reviewer_invitation", "under_review"}: actions.append("invite_reviewer")
            if (assignment.can_make_decisions or "editor_in_chief" in roles) and e.TRANSITIONS.get(paper.status, set()) & {"accepted", "declined", "revision_requested"}: actions.append("decision")
            if paper.status == "accepted" and not article: actions.append("production")
            if article and paper.status in {"production", "scheduled"}:
                actions += ["verify_license", "verify_doi", "assign_issue"]
                if article.issue_id: actions += ["schedule_issue", "publish_issue"]
        profile = db.scalar(select(ReviewerProfile).where(ReviewerProfile.user_id == user.id))
        owned = [r for r in reviews if profile and r.reviewer_profile_id == profile.id and r.round_number == e.current_review_round(db, paper.id)]
        if "reviewer" in roles and paper.status in {"editorial_screening", "reviewer_invitation", "under_review"}:
            if any(r.status == "invited" for r in owned): actions.append("review_response")
            if any(r.status == "accepted" for r in owned): actions.append("review_report")
        if user.id == paper.submitting_author_id and paper.status == "revision_requested" and "author" in roles: actions.append("revision")
        if actions: result.append({"id": str(user.id), "name": user.display_name, "roles": sorted(roles), "actions": actions, "review_ids": [str(r.id) for r in owned]})
    return result

def reviewer_options(db, paper, reviews):
    assigned = {
        review.reviewer_profile_id
        for review in reviews
        if review.round_number == e.current_review_round(db, paper.id)
    }
    profiles = db.scalars(
        select(ReviewerProfile)
        .join(User, User.id == ReviewerProfile.user_id)
        .where(
            ReviewerProfile.is_active.is_(True),
            User.is_active.is_(True),
            User.roles.any(Role.name == "reviewer"),
            ~User.roles.any(Role.name == e.PRIVILEGED_CONFIDENTIAL_ROLE),
        )
        .order_by(ReviewerProfile.full_name, ReviewerProfile.email)
        .limit(500)
    ).all()
    return [
        {
            "id": str(profile.id),
            "email": profile.email,
            "full_name": profile.full_name,
            "affiliation": profile.affiliation,
            "expertise": profile.expertise or [],
            "languages": profile.languages or [],
        }
        for profile in profiles
        if profile.id not in assigned
    ]

@router.get("/{paper_id}")
def case(paper_id: uuid.UUID, response: Response, db: e.DB, actor: Admin):
    response.headers["Cache-Control"] = "no-store"
    paper = e._editorial_submission(db, paper_id)
    summary = load_editorial_summaries(db, [paper])[paper.id]
    editors, reviews, article = records(db, paper)
    targets = [str(paper.id)] + [str(r.id) for r in reviews] + ([str(article.id), str(article.issue_id)] if article else [])
    events = db.scalars(select(AuditEvent).where(AuditEvent.target_id.in_(targets), AuditEvent.event_type != "admin.case_viewed").order_by(AuditEvent.created_at.desc()).limit(100)).all()
    author = db.get(User, paper.submitting_author_id)
    roles = [{"role": "Author", "person": author.display_name if author else "Unavailable", "status": "Revision required" if paper.status == "revision_requested" else "No action required"}]
    for assignment in editors:
        user = db.get(User, assignment.editor_id)
        roles.append({"role": "Decision editor" if assignment.can_make_decisions else "Handling editor", "person": user.display_name if user else "Unavailable", "status": summary.progress["next_action"].replace("_", " ")})
    review_rows = []
    for review in reviews:
        profile = db.get(ReviewerProfile, review.reviewer_profile_id)
        report = db.scalar(select(e.ReviewReport).where(e.ReviewReport.review_assignment_id == review.id))
        name = profile.full_name if profile else "Unavailable"
        roles.append({"role": f"Reviewer · Round {review.round_number}", "person": name, "status": review.status})
        review_rows.append({"id": str(review.id), "name": name, "status": review.status, "round": review.round_number, "recommendation": report.recommendation if report else None, "comments_to_editor": report.comments_to_editor if report else None, "comments_to_author": report.comments_to_author if report else None})
    data = {"id": str(paper.id), "title": paper.title, "reference": paper.reference, "status": paper.status, "snapshot": snapshot(db, paper), "progress": summary.progress, **public_progress(paper.status, summary), "roles": roles, "reviews": review_rows, "actors": choices(db, paper), "manual_transitions": e.manual_transitions(paper), "schemas": {key: model.model_json_schema() for key, (model, _, _) in ACTIONS.items()}, "editor_options": [{"id": str(u.id), "name": u.display_name} for u in db.scalars(select(User).where(User.is_active.is_(True))) if e._roles(u) & e.EDITOR_ROLES and "site_admin" not in e._roles(u)], "reviewer_options": reviewer_options(db, paper, reviews), "files": [{"id": str(f.id), "name": f.original_name} for f in db.scalars(select(e.SubmissionFile).where(e.SubmissionFile.submission_id == paper.id, e.SubmissionFile.scan_status == "clean"))], "issues": [{"id": str(i.id), "name": f"{i.title} · {i.status}"} for i in db.scalars(select(Issue))], "history": [{"event": x.event_type, "at": x.created_at.isoformat(), "by": (db.get(User, x.actor_id).display_name if x.actor_id and db.get(User, x.actor_id) else "System"), "details": x.details} for x in events]}
    visited = set(db.scalars(select(e.SubmissionWorkflowEvent.to_status).where(e.SubmissionWorkflowEvent.submission_id == paper.id)))
    raw_steps = [
        ("Submitted", True), ("Editor assigned", bool(editors)),
        ("Technical check completed", "editorial_screening" in visited),
        ("Review invited", bool(reviews)), ("Review reports received", any(r["recommendation"] for r in review_rows)),
        ("Editorial decision recorded", bool(db.scalar(select(e.EditorialDecision.id).where(e.EditorialDecision.submission_id == paper.id)))),
        ("Production prepared", article is not None), ("Published", paper.status == "published")]
    current_step = next((index for index, (_, recorded) in enumerate(raw_steps) if not recorded), None)
    data["steps"] = [
        {
            "label": label,
            "recorded": recorded,
            "state": "complete" if recorded else "current" if index == current_step else "upcoming",
        }
        for index, (label, recorded) in enumerate(raw_steps)
    ]
    e._audit(db, "admin.case_viewed", actor.id, "submission", paper.id)
    db.commit()
    return data

class Intervention(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    represented_user_id: uuid.UUID
    expected_snapshot: str = Field(min_length=64, max_length=64)
    action: str
    review_id: uuid.UUID | None = None
    reason: str = Field(min_length=3, max_length=4000)
    evidence_reference: str = Field(min_length=3, max_length=1000)
    source_confirmed: bool = False
    data: dict = Field(default_factory=dict)

def validate_assistance(paper, payload, db, actor):
    if payload.expected_snapshot != snapshot(db, paper): raise HTTPException(409, "This case changed. Refresh and review it before recording an action.")
    option = next((x for x in choices(db, paper) if x["id"] == str(payload.represented_user_id)), None)
    if not option or payload.action not in option["actions"]: raise HTTPException(403, "The represented user cannot perform this action on this case.")
    if payload.action in {"review_response", "review_report", "revision"} and not payload.source_confirmed: raise HTTPException(422, "Confirm the named person supplied this response, report or revision.")
    represented = db.get(User, payload.represented_user_id)
    db.info["admin_action"] = {"admin_id": actor.id, "represented_user_id": represented.id, "represented_name": represented.display_name, "reason": payload.reason, "evidence_reference": payload.evidence_reference, "intervention_id": uuid.uuid4()}
    return option, represented

@router.post("/{paper_id}/actions", dependencies=[Depends(require_csrf)])
def intervene(paper_id: uuid.UUID, payload: Intervention, db: e.DB, actor: Admin):
    paper = e._editorial_submission(db, paper_id)
    option, represented = validate_assistance(paper, payload, db, actor)
    try:
        if payload.action == "review_report" and not any(str(payload.data.get(k, "")).strip() for k in ("comments_to_editor", "comments_to_author")): raise HTTPException(422, "The supplied review report must contain comments.")
        _, _, article = records(db, paper)
        if payload.action == "publish_issue":
            if not article or not article.issue_id: raise HTTPException(409, "Assign an issue first.")
            call = lambda: p.publish_issue(article.issue_id, db, represented)
        else:
            if payload.action not in ACTIONS: raise HTTPException(422, "Use the revision file upload form.")
            model, handler, target_kind = ACTIONS[payload.action]
            validated = model.model_validate(payload.data)
            target = paper.id
            if target_kind == "review":
                if str(payload.review_id) not in option["review_ids"]: raise HTTPException(403, "Choose this reviewer's current assignment.")
                target = payload.review_id
            elif target_kind == "editor_review":
                review = db.get(ReviewAssignment, payload.review_id) if payload.review_id else None
                if not review or review.submission_id != paper.id or review.round_number != e.current_review_round(db, paper.id): raise HTTPException(403, "Select a current review from this manuscript.")
                target = review.id
            elif target_kind in {"article", "issue"}:
                if not article: raise HTTPException(409, "Create the production article first.")
                target = article.id if target_kind == "article" else article.issue_id
            if payload.action == "review_response":
                review = db.get(ReviewAssignment, target)
                due = review.due_at.replace(tzinfo=UTC) if review.due_at and review.due_at.tzinfo is None else review.due_at
                if due and due <= datetime.now(UTC): raise HTTPException(409, "This invitation has expired.")
            if payload.action == "review_response":
                review = db.get(ReviewAssignment, target)
                due = review.due_at.replace(tzinfo=UTC) if review.due_at and review.due_at.tzinfo is None else review.due_at
                if due and due <= datetime.now(UTC): raise HTTPException(409, "This invitation has expired.")
            call = lambda: handler(target, validated, db, represented)
        # Existing handlers commit their events and this assistance event together.
        e._audit(db, "admin.workflow_action", actor.id, "submission", paper.id, {"action": payload.action})
        result = call()
        return {"ok": True, "recorded_by": actor.display_name, "on_behalf_of": represented.display_name, "result": result}
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(422, exc.errors(include_context=False)) from exc
    except Exception:
        db.rollback()
        raise
    finally:
        db.info.pop("admin_action", None)

@router.post("/{paper_id}/revision", dependencies=[Depends(require_csrf)])
async def revision(paper_id: uuid.UUID, db: e.DB, actor: Admin,
                   upload: Annotated[e.UploadFile, e.File()],
                   assistance: Annotated[str, e.Form()],
                   response_note: Annotated[str, e.Form()] = ""):
    try:
        payload = Intervention.model_validate_json(assistance)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_context=False)) from exc
    if payload.action != "revision": raise HTTPException(422, "Revision action required.")
    paper = e._editorial_submission(db, paper_id)
    _, represented = validate_assistance(paper, payload, db, actor)
    try:
        # submit_revision records the actual operator via its normal workflow/audit events.
        # A quarantined upload is not recorded as a completed revision.
        return await e.submit_revision(paper_id, db, represented, upload, response_note)
    finally:
        db.info.pop("admin_action", None)

@router.get("/{paper_id}/files/{file_id}")
def download(paper_id: uuid.UUID, file_id: uuid.UUID, db: e.DB, actor: Admin):
    paper = e._editorial_submission(db, paper_id)
    record = db.scalar(select(e.SubmissionFile).where(e.SubmissionFile.id == file_id, e.SubmissionFile.submission_id == paper.id))
    if record is None: raise HTTPException(404, "Manuscript file not found.")
    if record.scan_status != "clean": raise HTTPException(423, "This file has not passed malware scanning.")
    path = e.safe_private_path(record.storage_name)
    e._audit(db, "admin.manuscript_downloaded", actor.id, "submission", paper.id, {"file_id": str(record.id)})
    db.commit()
    return e.FileResponse(path, media_type=record.media_type, filename=record.original_name, headers={"Cache-Control": "private, no-store"})
