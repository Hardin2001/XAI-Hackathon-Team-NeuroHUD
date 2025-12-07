#!/usr/bin/env python3
"""
Voice to Text and AI Interface - GUI Version
Integrates recording, transcription, and AI conversation features
"""

import pyaudio
import wave
import io
import threading
import time
import asyncio
import tkinter as tk
from tkinter import scrolledtext, ttk
from typing import Optional
from pathlib import Path
import requests
import tempfile
import os
import platform
from ai_client import AIClient
from tts_client import TTSClient
from PIL import Image, ImageDraw, ImageFont, ImageTk

HAS_PYGAME = False
HAS_PLAYSOUND = False
pygame = None
playsound = None

try:
    import pygame
    pygame.mixer.init()
    HAS_PYGAME = True
except ImportError:
    pass

if not HAS_PYGAME:
    try:
        from playsound import playsound
        HAS_PLAYSOUND = True
    except ImportError:
        pass


class VoiceToAIGUI:
    """GUI application for voice to text and AI interface"""
    
    def __init__(self, 
                 api_key_file: str = "neuroKEY.txt",
                 stt_api_key_file: Optional[str] = None,
                 sample_rate: int = 24000, 
                 channels: int = 1, 
                 chunk: int = 1024, 
                 min_duration: float = 0.5):
        """
        Initialize GUI application
        
        Args:
            api_key_file: Path to API key file for AI interface
            stt_api_key_file: Path to API key file for speech-to-text, if None uses api_key_file
            sample_rate: Sample rate, default 24000
            channels: Number of channels, default 1 (mono)
            chunk: Audio chunk size, default 1024
            min_duration: Minimum recording duration (seconds), default 0.5
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk = chunk
        self.format = pyaudio.paInt16
        self.frames = []
        self.is_recording = False
        self.audio = None
        self.stream = None
        self.min_duration = min_duration
        self.recording_thread = None
        self.recording_start_time = None
        
        # Add interrupt flag and processing thread reference
        self.is_processing = False
        self.interrupt_processing = False
        self.current_process_thread = None
        
        self.ai_client = AIClient(api_key_file)

        self.tts_client = TTSClient(api_key_file)
        self.tts_voice = "ara" 
        self.use_streaming_tts = True  

        if stt_api_key_file is None:
            stt_api_key_file = api_key_file
        self.stt_api_key = self._read_api_key(stt_api_key_file)
        self.stt_base_url = "https://api.x.ai/v1"
        self.stt_api_url = f"{self.stt_base_url}/audio/transcriptions"
        
        # Create GUI
        self.root = tk.Tk()
        self.root.title("Voice AI")
        self.root.geometry("100x100")
        self.root.resizable(False, False)
        
        # Remove window border
        self.root.overrideredirect(True)
        
        # Set transparent background
        self.root.attributes('-alpha', 1.0)
        if platform.system() == 'Windows':
            self.root.attributes('-transparentcolor', 'black')
        self.root.configure(bg='black')
        
        # Keep window always on top
        self.root.attributes('-topmost', True)
        
        # Bind ESC to close
        self.root.bind('<Escape>', lambda e: self.root.destroy())
        
        # Ensure window can receive keyboard events
        self.root.focus_force()
        
        self.setup_ui()
        
        # Make window draggable from anywhere
        self.root.bind('<Button-1>', self.start_move)
        self.root.bind('<B1-Motion>', self.do_move)
        
    def _read_api_key(self, filename: str) -> str:
        """Read API key from file"""
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
    
    def setup_ui(self):
        """Setup UI interface"""
        # Main container with transparent background (black will be transparent)
        main_frame = tk.Frame(self.root, bg='black')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        # Record button with gradient blue (circular icon only) - centered
        self.record_button = tk.Button(
            main_frame,
            text="●",
            font=("Arial", 48, "bold"),
            bg="black",
            fg="#1E88E5",  # Blue circle
            activebackground="black",
            activeforeground="#64B5F6",  # Light blue circle when pressed
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            highlightthickness=0
        )
        self.record_button.place(relx=0.5, rely=0.5, anchor="center")  # Centered
        
        # Bind mouse events
        self.record_button.bind("<Button-1>", self.on_button_press)
        self.record_button.bind("<ButtonRelease-1>", self.on_button_release)
        
        # Bind keyboard events (spacebar)
        self.root.bind("<KeyPress-space>", self.on_space_press)
        self.root.bind("<KeyRelease-space>", self.on_space_release)
    
    def start_move(self, event):
        """Start dragging window"""
        self.root.x = event.x
        self.root.y = event.y
    
    def do_move(self, event):
        """Dragging window"""
        x = self.root.winfo_x() + (event.x - self.root.x)
        y = self.root.winfo_y() + (event.y - self.root.y)
        self.root.geometry(f"+{x}+{y}")
    
    def add_char_to_display(self, char: str):
        """Add character to scrolling display (max 25 characters) with mirror and rotation"""
        self.char_queue.append(char)
        if len(self.char_queue) > self.max_chars:
            self.char_queue.pop(0)  # Remove first character
        
        # Create mirrored and rotated text image
        display_text = "".join(self.char_queue)
        if display_text:
            self.update_rotated_text(display_text)
        else:
            self.word_display.config(image='')
    
    def update_rotated_text(self, text: str):
        """Create and display 180-degree rotated text image"""
        # Create image with text
        font_size = 24
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        # Calculate text size
        dummy_img = Image.new('RGB', (1, 1))
        draw = ImageDraw.Draw(dummy_img)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Create image
        img_width = max(text_width + 20, 500)
        img_height = text_height + 10
        img = Image.new('RGB', (img_width, img_height), color='black')
        draw = ImageDraw.Draw(img)
        
        # Draw white text
        draw.text((10, 5), text, font=font, fill='white')
        
        # Rotate 180 degrees (upside down and horizontally flipped)
        img = img.rotate(180)
        
        # Convert to PhotoImage
        photo = ImageTk.PhotoImage(img)
        
        # Keep reference to prevent garbage collection
        self.word_display.image = photo
        self.word_display.config(image=photo)
    
    def clear_char_display(self):
        """Clear character display"""
        self.char_queue = []
        self.word_display.config(text="")
    
    def update_duration(self):
        """Update recording duration display"""
        if self.is_recording and self.recording_start_time:
            elapsed = time.time() - self.recording_start_time
            if self.is_recording:
                self.root.after(100, self.update_duration)
    
    def on_button_press(self, event):
        """Button press event"""
        if not self.is_recording:
            self.start_recording()
    
    def on_button_release(self, event):
        """Button release event"""
        if self.is_recording:
            self.stop_recording_and_process()
    
    def on_space_press(self, event):
        """Spacebar press event"""
        if not self.is_recording:
            self.start_recording()
            return "break"
    
    def on_space_release(self, event):
        """Spacebar release event"""
        if self.is_recording:
            self.stop_recording_and_process()
            return "break"
    
    def start_recording(self):
        """Start recording"""
        if self.is_recording:
            return
        
        # Interrupt any ongoing processing
        if self.is_processing:
            self.interrupt_processing = True
            self.clear_char_display()
        
        self.is_recording = True
        self.frames = []
        self.recording_start_time = time.time()
        
        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk
        )
        
        # Update UI
        self.record_button.config(fg="#0D47A1", text="◉")  # Dark blue circle when recording
        self.update_duration()
        
        # Start recording thread
        self.recording_thread = threading.Thread(target=self.record_loop, daemon=True)
        self.recording_thread.start()
    
    def stop_recording_and_process(self):
        """Stop recording and process"""
        if not self.is_recording:
            return
        
        self.is_recording = False
        
        # Wait for recording thread to finish
        if self.recording_thread and self.recording_thread.is_alive():
            self.recording_thread.join(timeout=1.0)
        
        # Stop stream
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                print(f"Error stopping stream: {e}")
            finally:
                self.stream = None
        
        # Calculate recording duration
        duration = len(self.frames) * self.chunk / self.sample_rate
        
        # Update UI (keep button enabled)
        self.record_button.config(fg="#42A5F5", text="○")  # Light blue circle when processing
        
        if duration < self.min_duration:
            self.record_button.config(fg="#1E88E5", text="●")  # Back to blue
            if self.audio:
                self.audio.terminate()
                self.audio = None
            return
        
        # Convert to WAV format
        wav_buffer = io.BytesIO()
        if self.audio:
            with wave.open(wav_buffer, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.audio.get_sample_size(self.format))
                wf.setframerate(self.sample_rate)
                wf.writeframes(b''.join(self.frames))
            
            self.audio.terminate()
            self.audio = None
        
        audio_data = wav_buffer.getvalue()
        
        # Set processing flag
        self.is_processing = True
        self.interrupt_processing = False
        
        # Process audio in new thread
        def process_in_thread():
            try:
                self.process_audio(audio_data)
            except Exception as e:
                if not self.interrupt_processing:
                    error_msg = str(e)
                    self.root.after(0, lambda msg=error_msg: self.show_error(f"Error processing audio: {msg}"))
                    import traceback
                    traceback.print_exc()
            finally:
                self.is_processing = False
        
        self.current_process_thread = threading.Thread(target=process_in_thread, daemon=True)
        self.current_process_thread.start()
    
    def record_loop(self):
        """Recording loop (runs in separate thread)"""
        while self.is_recording:
            if self.stream:
                try:
                    data = self.stream.read(self.chunk, exception_on_overflow=False)
                    self.frames.append(data)
                except Exception as e:
                    error_msg = str(e)
                    self.root.after(0, lambda msg=error_msg: self.show_error(f"Recording error: {msg}"))
                    break
            else:
                break
    
    def transcribe_audio(self, audio_data: bytes) -> str:
        """
        Transcribe audio using XAI API
        
        Args:
            audio_data: WAV format audio data (bytes)
            
        Returns:
            Transcribed text
        """
        headers = {
            "Authorization": f"Bearer {self.stt_api_key}",
        }
        
        # Create temporary file object
        audio_file = io.BytesIO(audio_data)
        audio_file.name = "recording.wav"
        
        files = {
            "file": (audio_file.name, audio_file, "audio/wav")
        }
        
        try:
            response = requests.post(
                self.stt_api_url, 
                headers=headers, 
                files=files,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            text = result.get('text', '')
            return text
        except requests.exceptions.RequestException as e:
            error_msg = f"Transcription failed: {e}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg += f"\nDetails: {error_detail}"
                except:
                    error_msg += f"\nResponse: {e.response.text}"
            raise RuntimeError(error_msg)
    
    def process_audio(self, audio_data: bytes):
        """Process audio: transcribe -> call AI"""
        # Step 1: Transcribe
        try:
            if self.interrupt_processing:
                return
            
            print(f"[DEBUG] Starting transcription, audio size: {len(audio_data)} bytes")
            transcript = self.transcribe_audio(audio_data)
            print(f"[DEBUG] Transcription result: {transcript}")
            
            if not transcript or self.interrupt_processing:
                if not self.interrupt_processing:
                    self.root.after(0, lambda: self.show_error("Transcription result is empty"))
                return
            
        except Exception as e:
            print(f"[ERROR] Transcription failed: {e}")
            import traceback
            traceback.print_exc()
            self.root.after(0, lambda msg=str(e): self.show_error(f"Transcription failed: {msg}"))
            return
        
        # Step 2: Call AI
        try:
            if self.interrupt_processing:
                return
            
            print(f"[DEBUG] Calling AI with transcript: {transcript}")
            response = self.ai_client.chat(transcript)
            ai_text = self.ai_client.get_response_text(response)
            print(f"[DEBUG] AI response: {ai_text}")
            
            if not ai_text or self.interrupt_processing:
                if not self.interrupt_processing:
                    self.root.after(0, lambda: self.show_error("AI response is empty"))
                return
            
            # Step 3: Convert to speech and play (with interrupt check)
            if not self.interrupt_processing:
                try:
                    self.convert_and_play_tts(ai_text)
                except Exception as e:
                    pass  # Ignore TTS errors
            
            self.root.after(0, self.on_processing_complete)
            
        except Exception as e:
            print(f"[ERROR] AI call failed: {e}")
            import traceback
            traceback.print_exc()
            self.root.after(0, lambda msg=str(e): self.show_error(f"AI call failed: {msg}"))
    
    def on_processing_complete(self):
        """Processing complete callback"""
        if not self.interrupt_processing:
            self.record_button.config(fg="#1E88E5", text="●")  # Blue circle
    
    def convert_and_play_tts(self, text: str):
        """
        Convert text to speech and play (using streaming TTS)
        
        Args:
            text: Text to convert
        """
        # Process streaming TTS in new thread to avoid blocking UI
        def tts_in_thread():
            try:
                # Create new event loop (because we're in a thread)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Define audio chunk callback
                def on_audio_chunk(chunk: bytes):
                    # Can process each audio chunk here if needed
                    pass
                
                # Use streaming TTS (auto-play)
                try:
                    loop.run_until_complete(
                        self.tts_client.streaming_text_to_speech(
                            text=text,
                            voice=self.tts_voice,
                            on_audio_chunk=on_audio_chunk,
                            play_audio=True
                        )
                    )
                finally:
                    loop.close()
                    
            except Exception as e:
                # If streaming TTS fails, try non-streaming TTS as fallback
                try:
                    audio_data = self.tts_client.text_to_speech(text, voice=self.tts_voice.capitalize(), response_format="mp3")
                    
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", prefix="tts_")
                    temp_path = temp_file.name
                    temp_file.write(audio_data)
                    temp_file.close()
                    
                    self.play_audio(temp_path)
                    
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                except Exception as e2:
                    pass  # Ignore all TTS errors
        
        thread = threading.Thread(target=tts_in_thread, daemon=True)
        thread.start()
    
    def play_audio(self, audio_file: str):
        """
        Play audio file
        
        Args:
            audio_file: Path to audio file
        """
        if HAS_PYGAME and pygame is not None:
            try:
                pygame.mixer.music.load(audio_file)  # type: ignore
                pygame.mixer.music.play()  # type: ignore
                # Wait for playback to complete
                while pygame.mixer.music.get_busy():  # type: ignore
                    time.sleep(0.1)
            except Exception as e:
                raise RuntimeError(f"pygame playback failed: {e}")
        elif HAS_PLAYSOUND and playsound is not None:
            try:
                playsound(audio_file, block=True)  # type: ignore
            except Exception as e:
                raise RuntimeError(f"playsound playback failed: {e}")
        else:
            raise RuntimeError("Audio playback library not installed, please install pygame or playsound: pip install pygame or pip install playsound")
    
    def show_error(self, error_msg: str):
        """Show error message"""
        if not self.interrupt_processing:
            self.record_button.config(fg="#1E88E5", text="●")  # Blue circle
    
    def run(self):
        """Run GUI"""
        self.root.mainloop()


if __name__ == "__main__":
    # Create and run GUI application
    app = VoiceToAIGUI()
    app.run()


