import os
import openai
import tiktoken
from mongodb import db
import discord
import asyncio
import json
from generation import generate_image, stability_rest
from save_load import load_stable_images, load_image_count, save_dalle, save_stable, load_tokens_used_today, load_total_tokens_used, save_tokens
from ui_elements import StableButtonView
from data import valid_styles, tools
from tts_openai import join_call, leave_call, speak_text
from music import play_music

#Variable initialisations
OPENAI_API_KEY = os.environ['API_KEY']
openai.api_key = OPENAI_API_KEY
TOKENS_USED_TODAY_KEY = "tokens_used_today"
TOTAL_TOKENS_USED_KEY = "total_tokens_used"

#Token costs from OpenAI
#TOKEN_COST_PROMPT = 0.00003
#TOKEN_COST_COMPLETION = 0.00006
GPT3_TOKEN_COST = 0.00000015
DAILY_LIMIT = 0.50
TOKENS_LIMIT = int(DAILY_LIMIT / GPT3_TOKEN_COST)#(TOKEN_COST_PROMPT + TOKEN_COST_COMPLETION))

#Token counters loading
tokens_used_today = load_tokens_used_today()
total_tokens = load_total_tokens_used()

#Load the encoding for GPT model
encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")

# Count tokens in text
def count_tokens(text):
    return len(encoding.encode(text))

#Function used to count the tokens used for the /tokencount command in main.py
async def tokens(self, interaction: discord.Interaction):
  global tokens_used_today, total_tokens, TOKENS_LIMIT
  
  tokens_used_today = load_tokens_used_today()
  total_tokens = load_total_tokens_used()
  
  percentage = round((tokens_used_today / TOKENS_LIMIT)*100,2)
  #price = round(tokens_used_today * 0.000002,8)
  await interaction.response.send_message(f"{tokens_used_today} tokens (% {percentage}) have been used today.\nTotal tokens used: {total_tokens}.\nThe token limit is {TOKENS_LIMIT}.", ephemeral=True)

#Adding the contents of a /ask command to the database for use in context
def add_interaction(interaction_id, command, user):
    # Check if 'interactions' key already exists in the database
    author = str(user)
    if 'interactions' in db.keys():
        interactions = db['interactions']
        # If there are already 50 interactions, remove the oldest one
        if len(interactions) == 50:
            interactions.pop(0)
    else:
        interactions = []
    
    # Add the new interaction
    interactions.append({'id': interaction_id, 'author': author, 'command': command})
    # Update the 'interactions' key in the database
    db['interactions'] = interactions


# To get all interactions in the database
def get_interactions():
    if 'interactions' in db.keys():
        return db['interactions']
    else:
        return []

# To get a specific interaction by id from the database
def get_interaction_by_id(interaction_id):
    interactions = get_interactions()
    for interaction in interactions:
        if interaction['id'] == interaction_id:
            author = interaction['author']
            command = interaction['command']
            return author, command
    return None, None

# Count total tokens with limit, including handling for images
def count_total_tokens_with_limit(message_dicts, token_limit, vision_token=50):
    """
    Adds `vision_token` to the token count for every image present in a message.
    """
    truncated_tokens = 0
    truncated_messages = []
    
    for message in reversed(message_dicts):
        content = message['content']
        tokens_in_text = 0

        # Check if content is a list (indicating mixed text and image content)
        if isinstance(content, list):
            for item in content:
                if item['type'] == 'text':
                    tokens_in_text += count_tokens(item['text'])
                elif item['type'] == 'image_url':
                    tokens_in_text += vision_token  # Add vision_token for each image
        else:
            # If it's plain text
            tokens_in_text = count_tokens(content)
        
        # Check token limit
        if truncated_tokens + tokens_in_text > token_limit:
            break
        
        truncated_tokens += tokens_in_text
        truncated_messages.append(message)

    truncated_messages.reverse()  # Reverse the list again to maintain original order
    return truncated_tokens, truncated_messages

#Function for checking if ChatGPT returns a real style from the list for /stable command
def check_style(style):
  #valid_styles imported from data.py
  if style not in valid_styles:
      return "none"
  return style

  
#Function for handling function calling in the ask function
async def handle_images(tool_calls,interaction,mention=False,bot=None):
  dalle2_today, dalle3_today = load_image_count()
  generated_stable_images = load_stable_images()
  # Check if the function to be called is 'generate_image'
  if tool_calls[0].function.name == 'generate_image':
    command = "dalle"
    # Extract the arguments for the function call
    args = json.loads(tool_calls[0].function.arguments)

    num_images = args.get('n',1)
    if num_images > 3:
      num_images = 3

    model = args.get('model',1)
    if model != "dall-e-2" and model != "dall-e-3":
      model = "dall-e-2"

    # Define a dictionary mapping model names to their daily limits
    daily_limits = {
        "dall-e-2": 50,
        "dall-e-3": 25
    }

    # Check if the model is in the dictionary and if the limit is exceeded
    if model in daily_limits and (daily_limits[model] < num_images + (dalle2_today if model == "dall-e-2" else dalle3_today)):
      return ("error", "Daily image generation limit reached. Please try again tomorrow.","generate_image")

    try:
      # Call the actual function in your application code
      images = await generate_image(args['prompt'], n=num_images, model=model)

    except Exception as e:
        return ("error",f"An error occured in your request: {str(e)}","generate_image")

    prompt = args['prompt']

    return ("success",images,prompt,num_images,command,model)

  #if it is the stable function
  if tool_calls[0].function.name == 'generate_stable':
    command = "stable"
    
    args = json.loads(tool_calls[0].function.arguments)

    num_images = args.get('num_images', 1)

    if num_images > 3:
      num_images = 3
    
    style = check_style(args.get('style','none'))

    if generated_stable_images + num_images > 2500:
      return ("error","Sorry, out of images, ask Alvar for some more.","generate_stable")

    try:
      images = await stability_rest(args['description'],num_images,style)

    except Exception as e:
      return ("error", f"An error occured in your request: {e}","generate_stable")

    save_stable(n=num_images)

    model = "stable"

    prompt = args['description']
    return ("success",images,prompt,num_images,command,model)
  if tool_calls[0].function.name == 'play_music':
    return await handle_music(tool_calls,interaction,bot,mention)
  else:
    return await handle_speech(tool_calls,interaction,mention,bot)

async def handle_speech(tool_calls,interaction,mention,bot):
  if tool_calls[0].function.name == 'join':
    await join_call(interaction,mention)
    return("speech", "Joining Channel")

  if tool_calls[0].function.name == 'leave':
    await leave_call(interaction,mention)
    return("speech","Leaving Channel")

  if tool_calls[0].function.name == 'speak':
    args = json.loads(tool_calls[0].function.arguments)
    text = args['text']
    voice = 'onyx'
    await speak_text(interaction, text, voice=voice, mention=mention, bot=bot)

    return("speech","Speaking...")

  else:
    return ("error", "None of the speech functions were chosen", "handle_speech")

async def handle_music(tool_calls,interaction, bot, mention):
  args = json.loads(tool_calls[0].function.arguments)
  query = args['query']
  await play_music(interaction,query,bot,mention)
  return("music",f"Playing {query}")
  
  
#/ask function used in chat.py
async def ask(question, num_context, bot_id, gpt_model, vision, self=None, interaction=None,mention=False, bot = None):
  #The try/catch is if the response is too long (or other discord errors seemingly (semi-obsolete))
  try:
    global tokens_used_today, total_tokens

    current_gpt3_model = "gpt-4o-mini"
    current_gpt4_model = "o1-mini"
    #points to the updated gpt automatically 
    
    if num_context > 150:
      num_context = 150
    if gpt_model == "o1-mini":
      num_context = 4
      gpt_model = current_gpt4_model

    if gpt_model == "gpt-4o-mini":
      gpt_model = current_gpt3_model

    chats = []
    channel = interaction.channel

    token_limit = 2500
    msg_tokens = 0

    recent_image_url = None
    recent_image_msg = None  # To keep track of the message with the most recent image

    #Takes message history for context
    async for msg in channel.history(limit=300):
        if  len(chats) < num_context:
            tokens_in_msg = count_tokens(msg.content)
            if msg_tokens + tokens_in_msg > token_limit:
              break
            msg_tokens += tokens_in_msg

            chats.append(msg)

  
    chats.reverse()

    if vision == True:
      for msg in chats:
        # Check for attachments and track the most recent image
        if msg.attachments:
          for att in msg.attachments:
            if att.content_type and "image" in att.content_type:
                recent_image_url = att.url  # Always update to the most recent image URL
                recent_image_msg = msg  # Store the message containing the image
    
    message_dicts = []

    if gpt_model == current_gpt3_model:
      message_dicts.append({"role": "system", "content": "You are a helpful assistant in a Discord server named DBOT#5557. You should answer or respond to the user to the best of your abilities consicely unless asked otherwise. The usable commands are found using the `/help {optional: command}` command."})

    #Adds all the messages from the chat in order for the context
    for msg in chats:
        #If it is reading the current command, it skips it
        if msg.interaction and msg.interaction.id == interaction.id:
            continue  # Skip the current command

        #If the ID is the bot's then it sets the role to assistant
        role = "assistant" if msg.author.id == bot_id else "user"

        #If it is a / command, then it gets the command and author of it
        if msg.type == discord.MessageType.chat_input_command:
          author, command = get_interaction_by_id(msg.interaction.id)
          #And if it is not empty (i.e. if it exists in the database) it    adds it
          if author is not None and command is not None:
            message_dicts.append({"role": "user", "content": f'{author}:{command}'})

        if role == "assistant":
          message_dicts.append({"role": role, "content": f'{msg.content}'})

        elif vision == True and gpt_model is not current_gpt4_model:
            # Check if the message is the one with the most recent image
            if msg == recent_image_msg and recent_image_url:
                # Add the image in the correct position
                message_dicts.append({
                    "role": role,
                    "content": [
                        {"type": "text", "text": f"{msg.author}: {msg.content}"},
                        {"type": "image_url", "image_url": {"url": recent_image_url}}
                    ]
                })

        else:
          #If it is not a command
          message_dicts.append({"role": role, "content": f'{msg.author}:{msg.content}'})

    #The actual question asked in the /ask command
    message_dicts.append({"role" : "user", "content": f'{question}'})
    
    truncated_tokens, truncated_messages = count_total_tokens_with_limit(message_dicts, token_limit)

    print(len(truncated_messages))
    
    if tokens_used_today + truncated_tokens > TOKENS_LIMIT:
        if mention:
          return "Daily token limit reached. Please try again tomorrow."
          
        await interaction.edit_original_response(content="Daily token limit reached. Please try again tomorrow.")
        return

    #Asking the question with 3 retries
    retries = 3
    for i in range(retries):
      try:
          # Set max_tokens based on the GPT model
          max_tokens = 1000 if gpt_model == current_gpt3_model else 200

          # Check for the model and modify parameters accordingly
          if gpt_model == current_gpt4_model:
              response = await asyncio.to_thread(
                openai.chat.completions.create,  # Function to call
                model=gpt_model,               # Arguments to the function
                messages=truncated_messages
              )
          else:
               response = await asyncio.to_thread(
                  openai.chat.completions.create,  # Function to call
                  model=gpt_model,               # Arguments to the function
                  messages=truncated_messages,
                  tools=tools,
                  tool_choice="auto",
                  temperature=0.7,
                  max_tokens=max_tokens
                )
          #If all is good    
          break
      
      except openai.APIError:
        print("OpenAI API error in ask function")
        if i < retries - 1:  # No delay on the last attempt
            await asyncio.sleep(2)  # Wait for 2 seconds before the next retry
        
      except Exception as e:
        # Send a message to the user
        if mention:
          return f"Something went wrong: {e}"
        await interaction.followup.send(f"Sorry, something went wrong: {e}. Please try again later.")
        
    else:
      if mention:
        return "OpenAI API error, failed after 3 retries. Please try again later."
      await interaction.followup.send("OpenAI API error, failed after 3 retries. Please try again later.")
      
    save_tokens(response=response)

    message = response.choices[0].message

    # Check if a function call was generated in the response
    if response.choices[0].message.tool_calls:
      tool_calls = response.choices[0].message.tool_calls
      result = await handle_images(tool_calls,interaction,mention,bot)

      #If the result from handle_images is successful, send the image to chat
      if result[0] == "success":
        status, images, prompt, num_images, command, model = result

        #If it was a mention, then don't include the view
        if mention:
          return status, images, prompt, model
          
        view = StableButtonView(command=command,description=prompt, num_images=num_images,gen_image=images,user=interaction.user,model=model)

        #Send the image with the button views
        await interaction.edit_original_response(content=f"Here are your images using the following prompt using the {model} model: {prompt}" ,attachments=images, view=view)

      #If the result of handle_images was an error, send the result to chatGPT and let it process the error for a second response with only the 5 most recent messages plus error message.
      elif result[0] == "error":
        status, error_message, function_name = result
        print(f"Error: {error_message}")
        second_response = await asyncio.to_thread(
            openai.chat.completions.create,  # Function to call without parentheses
            model=current_gpt3_model,      # Arguments to the function
            messages=truncated_messages[-5:] + [
                message,
                {
                    "role": "function",
                    "name": function_name,
                    "content": error_message,
                },
            ],
        )

        save_tokens(response=second_response)
        
        answer = second_response.choices[0].message.content.strip()
        answer = answer[:2000]

        if mention:
          return answer
        
        await interaction.edit_original_response(content=answer)

      elif result[0] == "speech":
        #text = result[1]
        if mention:
          return result
        else:
          pass
          #await interaction.followup.send(text)
          #await message.delete()
      elif result[0] == "music":
        if mention:
          return result
        else:
          #await interaction.followup.send(result[1])
          pass

    else:
      answer = response.choices[0].message.content.strip()
      answer = answer[:2000]

      if mention:
        return answer

      await interaction.edit_original_response(content=answer)
  
  except discord.errors.HTTPException as e:
    if mention:
      return f"Response Too Long: {str(e)}"
      
    await interaction.followup.send(f"Response Too Long: {str(e)}")