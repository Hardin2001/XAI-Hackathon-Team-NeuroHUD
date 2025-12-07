#!/usr/bin/env python3
"""
TTS Client Class - Encapsulates XAI Text-to-Speech API calls
Reads API key during initialization
"""

import os
import requests
import tempfile
import asyncio
import base64
import json
from pathlib import Path
from typing import Optional, Callable

# Try importing websockets
try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    websockets = None

# Try importing pyaudio for streaming playback
try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False
    pyaudio = None


class TTSClient:
    """TTS Client class for calling XAI Text-to-Speech API"""
    
    def __init__(self, api_key_file: str = "neuroKEY.txt"):
        """
        Initialize TTS client
        
        Args:
            api_key_file: Path to API key file, default is "neuroKEY.txt"
        """
        self.api_key = self._read_api_key(api_key_file)
        self.base_url = "https://api.x.ai/v1"
        self.api_url = f"{self.base_url}/audio/speech"
    
    def _read_api_key(self, filename: str) -> str:
        """
        Read API key from file
        
        Args:
            filename: Path to API key file
            
        Returns:
            API key string
            
        Raises:
            FileNotFoundError: File does not exist
            ValueError: File is empty
        """
        try:
            key_path = Path(filename)
            if not key_path.exists():
                raise FileNotFoundError(f"API key file not found: {filename}")
            
            api_key = key_path.read_text(encoding="utf-8").strip()
            if not api_key:
                raise ValueError(f"API key file is empty: {filename}")
            
            return api_key
        except Exception as e:
            raise RuntimeError(f"Failed to read API key: {e}")
    
    def text_to_speech(
        self,
        text: str,
        voice: str = "Ara",
        response_format: str = "mp3"
    ) -> bytes:
        """
        Convert text to speech
        
        Args:
            text: Text to convert
            voice: Voice type, options: "Ara", "Rex", "Sal", "Eve", "Una", "Leo", default "Ara"
            response_format: Audio format, options: "mp3", "wav", "opus", "flac", "pcm", default "mp3"
            
        Returns:
            Audio data as bytes
            
        Raises:
            requests.exceptions.RequestException: Request failed
        """
        if not text or not text.strip():
            raise ValueError("Text content cannot be empty")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        data = {
            "input": text,
            "voice": voice,
            "response_format": response_format,
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            
            return response.content
        except requests.exceptions.RequestException as e:
            error_msg = f"TTS request failed: {e}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg += f"\nDetails: {error_detail}"
                except:
                    error_msg += f"\nResponse: {e.response.text}"
            raise RuntimeError(error_msg)
    
    def text_to_speech_file(
        self,
        text: str,
        output_file: Optional[str] = None,
        voice: str = "Ara",
        response_format: str = "mp3"
    ) -> str:
        """
        Convert text to speech and save to file
        
        Args:
            text: Text to convert
            output_file: Output file path, if None uses temporary file
            voice: Voice type, default "Ara"
            response_format: Audio format, default "mp3"
            
        Returns:
            Path to saved audio file
        """
        audio_data = self.text_to_speech(text, voice, response_format)
        
        if output_file is None:
            # Use temporary file
            suffix = f".{response_format}"
            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
                prefix="tts_"
            )
            output_path = temp_file.name
            temp_file.close()
        else:
            output_path = output_file
        
        # Save audio data
        with open(output_path, "wb") as f:
            f.write(audio_data)
        
        return output_path
    
    async def streaming_text_to_speech(
        self,
        text: str,
        voice: str = "ara",
        sample_rate: int = 24000,
        channels: int = 1,
        sample_width: int = 2,
        on_audio_chunk: Optional[Callable[[bytes], None]] = None,
        play_audio: bool = True
    ) -> bytes:
        """
        Streaming text-to-speech (using WebSocket)
        
        Args:
            text: Text to convert
            voice: Voice ID, options: "ara", "rex", "sal", "eve", "una", "leo", default "ara"
            sample_rate: Sample rate, default 24000
            channels: Number of channels, default 1 (mono)
            sample_width: Sample width in bytes, default 2 (16-bit)
            on_audio_chunk: Audio chunk callback function, receives bytes parameter
            play_audio: Whether to play audio in real-time, default True
            
        Returns:
            Complete audio data (bytes)
            
        Raises:
            RuntimeError: WebSocket connection failed or other error
        """
        if not HAS_WEBSOCKETS:
            raise RuntimeError("websockets library not installed, please run: pip install websockets")
        
        if not text or not text.strip():
            raise ValueError("Text content cannot be empty")
        
        # Build WebSocket URL
        ws_url = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        uri = f"{ws_url}/realtime/audio/speech"
        
        # Set headers
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        # Initialize audio playback
        audio_stream = None
        p = None
        if play_audio:
            if not HAS_PYAUDIO or pyaudio is None:
                play_audio = False
            else:
                p = pyaudio.PyAudio()  # type: ignore
                audio_stream = p.open(
                    format=pyaudio.paInt16 if sample_width == 2 else pyaudio.paInt32,  # type: ignore
                    channels=channels,
                    rate=sample_rate,
                    output=True,
                )
        
        if not HAS_WEBSOCKETS or websockets is None:
            raise RuntimeError("websockets library not installed, please run: pip install websockets")
        
        audio_bytes = b""
        chunk_count = 0
        first_chunk_time = None
        import time
        start_time = time.time()
        
        print(f"\n{'='*60}")
        print(f"Starting Streaming TTS")
        print(f"{'='*60}")
        print(f"Text: {text[:50]}{'...' if len(text) > 50 else ''}")
        print(f"Voice: {voice}")
        print(f"Play Audio: {'Yes' if play_audio else 'No'}")
        print(f"WebSocket URL: {uri}")
        
        try:
            print(f"\nConnecting to WebSocket...")
            async with websockets.connect(uri, additional_headers=headers) as websocket:  # type: ignore
                print(f"WebSocket connected successfully")
                
                # Send config message
                config_message = {"type": "config", "data": {"voice_id": voice}}
                await websocket.send(json.dumps(config_message))
                print(f"Sent config message: {config_message}")
                
                # Send text chunk
                text_message = {
                    "type": "text_chunk",
                    "data": {"text": text, "is_last": True},
                }
                await websocket.send(json.dumps(text_message))
                request_sent_time = time.time()
                print(f"Sent text chunk ({len(text)} characters)")
                print(f"Waiting for audio response...\n")
                
                # Receive audio chunks
                while True:
                    try:
                        response = await websocket.recv()
                        data = json.loads(response)
                        
                        # Extract audio data
                        audio_b64 = data["data"]["data"]["audio"]
                        is_last = data["data"]["data"].get("is_last", False)
                        
                        # Decode audio
                        chunk_bytes = base64.b64decode(audio_b64)
                        audio_bytes += chunk_bytes
                        chunk_count += 1
                        
                        # Record time of first audio chunk
                        if first_chunk_time is None and len(chunk_bytes) > 0:
                            first_chunk_time = time.time()
                            time_to_first_audio = (first_chunk_time - request_sent_time) * 1000
                            print(f"First audio chunk received: {time_to_first_audio:.0f}ms")
                        
                        # Print each audio chunk info
                        if len(chunk_bytes) > 0:
                            print(f"Audio chunk #{chunk_count}: {len(chunk_bytes)} bytes", end="")
                            if is_last:
                                print(" (last chunk)")
                            else:
                                print()
                        
                        # Call callback function
                        if on_audio_chunk and len(chunk_bytes) > 0:
                            on_audio_chunk(chunk_bytes)
                        
                        # Play audio in real-time
                        if play_audio and audio_stream and len(chunk_bytes) > 0:
                            await asyncio.to_thread(audio_stream.write, chunk_bytes)
                        
                        if is_last:
                            break
                            
                    except websockets.exceptions.ConnectionClosedOK:  # type: ignore
                        print(f"WebSocket connection closed normally")
                        break
                    except websockets.exceptions.ConnectionClosedError as e:  # type: ignore
                        print(f"WebSocket connection error: {e}")
                        raise RuntimeError(f"WebSocket connection error: {e}")
                        
        finally:
            # Clean up audio playback
            if audio_stream:
                audio_stream.stop_stream()
                audio_stream.close()
            if p:
                p.terminate()
        
        # Calculate and display statistics
        total_time = time.time() - start_time
        audio_duration = len(audio_bytes) / (sample_rate * channels * sample_width)
        
        print(f"\n{'='*60}")
        print(f"Streaming TTS Complete")
        print(f"{'='*60}")
        print(f"Statistics:")
        print(f"   - Audio chunks: {chunk_count}")
        print(f"   - Total bytes: {len(audio_bytes):,} bytes")
        print(f"   - Audio duration: {audio_duration:.2f} seconds")
        print(f"   - Total time: {total_time:.2f} seconds")
        if first_chunk_time:
            time_to_first = (first_chunk_time - request_sent_time) * 1000
            print(f"   - First chunk latency: {time_to_first:.0f}ms")
        if audio_duration > 0:
            streaming_ratio = (total_time / audio_duration) * 100
            print(f"   - Streaming efficiency: {streaming_ratio:.1f}%")
            if streaming_ratio < 100:
                print(f"   - Audio generation speed > playback speed (streaming advantage!)")
        print(f"{'='*60}\n")
        
        return audio_bytes

