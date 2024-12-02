import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp as youtube_dl
import asyncio
from typing import Optional, Literal
import os
from spotify import fetch_spotify_data
import random

queue = []
tasks = []
currently_playing = None

# Configure youtube_dl options
ytdl_format_options = {
  'format': 'bestaudio/best',
  'restrictfilenames': True,
  'noplaylist': False,
  'playlist_items': '1-2',
  'skip_playlist_after_errors': 10,
  'nocheckcertificate': True,
  'ignoreerrors': True,
  'logtostderr': False,
  'quiet': True,
  'no_warnings': True,
  'default_search': 'ytsearch',
  'playlistrandom': False,
  'source_address': '0.0.0.0'
}
ffmpeg_options = {'options': '-vn'}  # Ensure this line is correctly placed
ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
  def __init__(self, source, *, data, volume=0.5):
    super().__init__(source, volume)
    self.data = data
    self.title = data.get('title')
    self.url = data.get('url')

  @classmethod
  async def from_url(cls, url, *, loop=None, stream=False, shuffle=False):
      global ytdl_format_options

      loop = loop or asyncio.get_event_loop()

      if shuffle:
        ytdl_format_options['playlistrandom'] = True

      ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

      playlist = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False, process=False))
      playlist_title = playlist['title']

      # Use provided YTDL instance or fall back to global instance
      data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

      # Check if 'entries' are present in the data
      if 'entries' in data:
        # Handle playlists
        playlist_sources = []
        # Handle playlists
        initial_entries = data['entries']
        for entry in initial_entries:
            filename = entry['url'] if stream else ytdl.prepare_filename(entry)
            playlist_sources.append(cls(discord.FFmpegPCMAudio(filename, before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", options="-vn"), data=entry))
      
        asyncio.create_task(cls.add_remaining_playlist_entries(url, loop, stream))
        return playlist_sources, playlist_title
      
      else:
        # Handle single video
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return [cls(discord.FFmpegPCMAudio(filename, before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", options="-vn"), data=data)], 'None'
      
  @classmethod
  async def add_remaining_playlist_entries(cls, url, loop, stream):
      global queue, tasks
      # Process entries 3-10
      await cls.process_playlist_range(url, '3-10', loop, stream)

      # Asynchronously process entries 11-40
      task = asyncio.create_task(cls.process_playlist_range(url, '11-40', loop, stream))

      tasks.append(task)

  @classmethod
  async def process_playlist_range(cls, url, playlist_range, loop, stream):
    global queue
    new_options = ytdl_format_options.copy()
    new_options['playlist_items'] = playlist_range
    new_options['sleep_interval_requests'] = 1
    new_options['lazy_playlist'] = True
    ytdl_range = youtube_dl.YoutubeDL(new_options)
    data = await loop.run_in_executor(None, lambda: ytdl_range.extract_info(url, download=not stream))
    if 'entries' in data:
      for entry in data['entries']:
        if len(queue) > 100:
            return
        filename = entry['url'] if stream else ytdl.prepare_filename(entry)
        player = cls(discord.FFmpegPCMAudio(filename, before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", options="-vn"), data=entry)
        queue.append(player)
        await asyncio.sleep(0.1)

class MusicControlView(discord.ui.View):
  def __init__(self, bot, interaction):
      super().__init__()
      self.bot = bot
      self.interaction = interaction

  @discord.ui.button(label='Pause', style=discord.ButtonStyle.grey, emoji='⏸️')
  async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
      await interaction.response.defer()
      await pause_song(self.interaction, True)

  @discord.ui.button(label='Resume', style=discord.ButtonStyle.grey, emoji='▶️')
  async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
      await interaction.response.defer()
      await resume_song(self.interaction, True)
      new_embed = generate_queue_embed(queue, self.interaction)
      await self.interaction.edit_original_response(embed=new_embed)
    
  @discord.ui.button(label='Skip', style=discord.ButtonStyle.grey, emoji='⏭️')
  async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
      await interaction.response.defer()
      await skip_song(self.interaction, True)
      # Update the embed with new queue information
      new_embed = generate_queue_embed(queue, self.interaction)
      await self.interaction.edit_original_response(embed=new_embed)

  @discord.ui.button(label='Stop', style=discord.ButtonStyle.red, emoji='⏹️')
  async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
      await interaction.response.defer()
      await stop_song(self.interaction, True)
    
      # Update the embed to show an empty queue
      new_embed = discord.Embed(title="Music Queue", description="The queue is empty.")
      await self.interaction.edit_original_response(embed=new_embed)

def generate_queue_embed(music_queue, interaction, max_entries=10):
    global currently_playing
    embed = discord.Embed(title="Music Queue", color=discord.Color.blue())
    voice_client = interaction.guild.voice_client

    if voice_client and voice_client.is_playing():
        if currently_playing:
            embed.add_field(name="Currently Playing", value=currently_playing, inline=False)

    if len(music_queue) > 0:
        start_index = 1 if currently_playing else 0
        displayed_queue = music_queue[:max_entries]
        queue_titles = [f"{index + start_index}. {song.title}" for index, song in enumerate(displayed_queue)]
        embed.add_field(name="Upcoming" if currently_playing else "Queue", value="\n".join(queue_titles), inline=False)

        if len(music_queue) > max_entries:
            embed.set_footer(text=f"and {len(music_queue) - max_entries} more...")
    elif currently_playing is None or ((voice_client is None or not voice_client.is_playing()) and len(music_queue) == 0):
        embed.description = "The queue is empty."

    return embed


  # Function to show music controls
async def show_controls(interaction: discord.Interaction, bot, music_queue=queue):
    embed = generate_queue_embed(music_queue, interaction)
    view = MusicControlView(bot, interaction)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def process_remaining_spotify_tracks(track_names, loop):
  global queue
  for track_name in track_names:
      youtube_url = "ytsearch:" + track_name
    
      try:
        player, _ = await YTDLSource.from_url(youtube_url, loop=loop, stream=True)
        queue += player
      except:
        continue
        
      await asyncio.sleep(0.1)  # Adjust the sleep interval as needed   

async def process_spotify_url(query, bot, shuffle = False):
  global queue,tasks
  # Fetch track names from Spotify URL
  track_names, playlist_title = await fetch_spotify_data(query)

  if track_names is None:
    return None, None

  if shuffle:
    random.shuffle(track_names)
  
  playlist_sources = []

  # Process the first two tracks immediately
  for track_name in track_names[:2]:
      youtube_url = "ytsearch:" + track_name
      try:
        player, _ = await YTDLSource.from_url(youtube_url, loop=bot.loop, stream=True)
      except:
        continue
      playlist_sources.extend(player)

  # Asynchronously process the next eight tracks (tracks 3-10)
  if len(track_names) > 2:
      task = asyncio.create_task(process_remaining_spotify_tracks(track_names[2:40], bot.loop))
      tasks.append(task)

  return playlist_sources, playlist_title

async def play_music(interaction: discord.Interaction, query: str, bot, mention = False, is_speech = False, speech = None, shuffle = False):
  global currently_playing, queue
  voice_client = interaction.guild.voice_client
  if not voice_client:
    if not mention:
      if interaction.user.voice:
        voice_client = await interaction.user.voice.channel.connect()
      else:
        try:
          await interaction.followup.send("You are not connected to a voice channel.") 
        except:
          await interaction.response.send_message("You are not connected to a voice channel.")
        return
    else:
      if interaction.author.voice:
        voice_client = await interaction.author.voice.channel.connect()
          
      else:
        await interaction.channel.send("You are not connected to a voice channel.")
        return

  # Create a local copy of ytdl_format_options and modify it
  if not is_speech:
    try:
        if query.startswith(('http://', 'https://')):
            if 'spotify.com' in query and ('track' in query or 'playlist' in query):
                # Handle Spotify URL
                player, playlist_title = await process_spotify_url(query, bot, shuffle)
            else:
                # Handle other URLs (e.g., YouTube)
                player, playlist_title = await YTDLSource.from_url(query, loop=bot.loop, stream=True, shuffle=shuffle)
        else:
            # If not a URL, treat it as a search query
            player, playlist_title = await YTDLSource.from_url("ytsearch:" + query, loop=bot.loop, stream=True, shuffle=shuffle)

    except Exception as e:
      if not mention:
        await interaction.followup.send(f'The following error occurred with your request: {e}')
      else:
        await interaction.channel.send(f'The following error occurred with your request: {e}')
      return
  else:
    player = [speech]

  if player:
    queue.extend(player)
    
    if not voice_client.is_playing():
      await play_next(interaction,bot)
      
    if len(player) > 1:
       content = f"Added playlist '{playlist_title}' to the queue"
    else:
       content = f"Added to queue: {player[0].title}"

  else:
    content = "Something went wrong. Try a different query or URL."  
    
  if not mention and not is_speech:
    await interaction.edit_original_response(content=content)
  elif not is_speech:
    await interaction.channel.send(content)
    

async def play_next(interaction, bot):
  global currently_playing
  voice_client = interaction.guild.voice_client
  if voice_client and not voice_client.is_playing() and len(queue) > 0:
      next_item = queue.pop(0)
      if next_item:
        currently_playing = next_item.title
      else:
        currently_playing = None

      # Check if the next item has a 'source' attribute
      if hasattr(next_item, 'source'):
          audio_source = next_item.source  # Use the source attribute for speech
      else:
          # If it's not a speech item, handle it as a regular song
          audio_source = next_item

      voice_client.play(audio_source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction, bot), bot.loop))


async def skip_song(interaction, controls=False):
  voice_client = interaction.guild.voice_client
  if voice_client and voice_client.is_playing():
      voice_client.stop()
              # No need to call play_next here as it will be triggered by the 'after' callback of voice_client.play

      if not controls:
          await interaction.response.send_message("Skipped the current song.",ephemeral=True)
  else:
      if not controls:
          await interaction.response.send_message("No music is playing right now.",ephemeral=True)


async def add_to_queue(interaction, query, bot, music_queue = queue):
  # Check if the query is a URL
  if query.startswith(('http://', 'https://')):
      player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
  else:
      # If not a URL, treat it as a search query
      player = await YTDLSource.from_url("ytsearch:" + query, loop=bot.loop, stream=True)
  music_queue.append(player)
  await interaction.response.send_message(f'Added to queue: {player.title}')


async def play_next_song(interaction, query, bot, music_queue = queue):
  if len(queue) < 1:
    await play_music(interaction,query,bot)
  else:
    try:
      if query.startswith(('http://', 'https://')):
        if 'spotify.com' in query and ('track' in query or 'playlist' in query):
            # Handle Spotify URL
            player, playlist_title = await process_spotify_url(query, bot)
        else:
            # Handle other URLs (e.g., YouTube)
            player, playlist_title = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
      else:
        # If not a URL, treat it as a search query
        player, playlist_title = await YTDLSource.from_url("ytsearch:" + query, loop=bot.loop, stream=True)

    except Exception as e:
      await interaction.followup.send(f'The following error occurred with your request: {e}')
      return
    if player:
      music_queue.insert(0, player[0])
      if len(player) > 1:
        music_queue.insert(1, player[1])
        content = f'Will play playlist next: {playlist_title}'
      else:
        content = f'Will play next: {player[0].title}'
    await interaction.edit_original_response(content=content)

async def pause_song(interaction, controls = False):
  voice_client = interaction.guild.voice_client
  if voice_client and voice_client.is_playing():
      voice_client.pause()
      if not controls:
        await interaction.response.send_message("Music playback paused.",ephemeral=True)
  else:
      if not controls:
        await interaction.response.send_message("No music is playing right now.",ephemeral=True)

async def resume_song(interaction, controls = False):
  voice_client = interaction.guild.voice_client
  if voice_client and voice_client.is_paused():
      voice_client.resume()
      if not controls:
        await interaction.response.send_message("Music playback resumed.",ephemeral=True)
  else:
      if not controls:
        await interaction.response.send_message("Music is not paused.",ephemeral=True)

async def stop_song(interaction, controls = False):
  global tasks, currently_playing
  queue.clear()  # Clearing the queue
  currently_playing = None
  
  for task in tasks:
    task.cancel()
  tasks.clear()

  try:
    voice_client = interaction.guild.voice_client
  except:
    voice_client = None
  if voice_client:
      voice_client.stop()
      if not controls:
        await interaction.response.send_message("Stopped playing music and cleared the queue.",ephemeral=True)
  else:
      if not controls:
        await interaction.response.send_message("No music is playing right now.",ephemeral=True)