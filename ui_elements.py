import discord
from discord import FFmpegPCMAudio
import discord.ext.commands
from typing import Optional
from generation import generate_image, generate_uploaded_image_variation, stability_rest, stability_imagetoimage
from tts import text_to_speech, check_job_status
from save_load import load_image_count, save_stable
import asyncio
from mongodb import db
import tempfile
import os

#Class for the buttons from using /dalle, /dalleupload and /stable
class StableButtonView(discord.ui.View):
  def __init__(self, command, num_images, description: Optional[str] = 'none', style: Optional[str] = 'none', attachment: Optional[discord.Attachment] = None, gen_image = None, img2img = False, old_image = None, user = None, model = 'dall-e-2'):
      
        #initialisations of local variables
        super().__init__(timeout=None)
        self.command = command
        self.description = description
        self.num_images = num_images
        self.style = style
        self.attachment = attachment
        self.img2img = img2img
        self.old_image = old_image
        self.user = user
        self.model = model
        #self.inter = inter
        if len(gen_image) > 1:
          self.gen_image = gen_image
        else:
          self.gen_image = gen_image[0]

  #Image regeneration button
  @discord.ui.button(label='Regenerate Image', custom_id='regenerate_stable',emoji = '🔁')
  async def regenerate_image_button(self, interaction: discord.Interaction, button: discord.ui.Button):

    dalle2_today, dalle3_today = load_image_count()

    # Define a dictionary mapping model names to their daily limits
    daily_limits = {
        "dall-e-2": 50,
        "dall-e-3": 25
    }

    # Check if the model is in the dictionary and if the limit is exceeded
    if self.model in daily_limits and (daily_limits[self.model] < self.num_images + (dalle2_today if self.model == "dall-e-2" else dalle3_today)):
        await interaction.response.send_message("Daily image generation limit reached. Please try again tomorrow.", ephemeral=True)
        return
    
    # Send initial message via interaction.channel.send()
    message_reg = await interaction.channel.send('Regenerating the image. Please wait...')
    await interaction.response.defer()

    #If the img2img button was not previously pressed, regenerate the image according to which command was used.
    comm = ""
    if not self.img2img:
      if self.command == "stable":
        filenames = await stability_rest(description=self.description, num_images=self.num_images, style=self.style)

        if filenames:
          save_stable(n=self.num_images)
          
        comm = "stable"
        
      if self.command == "dalle":
        filenames = await generate_image(prompt=self.description,n=self.num_images,model=self.model)
          
        comm = "dalle"
        
      if self.command == "dalleupload":
        image_bytes = self.attachment
        filenames = await generate_uploaded_image_variation(image_bytes=image_bytes,n=self.num_images)

    #If the img2img button was previously pressed (dalleupload or dalle command has no difference since it uses the previous image)
    else:
      #stable command
      if self.command == "stable":
        self.old_image.fp.seek(0)
        image_bytes = self.old_image.fp.read()
        
        filenames = await stability_imagetoimage(description=self.description, num_images=1, style=self.style, image_bytes=image_bytes)

        if filenames:
          save_stable(n=1)
          
        comm = "stable"

      #dalle or dalleupload command
      else:
        self.old_image.fp.seek(0)
        image_bytes = self.old_image.fp.read()
        
        filenames = await generate_uploaded_image_variation(image_bytes=image_bytes,n=1)
          
        comm = "dalle"

    #Deletes the "loading" message, sends the images with the new buttons.
    if not filenames:
          await message_reg.edit(content="Failed to regenerate images. Please try again.")
          return

    await message_reg.delete()
    
    view = StableButtonView(command=comm,description=self.description, num_images=1, style=self.style, gen_image=filenames,user=self.user, model=self.model)
    
    await interaction.followup.send("Regenerated Image:",files=filenames,view=view)

  #Image to Image button function (img2img)
  @discord.ui.button(label='Image To Image', custom_id='imagetoimage', emoji='♻️')
  async def generate_new_button(self, interaction: discord.Interaction, button: discord.ui.Button):

      dalle2_today, _ = load_image_count()
      if dalle2_today + self.num_images > 50:
        await interaction.response.send_message('Daily image generation limit reached. Please try again tomorrow.', ephemeral=True)
        return
                                                
      #Send the "loading" message.
      if self.model == 'dall-e-3':
        text = "Using DALLE 2 for image to image..."
      else:
        text = 'Making new image. Please wait...'
        
      message = await interaction.channel.send(f'{text}')

      #If the number of images was more than 1, it prompts selecting which image to use for img2img
      if self.num_images > 1:
        select_view = Selecting(self.command, self.num_images, message,self.gen_image,self.style,self.description,user=self.user)
        #Command in the Selecting class
        await select_view.send_message(interaction)

      #If the number of images was 1, skip prompting
      else:
        #For the stable command
        if self.command == "stable":
          text_input_view = TextInputView(attachment=self.gen_image, num_images=self.num_images, style=self.style,message=message,description=self.description,user=self.user)

          #await message.edit(content="Sorry, this is currently being reworked.")
          await interaction.response.send_modal(text_input_view)

        #For the dalle or dalleupload command
        else:
          await interaction.response.defer()
          self.gen_image.fp.seek(0)
          image_bytes = self.gen_image.fp.read()
          new_image = await generate_uploaded_image_variation(image_bytes=image_bytes,n=1)
          await message.delete()
          view = StableButtonView(command="dalle",description=self.description, num_images=1, gen_image=new_image, img2img=True, old_image=self.gen_image,user=self.user, model=self.model)
          await interaction.followup.send("New Image to Image:",files=new_image,view=view)

  #Delete button, deletes the message if the user is the same one that used the /command
  @discord.ui.button(label='Delete', custom_id='delete', emoji='❌')
  async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    if self.user == interaction.user:
      await interaction.message.delete()

    else:
     await interaction.response.send_message("Only the person who first used the command can delete this.", ephemeral=True)

#Function for Selecting class saying if its 1st or 2nd or 3rd image.
def ordinal(n):
    return "%d%s" % (n,"tsnrhtdd"[((n//10%10!=1)*(n%10<4)*n%10)::4])

#Class for the dropdown menu for img2img function to select which image to use
class Selecting(discord.ui.View):
  def __init__(self, command, num_images, message, gen_image, style, description, user = None):
        #Local variable declarations
        super().__init__(timeout=10)
        self.description = description
        self.command = command
        self.num_images = num_images
        self.message = message
        self.message2 = None
        self.gen_image = gen_image
        self.style = style
        self.interacted = False
        self.user = user
        #Uses the ordinal function to print which image number.
        self.options = [
            discord.SelectOption(
                label=f"{i+1}",
                description=f"{ordinal(i+1)} Image"
            ) for i in range(self.num_images)
        ]
        #Declaration allows for a dynamic select menu (changing depending on amount of images)
        self.select_menu = discord.ui.Select(
            placeholder="Choose one of the images.", 
            min_values=1, 
            max_values=1, 
            options=self.options
        )
        #Adds the select menu
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)

  #Sends the image selection view to chat
  async def send_message(self, interaction):
    await interaction.response.defer()
    self.message2 = await interaction.followup.send("Select an image:", view=self)

  #The function called when the user is done selecting options
  async def select_callback(self, interaction):
      #selected_option will be a string like 1 or 2
      selected_option = interaction.data['values'][0]
      # Convert to an integer and subtract 1 to get the index
      selected_index = int(selected_option) - 1
      selected_file = self.gen_image[selected_index]
    
      self.interacted = True
      await self.message2.delete()

      #If it is the stable command, it sends the text prompt
      if self.command == "stable":
        text_input_view = TextInputView(selected_file, self.num_images, self.style,self.message,self.description,user=self.user)
        await interaction.response.send_modal(text_input_view)

      #Else, it generates the image and sends it
      else:
        await interaction.response.defer()
        selected_file.fp.seek(0)
        image_bytes = selected_file.fp.read()
        new_image = await generate_uploaded_image_variation(image_bytes=image_bytes,n=1)
        await self.message.delete()
        view = StableButtonView(command="dalle",description=self.description, num_images=1, gen_image=new_image,img2img=True, old_image=selected_file,user=self.user)
        await interaction.followup.send("New Image to Image:",files=new_image,view=view)

  #If they take too long it deletes the message
  async def on_timeout(self):
    if self.message2 is not None and not self.interacted:
      await self.message2.delete()
    if self.message is not None and not self.interacted:
      await self.message.delete()


#Class for the prompting of the /stable img2img button
class TextInputView(discord.ui.Modal):
    def __init__(self, attachment, num_images, style, message, description,user=None):
        super().__init__(title='Write a similar prompt to guide the new image',timeout=60)

        #Local variable declarations
        self.text_input = discord.ui.TextInput(custom_id='my_input', label='Prompt', required=True)
        self.add_item(self.text_input)
        self.attachment = attachment
        self.description = description
        self.num_images = 1
        self.style = style
        self.message = message
        self.user = user
        self.interacted = False

    #When the prompt is submitted, this function is called.
    async def on_submit(self, interaction: discord.Interaction):
        # Generate a new image using the text input value and the last image URL
        await interaction.response.defer()
        self.attachment.fp.seek(0)
        image_bytes = self.attachment.fp.read()
        new_image = await stability_imagetoimage(description=self.text_input.value, num_images=self.num_images, style=self.style, image_bytes=image_bytes)
        save_stable(n=1)

        #Deletes the "loading" message if it is not empty
        try:
          if self.message is not None:
            await self.message.delete()
        except:
          pass
        
        view = StableButtonView(command="stable",description=self.description, num_images=1,style=self.style,gen_image=new_image,img2img=True, old_image=self.attachment,user=self.user)
        await interaction.followup.send("New Image to Image:",files=new_image,view=view)
        self.interacted = True

    #If they take too long, it deletes the message.
    async def on_timeout(self):
      if self.message is not None and not self.interacted:
        await self.message.delete()

#Class for the dropdown menu of the voices in tts
class TTSSelect(discord.ui.View):
  def __init__(self, matches, text):
        #Local variable declarations
        super().__init__(timeout=650)
        self.matches = matches
        self.text = text
        self.num_matches = len(matches)
        self.interacted = False
        #Uses the ordinal function to print which image number.
        self.options = [
            discord.SelectOption(
                label=f"{matches[i][0]}",
                description=f"'{ordinal(i+1)}' Voice",
                value=f"{matches[i][0]}∏{matches[i][1]}"
            ) for i in range(self.num_matches)
        ]
        #Declaration allows for a dynamic select menu (changing depending on amount of images)
        self.select_menu = discord.ui.Select(
            placeholder="Choose one of the voices.", 
            min_values=1, 
            max_values=1, 
            options=self.options
        )
        #Adds the select menu
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)

  #The function called when the user is done selecting options
  async def select_callback(self, interaction):
      self.interacted = True

      await interaction.response.edit_message(content='Generating the TTS, please wait... (this can take a while)',view=None)
    
      #await interaction.response.defer()
      selected_option = interaction.data['values'][0]
      selected_tuple = tuple(selected_option.split('∏'))
      # Here, selected_option is the token of the selected voice
      selected_token = selected_tuple[1]
      selected_voice = selected_tuple[0]

      # Create a task for the text_to_speech function and let it run in the background
      text_to_speech_task = asyncio.create_task(text_to_speech(message=self.text, token=selected_token))
    
      try:
        audio_file = await asyncio.wait_for(asyncio.shield(text_to_speech_task), timeout=30)
        
      except asyncio.TimeoutError:
        await interaction.message.edit(content="The function is still running and will complete later. A new message will be sent once it is done.",delete_after = 10)
        try:
          audio_file = await asyncio.wait_for(text_to_speech_task, timeout=600)
        except asyncio.TimeoutError:
          await interaction.channel.send("The /tts function took longer than 10 minutes, please try again later. There might be some problems with the TTS server itself, maybe try again tomorrow.")
        else:
          await interaction.channel.send(f"Here is your TTS output, using the '{selected_voice}' voice:", file=audio_file)
        return
      
      except:
        await interaction.message.edit(content="There was an error, please try again.")
        return
        
      if audio_file == "None":
        #await self.message2.delete()
        await interaction.message.edit(content="There was an error, please try again with a different name")
        
      else:
        #await self.message2.delete()
        #await interaction.followup.send("Here is your TTS output:", file=audio_file)
        await interaction.message.edit(content=f"Here is your TTS output, using the '{selected_voice}' voice:", attachments=[audio_file])

#Delete button for the /randomimg
class DeleteButtonView(discord.ui.View):
    def __init__(self, message_id: str, user_id: str):
        super().__init__(timeout=None)

        self.message_id = message_id
        self.user_id = user_id

        # Add the button's state to the database
        self.add_button_to_db()


    def add_button_to_db(self):
        button_data = {'message_id': self.message_id, 'user_id': self.user_id}

        # If there are already 100 buttons, remove the oldest one
        if len(db['buttons']) == 100:
            db['buttons'].pop(0)

        # Check if this button already exists in the database
        if button_data not in db['buttons']:
            # Add the new button
            db['buttons'].append(button_data)


    def delete_button_from_db(self):
      if 'buttons' in db.keys():
        # Find and remove the button with the matching message_id
        for i, button in enumerate(db['buttons']):
            if button['message_id'] == self.message_id:
                db['buttons'].pop(i)
                break
    
    @discord.ui.button(label='Delete', style=discord.ButtonStyle.red, custom_id="delete_button")
    async def delete_button_clicked(self, interaction, button):
        # Acknowledge the interaction immediately
        await interaction.response.defer()

        delete_message = None
        if str(interaction.user.id) != self.user_id:
            # Fetch the original user who executed the command
            original_user = await interaction.guild.fetch_member(int(self.user_id))
            delete_message = await interaction.followup.send(f'Only the user of the command can delete the message. {original_user.mention}, {interaction.user} wants you to delete this message.')
            return
        #print(f"self.message_id = {self.message_id}")
        # Fetch the message
        message = await interaction.channel.fetch_message(self.message_id)
        #print(f"message = {message}\nself.message_id = {self.message_id}")
        # Try to delete the message
        try:
            await message.delete()
            await interaction.followup.send('Message deleted!', ephemeral=True)
            self.delete_button_from_db()
            if delete_message is not None:
              delete_message.delete()
        except discord.NotFound:
            # Message doesn't exist, delete the record from the database
            self.delete_button_from_db()
            await interaction.followup.send('Message already deleted!', ephemeral=True)
            if delete_message is not None:
              delete_message.delete()
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to delete the message!", ephemeral=True)
        except discord.errors.NotFound as e:
            await interaction.followup.send(f"Message not found: {e}",ephemeral=True)
        except Exception as e:
            # Unexpected error, log it for debugging
            print(f"Failed to delete message: {e}")


class PlayInChatButton(discord.ui.View):
    def __init__(self, original_interaction_id, bot, play_from_file_func):
        super().__init__(timeout=None)
        self.bot = bot
        self.original_interaction_id = original_interaction_id
        self.play_from_file = play_from_file_func
        self.add_button_to_db(self.original_interaction_id)

    def add_button_to_db(self, audio_file_path):
      # Key for storing audio file paths in the database
      db_key = "play_in_chat_buttons"
      # Fetch the current list of audio file paths or initialize an empty list if it doesn't exist
      audio_file_paths = db.get(db_key, [])

      # Check if the audio file path is already in the database
      if audio_file_path in audio_file_paths:
        # Audio file path already exists, do not add it again
        return
      
      # Ensure the list does not exceed 100 entries
      if len(audio_file_paths) >= 100:
          # Remove the oldest entry
          audio_file_paths.pop(0)

      # Append the new audio file path to the list
      audio_file_paths.append(audio_file_path)
      # Save the updated list of audio file paths back to the database
      db[db_key] = audio_file_paths

    @discord.ui.button(label="Play in Voice Chat", style=discord.ButtonStyle.green, custom_id="play_in_voice_chat")
    async def play_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
      try:
        original_interaction = await interaction.channel.fetch_message(self.original_interaction_id)
      except:
        await interaction.response.send_message("Something went wrong... Try replying to this message with '!play' instead.", ephemeral = True)
        return

      # Check for an audio attachment in the original interaction
      if original_interaction.attachments and original_interaction.attachments[0].filename.endswith(('.mp3', '.wav')):
        audio_attachment = original_interaction.attachments[0]
        # Create an FFmpeg audio source from the attachment URL
        audio_source = discord.FFmpegPCMAudio(audio_attachment.url)

        # Play the audio in the user's voice channel
        await self.play_from_file(audio_source, audio_attachment.filename, interaction, self.bot, button=True)

      # Acknowledge the button click
        await interaction.response.send_message("Playing audio file in voice chat...", ephemeral=True)
      else:
        await interaction.response.send_message("Something went wrong... Try replying to this message with '!play' instead.", ephemeral=True)
