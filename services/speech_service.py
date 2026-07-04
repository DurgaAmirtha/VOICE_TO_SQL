import os
from pathlib import Path
from typing import Optional, Dict, Any
from config import Config
from llm.gemini_client import GeminiClient
from utils.common import logger

class SpeechService:
    def __init__(self, gemini_client: GeminiClient):
        self.client = gemini_client

    def transcribe_audio_file(self, file_path: str | Path, api_key: Optional[str] = None) -> str:
        """Transcribes a physical audio file using Gemini's native transcription."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")
            
        logger.info(f"SpeechService: Transcribing file {file_path.name}")
        return self.client.transcribe_audio(str(file_path), api_key=api_key)

    def transcribe_mic_bytes(self, audio_bytes: bytes, audio_format: str = "wav", api_key: Optional[str] = None) -> str:
        """
        Takes raw recorded audio bytes (e.g., from browser microphone), 
        saves them to a temporary file in Config.UPLOADS_DIR, 
        and transcribes them.
        """
        # Formulate temporary file path
        # Normalize the format extension (e.g. audio/webm -> webm)
        extension = audio_format.split("/")[-1] if "/" in audio_format else audio_format
        if not extension or extension == "octet-stream":
            extension = "wav"
            
        temp_file_path = Config.UPLOADS_DIR / f"temp_recording.{extension}"
        
        logger.info(f"SpeechService: Saving mic audio bytes ({len(audio_bytes)} bytes) to {temp_file_path}")
        
        # Write bytes
        try:
            with open(temp_file_path, "wb") as f:
                f.write(audio_bytes)
        except Exception as io_err:
            logger.error(f"Failed to write mic audio file: {io_err}")
            raise io_err
            
        # Transcribe
        try:
            text = self.transcribe_audio_file(temp_file_path, api_key=api_key)
            return text
        finally:
            # Clean up temp file
            if temp_file_path.exists():
                try:
                    os.remove(temp_file_path)
                    logger.info("Temporary mic audio file removed.")
                except Exception as del_err:
                    logger.warning(f"Could not delete temporary mic file: {del_err}")
