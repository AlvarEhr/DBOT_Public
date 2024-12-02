import os
import aiohttp
from discord import File
from io import BytesIO

async def text_to_speech_elevenlabs(text, voice_id):
    #voice_id = "7vum1Jtl6pXucAJo4159"
    xi_api_key = f"{os.environ['ELEVEN_API']}"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
  
    headers = {
        "Content-Type": "application/json",
        "xi-api-key": xi_api_key
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.9,
            "syle": 0.6,
            "use_speaker_boost": True
        }
    }

    async with aiohttp.ClientSession() as session:
      async with session.post(url, json=payload, headers=headers) as response:
          if response.status == 200:
            audio = await response.read()
            filename = 'tts_output.mp3'
            return audio,filename
          
          else:
              error_detail = await response.text()  # Getting text response for more detail
              print(f"Error: {response.status} - {error_detail}")
              return None,None