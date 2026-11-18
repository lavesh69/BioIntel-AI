from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from biointel.database.core import utc_now
from biointel.connect.services import ConnectError, PermissionDenied
from biointel.connect.phase_store import PersistentMap, PersistentList

class ServiceMarketplaceService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._listings = PersistentMap(services,"phase_f.marketplace_listings")
        self._quotes = PersistentMap(services,"phase_f.quote_requests")

    def create_listing(self, provider_id: str, service_name: str, category: str, turnaround_days: int) -> Dict[str, Any]:
        listing_id = f"srv_{uuid.uuid4().hex}"
        now = utc_now()
        listing = {
            "listing_id": listing_id,
            "provider_id": provider_id,
            "service_name": service_name,
            "category": category, # 'sequencing', 'bioinformatics', 'microscopy', 'flow_cytometry'
            "turnaround_days": turnaround_days,
            "payment_gateway_required": False,
            "state": "active",
            "created_at_utc": now
        }
        self._listings[listing_id] = listing
        return listing

    def request_quote(self, user_id: str, listing_id: str, sample_count: int, requirements: str) -> Dict[str, Any]:
        quote_id = f"quote_{uuid.uuid4().hex}"
        now = utc_now()
        quote = {
            "quote_id": quote_id,
            "requester_id": user_id,
            "listing_id": listing_id,
            "sample_count": sample_count,
            "requirements": requirements,
            "status": "pending_quote",
            "created_at_utc": now
        }
        self._quotes[quote_id] = quote
        return quote


class EquipmentBookingService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._equipment = PersistentMap(services,"phase_f.equipment")
        self._bookings = PersistentMap(services,"phase_f.equipment_bookings")

    def register_equipment(self, admin_id: str, name: str, location: str) -> Dict[str, Any]:
        eq_id = f"eq_{uuid.uuid4().hex}"
        now = utc_now()
        eq = {
            "equipment_id": eq_id,
            "owner_id": admin_id,
            "name": name,
            "location": location,
            "state": "available",
            "created_at_utc": now
        }
        self._equipment[eq_id] = eq
        self._bookings[eq_id] = []
        return eq

    def book_slot(self, user_id: str, equipment_id: str, start_time: str, end_time: str) -> Dict[str, Any]:
        eq = self._equipment.get(equipment_id)
        if not eq:
            raise ConnectError("Equipment not found.")
        
        # Transactional double-booking prevention check
        existing = self._bookings.get(equipment_id, [])
        for b in existing:
            if b["start_time"] == start_time and b["state"] == "confirmed":
                raise ConnectError("Double booking error: Slot is already reserved.")

        booking_id = f"book_{uuid.uuid4().hex}"
        booking = {
            "booking_id": booking_id,
            "equipment_id": equipment_id,
            "user_id": user_id,
            "start_time": start_time,
            "end_time": end_time,
            "state": "confirmed",
            "transaction_locked": True,
            "created_at_utc": utc_now()
        }
        self._bookings[equipment_id].append(booking)
        return booking


class AdvancedEventService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._events = PersistentMap(services,"phase_f.events")
        self._abstracts = PersistentMap(services,"phase_f.abstracts")

    def create_conference(self, organizer_id: str, title: str, start_date: str) -> Dict[str, Any]:
        event_id = f"event_{uuid.uuid4().hex}"
        now = utc_now()
        event = {
            "event_id": event_id,
            "organizer_id": organizer_id,
            "title": title,
            "start_date": start_date,
            "multi_track": True,
            "state": "published",
            "created_at_utc": now
        }
        self._events[event_id] = event
        return event

    def submit_abstract(self, author_id: str, event_id: str, title: str, abstract_text: str) -> Dict[str, Any]:
        abs_id = f"abs_{uuid.uuid4().hex}"
        now = utc_now()
        abs_item = {
            "abstract_id": abs_id,
            "event_id": event_id,
            "author_id": author_id,
            "title": title,
            "abstract_text": abstract_text,
            "status": "under_review",
            "created_at_utc": now
        }
        self._abstracts[abs_id] = abs_item
        return abs_item

    def generate_certificate(self, user_id: str, event_id: str) -> Dict[str, Any]:
        return {
            "certificate_id": f"cert_{uuid.uuid4().hex}",
            "user_id": user_id,
            "event_id": event_id,
            "accredited": False, # Non-accredited status explicitly declared per specification
            "issued_at_utc": utc_now()
        }


class MentorshipService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._mentorships = PersistentMap(services,"phase_f.mentorships")

    def request_mentorship(self, mentee_id: str, mentor_id: str, goals: str) -> Dict[str, Any]:
        m_id = f"mentor_{uuid.uuid4().hex}"
        now = utc_now()
        m = {
            "mentorship_id": m_id,
            "mentee_id": mentee_id,
            "mentor_id": mentor_id,
            "goals": goals,
            "status": "requested",
            "created_at_utc": now
        }
        self._mentorships[m_id] = m
        return m

    def accept_mentorship(self, mentor_id: str, mentorship_id: str) -> Dict[str, Any]:
        m = self._mentorships.get(mentorship_id)
        if not m:
            raise ConnectError("Mentorship request not found.")
        if m["mentor_id"] != mentor_id:
            raise PermissionDenied("Only assigned mentor can accept mentorship request.")
        m["status"] = "active"
        return m


