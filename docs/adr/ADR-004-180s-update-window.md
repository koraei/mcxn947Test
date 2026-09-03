# ADR-004 — 180-second application-layer Ethernet update service

## Decision
Update TCP port 5555 accepts new sessions only during the first 180 s after application start. Sessions accepted before the deadline may finish afterward.

## Status
P2: listener + window implemented; P5 streams raw SB3 over TCP into NXP `sb3_api`.
