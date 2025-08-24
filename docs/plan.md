# Vicidial-like System Building Plan

## Vicidial Source Reference
This document outlines a comprehensive building plan for implementing a predictive dialer/call-center system using Django Channels, based on the current Vicidial source code and architecture patterns.

**Official Vicidial Source Repository**: [AZY0720/astguiclient](https://github.com/AZY0720/astguiclient)  
**Current Vicidial Version**: 2.14b0.5  
**Documentation**: [Vicidial Documentation](https://github.com/AZY0720/astguiclient/tree/master/trunk/docs)  
**Installation Guide**: [install.pl](https://github.com/AZY0720/astguiclient/blob/master/trunk/install.pl)  
**Web Interface Source**: [www directory](https://github.com/AZY0720/astguiclient/tree/master/trunk/www)  
**Backend Scripts**: [bin directory](https://github.com/AZY0720/astguiclient/tree/master/trunk/bin)  
**Local Source Code**: The complete Vicidial source code is available at `docs\astguiclient-master` for future reference on this project  
**Last Updated**: 2025-08-22

This implementation plan references the latest Vicidial architecture and incorporates modern Django Channels patterns to create a scalable, real-time predictive dialer system.

## Table of Contents
1. [Project Overview](#project-overview)
2. [Core Infrastructure Setup](#core-infrastructure-setup)
3. [Database Design & Implementation](#database-design--implementation)
4. [Backend API Development](#backend-api-development)
5. [Real-time Communication Layer](#real-time-communication-layer)
6. [Background Task Processing](#background-task-processing)
7. [Frontend Application Development](#frontend-application-development)
8. [Telephony Integration](#telephony-integration)
9. [Analytics & Monitoring](#analytics--monitoring)
10. [Security & Compliance Implementation](#security--compliance-implementation)
11. [Testing Strategy](#testing-strategy)
12. [Deployment & Infrastructure](#deployment--infrastructure)
13. [Phased Implementation Timeline](#phased-implementation-timeline)

---

## Project Overview

### Goals
- Build a scalable, real-time predictive dialer system
- Support agent management, campaign management, and supervisor dashboards
- Provide real-time communication between agents and the system
- Enable both inbound and outbound call handling
- Implement comprehensive analytics and reporting
- Ensure compliance with telecommunications regulations

### Key Constraints
- Must use Django Channels as the core framework
- Real-time WebSocket communication is essential
- System must handle high-volume call processing
- Compliance with DNC, recording consent, and data privacy regulations
- Scalable architecture supporting multiple campaigns simultaneously

---

## Core Infrastructure Setup

### Django Project Structure
**Rationale**: Establish a solid foundation with proper Django project organization that supports the complex requirements of a call center system.

**Implementation Steps**:
1. **Configure Django Settings**
   - Set up multiple environment configurations (development, staging, production)
   - Configure database connections for PostgreSQL
   - Set up Redis configuration for Django Channels and Celery
   - Configure static/media files handling
   - Set up logging configuration

2. **Install and Configure Django Channels**
   - Install Django Channels and configure ASGI application
   - Set up Redis channel layer for WebSocket communication
   - Configure routing for both HTTP and WebSocket connections
   - Implement basic WebSocket authentication

3. **Set up ASGI Server Configuration**
   - Configure Daphne or Uvicorn for production deployment
   - Set up proper ASGI routing structure
   - Configure sticky session handling for WebSockets

**Expected Outcomes**:
- Functioning Django application with Channels support
- Proper environment configuration management
- Basic WebSocket infrastructure ready for development

---

## Database Design & Implementation

### Core Data Models
**Rationale**: Implement a robust database schema that supports all call center operations while maintaining data integrity and performance.

**Implementation Steps**:
1. **User & Authentication Models**
   - Extend Django's User model for agents, supervisors, and admins
   - Implement role-based permissions system
   - Create team and department organizational structure

2. **Campaign Management Models**
   ```python
   # Key models to implement:
   - Campaign (pacing_ratio, drop_sla, caller_id, dial_window, recycle_rules)
   - Lead (phone, status, last_call_at, attempts, timezone, priority)
   - CallTask (lead_id, campaign_id, state, agent_id, pbx_call_id)
   - Disposition (call_task_id, code, notes, wrapup_seconds)
   ```

3. **Agent & Call State Models**
   - Agent status tracking (available, busy, wrap-up, offline)
   - Real-time call state management
   - Agent skill-based routing capabilities

4. **CDR & Recording Models**
   - Call Detail Records with complete call lifecycle tracking
   - Recording metadata and S3/MinIO URL storage
   - Compliance and retention policy enforcement

5. **DNC & Compliance Models**
   - Do Not Call list management
   - Compliance audit trails
   - Recording consent tracking

**Migration Strategy**:
- Create migrations in logical groups
- Implement data validation at model level
- Set up proper indexing for high-query tables
- Create materialized views for reporting

**Expected Outcomes**:
- Complete database schema supporting all system requirements
- Proper data relationships and constraints
- Optimized queries for real-time operations

---

## Backend API Development

### REST API Implementation
**Rationale**: Provide comprehensive REST APIs for all system operations while maintaining security and performance standards.

**Implementation Steps**:
1. **Django REST Framework Setup**
   - Configure DRF with proper serializers and viewsets
   - Implement pagination for large datasets
   - Set up API versioning strategy
   - Configure proper error handling and response formatting

2. **Authentication & Authorization APIs**
   - JWT-based authentication with refresh tokens
   - Role-based access control for different user types
   - Session management for agent status tracking

3. **Campaign Management APIs**
   - CRUD operations for campaigns, leads, and dispositions
   - Bulk lead import/export functionality
   - Campaign scheduling and time-zone aware operations
   - Real-time campaign statistics endpoints

4. **Agent Management APIs**
   - Agent status management (login, logout, ready, not-ready)
   - Skill-based routing configuration
   - Performance metrics and KPI endpoints

5. **Reporting & Analytics APIs**
   - Real-time dashboard data endpoints
   - Historical reporting with efficient querying
   - Export functionality for compliance reporting

**GraphQL Integration** (Optional):
- Implement GraphQL for complex data requirements
- Optimize for real-time dashboard queries

**Expected Outcomes**:
- Complete REST API covering all system functionality
- Proper authentication and authorization
- Optimized endpoints for real-time operations

---

## Real-time Communication Layer

### WebSocket Implementation
**Rationale**: Enable real-time communication between agents, supervisors, and the system for immediate updates and notifications.

**Implementation Steps**:
1. **WebSocket Consumer Development**
   - Agent presence consumer for status updates
   - Call state consumer for real-time call information
   - Dashboard consumer for supervisor monitoring
   - Campaign consumer for real-time statistics

2. **Channel Groups Management**
   - Implement proper group membership for different user roles
   - Campaign-specific groups for targeted updates
   - Team-based groups for supervisor oversight
   - System-wide groups for global notifications

3. **Event Broadcasting System**
   - Call state change notifications
   - Agent status change broadcasts
   - Campaign statistics updates
   - System alerts and notifications

4. **WebSocket Authentication & Security**
   - Token-based WebSocket authentication
   - Connection rate limiting
   - Proper error handling and reconnection logic

5. **Message Serialization & Protocols**
   - Standardized message formats for different event types
   - Efficient serialization for high-frequency updates
   - Message acknowledgment systems

**Expected Outcomes**:
- Real-time communication infrastructure
- Proper WebSocket security implementation
- Scalable event broadcasting system

---

## Background Task Processing

### Celery Implementation
**Rationale**: Handle computationally intensive and time-sensitive operations outside the main request cycle to maintain system responsiveness.

**Implementation Steps**:
1. **Celery Configuration**
   - Set up Celery with Redis as message broker
   - Configure different queues for different task priorities
   - Implement proper error handling and retry mechanisms
   - Set up Celery Beat for scheduled tasks

2. **Predictive Dialing Engine**
   - Implement predictive dialing algorithms
   - Pacing ratio calculations based on agent availability
   - Drop rate monitoring and adjustment
   - Answer machine detection integration

3. **Lead Management Tasks**
   - Bulk lead import processing
   - DNC scrubbing and compliance checks
   - Lead recycling based on campaign rules
   - Time-zone aware call scheduling

4. **CDR Processing & Analytics**
   - Real-time CDR ingestion and processing
   - KPI calculation and aggregation
   - Report generation and materialization
   - Data archiving and cleanup tasks

5. **Notification & Alert Tasks**
   - Email notifications for campaign events
   - SMS alerts for system issues
   - Webhook integrations for third-party systems

**Task Monitoring & Management**:
- Implement Celery monitoring with Flower
- Set up proper logging for task execution
- Create task retry and failure handling strategies

**Expected Outcomes**:
- Robust background task processing system
- Automated predictive dialing capabilities
- Efficient data processing and analytics pipeline

---

## Frontend Application Development

### React/Vue Application
**Rationale**: Create an intuitive, responsive user interface that supports the complex workflows of call center operations.

**Implementation Steps**:
1. **Frontend Framework Setup**
   - Set up React with Vite for fast development
   - Configure state management (Redux Toolkit or Zustand)
   - Implement routing with React Router
   - Set up UI component library (Material-UI or Ant Design)

2. **Authentication & User Management**
   - Login/logout functionality with JWT handling
   - Role-based UI rendering
   - Session timeout handling
   - Password reset and user profile management

3. **Agent Interface Development**
   - Real-time agent status controls
   - Call popup interface with lead information
   - Disposition forms and wrap-up timers
   - Call history and notes interface

4. **Supervisor Dashboard**
   - Real-time campaign monitoring
   - Agent status overview
   - Live call statistics and wallboards
   - Campaign management interface

5. **WebSocket Integration**
   - Real-time connection management
   - Event handling for call states and notifications
   - Connection retry and error handling
   - Proper cleanup on component unmounting

6. **WebRTC Integration** (Optional)
   - SIP.js integration for browser-based calling
   - Audio controls and quality indicators
   - Call transfer and hold functionality

**Performance Optimization**:
- Implement code splitting and lazy loading
- Optimize WebSocket message handling
- Use efficient state management patterns
- Implement proper error boundaries

**Expected Outcomes**:
- Fully functional agent and supervisor interfaces
- Real-time data updates and notifications
- Responsive and intuitive user experience

---

## Telephony Integration

### PBX Integration Options
**Rationale**: Provide flexible telephony integration supporting both self-hosted and cloud-based solutions with AI-powered real-time features.

**Implementation Steps**:
1. **Asterisk/FreeSWITCH Integration (Primary Approach)**
   - ARI (Asterisk REST Interface) integration
   - AMI (Asterisk Manager Interface) for events
   - Call origination and control
   - Answer Machine Detection (AMD) integration
   - Advanced features: barge/whisper, call monitoring
   - Cost-effective scaling for high-volume operations

2. **AI Media Gateway Integration**

   **Option A: Internal AI Media Gateway (Self-hosted)**
   - Real-time audio ingestion from Asterisk via ExternalMedia channels
   - WebRTC support for browser-based agent interfaces
   - Raw RTP handling for direct audio stream processing
   - Integration with OpenAI Whisper for speech-to-text transcription
   - Optional text-to-speech (TTS) playback via reverse RTP or ARI
   - Real-time transcript broadcasting to agents via WebSockets

   **Option B: External AI Media Gateway Integration**
   - Connect to third-party AI media gateway providers (Deepgram, AssemblyAI, Azure Cognitive Services)
   - API-based audio streaming to external transcription services
   - Webhook integration for receiving real-time transcription results
   - Multi-provider failover and load balancing capabilities
   - Cost optimization through provider selection and usage analytics
   - Provider-agnostic abstraction layer for easy switching between services

3. **Advanced Audio Processing Pipeline**
   ```
   PSTN/ITSP → SBC → Asterisk (B2BUA)
                           │
                           ├─ ARI WS/HTTP  ⇆  ARI Controller (Python asyncio)
                           ├─ ExternalMedia RTP ⇆ AI Media Gateway (WebRTC/RTP)
                           │
                           └─ (optional) SIPREC fork  → AI Media Gateway
   
   AI Media Gateway → (Whisper via OpenAI) → Django API (/ai/events)
                                        └→ (optional TTS → RTP back or file → ARI play)
   
   Django (ASGI + Channels + Redis) → WebSocket groups per call → Agent desktop (HTML/JS)
   ```

4. **WebRTC Gateway Setup**
   - Configure aiortc for WebRTC peer connections
   - SIP over WebSocket implementation via Asterisk
   - STUN/TURN server configuration
   - Media relay and real-time audio processing
   - PCM audio track handling with VAD (Voice Activity Detection)

5. **Real-time Audio Processing Components**
   - **WebRTC Ingress**: aiortc-based peer connection handling
   - **RTP Ingress**: Direct G.711 μ/A-law audio processing
   - **Audio Resampling**: 8kHz/48kHz to 16kHz for Whisper compatibility
   - **STT Processing**: Chunked audio processing with OpenAI Whisper
   - **Event Broadcasting**: Real-time transcript delivery to agent interfaces

6. **CPaaS Integration (Alternative Approach)**
   - Implement Twilio/SignalWire integration (optional)
   - Webhook handling for call events
   - Programmable Voice integration
   - Recording and transcription services
   - Faster initial setup but higher operational costs

7. **Call Flow Management**
   - Inbound call routing and queuing with AI transcript support
   - Outbound call origination with real-time monitoring
   - Call transfer and conferencing
   - Call monitoring and barge/whisper with live transcription
   - Bridge management for ExternalMedia channel attachment

8. **Integration Abstraction Layer**
   - Create telephony service abstraction
   - Support multiple PBX backends
   - Unified call event handling
   - Provider-agnostic call control APIs
   - AI service integration abstraction

**Technical Implementation Details**:
- **ARI Controller**: Python asyncio-based daemon managing Asterisk Stasis applications
- **ExternalMedia Channels**: RTP streams directed to AI Media Gateway for processing
- **Audio Format Support**: PCM, G.711 μ-law/A-law with real-time resampling
- **WebSocket Integration**: Call-specific groups for targeted transcript delivery
- **Security**: HMAC signature validation for AI webhook events

**Expected Outcomes**:
- Functional telephony integration with AI capabilities
- Real-time speech-to-text transcription for all calls
- Support for both inbound and outbound calling
- WebRTC support for browser-based agent softphones
- Flexible architecture supporting multiple providers and AI services

---

## Analytics & Monitoring

### Data Analytics Implementation
**Rationale**: Provide comprehensive analytics and monitoring capabilities for performance optimization and compliance reporting.

**Implementation Steps**:
1. **Time-Series Database Setup**
   - Configure ClickHouse or TimescaleDB for metrics
   - Create optimized schemas for call data
   - Implement data retention policies
   - Set up data aggregation pipelines

2. **Metrics Collection**
   - Real-time call metrics collection
   - Agent performance KPIs
   - Campaign effectiveness metrics
   - System performance monitoring

3. **Dashboard & Reporting**
   - Real-time wallboards for operations
   - Historical reporting interfaces
   - Custom report builder
   - Automated report generation and delivery

4. **Observability Stack**
   - Prometheus for metrics collection
   - Grafana for visualization and alerting
   - Loki or ELK stack for log aggregation
   - Sentry for error tracking and monitoring

**Expected Outcomes**:
- Comprehensive analytics and reporting system
- Real-time monitoring and alerting
- Performance optimization insights

---

## Security & Compliance Implementation

### Security Measures
**Rationale**: Ensure system security and regulatory compliance for telecommunications and data privacy requirements.

**Implementation Steps**:
1. **Authentication & Authorization Security**
   - Multi-factor authentication (MFA) implementation
   - Strong password policies
   - Role-based access control (RBAC)
   - Session management and timeout controls

2. **Data Encryption & Protection**
   - TLS/SSL for all communications
   - Database encryption at rest
   - PII data encryption and tokenization
   - Secure key management

3. **Compliance Implementation**
   - DNC (Do Not Call) list management and scrubbing
   - Recording consent management by jurisdiction
   - GDPR/CCPA data privacy compliance
   - Audit trail and logging for compliance

4. **Network Security**
   - Firewall configuration and network segmentation
   - VPN access for remote agents
   - Rate limiting and DDoS protection
   - Security headers and CSRF protection

**Expected Outcomes**:
- Secure system architecture
- Regulatory compliance implementation
- Comprehensive audit and monitoring capabilities

---

## Testing Strategy

### Comprehensive Testing Plan
**Rationale**: Ensure system reliability, performance, and correctness through thorough testing at all levels.

**Implementation Steps**:
1. **Unit Testing**
   - Django model and API testing
   - Celery task testing
   - WebSocket consumer testing
   - Frontend component testing

2. **Integration Testing**
   - Database integration tests
   - Third-party API integration tests
   - WebSocket communication testing
   - Telephony integration testing

3. **Performance Testing**
   - Load testing for high-volume scenarios
   - WebSocket connection scaling tests
   - Database query performance optimization
   - CDR processing throughput testing

4. **End-to-End Testing**
   - Complete call flow testing
   - User interface automation testing
   - Cross-browser compatibility testing
   - Mobile responsiveness testing

**Expected Outcomes**:
- Reliable and well-tested system
- Performance validation under load
- Automated testing pipeline

---

## Deployment & Infrastructure

### Production Deployment Strategy
**Rationale**: Create a scalable, maintainable, and highly available deployment architecture.

**Implementation Steps**:
1. **Containerization**
   - Docker containers for all services
   - Multi-stage builds for optimization
   - Container orchestration with Kubernetes
   - Helm charts for deployment management

2. **Infrastructure as Code**
   - Terraform or CloudFormation for infrastructure
   - Automated provisioning and scaling
   - Environment-specific configurations
   - Disaster recovery and backup strategies

3. **Load Balancing & High Availability**
   - NGINX or HAProxy for load balancing
   - Sticky sessions for WebSocket connections
   - Database clustering and replication
   - Redis clustering for channel layer

4. **Monitoring & Alerting**
   - Comprehensive health checks
   - Performance monitoring and alerting
   - Log aggregation and analysis
   - Automated incident response

**Expected Outcomes**:
- Production-ready deployment architecture
- High availability and disaster recovery capabilities
- Automated deployment and scaling

---

## Phased Implementation Timeline

### MVP Phase (Months 1-3)
**Core Objectives**: Deliver a functional system with basic call center capabilities.

**Key Deliverables**:
- Basic Django application with user authentication
- Simple agent interface with manual dialing
- WebSocket-based real-time updates
- Basic call disposition and recording
- Asterisk PBX integration for telephony
- Simple supervisor dashboard

### Phase 2: Enhanced Features (Months 4-6)
**Core Objectives**: Add advanced dialing capabilities and comprehensive management features.

**Key Deliverables**:
- Predictive/progressive dialing implementation
- Advanced campaign management
- Lead import/export and DNC scrubbing
- Answer machine detection integration
- Enhanced analytics and reporting
- Quality assurance tools

### Phase 3: Advanced Integration (Months 7-9)
**Core Objectives**: Implement advanced telephony features and optimization.

**Key Deliverables**:
- Advanced Asterisk features (call monitoring, barge, whisper)
- WebRTC softphone implementation
- Advanced call routing and skills-based routing
- Optional CPaaS integration (as alternative to Asterisk)
- Comprehensive compliance features
- Performance optimization

### Phase 4: Scale & Polish (Months 10-12)
**Core Objectives**: Optimize for scale and add enterprise features.

**Key Deliverables**:
- Multi-tenant architecture
- Advanced analytics and machine learning
- API integrations and webhooks
- Mobile applications
- Enterprise security features
- Comprehensive documentation and training

---

## Success Metrics

### Key Performance Indicators
- **System Performance**: <100ms WebSocket latency, 99.9% uptime
- **Call Center Efficiency**: Improved agent utilization, reduced abandon rates
- **Development Velocity**: Automated deployment, comprehensive test coverage
- **Compliance**: 100% DNC compliance, complete audit trails
- **User Satisfaction**: Intuitive interfaces, reliable real-time updates

---

## Risk Mitigation

### Technical Risks
- **WebSocket Scalability**: Implement proper load balancing and connection management
- **Telephony Integration**: Primary focus on Asterisk self-hosted solution; CPaaS as fallback option
- **Database Performance**: Implement proper indexing and consider read replicas
- **Real-time Processing**: Use efficient queuing and background task processing

### Business Risks
- **Compliance Requirements**: Early implementation of regulatory features
- **Performance Requirements**: Regular load testing and optimization
- **Integration Complexity**: Modular architecture with clear service boundaries

---

This comprehensive building plan provides a roadmap for implementing a production-ready, scalable call center system using Django Channels. Each phase builds upon the previous one, allowing for iterative development and early value delivery while maintaining a path to full system implementation.
