# BioIntel Connect messaging specification

Messaging supports direct and group conversations, owner/administrator/moderator/member/guest/read-only roles, message requests, membership changes and block/report controls.

Messages carry a conversation sequence and client event ID. The unique `(conversation_id, client_event_id)` constraint makes retries idempotent; `(conversation_id, sequence)` preserves order. Text/Markdown/equation/code/media/document/voice/reference/announcement types are supported with attachments and scientific references.

Delivery lifecycle is sent → delivered → read, with per-user receipt timestamps. Authors can edit with preserved revisions or soft-delete; members can react, save and search visible history.

Realtime is durable: per-user events have sequences, dedupe keys and acknowledgement timestamps. WebSocket clients reconnect with an `after_sequence`; HTTP event replay is available. Typing indicators are transient event records. Blocking or membership removal closes access at the service layer. Automated tests cover idempotent send, receipt transition, offline replay/acknowledgement and blocking.
