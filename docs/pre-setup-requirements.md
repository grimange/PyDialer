# Pre-Setup Requirements for Vicidial-like Django Channels System

*Generated from: docs/tasks.md analysis*  
*Date: 2025-08-22*  
*Project: PyDialer*

This document outlines all system dependencies, software installations, and infrastructure requirements that must be established **before** starting the development of the Vicidial-like predictive dialer system.

## 1. System Environment & Platform Requirements

### Operating System
- **Development**: Windows/Linux/macOS (current: Windows with PowerShell)
- **Production**: Linux (Ubuntu 20.04+ or CentOS 8+ recommended)
- **Containerization**: Docker support required for production deployment

### Hardware Minimum Requirements
- **Development**: 8GB RAM, 4 CPU cores, 50GB disk space
- **Production**: 16GB+ RAM, 8+ CPU cores, 500GB+ SSD storage
- **Call Center Scale**: Requirements scale with concurrent agents (100+ agents = 32GB+ RAM)

## 2. Core Software Dependencies

### Programming Language & Runtime
- **Python 3.13** (as configured in PyCharm IDE)
  ```bash
  # Verify installation
  python --version
  # Should output: Python 3.13.x
  ```

### Virtual Environment Management
- **venv** (Python built-in) or **conda**
  ```bash
  # Create virtual environment
  python -m venv .venv
  # Activate (Windows)
  .venv\Scripts\activate
  # Activate (Linux/Mac)
  source .venv/bin/activate
  ```

### Package Management
- **pip** (latest version)
  ```bash
  python -m pip install --upgrade pip
  ```

## 3. Database Systems

### Primary Database - PostgreSQL
- **Version**: PostgreSQL 14+ (required for production)
- **Purpose**: Main application data, user management, call records
- **Configuration**: 
  - Connection pooling support
  - Proper indexing for high-volume call data
  - Backup and replication setup for production

```bash
# Installation examples:
# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib libpq-dev

# Windows (via installer or Chocolatey)
choco install postgresql

# Verify installation
psql --version
```

### Time-Series Database (Optional for Analytics)
- **ClickHouse** or **TimescaleDB** (Phase 4 requirement)
- **Purpose**: Call analytics, performance metrics, historical data
- **Note**: Can be added later in development phase

### Development Database
- **SQLite** (currently configured - for development only)
- **Note**: Must migrate to PostgreSQL before production

## 4. Message Broker & Caching

### Redis Server
- **Version**: Redis 6.0+
- **Purpose**: 
  - Django Channels layer for WebSocket communication
  - Celery message broker for background tasks
  - Session storage and caching

```bash
# Installation examples:
# Ubuntu/Debian
sudo apt-get install redis-server

# Windows (via MSI or Docker recommended)
# Docker approach:
docker run -d --name redis -p 6379:6379 redis:latest

# Verify installation
redis-cli ping
# Should respond: PONG
```

## 5. Django Framework & Extensions

### Core Django Dependencies
Create `requirements.txt` with minimum required packages:

```txt
# Core Framework
Django==5.2.5
channels==4.0.0
channels-redis==4.1.0

# Database
psycopg2-binary==2.9.7  # PostgreSQL adapter
django-redis==5.3.0     # Redis cache backend

# API Framework
djangorestframework==3.14.0
djangorestframework-simplejwt==5.3.0

# Background Tasks
celery==5.3.1
flower==2.0.1           # Celery monitoring

# ASGI Server
daphne==4.0.0           # Production ASGI server
uvicorn==0.23.2         # Alternative ASGI server

# Additional utilities
python-dotenv==1.0.0    # Environment variables
django-cors-headers==4.2.0  # CORS handling
django-extensions==3.2.3    # Development utilities
```

### Development Dependencies
```txt
# Testing & Quality
pytest==7.4.0
pytest-django==4.5.2
pytest-asyncio==0.21.1
coverage==7.3.0

# Development tools
django-debug-toolbar==4.2.0
ipython==8.14.0
black==23.7.0           # Code formatting
flake8==6.0.0          # Code linting
```

## 6. Frontend Development Environment

### Node.js & Package Manager
- **Node.js**: Version 18+ LTS
- **npm** or **yarn**: Latest stable version
- **Purpose**: React frontend, build tools, WebSocket client

```bash
# Verify installation
node --version  # Should be v18+
npm --version
```

### Frontend Framework Dependencies (Phase 2)
- **React 18+** with Vite build tool
- **State Management**: Redux Toolkit or Zustand
- **UI Library**: Material-UI or Ant Design
- **WebSocket Client**: native WebSocket API or ws library

## 7. Telephony & Communication Services

### Primary Telephony - Asterisk PBX (Phase 3)
- **Asterisk** or **FreeSWITCH** (primary self-hosted PBX)
- **Purpose**: Complete call control, predictive dialing, call recording, agent management
- **Requirements**:
  - Linux server (Ubuntu 20.04+ or CentOS 8+ recommended)
  - SIP trunking provider (for PSTN connectivity)
  - ARI (Asterisk REST Interface) configuration
  - AMI (Asterisk Manager Interface) setup
  - Call recording storage (local or S3/MinIO)
- **Benefits**: Full control, cost-effective at scale, advanced features (AMD, barge/whisper)

### WebRTC Infrastructure (Phase 4)
- **STUN/TURN Servers**: For browser-based calling
- **Options**: 
  - Self-hosted coturn server (recommended)
  - rtpengine or Janus WebRTC gateway
  - Google STUN servers (development only)
- **Integration**: SIP over WebSocket with Asterisk

### Alternative Telephony - CPaaS Providers (Optional)
- **Twilio** or **SignalWire** account (alternative option)
- **Purpose**: Quick prototyping, reduced infrastructure complexity
- **Requirements**:
  - Account with sufficient credits
  - Phone numbers provisioned
  - Webhook endpoint configuration
  - API credentials (Account SID, Auth Token)
- **Note**: Higher per-minute costs, limited control compared to Asterisk

## 8. Development Tools & IDE

### Integrated Development Environment
- **PyCharm Professional** (currently configured)
- **Alternative**: VS Code with Python extensions
- **Configuration**: Django integration, Python 3.13 interpreter

### Version Control
- **Git**: Latest version
- **GitHub/GitLab**: Repository hosting
- **Git LFS**: For large files (recordings, assets)

```bash
# Verify Git installation
git --version
```

### Code Quality Tools
- **Pre-commit hooks**: Automated code formatting and linting
- **Black**: Python code formatter
- **Flake8**: Python linter
- **ESLint**: JavaScript/TypeScript linting (for frontend)

## 9. Monitoring & Analytics Infrastructure (Phase 4)

### Application Monitoring
- **Sentry**: Error tracking and performance monitoring
- **Account setup**: Create Sentry project, obtain DSN key

### Metrics & Visualization
- **Prometheus**: Metrics collection
- **Grafana**: Dashboards and alerting
- **Note**: Can be containerized for easier deployment

### Log Aggregation
- **ELK Stack** (Elasticsearch, Logstash, Kibana) or **Loki**
- **Purpose**: Centralized logging, debugging, audit trails

## 10. Security & SSL Requirements

### SSL Certificates
- **Development**: Self-signed certificates acceptable
- **Production**: Valid SSL certificates (Let's Encrypt, commercial CA)
- **Purpose**: HTTPS, WSS (WebSocket Secure), SIP TLS

### Environment Variables Management
- **Production**: Secure secret management (AWS Secrets Manager, HashiCorp Vault)
- **Development**: `.env` files (never commit to version control)

## 11. Cloud Infrastructure (Production)

### Cloud Provider Account
- **AWS**, **Google Cloud**, or **Azure**
- **Services needed**:
  - Virtual machines/containers (EC2, GCE, Azure VMs)
  - Load balancers (ALB, Cloud Load Balancing)
  - Managed databases (RDS, Cloud SQL, Azure Database)
  - Object storage (S3, Cloud Storage, Blob Storage)

### Container Orchestration (Phase 5)
- **Docker**: Container runtime
- **Kubernetes**: Orchestration (or managed services like EKS, GKE, AKS)
- **Helm**: Package management for Kubernetes

## 12. Compliance & Legal Requirements

### Regulatory Compliance Setup
- **Do Not Call (DNC) Registry**: Account and API access
- **TCPA Compliance**: Consent management system requirements
- **GDPR/CCPA**: Data privacy compliance framework
- **Call Recording Laws**: Understanding of state/federal requirements

### Audit & Logging Requirements
- **Retention Policies**: Define data retention periods
- **Backup Strategies**: Regular backups with encryption
- **Access Logging**: Complete audit trails for compliance

## 13. Network & Firewall Configuration

### Port Requirements
```
# HTTP/HTTPS
80, 443 (inbound)

# WebSocket (WSS)
443 (typically over HTTPS)

# Database connections
5432 (PostgreSQL - internal/VPN only)
6379 (Redis - internal only)

# Telephony (if using SIP)
5060-5061 (SIP signaling)
10000-20000 (RTP media - configurable range)
```

### Network Security
- **Firewall Rules**: Restrict access to database and internal services
- **VPN Access**: For administrative and development access
- **Rate Limiting**: Protection against abuse and DDoS

## 14. Installation Checklist

### Phase 1 Prerequisites (Before Development)
- [ ] Python 3.13 installed and configured
- [ ] Virtual environment created and activated
- [ ] PostgreSQL installed and configured
- [ ] Redis server installed and running
- [ ] Git version control configured
- [ ] IDE/editor set up with proper configuration
- [ ] Basic requirements.txt created and installed

### Phase 2 Prerequisites (Before Frontend)
- [ ] Node.js 18+ installed
- [ ] npm/yarn package manager ready
- [ ] Django Channels configuration tested
- [ ] WebSocket basic connectivity verified

### Phase 3 Prerequisites (Before Telephony)
- [ ] Asterisk PBX server installed and configured
- [ ] SIP trunking provider account and credentials
- [ ] ARI (Asterisk REST Interface) enabled and tested
- [ ] AMI (Asterisk Manager Interface) configured
- [ ] Call recording storage setup (local or cloud)
- [ ] Phone numbers provisioned through SIP provider
- [ ] Network firewall configured for SIP/RTP traffic

### Phase 4 Prerequisites (Before Analytics)
- [ ] Time-series database selected and installed
- [ ] Monitoring tools accounts created
- [ ] SSL certificates obtained
- [ ] Security frameworks implemented

### Phase 5 Prerequisites (Before Production)
- [ ] Cloud infrastructure account and services
- [ ] Container runtime and orchestration tools
- [ ] Backup and disaster recovery plans
- [ ] Compliance and legal requirements addressed

## 15. Estimated Setup Time

### Development Environment Setup
- **Basic setup** (Python, Django, PostgreSQL, Redis): 2-4 hours
- **Full development environment**: 1-2 days
- **Frontend integration**: Additional 4-8 hours

### Production Infrastructure
- **Initial cloud setup**: 1-2 weeks
- **Full production deployment**: 2-4 weeks
- **Compliance and security hardening**: 1-3 weeks

## 16. Common Setup Issues & Solutions

### Database Connection Issues
- **Problem**: PostgreSQL connection refused
- **Solution**: Check service status, firewall, authentication settings
- **Command**: `sudo systemctl status postgresql`

### Redis Connection Issues
- **Problem**: Redis server not accessible
- **Solution**: Verify Redis service, check bind address configuration
- **Command**: `redis-cli ping`

### Python Virtual Environment Issues
- **Problem**: Package installation failures
- **Solution**: Upgrade pip, check Python version compatibility
- **Command**: `python -m pip install --upgrade pip`

### WebSocket Connection Issues
- **Problem**: WebSocket connections failing in development
- **Solution**: Check ASGI server configuration, Redis channel layer
- **Debug**: Enable Django Channels debug logging

## 17. Next Steps After Setup

1. **Verify Installation**: Run basic connectivity tests
2. **Create Requirements File**: Document exact versions used
3. **Initialize Git Repository**: Set up version control
4. **Configure Environment Variables**: Set up secure configuration
5. **Run Initial Tests**: Ensure all components communicate properly
6. **Begin Phase 1 Development**: Follow tasks.md development checklist

---

**Important Notes:**
- This setup must be completed before beginning any development tasks
- Production requirements can be phased in during later development stages
- Keep all credentials and API keys secure and never commit to version control
- Document any deviations from these requirements for team reference
- Regular updates to this document may be needed as technology evolves

**Support Resources:**
- Django Documentation: https://docs.djangoproject.com/
- Django Channels Documentation: https://channels.readthedocs.io/
- Celery Documentation: https://docs.celeryq.dev/
- PostgreSQL Documentation: https://www.postgresql.org/docs/
- Redis Documentation: https://redis.io/docs/
