"""Authenticated journal-wide administrative snapshot."""
from collections import Counter
from datetime import UTC, datetime
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.auth import require_admin
from app.core.config import get_settings
from app.db.session import get_db
from app.models import User, Submission, PublicPage, PublicPageHistory, Announcement, CallForPapers, Issue, OutboundMail, SubmissionChecklist
from app.services.workflow_progress import load_editorial_summaries, public_progress
from app.services.content_schedule import effective_status
from app.services.mail_delivery import delivery_configured
router = APIRouter(tags=["administration overview"])
PAGES = {"about":"About the journal","aims-and-scope":"Aims & scope","author-guidelines":"Author guidelines","publication-ethics":"Publication ethics","editorial-policies":"Editorial policies","corrections-and-retractions":"Corrections & retractions","fees-and-licensing":"Fees & licensing"}
@router.get("/api/v1/admin/overview")
def overview(response:Response, db:Annotated[Session,Depends(get_db)], actor:Annotated[User,Depends(require_admin)], offset:int=Query(0,ge=0), limit:int=Query(50,ge=1,le=100), q:str=Query("",max_length=300)):
    response.headers["Cache-Control"]="no-store"
    papers=db.scalars(select(Submission).where(Submission.status!="draft")).all()
    summaries=load_editorial_summaries(db,papers)
    ranks={name:i for i,name in enumerate(["needs_assignment","reports_available","revisions_received","needs_editor","needs_reviewer","waiting_review","awaiting_author","production","closed"])}
    papers.sort(key=lambda p:(ranks.get(summaries[p.id].progress["bucket"],99),p.reference))
    counts=Counter(s.progress["bucket"] for s in summaries.values())
    all_paper_count=len(papers)
    query=q.strip().casefold()
    papers=[p for p in papers if not query or query in f"{p.reference} {p.title} {' '.join(a.full_name for a in p.authors)}".casefold()]
    pages={p.slug:p for p in db.scalars(select(PublicPage))}
    historical=set(db.scalars(select(PublicPageHistory.page_id).where(PublicPageHistory.status=="published").distinct()))
    page_rows=[]
    for slug,title in {**PAGES,**{slug:p.title for slug,p in pages.items()}}.items():
        p=pages.get(slug);live=bool(p and (p.status=="published" or p.id in historical))
        state="missing" if not p else "unpublished_changes" if live and p.status!="published" else p.status
        page_rows.append({"slug":slug,"title":title,"live":live,"status":state,"next_action":"Up to date" if state=="published" else "Review and publish changes" if p else "Create and publish this page"})
    mail=Counter(db.scalars(select(OutboundMail.status)))
    checklist=db.scalar(select(SubmissionChecklist.id).where(SubmissionChecklist.approved_at.is_not(None)).limit(1)) is not None
    return {"observed_at":datetime.now(UTC).isoformat(),"summary":{"papers":all_paper_count,"drafts":len(db.scalars(select(Submission.id).where(Submission.status=="draft")).all()),"active":all_paper_count-counts["closed"],**counts},"pages":page_rows,
        "checks":[{"title":"Author signup email","ready":delivery_configured() and get_settings().mail_backend=="smtp","owner":"Site administrator","detail":"SMTP is required for real email delivery. Capture mode saves verification links locally."},
        {"title":"Submission declarations","ready":checklist,"owner":"Editor-in-chief","detail":"An approved checklist is required for final submission."},
        {"title":"Editor coverage","ready":counts["needs_assignment"]==0,"owner":"Editor-in-chief","detail":f"{counts['needs_assignment']} manuscript(s) need an editor."},
        {"title":"Email delivery queue","ready":not mail['pending'] and not mail['failed'],"owner":"Site administrator","detail":f"{mail['pending']} pending · {mail['failed']} failed"}],
        "content":{"announcements":dict(Counter(effective_status(x) for x in db.scalars(select(Announcement)))),"calls":dict(Counter(effective_status(x) for x in db.scalars(select(CallForPapers)))),"issues":dict(Counter(db.scalars(select(Issue.status))))},
        "manuscripts":{"total":len(papers),"offset":offset,"limit":limit,"items":[{"id":str(p.id),"title":p.title,"authors":[a.full_name for a in p.authors],"editors":summaries[p.id].assigned_editors,"reference":p.reference,"status":p.status,**public_progress(p.status,summaries[p.id]),"progress":summaries[p.id].progress} for p in papers[offset:offset+limit]]}}
