"""
SIP Trunk Manager for PyDialer.

This module provides comprehensive SIP trunk management for PSTN connectivity,
including configuration generation, trunk monitoring, and provider integration.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class TrunkStatus(Enum):
    """SIP trunk status enumeration."""
    ONLINE = "online"
    OFFLINE = "offline"
    UNREACHABLE = "unreachable"
    LAGGED = "lagged"
    UNKNOWN = "unknown"


class TrunkType(Enum):
    """SIP trunk type enumeration."""
    REGISTER = "register"  # Register-based trunk
    PEER = "peer"          # Peer-to-peer trunk
    USER = "user"          # User-based trunk
    FRIEND = "friend"      # Friend (combination)


class ProviderType(Enum):
    """PSTN provider type enumeration."""
    TWILIO = "twilio"
    BANDWIDTH = "bandwidth"
    FLOWROUTE = "flowroute"
    VOIPMS = "voipms"
    VITELITY = "vitelity"
    ANVEO = "anveo"
    CUSTOM = "custom"


@dataclass
class SIPTrunkConfig:
    """SIP trunk configuration."""
    name: str
    host: str
    username: str
    secret: str
    trunk_type: TrunkType = TrunkType.FRIEND
    provider: ProviderType = ProviderType.CUSTOM
    port: int = 5060
    transport: str = "udp"  # udp, tcp, tls
    context: str = "from-pstn"
    
    # Authentication
    auth_user: Optional[str] = None
    from_user: Optional[str] = None
    from_domain: Optional[str] = None
    
    # Registration
    register: bool = True
    register_timeout: int = 120
    register_attempts: int = 0  # 0 = infinite
    
    # Call limits
    call_limit: Optional[int] = None
    busy_level: Optional[int] = None
    
    # Codecs
    allow: List[str] = None
    disallow: str = "all"
    
    # DTMF
    dtmfmode: str = "rfc2833"
    
    # NAT handling
    nat: str = "force_rport,comedia"
    directmedia: bool = False
    
    # Quality settings
    qualify: Union[bool, int] = True
    qualify_frequency: int = 60
    qualify_timeout: int = 3
    
    # Advanced settings
    insecure: Optional[str] = None
    canreinvite: bool = False
    trust_rpid: bool = False
    send_rpid: bool = False
    
    # Provider-specific settings
    provider_settings: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.allow is None:
            self.allow = ["ulaw", "alaw", "g729", "gsm"]
        if self.provider_settings is None:
            self.provider_settings = {}


@dataclass
class TrunkStatus:
    """SIP trunk status information."""
    name: str
    status: TrunkStatus
    address: Optional[str] = None
    port: Optional[int] = None
    qualify: Optional[str] = None
    monitor: Optional[str] = None
    description: Optional[str] = None
    last_update: Optional[datetime] = None


class SIPTrunkManager:
    """
    SIP Trunk Manager for PSTN connectivity.
    
    Handles SIP trunk configuration, monitoring, and management
    for connecting to PSTN providers and carriers.
    """
    
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path("/etc/asterisk")
        self.sip_conf_path = self.config_dir / "sip.conf"
        self.pjsip_conf_path = self.config_dir / "pjsip.conf"
        self.extensions_conf_path = self.config_dir / "extensions.conf"
        
        # Trunk configurations
        self.trunks: Dict[str, SIPTrunkConfig] = {}
        
        # Provider templates
        self._load_provider_templates()
        
        logger.info(f"SIP Trunk Manager initialized with config dir: {self.config_dir}")
    
    def _load_provider_templates(self) -> None:
        """Load predefined provider templates."""
        self.provider_templates = {
            ProviderType.TWILIO: {
                "host": "pstn.twilio.com",
                "transport": "tls",
                "port": 5061,
                "dtmfmode": "rfc2833",
                "allow": ["ulaw", "alaw"],
                "insecure": "port,invite",
                "provider_settings": {
                    "auth_required": True,
                    "encryption": "tls",
                    "media_encryption": "srtp"
                }
            },
            ProviderType.BANDWIDTH: {
                "transport": "udp",
                "port": 5060,
                "dtmfmode": "rfc2833",
                "allow": ["ulaw", "alaw", "g729"],
                "provider_settings": {
                    "requires_registration": True,
                    "supports_origination": True,
                    "supports_termination": True
                }
            },
            ProviderType.FLOWROUTE: {
                "host": "sip.flowroute.com",
                "transport": "udp",
                "port": 5060,
                "dtmfmode": "rfc2833",
                "allow": ["ulaw", "alaw"],
                "provider_settings": {
                    "tech_prefix": "1",
                    "supports_ani": True
                }
            },
            ProviderType.VOIPMS: {
                "transport": "udp",
                "port": 5060,
                "dtmfmode": "rfc2833",
                "allow": ["ulaw", "alaw", "g729"],
                "register": True,
                "provider_settings": {
                    "location_servers": [
                        "montreal.voip.ms",
                        "toronto.voip.ms",
                        "vancouver.voip.ms"
                    ]
                }
            }
        }
    
    def create_trunk(self, config: SIPTrunkConfig) -> None:
        """Create a new SIP trunk configuration."""
        if config.name in self.trunks:
            raise ValueError(f"Trunk '{config.name}' already exists")
        
        # Apply provider template if available
        if config.provider in self.provider_templates:
            template = self.provider_templates[config.provider]
            for key, value in template.items():
                if key != "provider_settings" and not hasattr(config, key):
                    setattr(config, key, value)
                elif key == "provider_settings":
                    config.provider_settings.update(value)
        
        self.trunks[config.name] = config
        logger.info(f"Created SIP trunk: {config.name} ({config.provider.value})")
    
    def remove_trunk(self, name: str) -> None:
        """Remove a SIP trunk configuration."""
        if name not in self.trunks:
            raise ValueError(f"Trunk '{name}' not found")
        
        del self.trunks[name]
        logger.info(f"Removed SIP trunk: {name}")
    
    def get_trunk(self, name: str) -> Optional[SIPTrunkConfig]:
        """Get SIP trunk configuration by name."""
        return self.trunks.get(name)
    
    def list_trunks(self) -> Dict[str, SIPTrunkConfig]:
        """List all configured SIP trunks."""
        return self.trunks.copy()
    
    def generate_sip_conf(self) -> str:
        """Generate sip.conf configuration for legacy SIP."""
        lines = [
            "; PyDialer SIP Configuration",
            "; Generated automatically - DO NOT EDIT MANUALLY",
            f"; Generated: {timezone.now().isoformat()}",
            "",
            "[general]",
            "context=default",
            "allowoverlap=no",
            "udpbindaddr=0.0.0.0:5060",
            "tcpenable=yes",
            "tcpbindaddr=0.0.0.0:5060",
            "transport=udp",
            "srvlookup=yes",
            "useragent=PyDialer",
            "",
            "; Global settings",
            "disallow=all",
            "allow=ulaw",
            "allow=alaw",
            "allow=g729",
            "allow=gsm",
            "",
            "dtmfmode=rfc2833",
            "rfc2833compensate=yes",
            "",
            "nat=force_rport,comedia",
            "directmedia=no",
            "",
            "qualify=yes",
            "qualifyfreq=60",
            "",
            "; Trunk configurations",
            ""
        ]
        
        # Add trunk configurations
        for trunk in self.trunks.values():
            lines.extend(self._generate_trunk_sip_conf(trunk))
            lines.append("")
        
        return "\n".join(lines)
    
    def _generate_trunk_sip_conf(self, trunk: SIPTrunkConfig) -> List[str]:
        """Generate sip.conf section for a specific trunk."""
        lines = [f"; {trunk.name} ({trunk.provider.value})"]
        
        if trunk.register:
            # Registration line
            reg_line = f"register => {trunk.username}:{trunk.secret}@{trunk.host}"
            if trunk.port != 5060:
                reg_line += f":{trunk.port}"
            lines.append(reg_line)
            lines.append("")
        
        # Trunk definition
        lines.append(f"[{trunk.name}]")
        lines.append(f"type={trunk.trunk_type.value}")
        lines.append(f"host={trunk.host}")
        lines.append(f"username={trunk.username}")
        lines.append(f"secret={trunk.secret}")
        
        if trunk.port != 5060:
            lines.append(f"port={trunk.port}")
        
        lines.append(f"context={trunk.context}")
        lines.append(f"dtmfmode={trunk.dtmfmode}")
        lines.append(f"nat={trunk.nat}")
        lines.append(f"directmedia={'yes' if trunk.directmedia else 'no'}")
        lines.append(f"canreinvite={'yes' if trunk.canreinvite else 'no'}")
        
        # Codecs
        lines.append(f"disallow={trunk.disallow}")
        for codec in trunk.allow:
            lines.append(f"allow={codec}")
        
        # Quality monitoring
        if isinstance(trunk.qualify, bool):
            lines.append(f"qualify={'yes' if trunk.qualify else 'no'}")
        else:
            lines.append(f"qualify={trunk.qualify}")
        
        lines.append(f"qualifyfreq={trunk.qualify_frequency}")
        
        # Optional settings
        if trunk.call_limit:
            lines.append(f"call-limit={trunk.call_limit}")
        
        if trunk.busy_level:
            lines.append(f"busylevel={trunk.busy_level}")
        
        if trunk.insecure:
            lines.append(f"insecure={trunk.insecure}")
        
        if trunk.auth_user:
            lines.append(f"authuser={trunk.auth_user}")
        
        if trunk.from_user:
            lines.append(f"fromuser={trunk.from_user}")
        
        if trunk.from_domain:
            lines.append(f"fromdomain={trunk.from_domain}")
        
        return lines
    
    def generate_pjsip_conf(self) -> str:
        """Generate pjsip.conf configuration for PJSIP."""
        lines = [
            "; PyDialer PJSIP Configuration",
            "; Generated automatically - DO NOT EDIT MANUALLY",
            f"; Generated: {timezone.now().isoformat()}",
            "",
            "[global]",
            "type=global",
            "user_agent=PyDialer",
            "default_outbound_endpoint=default_outbound",
            "",
            "[transport-udp]",
            "type=transport",
            "protocol=udp",
            "bind=0.0.0.0:5060",
            "",
            "[transport-tcp]",
            "type=transport",
            "protocol=tcp",
            "bind=0.0.0.0:5060",
            "",
            "[transport-tls]",
            "type=transport",
            "protocol=tls",
            "bind=0.0.0.0:5061",
            "cert_file=/etc/asterisk/keys/asterisk.pem",
            "priv_key_file=/etc/asterisk/keys/asterisk.key",
            "",
            "; Trunk configurations",
            ""
        ]
        
        # Add trunk configurations
        for trunk in self.trunks.values():
            lines.extend(self._generate_trunk_pjsip_conf(trunk))
            lines.append("")
        
        return "\n".join(lines)
    
    def _generate_trunk_pjsip_conf(self, trunk: SIPTrunkConfig) -> List[str]:
        """Generate pjsip.conf sections for a specific trunk."""
        lines = [f"; {trunk.name} ({trunk.provider.value})"]
        
        # Endpoint
        lines.append(f"[{trunk.name}]")
        lines.append("type=endpoint")
        lines.append(f"transport=transport-{trunk.transport}")
        lines.append(f"context={trunk.context}")
        lines.append(f"dtmf_mode={trunk.dtmfmode}")
        lines.append(f"direct_media={'yes' if trunk.directmedia else 'no'}")
        
        # Codecs
        lines.append(f"disallow={trunk.disallow}")
        for codec in trunk.allow:
            lines.append(f"allow={codec}")
        
        # Auth (if required)
        if trunk.username and trunk.secret:
            lines.append(f"outbound_auth={trunk.name}_auth")
            lines.append("")
            
            # Auth section
            lines.append(f"[{trunk.name}_auth]")
            lines.append("type=auth")
            lines.append(f"auth_type=userpass")
            lines.append(f"username={trunk.username}")
            lines.append(f"password={trunk.secret}")
            lines.append("")
        
        # AOR (Address of Record)
        lines.append(f"[{trunk.name}_aor]")
        lines.append("type=aor")
        lines.append(f"contact=sip:{trunk.host}:{trunk.port}")
        lines.append("qualify_frequency=60")
        lines.append("")
        
        # Identify
        lines.append(f"[{trunk.name}_identify]")
        lines.append("type=identify")
        lines.append(f"endpoint={trunk.name}")
        lines.append(f"match={trunk.host}")
        
        return lines
    
    def generate_extensions_conf(self) -> str:
        """Generate extensions.conf dialplan for trunk routing."""
        lines = [
            "; PyDialer Extensions Configuration",
            "; Generated automatically - DO NOT EDIT MANUALLY",
            f"; Generated: {timezone.now().isoformat()}",
            "",
            "; Outbound routing contexts",
            ""
        ]
        
        # Generate outbound contexts for each trunk
        for trunk in self.trunks.values():
            lines.extend(self._generate_trunk_dialplan(trunk))
            lines.append("")
        
        # Generate inbound context
        lines.extend([
            "[from-pstn]",
            "; Inbound calls from PSTN",
            "exten => _X.,1,NoOp(Inbound call from PSTN: ${CALLERID(all)})",
            "exten => _X.,n,Set(CHANNEL(musicclass)=default)",
            "exten => _X.,n,Goto(pydialer-inbound,${EXTEN},1)",
            "",
            "[pydialer-inbound]",
            "; PyDialer inbound call handling",
            "exten => _X.,1,NoOp(PyDialer inbound: ${EXTEN})",
            "exten => _X.,n,Set(__PYDIALER_DIRECTION=inbound)",
            "exten => _X.,n,Set(__PYDIALER_DID=${EXTEN})",
            "exten => _X.,n,Stasis(pydialer,inbound,${EXTEN})",
            "exten => _X.,n,Hangup()",
            "",
            "exten => h,1,NoOp(Call ended)",
            "exten => h,n,Stasis(pydialer,hangup)",
        ])
        
        return "\n".join(lines)
    
    def _generate_trunk_dialplan(self, trunk: SIPTrunkConfig) -> List[str]:
        """Generate dialplan context for outbound routing via trunk."""
        context_name = f"outbound-{trunk.name}"
        
        lines = [
            f"[{context_name}]",
            f"; Outbound routing via {trunk.name}",
            "exten => _X.,1,NoOp(Outbound call via " + trunk.name + ": ${EXTEN})",
            "exten => _X.,n,Set(__PYDIALER_TRUNK=" + trunk.name + ")",
            "exten => _X.,n,Set(__PYDIALER_DIRECTION=outbound)",
        ]
        
        # Add provider-specific dial string modifications
        if trunk.provider == ProviderType.TWILIO:
            lines.extend([
                "exten => _X.,n,Set(DIAL_NUMBER=${EXTEN})",
                f"exten => _X.,n,Dial(SIP/{trunk.name}/${{DIAL_NUMBER}},60,rtT)",
            ])
        elif trunk.provider == ProviderType.FLOWROUTE:
            lines.extend([
                "exten => _X.,n,Set(DIAL_NUMBER=1${EXTEN})",  # Add tech prefix
                f"exten => _X.,n,Dial(SIP/{trunk.name}/${{DIAL_NUMBER}},60,rtT)",
            ])
        else:
            lines.extend([
                "exten => _X.,n,Set(DIAL_NUMBER=${EXTEN})",
                f"exten => _X.,n,Dial(SIP/{trunk.name}/${{DIAL_NUMBER}},60,rtT)",
            ])
        
        lines.extend([
            "exten => _X.,n,NoOp(Call result: ${DIALSTATUS})",
            "exten => _X.,n,Goto(outbound-${DIALSTATUS},${EXTEN},1)",
            "",
            "; Handle dial status",
            "exten => _X.,n(outbound-ANSWER),NoOp(Call answered)",
            "exten => _X.,n,Hangup()",
            "",
            "exten => _X.,n(outbound-BUSY),NoOp(Call busy)",
            "exten => _X.,n,Playtones(busy)",
            "exten => _X.,n,Wait(10)",
            "exten => _X.,n,Hangup()",
            "",
            "exten => _X.,n(outbound-CONGESTION),NoOp(Call congested)",
            "exten => _X.,n,Playtones(congestion)",
            "exten => _X.,n,Wait(10)",
            "exten => _X.,n,Hangup()",
            "",
            "exten => _X.,n(outbound-CHANUNAVAIL),NoOp(Channel unavailable)",
            "exten => _X.,n,Playtones(congestion)",
            "exten => _X.,n,Wait(10)",
            "exten => _X.,n,Hangup()",
        ])
        
        return lines
    
    def write_configurations(self) -> None:
        """Write all configuration files to disk."""
        try:
            # Ensure config directory exists
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            # Write sip.conf
            sip_conf = self.generate_sip_conf()
            with open(self.sip_conf_path, 'w') as f:
                f.write(sip_conf)
            logger.info(f"Written SIP configuration to {self.sip_conf_path}")
            
            # Write pjsip.conf
            pjsip_conf = self.generate_pjsip_conf()
            with open(self.pjsip_conf_path, 'w') as f:
                f.write(pjsip_conf)
            logger.info(f"Written PJSIP configuration to {self.pjsip_conf_path}")
            
            # Write extensions.conf
            extensions_conf = self.generate_extensions_conf()
            with open(self.extensions_conf_path, 'w') as f:
                f.write(extensions_conf)
            logger.info(f"Written extensions configuration to {self.extensions_conf_path}")
            
        except Exception as e:
            logger.error(f"Error writing configurations: {e}")
            raise
    
    async def reload_asterisk(self) -> bool:
        """Reload Asterisk configuration."""
        try:
            # This would typically use AMI to reload configs
            # For now, we'll just log the action
            logger.info("Reloading Asterisk configuration...")
            
            # TODO: Implement AMI reload commands
            # - "sip reload"
            # - "pjsip reload" 
            # - "dialplan reload"
            
            return True
            
        except Exception as e:
            logger.error(f"Error reloading Asterisk: {e}")
            return False
    
    def validate_trunk_config(self, config: SIPTrunkConfig) -> List[str]:
        """Validate trunk configuration and return any errors."""
        errors = []
        
        if not config.name:
            errors.append("Trunk name is required")
        
        if not config.host:
            errors.append("Trunk host is required")
        
        if not config.username:
            errors.append("Trunk username is required")
        
        if not config.secret:
            errors.append("Trunk secret is required")
        
        if config.port < 1 or config.port > 65535:
            errors.append("Invalid port number")
        
        if config.transport not in ["udp", "tcp", "tls"]:
            errors.append("Invalid transport protocol")
        
        return errors


# Global trunk manager instance
_trunk_manager: Optional[SIPTrunkManager] = None


def get_trunk_manager() -> SIPTrunkManager:
    """Get or create global trunk manager instance."""
    global _trunk_manager
    if _trunk_manager is None:
        config_dir = getattr(settings, 'ASTERISK_CONFIG_DIR', Path('/etc/asterisk'))
        _trunk_manager = SIPTrunkManager(config_dir=config_dir)
    return _trunk_manager


# Convenience functions
def create_trunk_from_dict(trunk_data: Dict[str, Any]) -> SIPTrunkConfig:
    """Create trunk configuration from dictionary."""
    # Convert enum strings to enum values
    if 'trunk_type' in trunk_data and isinstance(trunk_data['trunk_type'], str):
        trunk_data['trunk_type'] = TrunkType(trunk_data['trunk_type'])
    
    if 'provider' in trunk_data and isinstance(trunk_data['provider'], str):
        trunk_data['provider'] = ProviderType(trunk_data['provider'])
    
    return SIPTrunkConfig(**trunk_data)


def create_twilio_trunk(name: str, username: str, password: str) -> SIPTrunkConfig:
    """Create a Twilio SIP trunk configuration."""
    return SIPTrunkConfig(
        name=name,
        host="pstn.twilio.com",
        username=username,
        secret=password,
        provider=ProviderType.TWILIO,
        transport="tls",
        port=5061,
        insecure="port,invite"
    )


def create_flowroute_trunk(name: str, username: str, password: str) -> SIPTrunkConfig:
    """Create a Flowroute SIP trunk configuration."""
    return SIPTrunkConfig(
        name=name,
        host="sip.flowroute.com",
        username=username,
        secret=password,
        provider=ProviderType.FLOWROUTE,
        transport="udp",
        port=5060
    )
