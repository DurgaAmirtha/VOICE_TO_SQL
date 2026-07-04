from google import genai
from google.genai import types
from typing import Optional, Dict, Any
from pathlib import Path
from config import Config
from utils.common import logger

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None):
        """Initializes the Gemini client key."""
        self.api_key = api_key or Config.GEMINI_API_KEY
        if Config.GROQ_API_KEY:
            logger.info("LLM Client initialized with Groq support.")
        elif self.api_key:
            logger.info("LLM Client initialized with Gemini support.")
        else:
            logger.warning("LLM Client initialized without API Keys. Configure GEMINI_API_KEY or GROQ_API_KEY.")

    def generate_text(
        self, 
        prompt: str, 
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.1,
        api_key: Optional[str] = None
    ) -> str:
        """
        Queries the configured LLM (Groq if GROQ_API_KEY is set, fallback to Gemini).
        """
        groq_key = Config.GROQ_API_KEY
        if groq_key:
            import requests
            target_model = model_name or Config.GROQ_MODEL
            logger.info(f"Querying Groq model '{target_model}' (temp={temperature})...")
            
            headers = {
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json"
            }
            
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": target_model,
                "messages": messages,
                "temperature": temperature
            }
            
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"].strip()
                else:
                    logger.error(f"Groq API error (status {response.status_code}): {response.text}")
                    raise ValueError(f"Groq API error: {response.text}")
            except Exception as groq_err:
                logger.error(f"Groq generation failed: {groq_err}. Attempting Gemini fallback if key available...")
                if not (api_key or self.api_key):
                    raise groq_err
        
        # Fallback / Direct Gemini path
        current_api_key = api_key or self.api_key
        if not current_api_key:
            raise ValueError("No LLM keys configured. Please set GEMINI_API_KEY or GROQ_API_KEY in your .env file.")
            
        client = genai.Client(api_key=current_api_key)
        target_model = model_name or Config.GEMINI_MODEL
        logger.info(f"Querying Gemini model '{target_model}' (temp={temperature})...")
        
        try:
            safety_settings = [
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_MEDIUM_AND_ABOVE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
            ]
            
            config = types.GenerateContentConfig(
                temperature=temperature,
                system_instruction=system_instruction,
                safety_settings=safety_settings
            )
            
            response = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config
            )
            
            if response and response.text:
                return response.text.strip()
            return ""
                
        except Exception as e:
            # Auto-retry with fallback model on 429 quota exhaustion
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                fallback_model = "gemini-1.5-flash" if "2.5" in target_model else "gemini-2.5-flash"
                logger.warning(f"Quota exceeded (429) for '{target_model}'. Retrying with fallback model '{fallback_model}'...")
                try:
                    response = client.models.generate_content(
                        model=fallback_model,
                        contents=prompt,
                        config=config
                    )
                    if response and response.text:
                        return response.text.strip()
                    return ""
                except Exception as fallback_err:
                    logger.error(f"Fallback model '{fallback_model}' also failed: {fallback_err}")
                    raise fallback_err
            logger.error(f"Gemini API call failed: {e}")
            raise e
            
    def transcribe_audio(self, audio_file_path: str, api_key: Optional[str] = None) -> str:
        """
        Transcribes audio files. Routes to Groq Whisper if GROQ_API_KEY is configured,
        otherwise uses Gemini's inline content generation.
        """
        groq_key = Config.GROQ_API_KEY
        if groq_key:
            try:
                import requests
                logger.info(f"Transcribing audio file '{audio_file_path}' via Groq Whisper API...")
                
                headers = {"Authorization": f"Bearer {groq_key}"}
                files = {"file": (Path(audio_file_path).name, open(audio_file_path, "rb"), "audio/webm")}
                data = {"model": "whisper-large-v3"}
                
                response = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions", 
                    headers=headers, 
                    files=files, 
                    data=data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    text = response.json().get("text", "").strip()
                    logger.info(f"Groq Whisper transcription success: '{text}'")
                    return text
                else:
                    logger.error(f"Groq Whisper error (status {response.status_code}): {response.text}")
                    raise ValueError(f"Groq Whisper failed: {response.text}")
            except Exception as groq_err:
                logger.error(f"Groq Whisper transcription failed: {groq_err}. Attempting Gemini fallback if key available...")
                if not (api_key or self.api_key):
                    raise groq_err
                    
        # Fallback / Direct Gemini path
        current_api_key = api_key or self.api_key
        if not current_api_key:
            raise ValueError("No keys configured. Please set GEMINI_API_KEY or GROQ_API_KEY in your .env file.")
            
        try:
            client = genai.Client(api_key=current_api_key)
            logger.info(f"Transcribing audio file '{audio_file_path}' via inline Gemini API...")
            
            with open(audio_file_path, "rb") as f:
                audio_bytes = f.read()
                
            ext = Path(audio_file_path).suffix.lower()
            mime_type = "audio/webm"
            if ext == ".wav":
                mime_type = "audio/wav"
            elif ext == ".mp3":
                mime_type = "audio/mp3"
            elif ext == ".ogg":
                mime_type = "audio/ogg"
            elif ext == ".m4a":
                mime_type = "audio/m4a"
                
            prompt = "Transcribe the spoken audio in this file. Output only the transcribed text, word-for-word, without adding any prefix, explanation, or commentary. If there is no speech, return an empty string."
            
            target_model = "gemini-2.5-flash"
            try:
                response = client.models.generate_content(
                    model=target_model,
                    contents=[
                        types.Part.from_bytes(
                            data=audio_bytes,
                            mime_type=mime_type
                        ),
                        prompt
                    ]
                )
            except Exception as e:
                # Fallback to gemini-1.5-flash on rate limits
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    fallback_model = "gemini-1.5-flash"
                    logger.warning(f"Quota exceeded (429) for transcription under '{target_model}'. Retrying with '{fallback_model}'...")
                    response = client.models.generate_content(
                        model=fallback_model,
                        contents=[
                            types.Part.from_bytes(
                                data=audio_bytes,
                                mime_type=mime_type
                            ),
                            prompt
                        ]
                    )
                else:
                    raise e
            
            if response and response.text:
                transcription = response.text.strip()
                logger.info(f"Audio transcription success: '{transcription}'")
                return transcription
            return ""
            
        except Exception as e:
            logger.error(f"Gemini audio transcription failed: {e}")
            raise e
