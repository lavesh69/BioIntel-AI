from __future__ import annotations

import hmac
import json
import uuid
import hashlib
import os
import ipaddress
import socket
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from cryptography.fernet import Fernet
from typing import Any, Dict, List, Optional
from biointel.database.core import utc_now
from biointel.connect.services import ConnectError, PermissionDenied
from biointel.connect.phase_store import PersistentMap, PersistentList

class InstitutionalTenantService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._tenants = PersistentMap(services,"phase_g.tenants")

    def create_tenant(self, admin_id: str, institution_name: str, domain: str) -> Dict[str, Any]:
        t_id = f"tenant_{uuid.uuid4().hex}"
        now = utc_now()
        tenant = {
            "tenant_id": t_id,
            "admin_id": admin_id,
            "institution_name": institution_name,
            "domain": domain,
            "state": "active",
            "created_at_utc": now
        }
        self._tenants[t_id] = tenant
        return tenant

    def check_tenant_isolation(self, requester_tenant_id: str, target_tenant_id: str) -> bool:
        if requester_tenant_id != target_tenant_id:
            raise PermissionDenied("Cross-tenant access denied: Tenant isolation strictly enforced.")
        return True


class EnterpriseIdentityService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._sso_sessions = PersistentMap(services,"phase_g.sso_sessions")

    def provision_jit_user(self, provider: str, external_id: str, email: str, display_name: str) -> Dict[str, Any]:
        return {
            "user_id": f"usr_sso_{uuid.uuid4().hex[:8]}",
            "provider": provider, # 'oidc', 'saml', 'ldap'
            "external_id": external_id,
            "email": email,
            "display_name": display_name,
            "provision_type": "just_in_time",
            "created_at_utc": utc_now()
        }

    def revoke_session(self, admin_id: str, session_id: str) -> Dict[str, Any]:
        return {
            "session_id": session_id,
            "revoked_by": admin_id,
            "state": "revoked",
            "revoked_at_utc": utc_now()
        }


class DeveloperPlatformService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._api_keys = PersistentMap(services,"phase_g.api_keys")

    def create_api_key(self, user_id: str, app_name: str, scopes: List[str]) -> Dict[str, Any]:
        key_id = f"key_{uuid.uuid4().hex}"
        raw_secret = f"biointel_secret_{uuid.uuid4().hex}"
        hashed_secret = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
        now = utc_now()
        
        api_key = {
            "key_id": key_id,
            "user_id": user_id,
            "app_name": app_name,
            "scopes": scopes,
            "hashed_secret": hashed_secret,
            "state": "active",
            "created_at_utc": now
        }
        self._api_keys[key_id] = api_key
        return {"key_info": api_key, "raw_secret": raw_secret}


class WebhookAutomationService:
    def __init__(self,services:Any)->None:
        self.services=services; self._webhooks=PersistentMap(services,"phase_g.webhooks"); self._deliveries=PersistentMap(services,"phase_g.webhook_deliveries")
        key_dir=Path(services.media.storage_root)/"keys"; key_dir.mkdir(parents=True,exist_ok=True); key_path=key_dir/"webhooks.fernet"
        if not key_path.exists(): key_path.write_bytes(Fernet.generate_key())
        self._cipher=Fernet(key_path.read_bytes())
    def _validate_target(self,target_url:str)->None:
        parsed=urllib.parse.urlparse(target_url)
        if parsed.scheme not in {"http","https"} or not parsed.hostname: raise ConnectError("Webhook URL must use HTTP or HTTPS.")
        allow_private=os.getenv("BIOINTEL_WEBHOOK_ALLOW_PRIVATE","0")=="1"
        try: addresses={item[4][0] for item in socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=="https" else 80),type=socket.SOCK_STREAM)}
        except socket.gaierror as exc: raise ConnectError("Webhook hostname could not be resolved.") from exc
        for value in addresses:
            ip=ipaddress.ip_address(value)
            if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved) and not allow_private: raise PermissionDenied("Webhook target resolves to a private or restricted network address.")
    def register_webhook(self,user_id:str,target_url:str,events:List[str],secret:str)->Dict[str,Any]:
        if len(secret)<24: raise ConnectError("Webhook signing secret must contain at least 24 characters.")
        self._validate_target(target_url); hook_id=f"hook_{uuid.uuid4().hex}"; now=utc_now(); hook={"webhook_id":hook_id,"owner_id":user_id,"target_url":target_url,"events":sorted(set(events)),"secret_ciphertext":self._cipher.encrypt(secret.encode()).decode(),"state":"active","created_at_utc":now,"updated_at_utc":now}
        self._webhooks[hook_id]=hook; return {k:v for k,v in hook.items() if k!="secret_ciphertext"}
    def sign_payload(self,payload_bytes:bytes,secret:str)->str: return hmac.new(secret.encode("utf-8"),payload_bytes,hashlib.sha256).hexdigest()
    def trigger_event(self,webhook_id:str,event_name:str,payload:Dict[str,Any])->Dict[str,Any]:
        hook=self._webhooks.get(webhook_id)
        if not hook or hook["state"]!="active": raise ConnectError("Active webhook not found.")
        if event_name not in hook["events"]: raise PermissionDenied("Webhook is not subscribed to this event.")
        self._validate_target(hook["target_url"]); event_id=f"evt_{uuid.uuid4().hex}"; timestamp=utc_now(); body=json.dumps({"event_id":event_id,"event":event_name,"timestamp":timestamp,"data":payload},sort_keys=True,separators=(",",":")).encode(); secret=self._cipher.decrypt(hook["secret_ciphertext"].encode()).decode(); signature=self.sign_payload(body,secret)
        request=urllib.request.Request(hook["target_url"],data=body,method="POST",headers={"Content-Type":"application/json","User-Agent":"BioIntel-Connect/15.6.0","X-BioIntel-Event":event_id,"X-BioIntel-Timestamp":timestamp,"X-BioIntel-Signature":f"sha256={signature}"})
        delivery_id=f"delivery_{uuid.uuid4().hex}"; status="failed"; http_status=None; error=""
        try:
            with urllib.request.urlopen(request,timeout=5) as response: http_status=int(response.status); status="delivered" if 200<=http_status<300 else "failed"
        except urllib.error.HTTPError as exc: http_status=int(exc.code); error=f"HTTP {exc.code}"
        except (urllib.error.URLError,TimeoutError,OSError) as exc: error=str(exc)[:500]
        delivery={"delivery_id":delivery_id,"webhook_id":webhook_id,"event_id":event_id,"event_name":event_name,"delivery_status":status,"http_status":http_status,"attempt_count":1,"failure_reason":error,"timestamp_utc":timestamp,"signature":f"sha256={signature}"}
        self._deliveries[delivery_id]=delivery; return delivery
    def delivery_history(self,user_id:str,webhook_id:str)->List[Dict[str,Any]]:
        hook=self._webhooks.get(webhook_id)
        if not hook or hook["owner_id"]!=user_id: raise PermissionDenied("Webhook owner access required.")
        return [dict(item) for item in self._deliveries.values() if item["webhook_id"]==webhook_id]

