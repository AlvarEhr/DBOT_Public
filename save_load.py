from mongodb import db
from dotenv import load_dotenv
import os
import openai
import datetime

#Some global variable initialisations
load_dotenv()
API_KEY = os.environ['API_KEY']
openai.api_key = API_KEY
TOKEN = os.environ['TOKEN']
IMAGE_COUNT_KEY = "image_count"
DALLE3_COUNT = 'dalle3_count'
DATE_KEY = "date"
TOTAL_IMAGE_COUNT_KEY = "total_image_count"
DALLE3_TOTAL_COUNT = 'dalle3_total_count'
STABLE_IMAGES = "stable_images"
TOKENS_USED_TODAY_KEY = "tokens_used_today"
TOTAL_TOKENS_USED_KEY = "total_tokens_used"

#All database loading functions
def load_stable_images():
  if STABLE_IMAGES in db.keys():
    count = int(db[STABLE_IMAGES])
  else:
    count = 0
  return count

def load_total_image_count():
    if TOTAL_IMAGE_COUNT_KEY in db.keys():
        dalle2_count = int(db[TOTAL_IMAGE_COUNT_KEY])
    else:
        dalle2_count = 0

    if DALLE3_TOTAL_COUNT in db.keys():
      dalle3_count = int(db[DALLE3_TOTAL_COUNT])
    else:
      dalle3_count = 0
    return dalle2_count, dalle3_count

def load_image_count():
    if IMAGE_COUNT_KEY in db.keys():
        dalle2_count = int(db[IMAGE_COUNT_KEY])
    else:
        dalle2_count = 0

    if DALLE3_COUNT in db.keys():
      dalle3_count = int(db[DALLE3_COUNT])

    else:
      dalle3_count = 0
      
    return dalle2_count, dalle3_count

def load_date():
    if DATE_KEY in db.keys():
        date = db[DATE_KEY]
    else:
        date = str(datetime.date.today())
    return date


#All database saving functions
def save_stable_images(count):
  db[STABLE_IMAGES] = count

def save_total_image_count(dalle2_count, dalle3_count):
  db[TOTAL_IMAGE_COUNT_KEY] = dalle2_count
  db[DALLE3_TOTAL_COUNT] = dalle3_count

def save_image_count(dalle2_count, dalle3_count):
  db[IMAGE_COUNT_KEY] = dalle2_count
  db[DALLE3_COUNT] = dalle3_count

def save_date(date):
    db[DATE_KEY] = date

def save_dalle(n, model='dall-e-2'):
  dalle2_images_today, dalle3_images_today = load_image_count()
  dalle2_total_images, dalle3_total_images = load_total_image_count()

  if model == 'dall-e-2':
    dalle2_images_today += n
    dalle2_total_images += n
  elif model == 'dall-e-3':
    dalle3_images_today += n
    dalle3_total_images += n
  else:
    print(f'Invalid model: {model}')
    return
    
  save_image_count(dalle2_images_today, dalle3_images_today)
  save_total_image_count(dalle2_total_images, dalle3_total_images)

def save_stable(n):
  global stable_images
  stable_images = load_stable_images()

  stable_images += n
  save_stable_images(stable_images)

#All loading functions
def load_tokens_used_today():
    if TOKENS_USED_TODAY_KEY in db.keys():
        count = int(db[TOKENS_USED_TODAY_KEY])
    else:
        count = 0
    return count

def load_total_tokens_used():
    if TOTAL_TOKENS_USED_KEY in db.keys():
        count = int(db[TOTAL_TOKENS_USED_KEY])
    else:
        count = 0
    return count


#All saving functions
def save_tokens_used_today(count):
    db[TOKENS_USED_TODAY_KEY] = count

def save_total_tokens_used(count):
    db[TOTAL_TOKENS_USED_KEY] = count

def save_tokens(response):
  global tokens_used_today, total_tokens
  tokens_used_today += response.usage.total_tokens
  total_tokens += response.usage.total_tokens
  save_tokens_used_today(tokens_used_today)
  save_total_tokens_used(total_tokens)

#More global variable initialisations
current_date = load_date()
dalle2_images_today, dalle3_images_today = load_image_count()
dalle2_total_images, dalle3_total_images = load_total_image_count()
stable_images = load_stable_images()
tokens_used_today = load_tokens_used_today()
total_tokens = load_total_tokens_used()