import os
import openai
import aiohttp
from io import BytesIO
from PIL import Image
import io
import base64
import requests
import discord
import tempfile
import asyncio
from save_load import save_dalle

#Variable initialisations
API_KEY = os.environ['API_KEY']
STAB_KEY = os.environ['STAB_KEY']

#Generate Dalle image to filenames using generate_image_url function
async def generate_image(prompt,model="dall-e-2", n=1, size="1024x1024",response_format="url"):
  
  generated_image_urls = await generate_image_url(prompt=prompt,model=model, n=n)
  
  filenames=[]
  
  async with aiohttp.ClientSession() as session:
    for i, url in enumerate(generated_image_urls):
      async with session.get(url) as response:
        image_bytes = await response.read()
        filenames.append(discord.File(BytesIO(image_bytes), f"generated_image_{i + 1}.png"))
        
  return filenames

#Generates Dalle images to URLs
async def generate_image_url(prompt, n=1, model="dall-e-2", size="1024x1024", response_format="url"):

    if model == "dall-e-3":
      n = 1
  
    response = await asyncio.to_thread(
        openai.images.generate,  # Function to call without parentheses
        model=model,             # Arguments to the function
        prompt=prompt,
        n=n,
        size=size,
        response_format=response_format
    )


    save_dalle(n=n, model=model)
  
    return [image_data.url for image_data in response.data]

#Generates dalle image variations from an original image to URL
async def generate_image_variation(image_bytes, n=1, size="1024x1024", response_format="url"):
  
    image_file = BytesIO(image_bytes)
  
    response = await asyncio.to_thread(
        openai.images.create_variation,  # Function to call without parentheses
        image=image_file,                # Arguments to the function
        n=n,
        size=size,
        response_format=response_format
    )


    save_dalle(n=n)
  
    return [image_data.url for image_data in response.data]

#Generates dalle image variations as filenames from an uploaded image to (/dalleupload command), uses the generate_image_variation command
async def generate_uploaded_image_variation(image_bytes, n=1, size="1024x1024", response_format="url"):
  
  variation_image_urls = await generate_image_variation(image_bytes=image_bytes,n=n)
  
  async with aiohttp.ClientSession() as session:
    filenames = []
    for i, variation_image_url in enumerate(variation_image_urls):
      async with session.get(variation_image_url) as response:
        imagecontent = await response.read()

      filenames.append(discord.File(BytesIO(imagecontent), f"uploaded_variation_{i + 1}.png"))
      
  return filenames

#Generates stable diffusion images using stability.ai to filenames
async def stability_rest(description,num_images,style="none"):
  
  api_key = STAB_KEY
  engine_id = "stable-diffusion-xl-beta-v2-2-2"
  api_host = os.getenv('API_HOST', 'https://api.stability.ai')

  
  json_body = {
    "text_prompts": [
        {
            "text": description
        }
    ],
    "cfg_scale": 8,
    "height": 512,
    "width": 512,
    "samples": num_images,
    "steps": 50
  }

  if style != "none":
    json_body["style_preset"] = style

  response = await asyncio.to_thread(
      requests.post,  # Function to call without parentheses
      f"{api_host}/v1/generation/{engine_id}/text-to-image",  # First argument
      headers={
          "Content-Type": "application/json",
          "Accept": "application/json",
          "Authorization": f"Bearer {api_key}"
      },
      json=json_body
  )


  if response.status_code != 200:
    raise Exception("Non-200 response: " + str(response.text))

  data = response.json()
  filenames = []

  for i, artifact in enumerate(data["artifacts"]):
        img = Image.open(io.BytesIO(base64.b64decode(artifact["base64"])))
        byte_arr = io.BytesIO()
        img.save(byte_arr, format='PNG')
        byte_arr.seek(0)
        filenames.append(discord.File(byte_arr, f"v1_txt2img_{i}.png"))
    
  return filenames

#Stability Image to Image function
async def stability_imagetoimage(description, num_images, style, image_bytes):
  
    api_key = STAB_KEY
    engine_id = "stable-diffusion-xl-beta-v2-2-2"
    api_host = os.getenv('API_HOST', 'https://api.stability.ai')

    data = {
        "text_prompts[0][text]": description,
        "text_prompts[0][weight]": 0.5,
        "image_strength": 0.4,
        "init_image_mode": "IMAGE_STRENGTH",
        "cfg_scale": 8,
        #"height": 512,
        #"width": 512,
        "samples": num_images,
        "steps": 50
    }

    if style != "none":
        data["style_preset"] = style

    # If image bytes are provided, convert them to base64 and include it in the json_body
    files = {}
# If image bytes are provided, wrap them in a BytesIO object and add them to the files dictionary
    if image_bytes:
      with tempfile.NamedTemporaryFile(delete=False) as temp:
        temp.write(image_bytes)
        temp.seek(0)
        files["init_image"] = open(temp.name, 'rb')

    try:
      response = await asyncio.to_thread(
          requests.post,  # Function to call without parentheses
          f"{api_host}/v1/generation/{engine_id}/image-to-image",  # First argument
          headers={
              #"Accept": "application/json",
              "Authorization": f"Bearer {api_key}"
          },
          files=files,
          data=data,
          timeout=30
      )
    except requests.Timeout:
      return []
  
    if "init_image" in files:
      files["init_image"].close()
      os.unlink(files["init_image"].name)

    if response.status_code != 200:
        raise Exception("Non-200 response: " + str(response.text))

    data = response.json()
    filenames = []

    for i, artifact in enumerate(data["artifacts"]):
        img = Image.open(io.BytesIO(base64.b64decode(artifact["base64"])))
        byte_arr = io.BytesIO()
        img.save(byte_arr, format='PNG')
        byte_arr.seek(0)
        filenames.append(discord.File(byte_arr, f"v1_txt2img_{i}.png"))
    
    return filenames