# Science Pulse Notification Specification

Rules support query, category, content type, channel, frequency, per-user timezone, quiet hours, pause, limits, and duplicate suppression. Each delivery is persisted with pending/delivered/failed/configuration-required state, reference, and error. A message is delivered only after its dispatcher confirms a durable write.

Confirmed local channels: Science Pulse inbox, Shiro briefing, Connect. Education Home requires a configured active institution membership. Desktop, email, and institution channels require an explicit dispatcher. Retraction updates notify bookmark owners and flag linked drafts for review.
