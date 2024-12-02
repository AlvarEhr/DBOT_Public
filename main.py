from dotenv import load_dotenv
load_dotenv()
import os
import discord
from discord.ext import commands
from discord import app_commands
import discord.ext.commands
from typing import Optional, Literal
import openai
from server import keep_alive as KeepAlive
import datetime
from mongodb import db
import asyncio
from PIL import Image
from io import BytesIO
from chat import tokens
from tts import text_to_speech, get_closest_match, send_voice_titles
from ui_elements import TTSSelect, DeleteButtonView, PlayInChatButton
from save_load import load_stable_images, load_total_image_count, load_image_count, load_date, save_image_count, save_date, load_tokens_used_today, save_tokens_used_today, load_total_tokens_used
from data import command_info, StyleType, Commands, Voices, Eleven_Voices
from tts_openai import speak_text
from music import play_music, skip_song, play_next_song, resume_song, pause_song, stop_song, show_controls
from background_operations import process_message_stats, process_random_images, process_ask_command, process_dalle_image, process_dalle_url, process_dalle_upload, process_stable, process_stable_upload, handle_mention, eleven_tts, play_from_file

#DBOT setup for the Cog, adding it to Discord and syncing on start.
class DBOT(commands.Bot):
    async def setup_hook(self):
        await bot.add_cog(StableCog(bot))
        print(f"Logging in as: {self.user}")
        await self.tree.sync()
        # Add all buttons from the database
        if 'buttons' in db.keys():
            for button in db['buttons']:
                self.add_view(DeleteButtonView(button['message_id'], button['user_id']))
        if 'play_in_chat_buttons' in db.keys():
            for interaction_orig in db['play_in_chat_buttons']:
              self.add_view(PlayInChatButton(interaction_orig, bot, play_from_file))

#Some global variable initialisations
API_KEY = os.environ['API_KEY']
openai.api_key = API_KEY
TOKEN = os.environ['TOKEN']
IMAGE_COUNT_KEY = "image_count"
DATE_KEY = "date"
TOTAL_IMAGE_COUNT_KEY = "total_image_count"
STABLE_IMAGES = "stable_images"

#More global variable initialisations
current_date = load_date()
tokens_used_today = load_tokens_used_today()
total_tokens_used = load_total_tokens_used()
stable_images = load_stable_images()

#Date checker, resets certain counters if date changes
if current_date != str(datetime.date.today()):
    current_date = str(datetime.date.today())
    generated_images_today = 0
    tokens_used_today = 0
    save_tokens_used_today(tokens_used_today)
    save_date(current_date)
    save_image_count(generated_images_today, generated_images_today)

async def check_for_new_day():
    global generated_images_today
    global current_date

    while True:
        if current_date != str(datetime.date.today()):
            current_date = str(datetime.date.today())
            generated_images_today = 0
            tokens_used_today = 0
            save_tokens_used_today(tokens_used_today)
            save_date(current_date)
            save_image_count(generated_images_today, generated_images_today)
        await asyncio.sleep(3600)  # Check every hour

#Uncomment below for logging
#discord.utils.setup_logging()

# Seting up the bot's intents and initialising
intents = discord.Intents.default()
intents.typing = False
intents.presences = False
intents.message_content = True
bot = DBOT(command_prefix="!", intents=intents)

#DBOT startup message, and looking new day checker on startup
@bot.event
async def on_ready():
    global current_date
    dalle2_today, dalle3_today = load_image_count()
    dalle2_total, dalle3_total = load_total_image_count()
    print(f"{bot.user.name} has connected to Discord!\n")
    print("Usage")
    print("----------------------------")
    print("{:<10s} {:<10s} {:<10s}".format("", "Today", "Total"))
    print("{:<10s} {:<10d} {:<10d}".format("Dalle-2", dalle2_today, dalle2_total))
    print("{:<10s} {:<10d} {:<10d}".format("Dalle-3", dalle3_today, dalle3_total))
    print("{:<10s} {:<10s} {:<10d}".format("Stable", "---", stable_images))
    print("{:<10s} {:<10d} {:<10d}".format("Tokens", tokens_used_today, total_tokens_used))
    print("----------------------------\n")
    print(f"Today is: {current_date}")
    bot.loop.create_task(check_for_new_day()) 

#Response to being mentioned (function from chat.py)
@bot.event
async def on_message(message):
  if bot.user.mentioned_in(message) and not message.mention_everyone:
      asyncio.create_task(handle_mention(message, bot.user.id, bot))
  if not message.content == '!play':
    await bot.process_commands(message)

#The cog class for all of the / commands and the !sync command
class StableCog(commands.Cog):
  def __init__(self, bot: commands.Bot) -> None:
    self.bot = bot

#Sync function for syncing commands to server(s)
#sync command !sync {guild ID} or {-}
  @commands.command()
  @commands.guild_only()
  @commands.is_owner()
  async def sync(self, ctx: commands.Context, guilds: commands.Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
        if not guilds:
            if spec == "~":
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "^":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                synced = []
            else:
                synced = await ctx.bot.tree.sync()

            await ctx.send(
                f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
            )
            return

        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1

        await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

  #!delete command, deletes a message given the message ID.
  @commands.command()
  @commands.guild_only()
  @commands.is_owner()
  async def delete(self, ctx: commands.Context, id: str):
    ids = id.split(',')  # Split the ids string into a list of ids
    for one_id in ids:
        one_id = one_id.strip()  # Remove any leading/trailing whitespace
        message = ctx.channel.get_partial_message(one_id)
        try:
            await message.delete()
        except discord.errors.Forbidden:
            await ctx.send("I do not have the necessary permissions to delete messages in this channel.", ephemeral=True)
        except:
            await ctx.send(f"Something went wrong when trying to delete message with ID {one_id}.", ephemeral=True)

  @app_commands.command(name="pinguser", description="Ping a user multiple times")
  async def ping_user(self, interaction: discord.Interaction, user: discord.User, count: int = 5):
      # Fetch the bot's application information to get the owner's ID
      me = os.environ['USER_ID']
      allowed_users = [me, '1862134253639911424']
      user_id_str = str(interaction.user.id)
      if user_id_str not in allowed_users:
          await interaction.response.send_message("Only the bot owner can use this command.", ephemeral=True)
          return

      if count > 20:  # Limit the count to prevent abuse
          count = 20

      await interaction.response.send_message(f"Pinging {user.mention} {count} times...", ephemeral=True)
      for _ in range(count):
          await asyncio.sleep(0.3)  # Delay between pings
          await interaction.channel.send(user.mention)

  #/help command, helps the user
  @app_commands.command(name="help",description="Ask for help with any command, or see all available commands")
  async def help(self, interaction: discord.Interaction, command: Commands = "all"): #Commands imported from data.py
    if command == "all":
        #command_info imported from data.py
        response = "\n".join([f"{cmd}" for cmd in command_info.keys() if cmd != "/help"])
        embed = discord.Embed(title="Available commands", description=("Use /help followed by any of the below commands for details on the command. e.g. `/help /dalle`.\n"+response))
        await interaction.response.send_message(embed=embed,ephemeral=True)
    else:
        description, usage, example = command_info[command]
        embed = discord.Embed(title=f"Command: {command}", description=description)
        embed.add_field(name="Usage", value=usage, inline=False)
        embed.add_field(name="Example", value=example, inline=False)
        await interaction.response.send_message(embed=embed,ephemeral=True)
  
  
  #Sentience command, literally just sends a string without showing you the used the command.
  @app_commands.command(name="sentience",description="It is time")
  async def sentience(self, interaction: discord.Interaction, string: str):
    if str(interaction.user.id) != os.environ['USER_ID']:
        await interaction.channel.send(f'{str(interaction.user)} do you truly believe you are worthy of me? Begone.')
        return
    await interaction.channel.send(f"{string}")

  #/usage command, shows image counts and token counts in a nice graph
  @app_commands.command(name="usage", description="Display the number of images and tokens used today in a nice little graph")
  async def usage(self, interaction: discord.Interaction):
    #Loading current figures
    dalle2_today, dalle3_today = load_image_count()
    dalle2_total, dalle3_total = load_total_image_count()
    stable_images = load_stable_images()
    tokens_used_today = load_tokens_used_today()
    total_tokens_used = load_total_tokens_used()
    dalle2price = round(dalle2_total * 0.02,2)
    dalle3price = round(dalle3_total * 0.04,2)
    tokenprice = round(total_tokens_used*0.000002,2)

    #Usage graph as an embed
    embed = discord.Embed(title="Usage", color=discord.Color.blue())

    embed.add_field(name="Type", value="Dalle-2\nDalle-3\nStable\nTokens", inline=True)
    embed.add_field(name="Today", value=f"{dalle2_today}\n{dalle3_today}\n---\n{tokens_used_today}", inline=True)
    
    # Include price and limit information in the Total field for each row
    embed.add_field(name="Total", value=f"{dalle2_total} (${dalle2price})\n{dalle3_total} (${dalle3price})\n{stable_images} (/2500)\n{total_tokens_used}  (${tokenprice})", inline=True)

    await interaction.response.send_message(embed=embed,ephemeral=True)
  
  #/tokencount command, takes from chat.py
  @app_commands.command(name="tokencount", description="Display the number of tokens used today, and the total amount of tokens used")
  async def tokencount_command(self, interaction: discord.Interaction):
    await tokens(self, interaction)

  #/voices command, sends a .txt file that shows all the voices
  @app_commands.command(name='voices', description='Returns a .txt file of all the available voices for /tts')
  async def voices(self, interaction: discord.Interaction, voice: Optional[str] = None):
      if voice is None:
          voice_titles = await send_voice_titles()
          await interaction.response.send_message("Here are all available voices.", file=voice_titles, ephemeral=True)
      else:
          matches = await get_closest_match(voice)
          if len(matches) > 0:
              names_with_ratings = []
              for match in matches:
                  voice_name = match[0]
                  user_ratings = match[2]  # Assuming user_ratings is at index 2
                  positive_count = user_ratings['positive_count']
                  total_count = user_ratings['total_count']
                  positive_percentage = (positive_count / total_count * 100) if total_count > 0 else 0
                  names_with_ratings.append(f"{voice_name} - {positive_percentage:.2f}% positive votes")

              names_str = "\n".join(names_with_ratings)
              await interaction.response.send_message(f"These are the matches to the voice you asked for:\n{names_str}", ephemeral=True)

          else:
              await interaction.response.send_message("Sorry, there were no matches to that voice, try another one.", ephemeral=True)

  @app_commands.command(name="randomimg", description="Select and send 3 random images from message history")
  async def random_images_command(self, interaction: discord.Interaction, history: Optional[int] = 2000):

      history = max(50, min(history, 10000))

      await interaction.response.send_message("Searching for random images...")
    
      asyncio.create_task(process_random_images(interaction, history, interaction.channel))

  @app_commands.command(name="stats", description="Gives the statistics of how many times a word has been said and by who.")
  async def stats(self, interaction: discord.Interaction, word: str, history: Optional[int] = 2000):
    
    history = max(50, min(history, 10000))
      
    # Notify the user that processing has started
    await interaction.response.send_message(f"Processing the last {history} messages for the word '{word}'...")

    # Start the background task
    asyncio.create_task(process_message_stats(interaction, word, history, interaction.channel))
    
  
  #/ask command, takes from chat.py
  @app_commands.command(name='ask', description='Ask a question to the GPT-4o powered AI.')
  async def ask_command(self, interaction: discord.Interaction, question: str, vision: Optional[bool] = False, num_context: Optional[int] = 5, gpt_model: Literal["gpt-4o-mini","o1-mini"] = "gpt-4o-mini"):
    
    await interaction.response.send_message("Processing your question...")

    # Start the background task to process the ask command
    asyncio.create_task(process_ask_command(self, interaction, question, num_context, gpt_model, vision, bot_id=self.bot.user.id, bot=self.bot))
  
  #/dalle command, takes from generation.py
  @app_commands.command(name="dalle", description="Generate an image using DALL-E and send it as a .png file")
  async def dalle_image(self, interaction: discord.Interaction, prompt: str, num_images: Optional[int] = 1, model: Literal["dall-e-2", "dall-e-3"] = "dall-e-2"):
    dalle2_today, dalle3_today = load_image_count()
    
    if num_images > 3:
        num_images = 3

    # Define a dictionary mapping model names to their daily limits
    daily_limits = {
        "dall-e-2": 50,
        "dall-e-3": 25
    }

    # Check if the model is in the dictionary and if the limit is exceeded
    if model in daily_limits and (daily_limits[model] < num_images + (dalle2_today if model == "dall-e-2" else dalle3_today)):
        await interaction.response.send_message("Daily image generation limit reached. Please try again tomorrow.", ephemeral=True)
        return

    await interaction.response.send_message("Generating image...")
    asyncio.create_task(process_dalle_image(interaction, prompt, num_images, model, interaction.user))

  #/dalleurl command sending the URL, takes from generation.py
  @app_commands.command(name="dalleurl", description="Generate an image using DALL-E")
  async def dalle(self, interaction: discord.Interaction, prompt: str, num_images: Optional[int] = 1):
    
      generated_images_today, _ = load_image_count()
    
      if num_images > 3:
          num_images = 3

      if generated_images_today + num_images > 100:
          await interaction.response.send_message("Daily image generation limit reached. Please try again tomorrow.", ephemeral=True)
          return

      await interaction.response.send_message("Generating image URL...")
      asyncio.create_task(process_dalle_url(interaction, prompt, num_images))

  #/dalleupload command to generate variations of an uploaded image
  @app_commands.command(name="dalleupload", description="Generate variations of an uploaded image, image must be square and .PNG")
  async def image_variations(self, interaction: discord.Interaction, attachment: discord.Attachment, num_variations: Optional[int] = 1):
    
      generated_images_today, _ = load_image_count()

      if num_variations > 3:
          num_variations = 3

      if generated_images_today + num_variations > 100:
          await interaction.response.send_message("Daily image generation limit reached. Please try again tomorrow.", ephemeral=True)
          return

      await interaction.response.send_message("Processing your image...")
      asyncio.create_task(process_dalle_upload(interaction, attachment, num_variations, interaction.user))
  
  #/stable command
  @app_commands.command(name="stable", description="Generate an image using Stable Diffusion")
  async def stable(self, interaction: discord.Interaction, description: str, num_images: Optional[int] = 1,style: StyleType = 'none'):
    #StyleType imported from data.py
    
    global stable_images
    if num_images > 3:
        num_images = 3

    if stable_images + num_images > 2500:
        await interaction.response.send_message("Sorry, out of images, ask me for some more.", ephemeral=True)
        return

    await interaction.response.send_message("Generating image...")
    asyncio.create_task(process_stable(interaction, description, num_images, style, interaction.user))

  #/stableupload command, takes an image and does image to image with stability AI
  @app_commands.command(name="stableupload", description="Generate an image to image using Stable Diffusion")
  async def stableupload(self, interaction: discord.Interaction, attachment: discord.Attachment, description: str,  num_images: Optional[int] = 1,style: StyleType = 'none'):
    global stable_images
    if num_images > 3:
        num_images = 3

    if stable_images + num_images > 2500:
        await interaction.response.send_message("Sorry, out of images, ask me for some more.", ephemeral=True)
        return

    # Prepare the image data
    image_bytes = await attachment.read()
    img = Image.open(BytesIO(image_bytes))
    if img.size != (512, 512):
        img = img.resize((512, 512))
    byte_arr = BytesIO()
    img.save(byte_arr, format='PNG')
    image_bytes = byte_arr.getvalue()

    await interaction.response.send_message("Processing your image...")
    asyncio.create_task(process_stable_upload(interaction, image_bytes, description, num_images, style, interaction.user))
    
  
  #/tts command, sends text to speech, takes from tts.py
  @app_commands.command(name="tts",description="This command may take some time. Send a Text-to-Speech as anyone you want")
  async def tts(self, interaction: discord.Interaction, name: str, text: str):
    matches = await get_closest_match(query=name)
    if len(matches) > 1:
      select_view = TTSSelect(matches=matches,text=text)
      #Command in the TTSSelect class
      await interaction.response.send_message("Select a Voice:",view=select_view)
      #await select_view.send_message(interaction)
    elif len(matches) < 1:
      await interaction.followup.send("No voice by that name could be found in the database, please try another one.",ephemeral=True)
      return
    else:
      await interaction.response.send_message("Generating TTS... (this could take a while)")
      
      # Create a task for the text_to_speech function and let it run in the background
      text_to_speech_task = asyncio.create_task(text_to_speech(name=name,message=text))
    
      try:
        audio_file = await asyncio.wait_for(asyncio.shield(text_to_speech_task), timeout=30)
        
      except asyncio.TimeoutError:
        await interaction.edit_original_response(content="The function is taking longer than expected, it is still running and will complete later. A new message will be sent once it is done.")
        await asyncio.sleep(10)
        await interaction.delete_original_response()
        try:
          audio_file = await asyncio.wait_for(text_to_speech_task, timeout=600)
        except asyncio.TimeoutError:
          await interaction.channel.send("The /tts function took longer than 10 minutes, please try again later. There might be some problems with the TTS server itself, maybe try again tomorrow.")
        else:
          await interaction.channel.send(f"Here is your TTS output, using the '{matches[0][0]}' voice:", file=audio_file)
        return

      except:
        await interaction.edit_original_response(content="There was an error, please try again.")
        return
        
      if audio_file == "None":
        await interaction.edit_original_response(content="There was an error, please try again with a different name")
      else:
        await interaction.edit_original_response(content=f"Here is your TTS output using the '{matches[0][0]}' voice:", attachments=[audio_file])

  @app_commands.command(name='join', description='Join a voice channel')
  async def join(self, interaction: discord.Interaction, voice_channel : Optional[discord.VoiceChannel] = None):
    if voice_channel is not None:
      try:
        await voice_channel.connect()
        await interaction.response.send_message(f"Connected to voice channel {voice_channel}", ephemeral=True)
        await stop_song(interaction=interaction,controls=True)
        return
      except:
        pass
    # Check if the bot is already connected to a voice channel in this guild 
    if interaction.guild.voice_client is not None:
      await interaction.response.send_message("I'm already in a voice channel.", ephemeral=True)
    elif interaction.user.voice:
      channel = interaction.user.voice.channel
      await channel.connect()
      await interaction.response.send_message("Connected to voice channel.", ephemeral=True)
      await stop_song(interaction=interaction,controls=True)
    else:
      await interaction.response.send_message("You're not in a voice channel.", ephemeral=True)

  @app_commands.command(name='speak', description='Speak using TTS')
  async def speak(self, interaction: discord.Interaction, text: str, voice : Voices = 'onyx'):
    await interaction.response.send_message("Processing your request...")
    try:
      processing_message = await interaction.original_response()
    except:
      pass
    asyncio.create_task(speak_text(interaction,text,voice,self.bot,processing_message=processing_message))

  @app_commands.command(name='eleven_labs', description="Text to speech but with a friend's voice")
  async def eleven_labs(self, interaction: discord.Interaction, text: str, voice_id: Eleven_Voices = "Person1"):
    
    ElevenVoices = {
      "Person1" : "7vum1Jt3yha8AJo4159",
      "Person2" : "04sQ1Nabg81ZW9pMhYH",
      "Person3" : "RXRwN6ahg2881uYidbk",
      "Person4" : "muVJJG6AAGHhaesKuZy",
      "Person5" : "9HQWa515aGHwigGgAx8r",
      "Person6" : "o69C6l2gauj54liQgIVt"
    }

    voice_id = ElevenVoices[voice_id]

    await interaction.response.send_message("Processing your request...")

    asyncio.create_task(eleven_tts(text=text,voice_id=voice_id, interaction=interaction, bot=self.bot))

  @app_commands.command(name='leave', description='Leave the voice channel')
  async def leave(self, interaction: discord.Interaction):
      if interaction.guild.voice_client:
          await interaction.guild.voice_client.disconnect()
          await interaction.response.send_message("Disconnected from voice channel.", ephemeral=True)
      else:
          await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)

  @app_commands.command(name="play", description="Plays a song from YouTube search")
  async def play(self, interaction: discord.Interaction, query: str, shuffle: Optional[bool] = False):
    #await interaction.response.defer()
    await interaction.response.send_message("Processing the request...")
    asyncio.create_task(play_music(interaction, query, self.bot, shuffle=shuffle))

  @app_commands.command(name="skip", description="Skips the current song")
  async def skip(self, interaction: discord.Interaction):
    await skip_song(interaction)

  @app_commands.command(name="queue", description="Shows the music queue")
  async def show_queue(self, interaction: discord.Interaction):
    await show_controls(interaction, self.bot)

  @app_commands.command(name="playnext", description="Plays a song next after the current one")
  async def play_next_command(self, interaction: discord.Interaction, query: str):
    await interaction.response.send_message("Processing the request...")
    asyncio.create_task(play_next_song(interaction, query, self.bot))

  @app_commands.command(name="pause", description="Pauses the music")
  async def pause(self, interaction: discord.Interaction):
    await pause_song(interaction)

  @app_commands.command(name="resume", description="Resumes the music")
  async def resume(self, interaction: discord.Interaction):
    await resume_song(interaction)

  @app_commands.command(name="stop", description="Stops the music and clears the queue")
  async def stop(self, interaction: discord.Interaction):
    await stop_song(interaction)

  @app_commands.command(name="playfile", description="Play an MP3 or other filetype in voicechat.")
  async def playfile(self, interaction: discord.Interaction, file: discord.Attachment):
    # URL of the audio file
    file_url = file.url

    # List of supported audio file extensions
    supported_extensions = ['.mp3', '.wav', '.ogg', '.flac']

    # Check if the file extension is in the list of supported formats
    if not any(file.filename.lower().endswith(ext) for ext in supported_extensions):
        await interaction.response.send_message("Unsupported audio file format. Please use MP3, WAV, OGG, or FLAC.", ephemeral=True)
        return

    # Create an audio source that discord can play, directly from the URL
    audio_source = discord.FFmpegPCMAudio(file_url)

    await interaction.response.send_message("Processing your request...")

    asyncio.create_task(play_from_file(audio_source, file.filename, interaction, self.bot))

#KeepAlive function from server.py to ping replit so the bot stays on
KeepAlive()

# Run the bot
bot.run(TOKEN)