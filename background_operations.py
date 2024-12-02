import discord
from discord.errors import NotFound
import os
import random
import openai
import math
from PIL import Image
from io import BytesIO
from ui_elements import DeleteButtonView, StableButtonView, PlayInChatButton
from chat import ask, add_interaction
from generation import generate_image, generate_image_url, generate_uploaded_image_variation, stability_rest, stability_imagetoimage
from save_load import save_stable
from eleven_labs_tts import text_to_speech_elevenlabs
from tts_openai import SpeechItem
from music import play_music

async def process_message_stats(interaction, word, history_limit, response_channel):
  word_counts = {}
  async for message in interaction.channel.history(limit=history_limit):
      count_occurrences = message.content.lower().split().count(word.lower())
      if count_occurrences > 0:
          word_counts[message.author.id] = word_counts.get(message.author.id, 0) + count_occurrences

  sorted_counts = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:25]
  random_color = random.randint(0, 0xFFFFFF)
  embed = discord.Embed(title=f"Word statistics for '{word}'", description=f"Based on the last {history_limit} messages", color=random_color)

  for user_id, count in sorted_counts:
      try:
          # Attempt to fetch member from guild
          user = interaction.guild.get_member(user_id) or await interaction.guild.fetch_member(user_id)
      except NotFound:
          # If member not found, set name to "Unknown"
          name = "Unknown"
      else:
          # If member is found, use their display name
          name = user.display_name

      embed.add_field(name=name, value=f"{count} times", inline=True)

  await interaction.edit_original_response(content="",embed=embed)

async def process_random_images(interaction, history_limit, response_channel):
  images = []
  async for message in interaction.channel.history(limit=history_limit):
      for attachment in message.attachments:
          if attachment.content_type and attachment.content_type.startswith("image/"):
              images.append((message, attachment))

  num_images = min(len(images), 3)
  selected_attachments = random.sample(images, num_images) if images else []

  if selected_attachments:
      response_embeds = []
      for message, attachment in selected_attachments:
          original_message_link = f"[Original Message](https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id})"
          embed = discord.Embed()
          embed.set_image(url=attachment.url)
          embed.description = f"{original_message_link}\nUploaded by {message.author}"
          response_embeds.append(embed)

      response = await interaction.edit_original_response(content="",embeds=response_embeds)
      view = DeleteButtonView(str(response.id), str(interaction.user.id))
      await response.edit(view=view)
  else:
      await interaction.edit_original_response("No images found in the message history.")


async def process_ask_command(self, interaction, question, num_context, gpt_model, vision, bot_id, bot):
  # Add the interaction to record
  add_interaction(interaction.id, question, interaction.user)

  # Call the predefined 'ask' function and wait for the response
  await ask(self=self, interaction=interaction, question=question, num_context=num_context, bot_id=bot_id, gpt_model=gpt_model, bot = bot, vision=vision)
  
async def process_dalle_image(interaction, prompt, num_images, model, user):
  try:
      filenames = await generate_image(prompt=prompt, n=num_images, model=model)
      view = StableButtonView(command="dalle", description=prompt, num_images=num_images, gen_image=filenames, user=user, model=model)
      await interaction.edit_original_response(content="",attachments=filenames, view=view)

  except Exception as e:
    await interaction.edit_original_response(content=f"Something went wrong: {e}")

async def process_dalle_url(interaction, prompt, num_images):
  try:
      generated_image_urls = await generate_image_url(prompt=prompt, n=num_images)
      results = "\n".join([f"Generated image {i + 1} URL: {url}" for i, url in enumerate(generated_image_urls)])
      await interaction.edit_original_response(content=results)

  except Exception as e:
      await interaction.edit_original_response(content=f"Something went wrong: {e}")

async def process_dalle_upload(interaction, attachment, num_variations, user, fromreply = False):
  try:
      # Download the attached image
      image_bytes = await attachment.read()

      # Open image
      img = Image.open(BytesIO(image_bytes))

      # Calculate dimensions for square cropping
      width, height = img.size

      # Only crop if the image is not square
      if width != height:
        min_dim = min(width, height)
        left = (width - min_dim)/2
        top = (height - min_dim)/2
        right = (width + min_dim)/2
        bottom = (height + min_dim)/2

        # Crop to square
        img = img.crop((left, top, right, bottom))

        width, height = img.size

      # Calculate maximum dimension for 4MB PNG image
      max_bytes = 4 * 1024 * 1024  # 4MB in bytes
      bytes_per_pixel = 4  # a rough estimate for PNG images
      max_pixels = max_bytes / bytes_per_pixel
      max_dimension = int(math.sqrt(max_pixels))

      # Resize if necessary
      if width > max_dimension or height > max_dimension:
        img.thumbnail((max_dimension, max_dimension))

      # Convert back to bytes
      byte_arr = BytesIO()
      img.save(byte_arr, format='PNG')
      image_bytes = byte_arr.getvalue()

      # Check the size
      image_bytes = byte_arr.getvalue()

      # Generate variations of the uploaded image
      filenames = await generate_uploaded_image_variation(image_bytes=image_bytes, n=num_variations)

      if not fromreply:
        # Create the view for the response
        view = StableButtonView(command="dalleupload", attachment=image_bytes, num_images=num_variations, gen_image=filenames, user=user)

        # Send the generated images along with the view
        await interaction.edit_original_response(content="",attachments=filenames, view=view)
      else:
        await interaction.channel.send(content="",files=filenames)

  except Exception as e:
    if not fromreply:
      await interaction.edit_original_response(content=f"Something went wrong: {e}")
    else:
      await interaction.channel.send(content=f"Something went wrong: {e}")

async def process_stable(interaction, description, num_images, style, user):
  try:
      filenames = await stability_rest(description=description, num_images=num_images, style=style)

      # Create the view for the response
      view = StableButtonView(command="stable", description=description, num_images=num_images, style=style, gen_image=filenames, user=user)

      # Send the generated images along with the view
      await interaction.edit_original_response(content="",attachments=filenames, view=view)
      save_stable(n=num_images)

  except Exception as e:
      await interaction.edit_original_response(content=f"Error generating images: {e}")

async def process_stable_upload(interaction, image_bytes, description, num_images, style, user):
  try:
      filenames = await stability_imagetoimage(description=description, num_images=num_images, style=style, image_bytes=image_bytes)

      # Create the view for the response
      view = StableButtonView(command="stableupload", description=description, num_images=num_images, style=style, gen_image=filenames, user=user)

      # Send the generated images along with the view
      await interaction.edit_original_response(content="",attachments=filenames, view=view)
      save_stable(n=num_images)

  except Exception as e:
      await interaction.edit_original_response(content=f"Error generating images: {e}")

async def handle_play_command(message, bot):
  # Fetch the original message
  original_message = await message.channel.fetch_message(message.reference.message_id)

  # Check if there's an attachment and it's an audio file
  if original_message.attachments and original_message.attachments[0].filename.endswith(('.mp3','.wav')):
      audio_attachment = original_message.attachments[0]

      # Ensure the user is in a voice channel
      if message.author.voice is None:
          return 'failure'

      # Create an audio source from the MP3 file URL
      audio_source = discord.FFmpegPCMAudio(audio_attachment.url)

      # Play the audio in the voice channel
      # Adapt play_from_file according to your bot's structure
      await play_from_file(audio_source, audio_attachment.filename, message, bot, mention=True)
      return 'success'
  else:
    return 'failure'

async def handle_upload_image(message, bot):
  original_message = await message.channel.fetch_message(message.reference.message_id)

  if original_message.attachments and original_message.attachments[0].filename.endswith(('.png', '.jpg', '.jpeg', '.gif')):
    image_attachment = original_message.attachments[0]

    try:

      await process_dalle_upload(message,image_attachment,1,None,True)

      return 'success'
    except:
      return 'failure'
  else:
    return 'failure'

async def handle_mention(message, bot_id, bot):
  
  if message.content.replace(bot.user.mention, '').strip() == "!play":
    result = await handle_play_command(message, bot)
  elif message.content.replace(bot.user.mention, '').strip() == "!dalle":
    result = await handle_upload_image(message, bot)

    if result == "success":
      return
    else:
      pass

  text_of_message = message.content.replace(bot.user.mention, '')
  response = await ask(interaction=message,question=text_of_message,num_context=5,bot_id=bot_id,gpt_model="gpt-4o-mini",mention=True,bot=bot, vision=False)

  if response[0] == "success":
      status, images, prompt, model = response
      await message.channel.send(f"Here are your images using the following prompt using the {model} model: {prompt}", files=images)

  elif response[0] == "speech":
      # Handle speech response if needed
      pass

  elif response[0] == "music":
      # Handle music response if needed
      pass

  else:
      await message.channel.send(f"{response}")

async def eleven_tts(text, voice_id, interaction, bot):
  
  audio,filename = await text_to_speech_elevenlabs(text,voice_id)

  if audio is not None:

    speech = discord.File(BytesIO(audio),filename=filename)

    original_interaction = await interaction.original_response()

    original_interaction_id = original_interaction.id
  
    button_view = PlayInChatButton(original_interaction_id, bot, play_from_file)
  
    await interaction.edit_original_response(content="Here is your TTS output:", attachments=[speech], view=button_view)

  else:
     await interaction.edit_original_response(content="There was an error, please try again.")

async def play_from_file(audio_source, filename, interaction, bot, mention=False, button = False):

  speech_item = SpeechItem(audio_source, title=filename)
  
  await play_music(interaction=interaction, query=None, bot=bot, mention=mention, is_speech=True, speech=speech_item)

  if not button and not mention:
    await interaction.delete_original_response()