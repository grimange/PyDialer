# Asterisk PBX Installation Guide for PyDialer

*Generated on: 2025-08-24*  
*Project: PyDialer - Django Channels-based Predictive Dialer System*  
*Task: #77 - Install and configure Asterisk PBX server*

This guide provides comprehensive instructions for installing and configuring Asterisk PBX on Windows to work with the PyDialer system's AI Media Gateway and real-time call processing capabilities.

## Prerequisites

### System Requirements
- **Operating System**: Windows 10/11 (64-bit)
- **RAM**: Minimum 4GB, Recommended 8GB+
- **CPU**: Multi-core processor recommended for real-time audio processing
- **Network**: Reliable internet connection for SIP trunking
- **Ports**: 5060 (SIP), 8088 (HTTP/ARI), 5038 (AMI), 10000-20000 (RTP)

### Required Software
- **Python 3.9**: Already installed for PyDialer
- **Redis**: Already configured for PyDialer
- **Visual Studio Build Tools**: For compiling dependencies

## Installation Methods

### Method 1: Docker Installation (Recommended)

Docker provides the most reliable and consistent Asterisk installation on Windows.

#### Step 1: Install Docker Desktop
```powershell
# Download Docker Desktop from https://www.docker.com/products/docker-desktop/
# Install and restart your system
# Verify installation
docker --version
```

#### Step 2: Create Asterisk Docker Configuration
Create `docker-compose.asterisk.yml` in the project root:

```yaml
version: '3.8'
services:
  asterisk:
    image: andrius/asterisk:18-current
    container_name: pydialer-asterisk
    restart: unless-stopped
    ports:
      - "5060:5060/udp"  # SIP
      - "8088:8088/tcp"  # ARI HTTP
      - "5038:5038/tcp"  # AMI
      - "10000-10100:10000-10100/udp"  # RTP range
    volumes:
      - ./docs/asterisk/config:/etc/asterisk
      - ./logs/asterisk:/var/log/asterisk
      - ./media/recordings:/var/spool/asterisk/recording
    environment:
      - ASTERISK_UID=1000
      - ASTERISK_GID=1000
    networks:
      - pydialer-network

networks:
  pydialer-network:
    external: false
```

#### Step 3: Start Asterisk Container
```powershell
# Create required directories
mkdir logs\asterisk
mkdir media\recordings

# Start Asterisk container
docker-compose -f docker-compose.asterisk.yml up -d

# Verify container is running
docker ps | findstr asterisk

# Check Asterisk logs
docker logs pydialer-asterisk
```

### Method 2: Windows Native Installation (Advanced)

#### Step 1: Install Cygwin Environment
```powershell
# Download Cygwin installer from https://www.cygwin.com/
# Install with the following packages:
# - gcc-core, gcc-g++, make, autoconf, automake
# - libtool, pkg-config, wget, curl
# - openssl-devel, sqlite3-devel
# - ncurses-devel, readline-devel
```

#### Step 2: Compile Asterisk from Source
```bash
# In Cygwin terminal
cd /cygdrive/c/temp

# Download Asterisk
wget http://downloads.asterisk.org/pub/telephony/asterisk/asterisk-18-current.tar.gz
tar -xzf asterisk-18-current.tar.gz
cd asterisk-18.*

# Configure build
./configure --with-jansson-bundled --with-pjproject-bundled

# Install menuselect dependencies
make menuselect.makeopts

# Enable required modules
menuselect/menuselect \
  --enable app_stasis \
  --enable res_ari \
  --enable res_ari_channels \
  --enable res_ari_bridges \
  --enable res_http_websocket \
  --enable chan_pjsip \
  --enable res_pjsip \
  --enable app_external_media \
  menuselect.makeopts

# Compile and install
make && make install
make samples  # Install sample configurations
```

## Configuration

### Basic Asterisk Configuration

#### 1. Main Configuration (`asterisk.conf`)
```ini
[directories]
astetcdir => /etc/asterisk
astmoddir => /usr/lib/asterisk/modules
astvarlibdir => /var/lib/asterisk
astdbdir => /var/lib/asterisk
astkeydir => /var/lib/asterisk
astdatadir => /var/lib/asterisk
astagidir => /var/lib/asterisk/agi-bin
astspooldir => /var/spool/asterisk
astrundir => /var/run/asterisk
astlogdir => /var/log/asterisk
astsbindir => /usr/sbin

[options]
verbose = 3
debug = 3
alwaysfork = yes
nofork = no
quiet = no
timestamp = yes
execincludes = yes
console = yes
highpriority = yes
initcrypto = yes
nocolor = no

[compat]
pbx_realtime=1.6
res_agi=1.6
app_set=1.6
```

#### 2. HTTP/ARI Configuration (`http.conf`)
```ini
[general]
enabled=yes
bindaddr=0.0.0.0
bindport=8088
prefix=asterisk
sessionlimit=100
session_inactivity=30000
session_keep_alive=15000

; Enable ARI
enablestatic=yes
redirect = / /static/config/index.html

; CORS settings for PyDialer integration
cors_enabled=yes
allowed_origins=http://localhost:3000,http://localhost:8000
allowed_methods=GET,POST,PUT,DELETE,OPTIONS
allowed_headers=Content-Type,Authorization,X-Requested-With
```

#### 3. ARI Configuration (`ari.conf`)
```ini
[general]
enabled = yes
pretty = yes
allowed_origins = *
websocket_write_timeout = 100

[asterisk]
type = user
read_only = no
password = asterisk
password_format = plain
```

#### 4. Manager Interface Configuration (`manager.conf`)
```ini
[general]
enabled = yes
port = 5038
bindaddr = 0.0.0.0
displayconnects = yes
timestampevents = yes
debug = on

[asterisk]
secret = asterisk
read = all
write = all
```

#### 5. PJSIP Configuration (`pjsip.conf`)
```ini
[global]
type=global
endpoint_identifier_order=ip,username,anonymous

[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060
external_media_address=AUTO_IP
external_signaling_address=AUTO_IP

[transport-tcp]
type=transport
protocol=tcp
bind=0.0.0.0:5060

; Example endpoint for testing
[demo_endpoint]
type=endpoint
context=demo
disallow=all
allow=ulaw
allow=alaw
allow=g722
auth=demo_auth
aors=demo_aor

[demo_auth]
type=auth
auth_type=userpass
username=demo
password=demo123

[demo_aor]
type=aor
max_contacts=1
```

#### 6. Dialplan Configuration (`extensions.conf`)
```ini
[general]
static=yes
writeprotect=no
clearglobalvars=no

[globals]
PYDIALER_API_URL=http://localhost:8000/api/v1
PYDIALER_WEBHOOK_SECRET=your-webhook-secret-here

; PyDialer Stasis Application Context
[pydialer-stasis]
exten => _X.,1,NoOp(PyDialer Stasis Entry: ${EXTEN})
same => n,Stasis(pydialer,${EXTEN},${CALLERID(num)})
same => n,Hangup()

; Inbound call handling
[pydialer-inbound]
exten => _X.,1,NoOp(Inbound call: ${EXTEN} from ${CALLERID(num)})
same => n,Set(CHANNEL(hangup_handler_push)=hangup-handler,s,1)
same => n,Stasis(pydialer,inbound,${EXTEN},${CALLERID(num)})
same => n,Hangup()

; Outbound call handling
[pydialer-outbound]
exten => _X.,1,NoOp(Outbound call: ${EXTEN})
same => n,Set(CHANNEL(hangup_handler_push)=hangup-handler,s,1)
same => n,Stasis(pydialer,outbound,${EXTEN})
same => n,Hangup()

; External Media for AI processing
[pydialer-external-media]
exten => ai_media,1,NoOp(External Media for AI processing)
same => n,Answer()
same => n,ExternalMedia()
same => n,Hangup()

; Hangup handler for cleanup
[hangup-handler]
exten => s,1,NoOp(Call cleanup handler)
same => n,System(curl -X POST ${PYDIALER_API_URL}/telephony/call-ended/ \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: ${PYDIALER_WEBHOOK_SECRET}" \
  -d '{"channel": "${CHANNEL}", "uniqueid": "${UNIQUEID}"}')
same => n,Return()

; Demo context for testing
[demo]
exten => 100,1,Answer()
same => n,Wait(1)
same => n,Playback(hello-world)
same => n,Hangup()

exten => 200,1,Answer()
same => n,Wait(1)
same => n,Stasis(pydialer,demo,${CALLERID(num)})
same => n,Hangup()
```

#### 7. Modules Configuration (`modules.conf`)
```ini
[modules]
autoload=yes

; Required modules for PyDialer
load => app_stasis.so
load => res_ari.so
load => res_ari_applications.so
load => res_ari_asterisk.so
load => res_ari_bridges.so
load => res_ari_channels.so
load => res_ari_endpoints.so
load => res_ari_events.so
load => res_ari_playbacks.so
load => res_ari_recordings.so
load => res_ari_sounds.so
load => res_http_websocket.so
load => chan_pjsip.so
load => res_pjsip.so
load => res_pjsip_session.so
load => app_external_media.so

; Audio codecs
load => codec_ulaw.so
load => codec_alaw.so
load => codec_g722.so

; Essential applications
load => app_dial.so
load => app_playback.so
load => app_echo.so
load => app_answer.so
load => app_hangup.so
load => app_verbose.so
load => app_noop.so
load => app_set.so
load => app_system.so

; Channel drivers
load => chan_bridge_media.so

; Functions
load => func_channel.so
load => func_callerid.so
load => func_strings.so
load => func_logic.so

; Resources
load => res_timing_timerfd.so
load => res_musiconhold.so
```

### PyDialer Integration Configuration

#### Environment Variables
Add to your `.env` file:
```env
# Asterisk Configuration
ASTERISK_ARI_URL=http://localhost:8088
ASTERISK_ARI_USERNAME=asterisk  
ASTERISK_ARI_PASSWORD=asterisk
ASTERISK_AMI_HOST=localhost
ASTERISK_AMI_PORT=5038
ASTERISK_AMI_USERNAME=asterisk
ASTERISK_AMI_PASSWORD=asterisk

# Stasis Application
ASTERISK_STASIS_APP=pydialer

# Media Gateway
EXTERNAL_MEDIA_RTP_START=10000
EXTERNAL_MEDIA_RTP_END=10100
```

## Testing the Installation

### 1. Verify Asterisk Service
```powershell
# For Docker installation
docker ps | findstr asterisk
docker exec -it pydialer-asterisk asterisk -r

# Check modules are loaded
docker exec -it pydialer-asterisk asterisk -rx "module show like ari"
docker exec -it pydialer-asterisk asterisk -rx "module show like stasis"
docker exec -it pydialer-asterisk asterisk -rx "module show like external_media"
```

### 2. Test ARI Connectivity
```powershell
# Test ARI HTTP interface
curl -u asterisk:asterisk http://localhost:8088/ari/asterisk/info

# Expected response: JSON with Asterisk information
```

### 3. Test WebSocket Connection
```javascript
// Browser console test
const ws = new WebSocket('ws://localhost:8088/ari/events?api_key=asterisk:asterisk&app=pydialer');
ws.onopen = () => console.log('ARI WebSocket connected');
ws.onmessage = (msg) => console.log('ARI Event:', JSON.parse(msg.data));
```

### 4. PyDialer ARI Controller Test
```python
# Run in Django shell: python manage.py shell
import asyncio
from telephony.ari_controller import ARIController

async def test_ari():
    controller = ARIController()
    try:
        await controller.start()
        print("ARI Controller connected successfully")
        await asyncio.sleep(5)
    finally:
        await controller.stop()

asyncio.run(test_ari())
```

## Troubleshooting

### Common Issues

#### 1. Port Conflicts
```powershell
# Check if ports are in use
netstat -an | findstr ":5060"
netstat -an | findstr ":8088"
netstat -an | findstr ":5038"
```

#### 2. Permission Issues (Docker)
```powershell
# Ensure Docker has proper permissions
# Run PowerShell as Administrator if needed
```

#### 3. Module Loading Failures
```bash
# Check Asterisk logs
docker logs pydialer-asterisk | grep ERROR
docker logs pydialer-asterisk | grep WARNING
```

#### 4. ARI Authentication Issues
```powershell
# Verify credentials
curl -u asterisk:asterisk -v http://localhost:8088/ari/asterisk/info
```

### Performance Tuning

#### System Limits
For production deployments, configure system limits:

```bash
# Add to /etc/security/limits.conf (Linux) or equivalent
asterisk soft nofile 65535
asterisk hard nofile 65535
asterisk soft nproc 4096
asterisk hard nproc 4096
```

#### Asterisk Performance
```ini
# In asterisk.conf [options]
maxcalls=1000
maxload=0.9

# In pjsip.conf [global]  
max_initial_qualify_time=4
contact_expiration_check_interval=30
```

## Security Considerations

### 1. Change Default Passwords
```ini
# In ari.conf and manager.conf
# Use strong passwords in production
password = your-secure-password-here
```

### 2. Firewall Configuration
```powershell
# Open required ports
netsh advfirewall firewall add rule name="Asterisk SIP" dir=in action=allow protocol=UDP localport=5060
netsh advfirewall firewall add rule name="Asterisk ARI" dir=in action=allow protocol=TCP localport=8088
netsh advfirewall firewall add rule name="Asterisk AMI" dir=in action=allow protocol=TCP localport=5038
netsh advfirewall firewall add rule name="Asterisk RTP" dir=in action=allow protocol=UDP localport=10000-10100
```

### 3. Network Security
- Use VPN for remote access
- Implement fail2ban for brute force protection
- Regular security updates
- Monitor authentication attempts

## Next Steps

After successful installation:

1. **Task #78**: Set up ARI (Asterisk REST Interface) integration
2. **Task #79**: Configure AMI (Asterisk Manager Interface) for events  
3. **Task #80**: Implement call origination and control via ARI
4. **Task #81**: Create telephony service abstraction layer
5. **Task #82**: Set up SIP trunking and PSTN connectivity

## References

- [Asterisk Documentation](https://docs.asterisk.org/)
- [ARI Documentation](https://docs.asterisk.org/Asterisk_18_Documentation/API_Documentation/Asterisk_REST_Interface/)
- [PyDialer Architecture Documentation](../plan.md)
- [Stasis Application Guide](https://wiki.asterisk.org/wiki/display/AST/Getting+Started+with+ARI)

---

**Note**: This installation creates the foundation for PyDialer's AI-powered call center system. The configuration files provided are optimized for integration with the existing ARI controller, WebRTC gateway, and AI Media Gateway components.
