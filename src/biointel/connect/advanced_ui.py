from __future__ import annotations
from pathlib import Path
import json
import streamlit as st
from .complete_ui import _suite
from .ui import header,run
from biointel.ui.frontend_v10 import empty_state

def _csv(value:str)->list[str]: return [x.strip() for x in value.split(',') if x.strip()]
def _show(items):
    if not items:
        empty_state('No persisted records yet', 'This workspace is ready but has no permission-visible records.', icon='＋', action_hint='Use the creation controls above to add the first governed record.')
        return
    st.dataframe([dict(x) for x in items],hide_index=True,width="stretch")

def render_docs_whiteboard(root:Path)->None:
    _,user,s=_suite(root); header('Collaborative documents and whiteboards','Durable optimistic-version documents with real Markdown, PDF, DOCX and PNG exports.')
    docs,boards=st.tabs(['Documents','Whiteboards'])
    with docs:
        with st.form('doc_create'):
            title=st.text_input('Document title'); kind=st.selectbox('Type',['manuscript','protocol','proposal','meeting_notes','technical_report']); content=st.text_area('Initial content'); submit=st.form_submit_button('Create document',type='primary')
        if submit:
            result=run(lambda:s.documents.create(user['user_id'],title,kind,content),'Document created')
            if result: st.session_state['advanced_doc_id']=result['document_id']
        doc_id=st.text_input('Document ID',value=st.session_state.get('advanced_doc_id','')); delta=st.text_area('Text to append'); expected=st.number_input('Expected version',min_value=1,value=1)
        with st.container(horizontal=True):
            if st.button('Save revision',disabled=not doc_id): run(lambda:s.documents.apply_crdt_patch(user['user_id'],doc_id,'insert',delta,int(expected)),'Revision saved')
            for fmt in ('markdown','pdf','docx'):
                if st.button(f'Export {fmt.upper()}',disabled=not doc_id,key=f'export_{fmt}'):
                    result=run(lambda fmt=fmt:s.documents.export(user['user_id'],doc_id,fmt),'Export created')
                    if result: st.json({k:v for k,v in result.items() if not k.startswith('_')})
    with boards:
        title=st.text_input('Whiteboard title'); template=st.selectbox('Template',['custom','bioinformatics_workflow','study_design','pathway'])
        if st.button('Create whiteboard',type='primary'):
            result=run(lambda:s.whiteboards.create(user['user_id'],title,template),'Whiteboard created')
            if result: st.session_state['advanced_wb_id']=result['whiteboard_id']
        wb_id=st.text_input('Whiteboard ID',value=st.session_state.get('advanced_wb_id',''))
        if st.button('Export real PNG',disabled=not wb_id):
            result=run(lambda:s.whiteboards.export(user['user_id'],wb_id),'PNG created')
            if result: st.json({k:v for k,v in result.items() if not k.startswith('_')})

def render_notebooks_data_rooms(root:Path)->None:
    _,user,s=_suite(root); header('Lab notebooks and secure data rooms','Server-signed durable ELN entries and agreement-gated media access.')
    notebook,room=st.tabs(['ELN','Data rooms'])
    with notebook:
        title=st.text_input('Entry title'); kind=st.selectbox('Entry type',['experiment','observation','protocol','analysis']); content=st.text_area('Entry content')
        if st.button('Create ELN entry',type='primary'):
            result=run(lambda:s.notebooks.create_entry(user['user_id'],title,kind,content),'Entry created')
            if result: st.session_state['eln_id']=result['entry_id']
        eid=st.text_input('Entry ID',value=st.session_state.get('eln_id',''))
        if st.button('Lock and server-sign',disabled=not eid):
            result=run(lambda:s.notebooks.lock_and_sign(user['user_id'],eid),'Entry signed')
            if result: st.json({k:v for k,v in result.items() if k!='content'})
    with room:
        title=st.text_input('Room title'); institution=st.text_input('Institution')
        if st.button('Create data room',type='primary'):
            result=run(lambda:s.data_rooms.create(user['user_id'],title,institution),'Data room created')
            if result: st.session_state['room_id']=result['room_id']
        rid=st.text_input('Data-room ID',value=st.session_state.get('room_id','')); media_id=st.text_input('Existing media ID')
        with st.container(horizontal=True):
            if st.button('Accept agreement',disabled=not rid): run(lambda:s.data_rooms.accept_agreement(user['user_id'],rid),'Agreement accepted')
            if st.button('Assign owned media',disabled=not(rid and media_id)): run(lambda:s.data_rooms.add_file(user['user_id'],rid,media_id),'Media assigned')
            if st.button('Authorize download',disabled=not(rid and media_id)):
                result=run(lambda:s.data_rooms.download_file(user['user_id'],rid,media_id),'Download authorized')
                if result: st.json(result)

def render_grants_consortia(root:Path)->None:
    _,user,s=_suite(root); header('Grants and consortia','Persisted grant proposals, consortium decisions and quorum-aware voting.')
    grant,consortium=st.tabs(['Grants','Consortia'])
    with grant:
        sponsor=st.text_input('Sponsor'); title=st.text_input('Opportunity title'); amount=st.number_input('Funding amount',min_value=0.0); deadline=st.text_input('Deadline (ISO)'); fields=st.text_input('Fields, comma separated')
        if st.button('Add grant opportunity',type='primary'):
            result=run(lambda:s.grants.add_opportunity(sponsor,title,amount,deadline,_csv(fields)),'Opportunity added')
            if result: st.session_state['grant_id']=result['grant_id']
        gid=st.text_input('Grant ID',value=st.session_state.get('grant_id','')); proposal=st.text_input('Proposal title')
        if st.button('Create proposal',disabled=not gid): run(lambda:s.grants.create_proposal(user['user_id'],gid,proposal,user['user_id']),'Proposal created')
    with consortium:
        name=st.text_input('Consortium name'); lead=st.text_input('Lead institution')
        if st.button('Create consortium',type='primary'):
            result=run(lambda:s.consortia.create(user['user_id'],name,lead),'Consortium created')
            if result: st.session_state['consortium_id']=result['consortium_id']
        cid=st.text_input('Consortium ID',value=st.session_state.get('consortium_id','')); decision=st.text_input('Decision title'); quorum=st.number_input('Quorum',min_value=1,value=2)
        if st.button('Open decision vote',disabled=not cid):
            result=run(lambda:s.consortia.propose_decision_vote(user['user_id'],cid,decision,int(quorum)),'Vote opened')
            if result: st.session_state['vote_id']=result['vote_id']
        vote_id=st.text_input('Vote ID',value=st.session_state.get('vote_id','')); choice=st.selectbox('Choice',['approve','reject','abstain'])
        if st.button('Cast vote',disabled=not(cid and vote_id)): run(lambda:s.consortia.cast_vote(user['user_id'],cid,vote_id,choice),'Vote recorded')

def render_governance_dac(root:Path)->None:
    _,user,s=_suite(root); header('Governance and DAC','Persisted policies, acknowledgements and membership-controlled data-access decisions.')
    policy,dac=st.tabs(['Policies','Data access committee'])
    with policy:
        title=st.text_input('Policy title'); content=st.text_area('Policy content'); scope=st.text_input('Scope',value='global')
        if st.button('Create policy',type='primary'):
            result=run(lambda:s.policies.create_policy(user['user_id'],title,content,scope),'Policy created')
            if result: st.session_state['policy_id']=result['policy_id']
        pid=st.text_input('Policy ID',value=st.session_state.get('policy_id',''))
        if st.button('Acknowledge policy',disabled=not pid): run(lambda:s.policies.acknowledge_policy(user['user_id'],pid),'Acknowledged')
    with dac:
        dataset=st.text_input('Dataset ID'); purpose=st.text_area('Intended use')
        if st.button('Submit access request',type='primary'):
            result=run(lambda:s.dac.submit_request(user['user_id'],dataset,purpose),'Request submitted')
            if result: st.session_state['dac_request']=result['request_id']
        request_id=st.text_input('Request ID',value=st.session_state.get('dac_request','')); decision=st.selectbox('DAC decision',['approve','reject'])
        if st.button('Record committee vote',disabled=not request_id): run(lambda:s.dac.vote_request(user['user_id'],request_id,decision),'Vote recorded')

def render_peer_review_preprints(root:Path)->None:
    _,user,s=_suite(root); header('Peer review and preprints','Assignment-gated reviews and versioned correction/withdrawal records.')
    review,preprint=st.tabs(['Peer review','Preprints'])
    with review:
        manuscript=st.text_input('Manuscript ID'); reviewer=st.text_input('Reviewer user ID')
        if st.button('Invite reviewer',type='primary'):
            result=run(lambda:s.peer_review.invite_reviewer(user['user_id'],manuscript,reviewer),'Invitation created')
            if result: st.session_state['review_id']=result['review_id']
        rid=st.text_input('Review ID',value=st.session_state.get('review_id','')); accept=st.toggle('Accept invitation'); coi=st.toggle('Conflict of interest declared')
        if st.button('Respond as reviewer',disabled=not rid): run(lambda:s.peer_review.respond_invitation(user['user_id'],rid,accept,coi),'Response recorded')
    with preprint:
        title=st.text_input('Preprint title'); abstract=st.text_area('Abstract'); licence=st.selectbox('Licence',['CC-BY-4.0','CC0-1.0','All rights reserved'])
        if st.button('Submit preprint',type='primary'):
            result=run(lambda:s.preprints.submit_preprint(user['user_id'],title,abstract,licence),'Preprint submitted')
            if result: st.session_state['preprint_id']=result['preprint_id']
        pid=st.text_input('Preprint ID',value=st.session_state.get('preprint_id','')); notice=st.text_area('Correction notice')
        if st.button('Issue correction',disabled=not pid): run(lambda:s.preprints.issue_correction(user['user_id'],pid,notice),'Correction recorded')

def render_contributorship_trust(root:Path)->None:
    _,user,s=_suite(root); header('Contributorship and trust portfolio','Evidence-linked CRediT roles and transparent endorsement records; no opaque trust score.')
    manuscript=st.text_input('Manuscript ID'); target=st.text_input('Contributor user ID'); roles=st.text_input('CRediT roles, comma separated')
    if st.button('Assign roles',type='primary'): run(lambda:s.contributorship.assign_credit_roles(user['user_id'],manuscript,target,_csv(roles)),'Roles assigned')
    if st.button('Lock authorship',disabled=not manuscript): run(lambda:s.contributorship.lock_authorship(user['user_id'],manuscript),'Authorship locked')
    skill=st.text_input('Skill endorsement'); endorsed=st.text_input('Endorsed user ID')
    if st.button('Add endorsement',disabled=not(skill and endorsed)): run(lambda:s.trust.add_skill_endorsement(user['user_id'],endorsed,skill),'Endorsement added')
    if st.button('View my portfolio'):
        result=run(lambda:s.trust.get_reputation_portfolio(user['user_id']),'')
        if result: st.json(result)

def render_integrity_knowledge_graph(root:Path)->None:
    _,user,s=_suite(root); header('Integrity and knowledge graph','Human-review integrity signals plus permission-aware evidence relationships.')
    integrity,graph=st.tabs(['Integrity','Knowledge graph'])
    with integrity:
        content=st.text_input('Content ID'); checksum=st.text_input('SHA-256')
        if st.button('Record integrity scan',type='primary'): run(lambda:s.integrity.scan_content_integrity(user['user_id'],content,checksum),'Integrity evidence recorded')
    with graph:
        node=st.text_input('Node ID'); label=st.text_input('Label'); entity=st.selectbox('Entity type',['researcher','project','publication','dataset','protocol','gene','disease','institution']); visibility=st.selectbox('Visibility',['public','private'])
        if st.button('Add node',type='primary'): run(lambda:s.knowledge_graph.add_node(node,label,entity,visibility),'Node added')
        source=st.text_input('Source node'); target=st.text_input('Target node'); relation=st.text_input('Evidence relation')
        if st.button('Add edge',disabled=not(source and target and relation)): run(lambda:s.knowledge_graph.add_edge(source,target,relation,visibility),'Edge added')
        if st.button('Query authorized graph'):
            result=run(lambda:s.knowledge_graph.query_graph(user['user_id'],entity),'')
            if result: st.json(result)

def render_matching_experts(root:Path)->None:
    _,user,s=_suite(root); header('Collaborator matching and expert finder','Explainable matching derived from stored profile data; users may opt out through privacy settings.')
    field=st.text_input('Research field, gene or pathway'); skills=st.text_input('Required skills, comma separated')
    if st.button('Find collaborators',type='primary'):
        _show(run(lambda:s.matching.find_collaborators(user['user_id'],field,_csv(skills)),'') or [])
    if st.button('Search experts'):
        _show(run(lambda:s.experts.search_experts(field),'') or [])
    expert=st.text_input('Expert user ID'); question=st.text_area('Research question'); commitment=st.text_input('Requested commitment')
    if st.button('Request consultation',disabled=not expert): run(lambda:s.experts.request_consultation(user['user_id'],expert,question,commitment),'Request saved')

def render_marketplace_equipment(root:Path)->None:
    _,user,s=_suite(root); header('Marketplace and equipment','Persisted service listings, quotes and conflict-checked equipment bookings; availability is never fabricated.')
    market,equipment=st.tabs(['Services','Equipment'])
    with market:
        name=st.text_input('Service name'); category=st.text_input('Category'); days=st.number_input('Turnaround days',min_value=1,value=7)
        if st.button('Create listing',type='primary'):
            result=run(lambda:s.marketplace.create_listing(user['user_id'],name,category,int(days)),'Listing created')
            if result: st.session_state['listing_id']=result['listing_id']
        lid=st.text_input('Listing ID',value=st.session_state.get('listing_id','')); samples=st.number_input('Sample count',min_value=1,value=1); requirements=st.text_area('Requirements')
        if st.button('Request quote',disabled=not lid): run(lambda:s.marketplace.request_quote(user['user_id'],lid,int(samples),requirements),'Quote requested')
    with equipment:
        name=st.text_input('Equipment name'); location=st.text_input('Location')
        if st.button('Register equipment',type='primary'):
            result=run(lambda:s.equipment.register_equipment(user['user_id'],name,location),'Equipment registered')
            if result: st.session_state['equipment_id']=result['equipment_id']
        eid=st.text_input('Equipment ID',value=st.session_state.get('equipment_id','')); start=st.text_input('Start time (ISO)'); end=st.text_input('End time (ISO)')
        if st.button('Book slot',disabled=not(eid and start and end)): run(lambda:s.equipment.book_slot(user['user_id'],eid,start,end),'Booking confirmed')

def render_events_mentorship(root:Path)->None:
    _,user,s=_suite(root); header('Events and mentorship','Persisted events with Calls integration metadata and durable mentorship lifecycles.')
    events,mentorship=st.tabs(['Events','Mentorship'])
    with events:
        title=st.text_input('Event title'); date=st.text_input('Start date/time (ISO)')
        if st.button('Create event',type='primary'):
            result=run(lambda:s.events.create_conference(user['user_id'],title,date),'Event created')
            if result: st.session_state['event_id']=result['event_id']
        eid=st.text_input('Event ID',value=st.session_state.get('event_id','')); abstract_title=st.text_input('Abstract title'); abstract=st.text_area('Abstract')
        if st.button('Submit abstract',disabled=not eid): run(lambda:s.events.submit_abstract(user['user_id'],eid,abstract_title,abstract),'Abstract submitted')
    with mentorship:
        mentor=st.text_input('Mentor user ID'); goals=st.text_area('Mentorship goals')
        if st.button('Request mentorship',type='primary'):
            result=run(lambda:s.mentorship.request_mentorship(user['user_id'],mentor,goals),'Request saved')
            if result: st.session_state['mentorship_id']=result['mentorship_id']
        mid=st.text_input('Mentorship ID',value=st.session_state.get('mentorship_id',''))
        if st.button('Accept as mentor',disabled=not mid): run(lambda:s.mentorship.accept_mentorship(user['user_id'],mid),'Mentorship active')

def render_enterprise_identity(root:Path)->None:
    _,user,s=_suite(root); header('Enterprise tenants and identity','Persistent tenant boundaries. OIDC/SAML/LDAP remain adapter-driven and must not claim success without provider validation.')
    institution=st.text_input('Institution'); domain=st.text_input('Verified domain')
    if st.button('Create tenant',type='primary'):
        result=run(lambda:s.tenants.create_tenant(user['user_id'],institution,domain),'Tenant created')
        if result: st.json(result)
    st.warning('Enterprise SSO provider authentication is configuration-required. JIT provisioning alone is not proof of OIDC/SAML/LDAP authentication.')

def render_developer_webhooks(root:Path)->None:
    _,user,s=_suite(root); header('Developer API and webhooks','Hashed API secrets and real HMAC-signed HTTP POST delivery with SSRF protection.')
    api_tab,hook_tab=st.tabs(['API clients','Webhooks'])
    with api_tab:
        app=st.text_input('Application name'); scopes=st.multiselect('Scopes',['read:profiles','read:datasets','write:workflows','read:projects'])
        if st.button('Create API key',type='primary'):
            result=run(lambda:s.developer.create_api_key(user['user_id'],app,scopes),'API key created')
            if result: st.code(result['raw_secret']); st.caption('Displayed once. Store it securely; only the hash is persisted.')
    with hook_tab:
        url=st.text_input('HTTPS endpoint'); events=st.text_input('Events, comma separated'); secret=st.text_input('Signing secret (24+ chars)',type='password')
        if st.button('Register webhook',type='primary'): run(lambda:s.webhooks.register_webhook(user['user_id'],url,_csv(events),secret),'Webhook registered')
        st.caption('Delivery is marked successful only after the endpoint returns HTTP 2xx. Private-network targets are blocked unless explicitly enabled for local integration tests.')

def render_analytics_preservation(root:Path)->None:
    _,user,s=_suite(root); header('Analytics, trends and preservation','Metrics come from persisted events; preservation creates and verifies a real local ZIP fixity package.')
    analytics,preservation=st.tabs(['Analytics','Preservation'])
    with analytics:
        if st.button('Refresh my real metrics',type='primary'):
            result=run(lambda:s.analytics.get_user_analytics(user['user_id']),'')
            if result: st.json(result)
        if st.button('Discover hashtag trends'): _show(run(lambda:s.trends.discover_trends(),'') or [])
    with preservation:
        title=st.text_input('Bundle title'); datasets=st.text_input('Dataset IDs, comma separated'); workflows=st.text_input('Workflow IDs, comma separated')
        if st.button('Create verified local package',type='primary'):
            result=run(lambda:s.preservation.create_reproducibility_bundle(user['user_id'],title,_csv(datasets),_csv(workflows)),'Local package created')
            if result: st.session_state['bundle_id']=result['bundle_id']; st.json({k:v for k,v in result.items() if k!='archive_path'})
        bid=st.text_input('Bundle ID',value=st.session_state.get('bundle_id',''))
        if st.button('Verify fixity',disabled=not bid):
            result=run(lambda:s.preservation.verify_bundle(user['user_id'],bid),'')
            if result: st.json(result)
        st.caption('No permanent archive claim is made; this creates a locally verified preservation package only.')

def render_tasks_milestones(root:Path)->None:
    _,user,s=_suite(root); header('Tasks and milestones','Project-scoped durable planning with dependencies, due dates and calculated progress.')
    project=st.text_input('Project ID'); title=st.text_input('Task title'); assignee=st.text_input('Assignee user ID'); due=st.text_input('Due time (ISO, optional)'); priority=st.selectbox('Priority',['low','medium','high','critical']); deps=st.text_input('Dependency task IDs, comma separated')
    if st.button('Create task',type='primary',disabled=not project):
        result=run(lambda:s.planning.create_task(user['user_id'],project,title,assignee or None,due or None,priority,_csv(deps)),'Task created')
        if result: st.session_state['task_id']=result['task_id']
    task=st.text_input('Task ID',value=st.session_state.get('task_id','')); status=st.selectbox('Status',['todo','in_progress','blocked','completed','cancelled'])
    if st.button('Update task status',disabled=not task): run(lambda:s.planning.set_task_status(user['user_id'],task,status),'Task updated')
    milestone=st.text_input('Milestone title'); milestone_tasks=st.text_input('Milestone task IDs, comma separated')
    if st.button('Create milestone',disabled=not project): run(lambda:s.planning.create_milestone(user['user_id'],project,milestone,None,_csv(milestone_tasks)),'Milestone created')
    if st.button('Refresh project progress',disabled=not project):
        result=run(lambda:s.planning.progress(user['user_id'],project),'')
        if result: st.json(result); _show(s.planning.list_tasks(user['user_id'],project))
