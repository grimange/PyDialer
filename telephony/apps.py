"""
Telephony app configuration for PyDialer.

This app handles telephony integration including:
- Asterisk ARI controller
- AI Media Gateway components
- WebRTC gateway functionality
- Audio processing and resampling
- OpenAI Whisper integration
"""
from django.apps import AppConfig


class TelephonyConfig(AppConfig):
    """Configuration for the telephony app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'telephony'
    verbose_name = 'Telephony & AI Media Gateway'
    
    def ready(self):
        """Initialize app when Django starts."""
        # Import signal handlers if any
        pass
