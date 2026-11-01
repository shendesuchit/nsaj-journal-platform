import json
import uuid
from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from conftest import login, PASSWORD
from test_changes import details, submit, PDF
from app.db.session import get_session_factory
from app.models import User, Role, ReviewerProfile, AuditEvent, EditorialDecision, EditorAssignment, Volume, Issue, SubmissionRevision
from app.services.security import hash_password

def setup(client):
    login(client)
    pid=client.post('/api/v1/author/submissions',json=details()).json()['id']
    assert client.post(f'/api/v1/author/submissions/{pid}/files',files={'upload':('paper.pdf',PDF,'application/pdf')}).status_code==201
    assert submit(client,pid).status_code==200
    with get_session_factory()() as db:
        role=Role(name='reviewer');db.add(role);db.flush()
        for name in ['reviewer1','reviewer2']:
            user=User(email=f'{name}@example.test',display_name=name,password_hash=hash_password(PASSWORD),roles=[role])
            db.add(user);db.flush()
            db.add(ReviewerProfile(user_id=user.id,email=user.email,full_name=user.display_name))
        db.commit();ids={u.display_name:str(u.id) for u in db.scalars(select(User))}
    login(client,'site_admin')
    return pid,ids

def case(client,pid):
    r=client.get(f'/api/v1/admin/manuscripts/{pid}');assert r.status_code==200,r.text;return r.json()

def act(client,pid,person,action,data,review_id=None,expected=200):
    payload=dict(represented_user_id=person,expected_snapshot=case(client,pid)['snapshot'],action=action,data=data,review_id=review_id,reason='Colleague unavailable',evidence_reference='Written authorization reference 123',source_confirmed=True)
    r=client.post(f'/api/v1/admin/manuscripts/{pid}/actions',json=payload);assert r.status_code==expected,r.text;return r.json()

def test_complete_assisted_publication(client):
    pid,ids=setup(client);chief=ids['editor_in_chief']
    assert client.get('/api/v1/editorial/worklist').status_code==403
    act(client,pid,chief,'assign_editor',{'editor_id':chief,'can_make_decisions':True})
    for state in ['technical_check','editorial_screening']:act(client,pid,chief,'transition',{'to_status':state,'reason':'Checked manuscript'})
    for name in ['reviewer1','reviewer2']:
        act(client,pid,chief,'invite_reviewer',{'email':name+'@example.test','full_name':name,'due_at':(datetime.now(UTC)+timedelta(days=7)).isoformat(),'round_number':1})
        review=next(r for r in case(client,pid)['reviews'] if r['name']==name)
        act(client,pid,ids[name],'review_response',{'accept':True,'confidentiality_accepted':True},review['id'])
    act(client,pid,chief,'transition',{'to_status':'editorial_screening','reason':'Attempt to go back'},expected=403)
    act(client,pid,chief,'decision',{'decision':'accepted','author_letter':'Accepted','round_number':1},expected=409)
    for name in ['reviewer1','reviewer2']:
        review=next(r for r in case(client,pid)['reviews'] if r['name']==name)
        act(client,pid,ids[name],'review_report',{'recommendation':'accept','comments_to_author':'Methods and results checked.'},review['id'])
    assert case(client,pid)['progress']['bucket']=='reports_available'
    login(client,'author');r=client.get(f'/api/v1/author/submissions/{pid}/editorial');assert r.status_code==200,r.text;assert 'Awaiting' in r.json()['status_detail']
    login(client,'site_admin');act(client,pid,chief,'decision',{'decision':'accepted','author_letter':'Accepted after review','round_number':1})
    with get_session_factory()() as db:
        assert str(db.scalar(select(EditorialDecision)).editor_id)==ids['site_admin']
        assert str(db.scalar(select(EditorAssignment)).editor_id)==chief
        events=db.scalars(select(AuditEvent).where(AuditEvent.event_type=='review.report_submitted')).all()
        assert len(events)==2 and all(str(x.actor_id)==ids['site_admin'] and x.details['represented_user_id'] in [ids['reviewer1'],ids['reviewer2']] for x in events)
        v=Volume(number=1,year=2026,created_by_id=uuid.UUID(ids['site_admin']));db.add(v);db.flush()
        issue=Issue(volume_id=v.id,number='1',title='Research issue',created_by_id=uuid.UUID(ids['site_admin']));db.add(issue);db.commit();issue_id=str(issue.id)
    file_id=case(client,pid)['files'][0]['id']
    act(client,pid,chief,'production',{'slug':'clinical-study','title':'Clinical study','abstract':'Research abstract','final_file_id':file_id,'license':'CC BY 4.0'})
    act(client,pid,chief,'assign_issue',{'issue_id':issue_id})
    act(client,pid,chief,'publish_issue',{},expected=409)
    act(client,pid,chief,'verify_license',{'evidence_reference':'Author license agreement'})
    act(client,pid,chief,'schedule_issue',{'scheduled_at':(datetime.now(UTC)-timedelta(minutes=1)).isoformat()})
    act(client,pid,chief,'publish_issue',{})
    assert case(client,pid)['status']=='published'

def test_stale_permissions_and_revision(client):
    pid,ids=setup(client);chief=ids['editor_in_chief'];stale=case(client,pid)['snapshot']
    act(client,pid,chief,'assign_editor',{'editor_id':chief,'can_make_decisions':True})
    payload=dict(represented_user_id=chief,expected_snapshot=stale,action='transition',data={'to_status':'technical_check','reason':'Checked'},reason='Unavailable editor',evidence_reference='email 123')
    assert client.post(f'/api/v1/admin/manuscripts/{pid}/actions',json=payload).status_code==409
    act(client,pid,ids['author'],'transition',{'to_status':'technical_check','reason':'Checked'},expected=403)
    act(client,pid,chief,'transition',{'to_status':'technical_check','reason':'Checked files'})
    act(client,pid,chief,'decision',{'decision':'revision_requested','author_letter':'Please revise the methods','round_number':1})
    payload=dict(represented_user_id=ids['author'],expected_snapshot=case(client,pid)['snapshot'],action='revision',reason='Author requested assistance',evidence_reference='Author email 456',source_confirmed=True)
    r=client.post(f'/api/v1/admin/manuscripts/{pid}/revision',data={'assistance':json.dumps(payload),'response_note':'Revised methods'},files={'upload':('revised.pdf',PDF,'application/pdf')});assert r.status_code==200,r.text
    assert case(client,pid)['progress']['current_round']==2
    with get_session_factory()() as db:
        assert str(db.scalar(select(SubmissionRevision)).author_id)==ids['author']
        event=db.scalar(select(AuditEvent).where(AuditEvent.event_type=='submission.revision_submitted'));assert str(event.actor_id)==ids['site_admin']
    login(client,'author');assert client.get(f'/api/v1/admin/manuscripts/{pid}').status_code==403

def test_conflict_and_cancellation(client):
    pid,ids=setup(client);chief=ids['editor_in_chief']
    initial=case(client,pid)
    assert any(option['email']=='reviewer1@example.test' for option in initial['reviewer_options'])
    assert any(step['state']=='current' for step in initial['steps'])
    act(client,pid,chief,'assign_editor',{'editor_id':chief,'can_make_decisions':True})
    for state in ['technical_check','editorial_screening']:act(client,pid,chief,'transition',{'to_status':state,'reason':'Checks completed'})
    act(client,pid,chief,'invite_reviewer',{'email':'reviewer1@example.test','full_name':'reviewer1','due_at':(datetime.now(UTC)+timedelta(days=7)).isoformat()})
    rid=case(client,pid)['reviews'][0]['id']
    act(client,pid,ids['reviewer1'],'review_response',{'accept':True,'confidentiality_accepted':True,'has_conflict':True,'conflict_details':'Previously collaborated'},rid)
    act(client,pid,chief,'resolve_conflict',{'clear':True},rid)
    act(client,pid,chief,'cancel_review',{'reason':'Reviewer no longer available'},rid)
    assert case(client,pid)['reviews'][0]['status']=='cancelled'
    act(client,pid,ids['reviewer1'],'review_report',{'recommendation':'accept','comments_to_author':'Late report'},rid,expected=403)
