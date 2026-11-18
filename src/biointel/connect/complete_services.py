from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .collaboration import CollaborationService
from .communities import CommunityService
from .discovery import DiscoveryService, ShiroConnectService
from .governance import DraftSchedulerService, LifecycleService, NotificationDeliveryService, OnboardingService, VerificationService
from .messaging import MessagingService
from .operations import AccessibilityService, AdminService, OperationsService
from .social_media import CallService, LiveStreamService, ShortVideoService, StoryService
from .phase_b import CollaborativeDocumentService, WhiteboardService, ResearchNotebookService, DataRoomService
from .phase_c import GrantIntelligenceService, ConsortiumService, DataAccessCommitteeService, GovernancePolicyService
from .phase_d import PeerReviewService, PreprintPublishingService, ContributorshipService, TrustPortfolioService
from .phase_e import ContentIntegrityService, RetractionAlertService, KnowledgeGraphService, CollaboratorMatchingService, ExpertFinderService
from .phase_f import ServiceMarketplaceService, EquipmentBookingService, AdvancedEventService, MentorshipService
from .phase_g import InstitutionalTenantService, EnterpriseIdentityService, DeveloperPlatformService, WebhookAutomationService
from .phase_h import NetworkAnalyticsService, ScientificTrendService, DigitalPreservationService
from .planning import PlanningService

@dataclass(frozen=True)
class CompleteConnectSuite:
    messaging: MessagingService
    communities: CommunityService
    collaboration: CollaborationService
    discovery: DiscoveryService
    shiro: ShiroConnectService
    stories: StoryService
    short_videos: ShortVideoService
    live_streams: LiveStreamService
    calls: CallService
    verification: VerificationService
    onboarding: OnboardingService
    delivery: NotificationDeliveryService
    drafts: DraftSchedulerService
    lifecycle: LifecycleService
    accessibility: AccessibilityService
    admin: AdminService
    operations: OperationsService
    documents: CollaborativeDocumentService
    whiteboards: WhiteboardService
    notebooks: ResearchNotebookService
    data_rooms: DataRoomService
    grants: GrantIntelligenceService
    consortia: ConsortiumService
    dac: DataAccessCommitteeService
    policies: GovernancePolicyService
    peer_review: PeerReviewService
    preprints: PreprintPublishingService
    contributorship: ContributorshipService
    trust: TrustPortfolioService
    integrity: ContentIntegrityService
    retractions: RetractionAlertService
    knowledge_graph: KnowledgeGraphService
    matching: CollaboratorMatchingService
    experts: ExpertFinderService
    marketplace: ServiceMarketplaceService
    equipment: EquipmentBookingService
    events: AdvancedEventService
    mentorship: MentorshipService
    tenants: InstitutionalTenantService
    enterprise_identity: EnterpriseIdentityService
    developer: DeveloperPlatformService
    webhooks: WebhookAutomationService
    analytics: NetworkAnalyticsService
    trends: ScientificTrendService
    preservation: DigitalPreservationService
    planning: PlanningService


def build_complete_suite(base:Any,storage_root:str|Path)->CompleteConnectSuite:
    repo=base.repository
    communities=CommunityService(repo); collaboration=CollaborationService(repo)
    discovery=DiscoveryService(repo,base.profiles,communities,collaboration)
    admin=AdminService(repo)
    return CompleteConnectSuite(
        messaging=MessagingService(repo,base.network), communities=communities,
        collaboration=collaboration, discovery=discovery,
        shiro=ShiroConnectService(repo,discovery), stories=StoryService(repo),
        short_videos=ShortVideoService(repo), live_streams=LiveStreamService(repo),
        calls=CallService(repo), verification=VerificationService(repo),
        onboarding=OnboardingService(repo), delivery=NotificationDeliveryService(repo),
        drafts=DraftSchedulerService(repo,base.content), lifecycle=LifecycleService(repo,base.content),
        accessibility=AccessibilityService(repo), admin=admin,
        operations=OperationsService(repo,storage_root,admin),
        documents=CollaborativeDocumentService(base), whiteboards=WhiteboardService(base),
        notebooks=ResearchNotebookService(base), data_rooms=DataRoomService(base),
        grants=GrantIntelligenceService(base), consortia=ConsortiumService(base),
        dac=DataAccessCommitteeService(base), policies=GovernancePolicyService(base),
        peer_review=PeerReviewService(base), preprints=PreprintPublishingService(base),
        contributorship=ContributorshipService(base), trust=TrustPortfolioService(base),
        integrity=ContentIntegrityService(base), retractions=RetractionAlertService(base),
        knowledge_graph=KnowledgeGraphService(base), matching=CollaboratorMatchingService(base),
        experts=ExpertFinderService(base), marketplace=ServiceMarketplaceService(base),
        equipment=EquipmentBookingService(base), events=AdvancedEventService(base),
        mentorship=MentorshipService(base), tenants=InstitutionalTenantService(base),
        enterprise_identity=EnterpriseIdentityService(base), developer=DeveloperPlatformService(base),
        webhooks=WebhookAutomationService(base), analytics=NetworkAnalyticsService(base),
        trends=ScientificTrendService(base), preservation=DigitalPreservationService(base),
        planning=PlanningService(base),
    )


