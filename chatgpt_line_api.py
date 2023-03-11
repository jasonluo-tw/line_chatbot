from flask import Flask, request
from flask import session
from datetime import timedelta
## 
import openai, os
import io
import json

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage

app = Flask(__name__)

class NamedBufferedWrapper(io.BufferedReader):
    def __init__(self, buffer, name=None, **kwargs):
        vars(self)['name'] = name
        super().__init__(buffer, **kwargs)

    def __getattribute__(self, name):
        if name == 'name':
            return vars(self)['name']
        return super().__getattribute__(name)


@app.route("/", methods=['POST'])
def linebot():
    global conv_dicts
    body = request.get_data(as_text=True)
    chat_log = ""
    reply = None
    try:
        json_data = json.loads(body)
        ## Get the access token and secret
        access_token = os.environ['LINE_ACCESS_TOKEN']
        secret = os.environ['LINE_SECRET']

        ## verify the token
        line_bot_api = LineBotApi(access_token)
        handler = WebhookHandler(secret)
        ## add header
        signature = request.headers['X-Line-Signature']
        handler.handle(body, signature)
        tk = json_data['events'][0]['replyToken']
        kind = json_data['events'][0]['message']['type']
        ## get userId
        userId = json_data['events'][0]['source']['userId']
        if userId in conv_dicts:
            chat_log = conv_dicts[userId]
        
        if kind == 'audio':
            if json_data['events'][0]['message']['contentProvider']['type'] == 'line':
                msg_id = json_data['events'][0]['message']['id']
                msg_content = line_bot_api.get_message_content(msg_id)
                audio_binary = b''.join([chunk for chunk in msg_content.iter_content()])
                io_b = io.BytesIO(audio_binary)
                stdin = NamedBufferedWrapper(io_b, name="stdin.m4a")
                transcript = openai.Audio.transcribe("whisper-1", stdin)
                text = transcript['text']
                reply, chat_log = AI_reply(text, chat_log)
                conv_dicts[userId] = chat_log
                reply = f'Input: {text}\nAI Reply:{reply}'

            reply_kind = 'text'

        elif kind =='text':
            msg = json_data['events'][0]['message']['text']  # get the message from line
            print("msg:", msg)
            splits = msg.split(':')
            if len(splits) >= 2 and splits[0].strip() == 'imagine':
                prompt = ''.join(splits[1:])
                img_url = AI_create_img(prompt)
                reply_kind = 'image'

            else:
                reply, chat_log = AI_reply(msg, chat_log)
                conv_dicts[userId] = chat_log
                reply_kind = 'text'
        else:
            reply = 'Can not deal with this'
            reply_kind = 'text'
        
        ## reply the message
        if reply_kind == 'text':
            line_bot_api.reply_message(tk, TextSendMessage(reply))
        elif reply_kind == 'image':
            line_bot_api.reply_message(tk, ImageSendMessage(original_content_url=img_url, preview_image_url=img_url))

        if reply is not None:
            print("reply:", reply)
            print(f'######## chat log - userId:{userId} #############')
            print(chat_log)
            print('######### chat log end ################')
            ###TODO:
            ##conv_dicts = {}
    except Exception as e:
        print(e)
        #print("body", body)

    return 'OK' # The 'OK' is used to verify, and this cannot be deleted

def AI_create_img(prompt, size=512):
    prompt = prompt.strip()
    response = openai.Image.create(
        prompt=prompt,
        n=1,
        size=f"{size}x{size}"
    )

    img_url = response['data'][0]['url']

    return img_url

def AI_reply(msg, chat_log=""):
    start_chat_log = [{"role": "system", "content": "You are a helpful assistant."}]
    if chat_log == "":
        chat_log = start_chat_log

    user_input = {"role": "user", "content": msg}
    chat_log.append(user_input)
    response = completion.create(
        model="gpt-3.5-turbo",
        messages=chat_log
    )

    reply = response['choices'][0]['message']['content']

    chat_log.append({"role": "assistant","content": reply})


    if len(chat_log) >= 20:
        print("Longer than 20, delete the first two contents")
        chat_log = start_chat_log + chat_log[3:]

    return reply, chat_log


if __name__ == "__main__":
    global conv_dicts

    openai.api_key = os.environ["OPENAI_API_KEY"]
    completion = openai.ChatCompletion()

    conv_dicts = {}
    ## this is for session
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=60)
    app.secret_key = os.environ["FLASK_SECRET_KEY"]

    app.run()

