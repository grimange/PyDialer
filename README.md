# PyDialer - Django Channels Predictive Dialer System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Django](https://img.shields.io/badge/Django-4.2.16-green.svg)](https://djangoproject.com)
[![Channels](https://img.shields.io/badge/Channels-4.0.0-blue.svg)](https://channels.readthedocs.io)
[![Python](https://img.shields.io/badge/Python-3.9-blue.svg)](https://www.python.org)

A sophisticated, real-time predictive dialer and call center management system built with Django Channels, designed for scalable operations with comprehensive AI integration capabilities.

## 🎯 Overview

PyDialer is a modern call center solution that reimagines traditional predictive dialing systems using Django Channels for real-time WebSocket communication. Based on the proven Vicidial architecture but built with modern web technologies, it provides a complete platform for inbound and outbound call center operations.

### Key Features

- **🚀 Real-time Communication**: WebSocket-based real-time updates using Django Channels
- **📞 Predictive Dialing**: Advanced predictive and progressive dialing algorithms
- **🤖 AI Integration**: Real-time speech-to-text transcription with OpenAI Whisper
- **📊 Comprehensive Analytics**: Real-time dashboards and detailed reporting
- **🔒 Security & Compliance**: DNC management, call recording, and regulatory compliance
- **🎛️ Multi-tenant Architecture**: Support for multiple campaigns and teams
- **☁️ Cloud-Ready**: Docker containerization and scalable deployment options

## 🏗️ Architecture

PyDialer follows a microservices architecture with the following core components:

- **Django Backend**: REST APIs and business logic
- **Django Channels**: WebSocket communication layer
- **PostgreSQL**: Primary database for persistent data
- **Redis**: Channel layer, caching, and message broker
- **Celery**: Background task processing and predictive dialing engine
- **AI Media Gateway**: Real-time audio processing and transcription
- **Asterisk/FreeSWITCH**: Telephony backend integration

### System Requirements

- **Python**: 3.9+
- **Django**: 4.2.16 LTS
- **PostgreSQL**: 12+ (production)
- **Redis**: 6.0+
- **Node.js**: 18+ (for frontend development)

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Redis 6.0+
- Git

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/PyDialer.git
   cd PyDialer
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # source .venv/bin/activate  # Linux/Mac
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment configuration**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Database setup**:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

6. **Start development services**:
   ```bash
   # Start Redis (required)
   redis-server

   # Start Django development server
   python manage.py runserver

   # Start Celery worker (in separate terminal)
   celery -A PyDialer worker -l info

   # Start Celery beat scheduler (in separate terminal)
   celery -A PyDialer beat -l info
   ```

### Docker Quick Start

For a complete setup with AI capabilities:

```bash
# Start AI Gateway with all dependencies
docker-compose -f docker-compose.ai-gateway.yml up -d

# Or start basic Asterisk integration
docker-compose -f docker-compose.asterisk.yml up -d
```

## 📋 Configuration

### Environment Variables

Key environment variables (see `.env.example` for complete list):

```env
# Django Settings
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=True
DJANGO_SETTINGS_MODULE=PyDialer.settings.base

# Database
DB_CONNECTION=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_NAME=pydialer
DB_USER=pydialer
DB_PASSWORD=your-password

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# OpenAI Integration (for AI features)
OPENAI_API_KEY=your-openai-api-key
ENABLE_AI_TRANSCRIPTION=true

# Asterisk Integration
ASTERISK_ARI_HOST=localhost
ASTERISK_ARI_PORT=8088
ASTERISK_ARI_USERNAME=pydialer
ASTERISK_ARI_PASSWORD=your-password
```

## 🎮 Usage

### Agent Interface

1. **Login**: Access the agent interface at `/agent/`
2. **Status Management**: Set availability status (Available, Break, Lunch, etc.)
3. **Call Handling**: Receive calls via the predictive dialer
4. **Dispositions**: Complete call outcomes and notes
5. **Real-time Updates**: Receive live notifications and call information

### Supervisor Dashboard

1. **Campaign Management**: Create and manage dialing campaigns
2. **Real-time Monitoring**: View live agent status and campaign statistics
3. **Analytics**: Access comprehensive reporting and KPIs
4. **Lead Management**: Import/export leads and manage DNC lists

### API Integration

PyDialer provides comprehensive REST APIs:

```python
# Example API usage
import requests

# Authentication
response = requests.post('/api/v1/auth/login/', {
    'username': 'your-username',
    'password': 'your-password'
})
token = response.json()['access']

# Campaign statistics
headers = {'Authorization': f'Bearer {token}'}
stats = requests.get('/api/v1/campaigns/stats/', headers=headers)
```

## 🧪 Testing

PyDialer uses pytest for comprehensive testing:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=.

# Run specific test module
pytest agents/tests.py

# Run async tests (for Channels)
pytest --asyncio-mode=auto
```

### Test Categories

- **Unit Tests**: Model logic and API endpoints
- **Integration Tests**: Database and third-party integrations
- **WebSocket Tests**: Real-time communication testing
- **Performance Tests**: Load testing for high-volume scenarios

## 📊 Project Structure

```
PyDialer/
├── PyDialer/           # Main project configuration
│   ├── settings/       # Modular settings (base, staging, production)
│   ├── asgi.py         # ASGI configuration for Channels
│   └── urls.py         # URL routing
├── agents/             # User management and agent status
├── calls/              # Call handling, CDR, dispositions
├── campaigns/          # Campaign management and dialing rules
├── leads/              # Lead management and imports
├── reporting/          # Analytics and reporting
├── telephony/          # PBX integration and audio processing
├── frontend/           # React/Vue frontend application
├── docs/               # Comprehensive documentation
├── requirements.txt    # Python dependencies
├── docker-compose*.yml # Container orchestration
└── manage.py          # Django management script
```

## 🔧 Development

### Prerequisites for Development

- Python 3.9+
- Node.js 18+ (for frontend)
- PostgreSQL 12+
- Redis 6.0+
- Docker (optional but recommended)

### Development Workflow

1. **Backend Development**:
   ```bash
   python manage.py runserver
   celery -A PyDialer worker -l info
   ```

2. **Frontend Development**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

3. **Testing**:
   ```bash
   pytest --cov=.
   npm test  # Frontend tests
   ```

### Code Quality

- **Linting**: Use `ruff` for Python linting and formatting
- **Type Hints**: Gradual typing adoption
- **Documentation**: Comprehensive docstrings and API documentation
- **Testing**: Maintain >80% code coverage

## 📈 Deployment

### Production Deployment

1. **Using Docker**:
   ```bash
   docker-compose -f docker-compose.production.yml up -d
   ```

2. **Manual Deployment**:
   ```bash
   # ASGI server (required for Channels)
   daphne -p 8000 PyDialer.asgi:application

   # Background workers
   celery -A PyDialer worker -l info
   celery -A PyDialer beat -l info
   ```

### Scaling Considerations

- **Load Balancing**: Use sticky sessions for WebSocket connections
- **Database**: Configure read replicas and connection pooling
- **Redis**: Use Redis Cluster for high availability
- **Monitoring**: Implement comprehensive logging and monitoring

## 🗺️ Roadmap

PyDialer follows a phased implementation approach:

### Phase 1: MVP (Months 1-3) ✅
- Basic Django application with user authentication
- Simple agent interface with manual dialing
- WebSocket-based real-time updates
- Basic call disposition and recording
- Asterisk PBX integration

### Phase 2: Enhanced Features (Months 4-6) 🚧
- Predictive/progressive dialing implementation
- Advanced campaign management
- Lead import/export and DNC scrubbing
- Answer machine detection integration
- Enhanced analytics and reporting

### Phase 3: Advanced Integration (Months 7-9) 📋
- Advanced Asterisk features (monitoring, barge, whisper)
- WebRTC softphone implementation
- AI-powered real-time transcription
- Advanced call routing and skills-based routing
- Comprehensive compliance features

### Phase 4: Scale & Polish (Months 10-12) 📋
- Multi-tenant architecture
- Advanced analytics and machine learning
- API integrations and webhooks
- Mobile applications
- Enterprise security features

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Ensure all tests pass: `pytest`
5. Commit your changes: `git commit -m 'Add amazing feature'`
6. Push to the branch: `git push origin feature/amazing-feature`
7. Open a Pull Request

### Reporting Issues

- Use the [GitHub Issues](https://github.com/your-username/PyDialer/issues) tracker
- Include detailed reproduction steps
- Provide environment information
- Add relevant logs and error messages

## 📝 Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[Installation Guide](docs/INSTALLATION.md)**: Detailed setup instructions
- **[API Documentation](docs/API.md)**: Complete API reference
- **[Architecture Guide](docs/ARCHITECTURE.md)**: System design and components
- **[Deployment Guide](docs/DEPLOYMENT.md)**: Production deployment strategies
- **[Implementation Plan](docs/plan.md)**: Detailed development roadmap

## 🔐 Security

- **Authentication**: JWT-based authentication with refresh tokens
- **Authorization**: Role-based access control (RBAC)
- **Data Protection**: TLS/SSL encryption and data encryption at rest
- **Compliance**: DNC management and regulatory compliance features
- **Monitoring**: Comprehensive audit trails and security logging

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Vicidial Project**: Original inspiration and architecture reference
- **Django Community**: For the excellent framework and ecosystem
- **Django Channels**: For real-time WebSocket capabilities
- **Contributors**: All the developers who have contributed to this project

## 📞 Support

- **Documentation**: [docs/](docs/)
- **Issues**: [GitHub Issues](https://github.com/your-username/PyDialer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-username/PyDialer/discussions)

---

**PyDialer** - Empowering modern call centers with real-time technology and AI integration.
