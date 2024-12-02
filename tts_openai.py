from openai import OpenAI
import openai
import os
from io import BytesIO
import discord
from discord import FFmpegPCMAudio
import tempfile
from music import play_music, stop_song

api_key = os.environ['API_KEY']
openai.api_key = api_key

# Initialize the OpenAI client
#client = OpenAI()

def generate_speech(text,voice = "onyx"):
    """
    Generates speech using OpenAI's TTS API and returns an FFmpegPCMAudio source.

    Args:
        text (str): The text to convert to speech.

    Returns:
        FFmpegPCMAudio: An audio source for Discord to play.
    """
    response = openai.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text
    )

    # Create a BytesIO object to hold the audio data
    # Create a BytesIO object to hold the audio data
    audio_data = BytesIO(response.content)  # Assuming 'response.content' holds the binary audio data
    audio_data.seek(0)  # Move the cursor to the start of the BytesIO object

  # Create an FFmpegPCMAudio source using the BytesIO object
    audio_source = FFmpegPCMAudio(audio_data, pipe=True)  # Use pipe=True for streaming from BytesIO

    return audio_source

async def join_call(interaction, mention=False):
  guild = interaction.guild
  voice_client = guild.voice_client

  # Function to send follow-up messages depending on the context (interaction or mention)
  async def send_message(content):
      if mention:
          await interaction.channel.send(content)
      else:
          await interaction.followup.send(content, ephemeral=True)

  if voice_client:
      # Bot is already in a voice channel
      await send_message("I'm already connected to a voice channel.")
      return

  # Check if the user is in a voice channel
  user_voice_state = interaction.user.voice if not mention else interaction.author.voice
  if user_voice_state:
      channel = user_voice_state.channel
      try:
          await channel.connect()
          await send_message("Connected to voice channel.")
      except Exception as e:
          await send_message(f"Failed to connect to the voice channel: {e}")
  else:
      await send_message("You're not in a voice channel.")


async def leave_call(interaction, mention = False):
  await stop_song(interaction, controls = True)
  if not mention:
    if interaction.guild.voice_client:
      await interaction.guild.voice_client.disconnect()
      #await interaction.response.send_message("Disconnected from voice channel.", ephemeral=True)
    else:
      await interaction.followup.send_message("I am not connected to a voice channel.", ephemeral=True)

  else:
    message = interaction
    if message.guild.voice_client:
      await message.guild.voice_client.disconnect()
      #await message.channel.send("Disconnected from voice channel.")
    else:
      await message.channel.send("I am not connected to a voice channel.")

class SpeechItem:
  def __init__(self, source, title):
      self.source = source
      self.title = title

async def speak_text(interaction, text, voice, bot=None, mention=False, processing_message=None):
  # Generate TTS audio
  audio_source = generate_speech(text, voice)

  # Wrap the audio source in a SpeechItem with a title
  speech_item = SpeechItem(audio_source, title=f"TTS: {text[:20]}...")  # Use a part of the text as the title

  # Utilize play_music to handle everything including playing or queuing the speech
  await play_music(interaction=interaction, query=None, bot=bot, mention=mention, is_speech=True, speech=speech_item) 

  # Delete the processing message if it exists and the interaction is not a mention
  #print(processing_message)
  if processing_message:
    try:
      await processing_message.delete()
    except:
      pass
