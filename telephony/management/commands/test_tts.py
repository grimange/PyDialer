"""
Django management command to test TTS (Text-to-Speech) integration.
Usage: python manage.py test_tts --text "Hello world" --voice alloy
"""

import asyncio
import os
import tempfile
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from telephony.tts_integration import TTSService, TTSConfig, TTSError


class Command(BaseCommand):
    help = 'Test OpenAI TTS integration'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--text',
            type=str,
            default="Hello, this is a test of the PyDialer TTS integration system.",
            help='Text to synthesize (default: test message)'
        )
        
        parser.add_argument(
            '--voice',
            type=str,
            choices=['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'],
            default='alloy',
            help='Voice to use for synthesis'
        )
        
        parser.add_argument(
            '--model',
            type=str,
            choices=['tts-1', 'tts-1-hd'],
            default='tts-1',
            help='TTS model to use'
        )
        
        parser.add_argument(
            '--speed',
            type=float,
            default=1.0,
            help='Speech speed (0.25 to 4.0)'
        )
        
        parser.add_argument(
            '--format',
            type=str,
            choices=['mp3', 'opus', 'aac', 'flac', 'wav', 'pcm'],
            default='wav',
            help='Audio format'
        )
        
        parser.add_argument(
            '--output',
            type=str,
            help='Output file path (optional)'
        )
        
        parser.add_argument(
            '--no-api-key-check',
            action='store_true',
            help='Skip OpenAI API key validation'
        )
    
    def handle(self, *args, **options):
        """Handle the command execution."""
        try:
            # Run the async test function
            asyncio.run(self.test_tts(**options))
        except Exception as e:
            raise CommandError(f'TTS test failed: {e}')
    
    async def test_tts(self, **options):
        """Test TTS functionality asynchronously."""
        text = options['text']
        voice = options['voice']
        model = options['model']
        speed = options['speed']
        format = options['format']
        output_path = options.get('output')
        skip_api_check = options.get('no_api_key_check', False)
        
        self.stdout.write('=' * 60)
        self.stdout.write(self.style.SUCCESS('PyDialer TTS Integration Test'))
        self.stdout.write('=' * 60)
        
        # Check configuration
        self.stdout.write('\n1. Checking configuration...')
        
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key and not skip_api_check:
            self.stdout.write(
                self.style.ERROR('❌ OPENAI_API_KEY not found in Django settings')
            )
            self.stdout.write('   Add OPENAI_API_KEY to your settings or .env file')
            return
        elif skip_api_check:
            self.stdout.write(
                self.style.WARNING('⚠️  Skipping API key validation (--no-api-key-check)')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'✅ OpenAI API key configured (length: {len(api_key)})')
            )
        
        # Display test parameters
        self.stdout.write('\n2. Test parameters:')
        self.stdout.write(f'   Text: "{text}"')
        self.stdout.write(f'   Voice: {voice}')
        self.stdout.write(f'   Model: {model}')
        self.stdout.write(f'   Speed: {speed}')
        self.stdout.write(f'   Format: {format}')
        self.stdout.write(f'   Text length: {len(text)} characters')
        
        if skip_api_check:
            self.stdout.write(
                self.style.WARNING('\n⚠️  API key check skipped - will not make actual API calls')
            )
            return
        
        # Initialize TTS service
        self.stdout.write('\n3. Initializing TTS service...')
        
        try:
            tts_service = TTSService()
            await tts_service.start()
            
            self.stdout.write(
                self.style.SUCCESS('✅ TTS service initialized successfully')
            )
            
            # Display service information
            self.stdout.write(f'   Available voices: {", ".join(tts_service.get_available_voices())}')
            self.stdout.write(f'   Available models: {", ".join(tts_service.get_available_models())}')
            self.stdout.write(f'   Supported formats: {", ".join(tts_service.get_supported_formats())}')
            
        except TTSError as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Failed to initialize TTS service: {e}')
            )
            return
        
        # Test speech synthesis
        self.stdout.write('\n4. Testing speech synthesis...')
        
        try:
            result = await tts_service.synthesize_speech(
                text=text,
                voice=voice,
                model=model,
                speed=speed,
                response_format=format
            )
            
            self.stdout.write(
                self.style.SUCCESS('✅ Speech synthesis completed successfully')
            )
            
            # Display result information
            self.stdout.write(f'   Processing time: {result.processing_time:.2f} seconds')
            self.stdout.write(f'   Audio format: {result.format}')
            self.stdout.write(f'   Sample rate: {result.sample_rate} Hz')
            self.stdout.write(f'   Audio data size: {len(result.audio_data)} bytes')
            
            if result.duration:
                self.stdout.write(f'   Audio duration: {result.duration:.2f} seconds')
            
        except TTSError as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Speech synthesis failed: {e}')
            )
            await tts_service.stop()
            return
        
        # Save audio file
        self.stdout.write('\n5. Saving audio file...')
        
        if not output_path:
            # Create temporary file
            with tempfile.NamedTemporaryFile(
                suffix=f'.{format}', 
                delete=False,
                prefix='tts_test_'
            ) as tmp_file:
                output_path = tmp_file.name
        
        try:
            with open(output_path, 'wb') as f:
                f.write(result.audio_data)
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Audio saved to: {output_path}')
            )
            
            # Display file information
            file_size = os.path.getsize(output_path)
            self.stdout.write(f'   File size: {file_size} bytes')
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Failed to save audio file: {e}')
            )
        
        # Test rate limiter
        self.stdout.write('\n6. Testing rate limiter...')
        
        try:
            rate_limiter = tts_service.rate_limiter
            can_process = await rate_limiter.acquire(len(text))
            
            if can_process:
                self.stdout.write(
                    self.style.SUCCESS('✅ Rate limiter working correctly')
                )
                self.stdout.write(f'   Minute tokens remaining: {rate_limiter.minute_tokens}')
                self.stdout.write(f'   Hour tokens remaining: {rate_limiter.hour_tokens}')
                self.stdout.write(f'   Characters used this hour: {rate_limiter.characters_used}')
            else:
                self.stdout.write(
                    self.style.WARNING('⚠️  Rate limit exceeded')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Rate limiter test failed: {e}')
            )
        
        # Clean up
        self.stdout.write('\n7. Cleaning up...')
        
        try:
            await tts_service.stop()
            self.stdout.write(
                self.style.SUCCESS('✅ TTS service stopped successfully')
            )
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Error stopping TTS service: {e}')
            )
        
        # Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('🎉 TTS Integration Test Completed'))
        self.stdout.write('=' * 60)
        
        if output_path and os.path.exists(output_path):
            self.stdout.write(f'\n📁 Generated audio file: {output_path}')
            self.stdout.write('   You can play this file to verify audio quality')
        
        self.stdout.write('\n✨ TTS integration is working correctly!')
        self.stdout.write('   The service is ready for use in the PyDialer system.')
