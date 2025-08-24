"""
Django management command for ARI Controller service management.

This command provides lifecycle management for the Asterisk REST Interface controller,
allowing it to be started, stopped, monitored, and configured as part of the Django application.

Usage:
    python manage.py ari_controller start
    python manage.py ari_controller stop
    python manage.py ari_controller status
    python manage.py ari_controller restart
    python manage.py ari_controller test
"""

import asyncio
import signal
import sys
import time
import logging
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from telephony.ari_controller import ARIController

logger = logging.getLogger('vicidial.telephony')


class Command(BaseCommand):
    help = 'Manage the ARI Controller service for Asterisk integration'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.controller: Optional[ARIController] = None
        self.running = False
        self.shutdown_requested = False
        
    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            'action',
            choices=['start', 'stop', 'status', 'restart', 'test'],
            help='Action to perform with the ARI Controller'
        )
        
        parser.add_argument(
            '--ari-url',
            default=getattr(settings, 'ASTERISK_ARI_URL', 'http://localhost:8088'),
            help='Asterisk ARI URL (default: http://localhost:8088)'
        )
        
        parser.add_argument(
            '--username',
            default=getattr(settings, 'ASTERISK_ARI_USERNAME', 'asterisk'),
            help='ARI username (default: asterisk)'
        )
        
        parser.add_argument(
            '--password',
            default=getattr(settings, 'ASTERISK_ARI_PASSWORD', 'asterisk'),
            help='ARI password (default: asterisk)'
        )
        
        parser.add_argument(
            '--app-name',
            default=getattr(settings, 'ASTERISK_STASIS_APP', 'pydialer'),
            help='Stasis application name (default: pydialer)'
        )
        
        parser.add_argument(
            '--daemon',
            action='store_true',
            help='Run as daemon (background process)'
        )
        
        parser.add_argument(
            '--pid-file',
            default='/tmp/ari_controller.pid',
            help='PID file location for daemon mode'
        )
    
    def handle(self, *args, **options):
        """Handle the management command."""
        action = options['action']
        
        try:
            if action == 'start':
                self.start_controller(options)
            elif action == 'stop':
                self.stop_controller(options)
            elif action == 'status':
                self.show_status(options)
            elif action == 'restart':
                self.restart_controller(options)
            elif action == 'test':
                self.test_connection(options)
        except Exception as e:
            raise CommandError(f'Error executing {action}: {e}')
    
    def start_controller(self, options):
        """Start the ARI Controller service."""
        self.stdout.write('Starting ARI Controller...')
        
        # Initialize controller with settings
        self.controller = ARIController(
            ari_url=options['ari_url'],
            username=options['username'],
            password=options['password'],
            app_name=options['app_name']
        )
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        if options['daemon']:
            self._run_as_daemon(options)
        else:
            self._run_foreground()
    
    def stop_controller(self, options):
        """Stop the ARI Controller service."""
        pid_file = options['pid_file']
        
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            import os
            try:
                os.kill(pid, signal.SIGTERM)
                self.stdout.write(f'Sent SIGTERM to process {pid}')
                
                # Wait for process to stop
                for _ in range(30):  # Wait up to 30 seconds
                    try:
                        os.kill(pid, 0)  # Check if process exists
                        time.sleep(1)
                    except ProcessLookupError:
                        # Process has stopped
                        os.remove(pid_file)
                        self.stdout.write(
                            self.style.SUCCESS('ARI Controller stopped successfully')
                        )
                        return
                
                # Force kill if still running
                os.kill(pid, signal.SIGKILL)
                os.remove(pid_file)
                self.stdout.write(
                    self.style.WARNING('ARI Controller force killed')
                )
                
            except ProcessLookupError:
                os.remove(pid_file)
                self.stdout.write('ARI Controller was not running')
                
        except FileNotFoundError:
            self.stdout.write('ARI Controller is not running (no PID file)')
    
    def show_status(self, options):
        """Show ARI Controller service status."""
        pid_file = options['pid_file']
        
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            import os
            try:
                os.kill(pid, 0)  # Check if process exists
                self.stdout.write(
                    self.style.SUCCESS(f'ARI Controller is running (PID: {pid})')
                )
                
                # Try to get additional status information
                asyncio.run(self._check_connection_status(options))
                
            except ProcessLookupError:
                os.remove(pid_file)
                self.stdout.write(
                    self.style.ERROR('ARI Controller is not running (stale PID file removed)')
                )
                
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR('ARI Controller is not running')
            )
    
    def restart_controller(self, options):
        """Restart the ARI Controller service."""
        self.stdout.write('Restarting ARI Controller...')
        self.stop_controller(options)
        time.sleep(2)  # Brief pause
        self.start_controller(options)
    
    def test_connection(self, options):
        """Test connection to Asterisk ARI."""
        self.stdout.write('Testing ARI connection...')
        
        asyncio.run(self._test_connection(options))
    
    async def _test_connection(self, options):
        """Test ARI connection asynchronously."""
        controller = ARIController(
            ari_url=options['ari_url'],
            username=options['username'],
            password=options['password'],
            app_name=options['app_name']
        )
        
        try:
            await controller.start()
            self.stdout.write(
                self.style.SUCCESS('ARI connection test successful')
            )
            
            # Test basic functionality
            if controller.connected:
                self.stdout.write('✓ WebSocket connection established')
            else:
                self.stdout.write(
                    self.style.WARNING('✗ WebSocket connection failed')
                )
            
            await asyncio.sleep(2)  # Brief test period
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'ARI connection test failed: {e}')
            )
        finally:
            await controller.stop()
    
    async def _check_connection_status(self, options):
        """Check detailed connection status."""
        controller = ARIController(
            ari_url=options['ari_url'],
            username=options['username'],
            password=options['password'],
            app_name=options['app_name']
        )
        
        try:
            # Quick connection test without starting full service
            timeout = 5
            import aiohttp
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout),
                auth=aiohttp.BasicAuth(options['username'], options['password'])
            ) as session:
                async with session.get(f"{options['ari_url']}/ari/asterisk/info") as response:
                    if response.status == 200:
                        info = await response.json()
                        self.stdout.write(f"✓ Connected to Asterisk {info.get('version', 'unknown')}")
                    else:
                        self.stdout.write(f"✗ HTTP connection failed: {response.status}")
                        
        except Exception as e:
            self.stdout.write(f"✗ Connection check failed: {e}")
    
    def _run_foreground(self):
        """Run ARI controller in foreground mode."""
        try:
            asyncio.run(self._run_controller())
        except KeyboardInterrupt:
            self.stdout.write('\nShutdown requested by user')
        except Exception as e:
            raise CommandError(f'ARI Controller error: {e}')
    
    def _run_as_daemon(self, options):
        """Run ARI controller as daemon process."""
        import os
        pid_file = options['pid_file']
        
        # Check if already running
        if os.path.exists(pid_file):
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)
                raise CommandError(f'ARI Controller is already running (PID: {pid})')
            except ProcessLookupError:
                os.remove(pid_file)
        
        # Fork process
        try:
            pid = os.fork()
            if pid > 0:
                # Parent process
                with open(pid_file, 'w') as f:
                    f.write(str(pid))
                self.stdout.write(
                    self.style.SUCCESS(f'ARI Controller started as daemon (PID: {pid})')
                )
                return
        except OSError as e:
            raise CommandError(f'Fork failed: {e}')
        
        # Child process (daemon)
        os.setsid()
        
        # Redirect standard file descriptors
        sys.stdin.close()
        sys.stdout.close()
        sys.stderr.close()
        
        try:
            asyncio.run(self._run_controller())
        except Exception as e:
            logger.error(f'ARI Controller daemon error: {e}')
        finally:
            try:
                os.remove(pid_file)
            except FileNotFoundError:
                pass
    
    async def _run_controller(self):
        """Run the ARI controller service."""
        logger.info('Starting ARI Controller service')
        
        try:
            await self.controller.start()
            self.running = True
            
            self.stdout.write(
                self.style.SUCCESS('ARI Controller started successfully')
            )
            
            # Main service loop
            while self.running and not self.shutdown_requested:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f'ARI Controller error: {e}')
            raise
        finally:
            if self.controller:
                logger.info('Stopping ARI Controller service')
                await self.controller.stop()
                logger.info('ARI Controller service stopped')
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        signal_names = {signal.SIGINT: 'SIGINT', signal.SIGTERM: 'SIGTERM'}
        signal_name = signal_names.get(signum, f'Signal {signum}')
        
        self.stdout.write(f'\nReceived {signal_name}, shutting down gracefully...')
        self.shutdown_requested = True
        self.running = False
