import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes, MessageHandler, filters, CommandHandler
from io import BytesIO
import random
from modules.processing import StableDiffusionProcessingTxt2Img, StableDiffusionProcessingImg2Img, process_images
from modules.api.models import *
from modules.call_queue import wrap_queued_call, queue_lock
from modules.txt2img import *
import requests
from PIL import Image, PngImagePlugin
import base64
import io
import webuiapi
from dotenv import load_dotenv

load_dotenv()

TG_TOKEN = os.getenv('TG_TOKEN')
API_URL = os.getenv('API_URL')
PORT= os.getenv('PORT')
api = webuiapi.WebUIApi(host=API_URL, port=PORT)
height = 512
width = 512

baseurl = f"http://{API_URL}:{PORT}/sdapi/v1"
def image_to_bytes(image):
    bio = BytesIO()
    bio.name = 'image.jpeg'
    image.save(bio, 'JPEG')
    bio.seek(0)
    return bio
def b64_img(image: Image):
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_base64 = 'data:image/png;base64,' + str(base64.b64encode(buffered.getvalue()), 'utf-8')
    return img_base64
def get_try_again_markup():
    keyboard = [[InlineKeyboardButton("Try again", callback_data="TRYAGAIN"), InlineKeyboardButton("Variations", callback_data="VARIATIONS")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return reply_markup

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Help!")

def img_to_img_generate(prompt, photo, seed=None):
    seed = seed if seed is not None else random.randint(10000, 100000)
    json = {
        "prompt": prompt,
        "init_images": [b64_img(photo)],
        "seed": seed
    }
    response = requests.post(url=f'{baseurl}/txt2img', json=json)
    r = response.json()
    images = []
    if 'images' in r.keys():
        images = [Image.open(io.BytesIO(base64.b64decode(i))) for i in r['images']]
    elif 'image' in r.keys():
        images = [Image.open(io.BytesIO(base64.b64decode(r['image'])))]
    return images[0]
def generate_image(prompt, seed=None, photo=None, variation=None):
    seed = seed if seed is not None else random.randint(10000, 100000)
    if photo is not None:
        init_image = Image.open(BytesIO(photo)).convert("RGB")
        # if not variation:
        #     print("No variation")
        init_image = init_image.resize((height, width))
        result1 = img_to_img_generate(prompt, init_image, seed=seed)
        return result1, seed

    else :
        result1 = api.txt2img(prompt=prompt,
                              negative_prompt="ugly, out of frame",
                              seed=seed,
                              styles=["anime"],
                              cfg_scale=7,
                              )
        return result1.image, seed


async def generate_and_send_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(update.message.chat_id)
    progress_msg = await update.message.reply_text("Generating image...", reply_to_message_id=update.message.message_id)
    im, seed = generate_image(prompt=update.message.text)
    generate_image(prompt=update.message.text)
    await context.bot.delete_message(chat_id=progress_msg.chat_id, message_id=progress_msg.message_id)
    await context.bot.send_photo(update.effective_user.id, image_to_bytes(im), caption=f'"{update.message.text}" (Seed: {seed})', reply_markup=get_try_again_markup(), reply_to_message_id=update.message.message_id)
async def generate_and_send_photo_from_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.caption is None:
        await update.message.reply_text("The photo must contain a text in the caption", reply_to_message_id=update.message.message_id)
        return
    progress_msg = await update.message.reply_text("Generating image...", reply_to_message_id=update.message.message_id)
    photo_file = await update.message.photo[-1].get_file()
    photo = await photo_file.download_as_bytearray()
    im, seed = generate_image(prompt=update.message.caption, photo=photo)
    await context.bot.delete_message(chat_id=progress_msg.chat_id, message_id=progress_msg.message_id)
    await context.bot.send_photo(update.effective_user.id, image_to_bytes(im), caption=f'"{update.message.caption}" (Seed: {seed})', reply_markup=get_try_again_markup(), reply_to_message_id=update.message.message_id)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    replied_message = query.message.reply_to_message

    await query.answer()
    progress_msg = await query.message.reply_text("Generating image...", reply_to_message_id=replied_message.message_id)

    if query.data == "TRYAGAIN":
        if replied_message.photo is not None and len(replied_message.photo) > 0 and replied_message.caption is not None:
            photo_file = await replied_message.photo[-1].get_file()
            photo = await photo_file.download_as_bytearray()
            prompt = replied_message.caption
            im, seed = generate_image(prompt, photo=photo)
        else:
            prompt = replied_message.text
            im, seed = generate_image(prompt)
    elif query.data == "VARIATIONS":
        photo_file = await query.message.photo[-1].get_file()
        photo = await photo_file.download_as_bytearray()
        prompt = replied_message.text if replied_message.text is not None else replied_message.caption
        im, seed = generate_image(prompt, photo=photo, variation=True)
    await context.bot.delete_message(chat_id=progress_msg.chat_id, message_id=progress_msg.message_id)
    await context.bot.send_photo(update.effective_user.id, image_to_bytes(im), caption=f'"{prompt}" (Seed: {seed})', reply_markup=get_try_again_markup(), reply_to_message_id=replied_message.message_id)

def start():

    app = ApplicationBuilder().token(TG_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generate_and_send_photo))
    app.add_handler(MessageHandler(filters.PHOTO, generate_and_send_photo_from_photo))
    app.add_handler(CommandHandler("imagine", generate_and_send_photo))
    app.add_handler(CallbackQueryHandler(button))
    app.run_polling()

if __name__ == "__main__":
    start()