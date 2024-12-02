import aiohttp
import asyncio
from discord import File
from io import BytesIO
import json
import uuid
#from difflib import get_close_matches
from fuzzywuzzy import process
from datetime import datetime
import os
from mongodb import db

# Define the base API URL
base_url = 'https://api.fakeyou.com/tts'

# Define the headers for the API requests
headers = {
  'Accept': 'application/json',
  'Content-Type': 'application/json',
}

def load_voice_list_from_file():
    filename = db["filename"]
    with open(filename, 'r') as file:
        data = json.load(file)
    voice_list = data['models']
    return voice_list

def save_voice_list_to_file(voice_list):
    filename = db["filename"]
    with open(filename, 'w') as file:
        json.dump(voice_list, file)

async def get_voice_list():
    filename = db["filename"]
    today = datetime.now().strftime('%Y-%m-%d')
    new_filename = f'voice_list_{today}.txt'
    if new_filename != filename:
        if os.path.exists(filename):
            os.remove(filename)
        db["filename"] = new_filename
    if os.path.exists(filename):
        voice_list = load_voice_list_from_file()
    else:
        url = "https://api.fakeyou.com/tts/list"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                voice_list = await response.json()
        save_voice_list_to_file(voice_list)
    return voice_list

#get_closest_match using difflib
'''
def get_closest_match(name, voice_list, n=5):
    if isinstance(voice_list, dict) and 'models' in voice_list:
        voice_list = voice_list['models']
    names = [voice['title'] for voice in voice_list]
    matches = get_close_matches(name, names)
    print(f"Matches: {matches}")
    if matches:
        match = matches[0]
        for voice in voice_list:
            if voice['title'] == match:
                return voice['model_token']
    return None
'''

#get_closest_match using fuzzywuzzy
async def get_closest_match(query, score_cutoff=70,limit=10):
    voice_list = await get_voice_list()
    if isinstance(voice_list, dict) and 'models' in voice_list:
        voice_list = voice_list['models']

    names = [voice['title'] for voice in voice_list]
    matches = process.extractBests(query, names, score_cutoff=score_cutoff, limit=limit)
    matched_voices = []
    if matches:
        for match in matches:
            for voice in voice_list:
                if voice['title'] == match[0]:
                    matched_voices.append((voice['title'], voice['model_token'],voice['user_ratings']))
    return matched_voices

async def send_voice_titles():
    voice_list = await get_voice_list()
    if isinstance(voice_list, dict) and 'models' in voice_list:
        voice_list = voice_list['models']

    names = [voice['title'] for voice in voice_list]
    titles_text = "\n".join(names)
    titles_bytes = titles_text.encode()

    file_like_object = BytesIO(titles_bytes)
    discord_file = File(file_like_object, filename='voice_titles.txt')
    return discord_file

async def poll_for_job_completion(inference_job_token, session):
    while True:
        async with session.get(f'{base_url}/job/{inference_job_token}', headers=headers) as response:
            response_data = await response.json()

        job_status = response_data['state']['status']
        if job_status == 'complete_success':
            return response_data
        elif job_status in ['complete_failure', 'dead']:
            raise Exception('The TTS request failed.')

        await asyncio.sleep(1)  # wait for 1 second before polling again

async def check_job_status(inference_job_token, session, sleep_time = 10):
  while True:
        async with session.get(f'{base_url}/job/{inference_job_token}', headers=headers) as response:
            response_data = await response.json()

        job_status = response_data['state']['status']

        if job_status == 'complete_success':
            return response_data  # return the response data when the job is complete
        elif job_status in ['complete_failure', 'dead']:
            raise Exception('The TTS request failed.')
        
        await asyncio.sleep(sleep_time)  # wait for sleep_time seconds before polling again

async def text_to_speech(message,name = None,token = None):
  # Define the text to be converted to speech
  inference_text = message  # replace this with your text

  if token is None:
    matches = await get_closest_match(name)
    tts_model_token = matches[0][1]
  else:
    tts_model_token = token

  if tts_model_token is None:
    return "None"
  async with aiohttp.ClientSession() as session:

    # Make a TTS request
    data = {
      'uuid_idempotency_token':
      str(uuid.uuid4()),  # generate a new UUID for each request
      'tts_model_token': tts_model_token,
      'inference_text': inference_text,
    }
    async with session.post(f'{base_url}/inference',
                            headers=headers,
                            data=json.dumps(data)) as response:
      response_data = await response.json()
    # Extract the inference job token
    inference_job_token = response_data['inference_job_token']

    try:
      response_data = await asyncio.wait_for(poll_for_job_completion(inference_job_token, session), timeout=30)
    except asyncio.TimeoutError:
    # If the polling loop has not completed after 30 seconds, pass the job to another function
      try:
        response_data = await asyncio.wait_for(check_job_status(inference_job_token, session), timeout = 620)

      except asyncio.TimeoutError:
        return "None"

    #except:
      #return "None"

    # Extract the path to the audio file
    audio_path = response_data['state']['maybe_public_bucket_wav_audio_path']

    # Define the base URL for the audio files
    audio_base_url = 'https://storage.googleapis.com/vocodes-public'

    # Construct the URL for the audio file
    audio_url = f'{audio_base_url}{audio_path}'

    # Download the audio file
    async with session.get(audio_url) as response:
      audio_content = await response.read()

    return File(BytesIO(audio_content), "tts_output.wav")
