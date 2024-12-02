from typing import Literal

#command info for the /help command
command_info = {
    "/help": ("Gives help with the different commands available from DBOT. Can also help with specific commands.", "Usage: `/help {optional: command}`", "Example: `/help command: /ask`"),  
    "/voices": ("Lists available voices for text-to-speech conversion. Can be filtered by an optional voice name.", "Usage: `/voices {optional: voice}`", "Example: `/voices` or `/voices voice: Trump`"),
    "/ask": ("Asks a question to ChatGPT. Optionally, the number of previous messages to consider as context and the specific GPT model can be provided. If GPT-4, then no context can be given. This can also be used to generate images by just asking ChatGPT to do so.", "Usage: `/ask {required: question} {optional: num_context} {optional: gpt_model}`", "Example: `/ask question: What is the capital of France?`"),
    "/dalle": ("Generates an image based on a provided text prompt using DALL-E. Optionally, the number of images to generate can be specified.", "Usage: `/dalle {required: prompt} {optional: num_images}`", "Example: `/dalle prompt: A sunset over the mountains num_images: 3`"),
    "/dalleurl": ("Generates a URL to an image based on a provided text prompt using DALL-E. Optionally, the number of images to generate can be specified.", "Usage: `/dalleurl {required: prompt} {optional: num_images}`", "Example: `/dalleurl prompt: A sunset over the mountains num_images: 3`"),
    "/dalleupload": ("Generates variations of an attached image using DALL-E. Optionally, the number of variations to generate can be specified.", "Usage: `/dalleupload {required: attached image} {optional: num_images}`", "Example: `/dalleupload {attached_image.jpg} num_images: 3`"),
    "/stable": ("Generates an image based on a provided text prompt using Stable Diffusion. Optionally, the number of images to generate and a specific style can be specified.", "Usage: `/stable {required: prompt} {optional: num_images} {optional: style}`", "Example: `/stable prompt: A sunset over the mountains num_images: 3 style: none`"),
    "/stableupload": ("Generates variations of an attached image using Stable Diffusion. Optionally, the number of variations to generate and a specific style can be specified.", "Usage: `/stableupload {required: attached image} {optional: num_images} {optional: style}`", "Example: `/stableupload {attached_image.jpg} num_images: 3 style: none`"),
    "/tts": ("Generates text-to-speech audio for a provided message using a specified voice.", "Usage: `/tts {required: message} {required: voice}`", "Example: `/tts message: Hello world voice: Trump`"),
    "/eleven_labs": ("Generates text-to-speech audio using ElevenLabs AI and one of a select few chosen voices.", "Usage: `/eleven_labs {required: message} {optional: voice}`", "Example: `/eleven_labs message: Hellow I am person1`"),
    "/randomimg": ("Goes through message history and finds 3 random images and sends it to chat. Optional message history variable, max of 5000, default of 2000 messages in chat history.", "Usage: `/randomimg {optional: history}`", "Example: `/randomimg history: 3000`"),
    "/join": ("Joins the voice channel that the user is in.", "Usage: `/join`", "Example: `/join`"),
    "/leave": ("Leaves the current voice channel.", "Usage: `/leave`", "Example: `/leave`"),
    "/speak": ("Speaks the given text in the voice channel.", "Usage: `/speak {text}`", "Example: `/speak text: Hello everyone`"),
    "/play": ("Plays a song from YouTube based on the search query or URL.", "Usage: `/play {query}`", "Example: `/play query: Never Gonna Give You Up`"),
    "/playfromfile": ("Plays a song from an mp3 file into your voice channel.", "Usage: `/playfromfile {attachment: mp3 file}`", "Example: `/playfromfile {attachment: audio_file.mp3}`"),
    "/skip": ("Skips the current song and plays the next one in the queue.", "Usage: `/skip`", "Example: `/skip`"),
    "/queue": ("Shows the current music queue.", "Usage: `/queue`", "Example: `/queue`"),
    "/playnext": ("Adds a song to the front of the queue to be played next.", "Usage: `/playnext {query}`", "Example: `/playnext query: Bohemian Rhapsody`"),
    "/pause": ("Pauses the currently playing song.", "Usage: `/pause`", "Example: `/pause`"),
    "/resume": ("Resumes a paused song.", "Usage: `/resume`", "Example: `/resume`"),
    "/stop": ("Stops playing music and clears the music queue.", "Usage: `/stop`", "Example: `/stop`"),
    "/stats" : ("Shows how many times each person has used a specified word in chat", "Usage: `/stats {required: word} {optional: history}`", "Example: `/stats word: hello history: 2000`"),
    "@-mention": ("Ask a question to ChatGPT when mentioning the bot. The context will be the 5 most recent messages and the model used will be gpt-3.5-turbo.", "Usage: `@DBOT {required: question}`", "Example: `@DBOT What is the tallest mountain?`")
}

#The different style options for /stable
StyleType = Literal["none","3d-model","analog-film","anime","cinematic","comic-book","digital-art","enhance","fantasy-art","isometric","line-art","low-poly","modeling-compound","neon-punk","origami","photographic","pixel-art","tile-texture"]

#Valid styles for /ask function
valid_styles = ["3d-model", "analog-film", "anime", "cinematic", "comic-book", "digital-art", "enhance", "fantasy-art", "isometric", "line-art", "low-poly", "modeling-compound", "neon-punk", "origami", "photographic", "pixel-art", "tile-texture"]

# Existing functions for /ask ChatGPT stuff
tools = [
    {
        "type": "function",
        "function": {
        "name": "generate_image",
        "description": "Generates an image based on a prompt using DALLE. The more descriptive and detailed the prompt, the better.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string", "description": "The prompt to generate the image from"
                },
                "n": {
                    "type": "integer", "description": "The number of images to generate"
                },
                "model": {
                    "type": "string",
                    "description": "The model used to generate the images. The options are: dall-e-2 and dall-e-3"
                },
            },
            "required": ["prompt"],      
          },
        },
    },
    {
        "type": "function",
        "function": {
        "name": "generate_stable",
        "description": "Generates an image based on a prompt using Stable Diffusion. The more descriptive and detailed the prompt, the better.",   
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string", "description": "The prompt to generate the image from"
                },
                "num_images": {
                    "type": "integer", "description": "The number of images to generate"
                },
                "style": {
                    "type": "string", "description": "Choose one of the following styles: [various styles listed]"
                }
            }, 
            "required": ["description"], 
        },
      },
    },
    # New function 'speak'
    {
        "type": "function",
        "function": {
        "name": "speak",
        "description": "If prompted to do so, speaks the given text in a call. You should answer the given question or speak what the user asks to be spoken.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string", "description": "The text to speak"
                },
            },
            "required": ["text"],
        },
      },
    },
    {
        "type": "function",
        "function": {
        "name": "play_music",
        "description": "Plays music from a given search query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string", "description": "The search query for the music to play."
                }
            },
            "required": ["query"]
        },
      },
    }
]

Commands = Literal["/help", "/voices", "/ask", "/dalle", "/dalleurl", "/dalleupload", "/stable", "/stableupload", "/tts", "/eleven_labs", "/randomimg", "/join", "/leave", "/speak", "/play", "/playfromfile", "/skip", "/queue", "/playnext", "/pause", "/resume", "/stop", "@-mention"]

Voices = Literal["onyx", "alloy", "echo", "fable","nova", "shimmer"]

#Name of people included in the below list removed for privacy reasons
Eleven_Voices = Literal['Person1','Person2','Person3','Person4','Person5','Person6']