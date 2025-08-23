# PyDialer Development Guidelines

## Project Overview
This is a Django Channels-based implementation of a Vicidial-like predictive dialer/call center system. The project is in early development stages with the basic Django 4.2.16 project structure in place.

## Build/Configuration Instructions

### Prerequisites
- Python 3.9 (as configured in PyCharm IDE)
- Virtual environment support (.venv directory present)

### Initial Setup
1. **Virtual Environment Setup**:
   ```powershell
   # Activate the existing virtual environment
   .venv\Scripts\activate
   ```

2. **Django Installation**:
   The project uses Django 4.2.16. Install dependencies:
   ```powershell
   pip install Django==4.2.16
   # Additional dependencies will be needed as development progresses:
   pip install channels redis celery psycopg2-binary
   ```

3. **Database Setup**:
   Currently using SQLite for development. Run initial migrations:
   ```powershell
   python manage.py migrate
   ```

4. **Development Server**:
   ```powershell
   python manage.py runserver
   ```

### Planned Architecture Components
Based on the architectural documentation (`docs/vicidial_like_system_architecture_django_channels.md`), the full system will require:

- **Django + Django Channels** (ASGI with Daphne)
- **Redis** (Channel layer for WebSocket groups and Celery broker)
- **PostgreSQL** (Production database, replace SQLite)
- **Celery** (Task processing - dial loops, CDR ingestion, reporting)
- **Frontend** (React/Vue with WebSocket integration)
- **Telephony Integration** (Asterisk/FreeSWITCH or CPaaS like Twilio)

### Configuration Notes
- **Settings Module**: `PyDialer.settings`
- **Templates Directory**: `templates/` (configured in settings)
- **Development Secret Key**: Currently using Django's default insecure key - **MUST** be changed for production
- **Debug Mode**: Currently `DEBUG = True` - **MUST** be disabled in production

## Testing Information

### Test Configuration
The project uses Django's built-in testing framework with no additional configuration required.

### Running Tests
```powershell
# Run all tests
python manage.py test

# Run specific test file
python manage.py test test_filename

# Run with verbose output
python manage.py test --verbose

# Run tests with coverage (if coverage.py is installed)
coverage run --source='.' manage.py test
coverage report
```

### Test Database
Django automatically creates and destroys test databases (SQLite by default). No additional setup required.

### Adding New Tests
1. Create test files in individual Django apps following Django conventions:
   - `tests.py` in each app directory
   - Or `tests/` package with `__init__.py` and individual test modules

2. **Test Example Structure**:
   ```python
   from django.test import TestCase
   from django.contrib.auth.models import User

   class YourModelTestCase(TestCase):
       def setUp(self):
           """Set up test data"""
           pass

       def test_your_functionality(self):
           """Test specific functionality"""
           pass
   ```

3. **WebSocket Testing** (for future Django Channels implementation):
   ```python
   from channels.testing import WebsocketCommunicator
   from channels.routing import URLRouter
   from django.test import TransactionTestCase

   class WebSocketTestCase(TransactionTestCase):
       async def test_websocket_connection(self):
           communicator = WebsocketCommunicator(application, "/ws/path/")
           connected, subprotocol = await communicator.connect()
           self.assertTrue(connected)
           await communicator.disconnect()
   ```

### Testing Best Practices for This Project
- **Model Tests**: Test all custom models, especially call center specific models (campaigns, leads, agents)
- **API Tests**: Test REST/GraphQL APIs thoroughly with various scenarios
- **WebSocket Tests**: Test real-time features (agent presence, call events, dashboards)
- **Celery Task Tests**: Test asynchronous tasks (dial loops, CDR processing, reporting)
- **Integration Tests**: Test telephony integration components
- **Load Testing**: Essential for call center performance requirements

## Development Information

### Project Architecture Patterns

#### Django Apps Organization (Planned)
Based on the architectural documentation, the project should be organized into these Django apps:
- **agents** - Agent management, authentication, presence
- **campaigns** - Campaign configuration, dial lists, scheduling
- **calls** - Call management, CDR, recording metadata
- **leads** - Lead management, disposition, callbacks
- **telephony** - PBX/CPaaS integration abstraction
- **monitoring** - Real-time dashboards, supervisory tools
- **reporting** - Analytics, KPIs, compliance reports

#### Key Development Patterns
1. **ASGI Application**: Django Channels for WebSocket support
2. **Channel Groups**: For real-time updates to agent/supervisor interfaces
3. **Celery Tasks**: For background processing (predictive dialing, data imports)
4. **Service Layer**: Abstraction for telephony providers (Asterisk/Twilio/etc.)
5. **Event-Driven Architecture**: Call events trigger WebSocket updates

### Database Considerations
- **Development**: SQLite (current)
- **Production**: PostgreSQL with proper indexing for call center workloads
- **Time-Series Data**: Consider ClickHouse or TimescaleDB for analytics
- **Caching**: Redis for session data and real-time state

### Real-Time Features Implementation
- **WebSocket Consumers**: For agent state, call popups, supervisor dashboards
- **Channel Layers**: Redis-based for multi-server deployments
- **Presence System**: Track agent status across multiple browser tabs/devices

### Security Considerations
- **Authentication**: Multi-level (agents, supervisors, admins)
- **CSRF Protection**: Especially important for telephony API endpoints
- **Rate Limiting**: Critical for API endpoints that trigger calls
- **Audit Logging**: Required for compliance in call center environments

### Performance Considerations
- **Database Queries**: Optimize for high-volume call data
- **WebSocket Scaling**: Use Redis channel layer for horizontal scaling
- **Celery Monitoring**: Monitor task queues for dial loop performance
- **CDR Processing**: Efficient bulk operations for call detail records

### Development Workflow
1. **Feature Development**: Start with models, add APIs, implement WebSocket consumers
2. **Testing Strategy**: Unit tests → Integration tests → Load testing
3. **Telephony Integration**: Use webhook endpoints for initial CPaaS integration
4. **Frontend Integration**: WebSocket client for real-time updates

### IDE Configuration
- **PyCharm Project**: Configured with Python 3.9 interpreter
- **Django Integration**: Django server run configuration available
- **Module Structure**: Main project in `PyDialer/`

### Known Limitations/TODOs
- No requirements.txt file yet - create when dependencies are finalized
- No Docker configuration - consider for production deployment
- Default SQLite database - migrate to PostgreSQL for production
- No CI/CD pipeline configured
- No logging configuration beyond Django defaults
- No environment-specific settings (dev/staging/prod)

### Compliance Requirements
Call centers have specific regulatory requirements:
- **Call Recording**: Legal compliance for recording storage and access
- **Do Not Call (DNC)**: Integration with DNC registries
- **TCPA Compliance**: Consent management for automated calls
- **Data Retention**: Policies for call data and recordings
- **Audit Trails**: Complete logging of agent actions and call dispositions

---
*Generated: 2025-08-22 07:58*
*Django Version: 4.2.16*
*Python Version: 3.9*
