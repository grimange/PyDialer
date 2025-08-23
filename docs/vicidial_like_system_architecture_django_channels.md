# Vicidial‑like System Architecture (Django Channels)

Below is a reference architecture you can adapt for a predictive dialer / call‑center stack built around **Django Channels**.

---

## 1) High‑Level Diagram (Logical View)

```
                          ┌──────────────────────────────────────────────────┐
                          │                    Users                         │
                          │  • Agents (browser)   • Supervisors (browser)    │
                          └───────────────▲─────────────────────▲────────────┘
                                          │ Web UI (HTTPS)      │ Web UI (HTTPS)
                                          │ + WebSockets        │ + WebSockets
                                          │ + (optional) WebRTC │
                              ┌───────────┴─────────────────────┴───────────┐
                              │                Web Frontend                  │
                              │  React/Vue + auth + state mgmt               │
                              └───────────▲──────────────────────────────────┘
                                          │
                                          │  ASGI (w/ sticky WS)
                           ┌──────────────┴─────────────────────────┐
                           │           Django ASGI Layer            │
                           │  Django + DRF + Channels (Daphne)      │
                           │  REST + GraphQL + WS consumers         │
                           └───────▲──────────────┬─────────────▲───┘
                                   │              │             │
                     Channel Layer  │              │             │  ORM
                        (Redis)     │              │             │
                                   ▼              │             ▼
                      ┌─────────────────┐          │   ┌──────────────────┐
                      │ Channels Groups │          │   │  PostgreSQL (RDS) │
                      │ Presence/Events │          │   │  Core OLTP        │
                      └─────────────────┘          │   └──────────────────┘
                                                   │
                                                   │
                                  ┌────────────────┴─────────────────┐
                                  │     Task / Job Processing         │
                                  │ Celery workers + Beat (sched)     │
                                  │ Queue: Redis or RabbitMQ          │
                                  └────────────────▲──────────────────┘
                                                   │ events/jobs
                                                   │ (dial, CDR ingest,
                                                   │  reporting, cleanup)
                                                   │
     ┌───────────────────────────────┐             │
     │   Telephony / Media Plane     │◄────────────┘
     │  (Choose one path below)      │
     ├───────────────────────────────┤
     │ A) Asterisk/FreeSWITCH Stack  │
     │  • SIP trunks (Inbound/Out)   │
     │  • WebRTC GW (rtpengine/      │
     │    Janus/Kamailio/OpenSIPS)   │
     │  • ARI/AMI/ESL event bridge   │
     │  • Call progress detection    │
     │  • Recording (mix/monitor)    │
     ├───────────────────────────────┤
     │ B) CPaaS (Twilio/Plivo/etc.)  │
     │  • Programmable Voice         │
     │  • <Sip> / WebRTC             │
     │  • Webhooks → Django          │
     │  • Media/recording storage    │
     └───────────────────────────────┘

                                                   │
                                                   │ CDRs/recordings/metrics
                                                   ▼
                                 ┌──────────────────────────────────────┐
                                 │  Storage & Analytics                 │
                                 │  • Object store: S3/MinIO (records)  │
                                 │  • TSDB: ClickHouse/Timescale         │
                                 │  • OLAP: ClickHouse/BigQuery (opt)   │
                                 └──────────────────────────────────────┘

                                                   │
                                                   ▼
                                 ┌──────────────────────────────────────┐
                                 │  Observability & Ops                │
                                 │  • Prometheus + Grafana             │
                                 │  • Loki/ELK for logs                │
                                 │  • Sentry for app errors            │
                                 └──────────────────────────────────────┘

Ingress / Edge:  Cloud LB/NGINX/HAProxy/Traefik (TLS offload, sticky WS, HTTP/2)
```

---

## 2) Component Responsibilities

**Frontend (React/Vue)**
- Auth (agent, supervisor, admin), campaign selection.
- WS client for real‑time agent state, queue stats, call popups.
- Optional WebRTC softphone (via SIP over WebSocket + SRTP) or CPaaS JS SDK.
- Disposition forms, wrap‑up timers, QA tools.

**Django + Channels (ASGI)**
- REST/GraphQL APIs for CRUD on agents, leads, campaigns.
- WebSocket consumers for: agent presence, live call state, dashboards.
- Dispatch events to channel groups (per‑campaign, per‑team).

**Channel Layer (Redis)**
- Low‑latency fan‑out for updates to hundreds/thousands of sockets.
- Presence lists, lightweight pub/sub.

**Celery Workers (+ Beat)**
- Predictive dial loop (schedule, throttling, recycle rules).
- Import/export leads, list management, DNC scrubs, retries.
- CDR ingestion, KPI aggregation, report materialization.

**Database (PostgreSQL)**
- OLTP for users, teams, lists, campaigns, call tasks, dispositions.
- Optimistic locking on agent/call state rows.

**Timeseries / Analytics (ClickHouse/Timescale)**
- High‑volume metrics: per‑second call states, ACD, service levels.
- Powers live wallboards without hammering OLTP.

**Telephony Plane**
- *Primary: Asterisk/FreeSWITCH*: full control, AMD, barge/whisper, transfers, cost-effective at scale.
- *Alternative: CPaaS*: optional for rapid prototyping; webhooks for call state; higher per‑minute costs.

**Storage (S3/MinIO)**
- Call recordings, QA snippets, compliance‑driven retention policies.

**Observability**
- Prometheus exporters (Django, Celery, DB, PBX). Dashboards per queue/campaign.
- Centralized logs (app + SIP/PBX). Sentry for error tracking.

**Edge / Ingress**
- NGINX/HAProxy with sticky sessions for WebSockets; WAF rules; rate limits.

---

## 3) Event Flow: Predictive Outbound (Asterisk example)

1) **Celery Beat** ticks → enqueue predictive dial cycle per campaign.
2) **Worker** pulls N leads = `ceil(free_agents * pacing_ratio)` (bounded by drop SLA).
3) **Worker** asks PBX via ARI/AMI to originate calls; tags them with `campaign_id`.
4) **PBX** runs AMD (answer machine detection); connects humans to a queue.
5) **Queue** routes the next answered call to a **Ready** agent (agent SIP/WebRTC contact).
6) **PBX event** (bridged/ringing/hangup) → webhook/AMI → Django → Channels group.
7) **Agent UI** shows call popup; timers start; disposition form enabled.
8) **On hangup**, CDR + disposition saved; recording URL stored to S3; metrics updated.

---

## 4) Data Model Sketch (minimum tables)

- `agent(id, user_id, status, device, last_heartbeat)`
- `campaign(id, type, pacing_ratio, drop_sla, caller_id, dial_window, recycle_rules)`
- `lead(id, campaign_id, phone, status, last_call_at, attempts, timezone, priority)`
- `call_task(id, lead_id, campaign_id, state, agent_id, pbx_call_id, started_at)`
- `disposition(id, call_task_id, code, notes, wrapup_seconds)`
- `cdr(id, pbx_call_id, from, to, answer_at, end_at, duration, recording_url)`
- `dnc(number, scope)`

Add materialized views for wallboards (active calls, AHT, abandon rate, agents ready).

---

## 5) Scaling & Deploy Topology

- **ASGI app**: multiple Daphne/Uvicorn instances behind NGINX/ALB (sticky WS).
- **Redis**: dedicated cluster for channel layer + (optionally) separate broker.
- **Celery**: autoscaled workers per campaign load; queue separation for priorities.
- **DB**: managed Postgres with read replicas; pgbouncer; write‑heavy tables sharded or moved to CH.
- **PBX**: dedicated Asterisk/FS nodes; separate SBC (Kamailio/OpenSIPS) and RTP media relays.
- **Storage**: S3/MinIO with lifecycle policies (hot → cold → delete).
- **Observability**: Prometheus + Grafana; alerts on drop rate, answer rate, agent idle, queue size.

---

## 6) Security & Compliance Checklist

- TLS everywhere; SRTP for WebRTC; rotate secrets; short‑lived tokens (JWT w/ refresh).
- Role‑based access (agent/supervisor/admin/QA). Fine‑grained campaign scoping.
- Two‑party/one‑party recording consent by region; announcement inject.
- DNC scrubs (campaign, national, internal). Privacy masking (DTMF/PCI pause) if needed.
- PII minimization; encrypt at rest; audit trails; Data Privacy Act (PH), GDPR/CCPA if global.

---

## 7) Build Path (MVP → Full)

**MVP**
- Manual dial from UI (Asterisk originate, CPaaS as alternative)
- Agent WS presence + basic call popup
- Disposition + recording URL capture
- Basic wallboard

**Phase 2**
- Progressive/predictive dialer with pacing controller
- AMD integration; call recycling; time‑zone aware windows
- Inbound ACD; skills/routing; transfers; barge/whisper
- QA tools: screen+call capture, scorecards, calibration

---

## 8) Technology Choices (pragmatic defaults)

- **Web**: React + Vite, TanStack Query, WebSocket client, optional SIP.js for WebRTC
- **Backend**: Django 5 + DRF + Channels; Daphne; Celery + Redis broker
- **DB**: Postgres 15+; TimescaleDB or ClickHouse for metrics
- **Telephony**: Primary focus on Asterisk for control/cost; optional CPaaS (Twilio/SignalWire) for rapid prototyping
- **Infra**: Docker + Kubernetes (HPA on CPU/lag); NGINX Ingress; cert‑manager
- **Obs**: Prometheus, Grafana, Loki, Sentry; PBX exporters (chan_metrics, ESL/AMI)

---

### Notes
- Keep WS consumers thin; heavy lifting in Celery or PBX.
- Use idempotent jobs; durable queues; exactly‑once semantics for CDR upserts.
- Consider multi‑tenant boundaries early (schema‑per‑tenant vs row‑level security).

