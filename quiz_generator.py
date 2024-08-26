from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
import azure.cognitiveservices.speech as speechsdk
import json
import os
from datetime import timedelta, datetime
import srt
import pandas as pd
import json
from pydub import AudioSegment
from openai import AzureOpenAI
from moviepy.editor import *
import srt
from moviepy.video.tools.subtitles import SubtitlesClip
from moviepy.config import change_settings
import brainrot_util as bu
import azure.functions as func
import random

app = func.FunctionApp()

@app.function_name(name="quizgeneration")
@app.timer_trigger(schedule="0 0 */3 * * *", 
              arg_name="mytimer",
              run_on_startup=True) 
def quizgeneration(mytimer: func.TimerRequest) -> None:
    
    service_region = 'eastus'
    vault_name = os.environ.get("KEY_VAULT_NAME")
    tts_secret_name = "brainrot-tts-key"
    gpt_secret_name = 'brainrot-openai-gpt-key'
    speech_key = bu.get_key(vault_name, tts_secret_name)
    openai_key = bu.get_key(vault_name, gpt_secret_name)

    speech_type = "en-US-GuyNeural"


    with open('assets/quiz_messages.json', 'r') as quiz_message_file:
        messages = json.load(quiz_message_file)

    options = ['general knowledge', 'random']

    topic = random.choice(options)

    if topic == 'random':
        with open('assets/list_of_things.txt') as topic_list:
            topics = topic_list.readlines()
        topic = random.choice(topics)


    topic_text = f'Quiz time! Can you answer these five questions about {topic}?'
    messages = messages['messages']
    prompt_dict = {
      "role": "user",
      "content": [
          {
          "type": "text",
          "text": f"Generate a quiz about {topic}"
          }
      ]
    }

    messages.append(prompt_dict)

    quiz = bu.generate_text(openai_key, messages)
    print(quiz)
    
    qapair = quiz.split('----')

    audio_elements = []

    ctr = 1
    pair_ctr = 1
    for pair in qapair:
        lines = pair.split('\n')

        for line in lines:
            if line != '':

                text_type = f'answer{pair_ctr}'

                if ctr % 2 == 1:
                    line = f'Question {pair_ctr}: {line}'
                    text_type = f'question{pair_ctr}'
                
                if ctr == 1:
                    line = f'{topic_text} {line}'

                res = bu.text_to_speech(speech_type, speech_key, service_region, line)
                res.append(text_type)
                audio_elements.append(res)
                ctr += 1
        
        pair_ctr += 1


    final_text = 'Did you pass this quiz? Comment how many questions you got right and follow for more epic quizzes'

    res = bu.text_to_speech(speech_type, speech_key, service_region, final_text)
    res.append('final')
    audio_elements.append(res)

    transcriptions = []
    sub_index = 1

    total_elapsed_time = timedelta(microseconds=0)

    full_audio = AudioSegment.empty()
    tick_segment = AudioSegment.from_wav('assets/ticking_sound.wav')

    answer_data = []
    subtitle_list = []
    for result_set in audio_elements:
        word_boundary_df = result_set[0]
        audio_data = result_set[1]
        audio_duration = result_set[2]
        text = result_set[3]
        text_type = result_set[4]

        if not 'answer' in text_type:
            for idx, row in word_boundary_df.iterrows():
                if row['boundary_type'] == 'Punctuation':
                    continue
                else:
                    start_delta = timedelta(microseconds=(row['audio_offset']/10)) + total_elapsed_time
                    end_delta = start_delta + row['duration_milliseconds']
                    current_word = row['text'].strip()
                    sub = srt.Subtitle(index = sub_index, start = start_delta, end = end_delta, content = current_word)
                    transcriptions.append(sub)
                    sub_index = sub_index + 1
                    subtitle_list.append(((round(start_delta.total_seconds(), 3), round(end_delta.total_seconds(), 3)), current_word))
        
        else:
            answer_data.append([text, round(total_elapsed_time.total_seconds(), 3)])
        
        
        # getting the total elapsed time allows me to create a timestamp for the captions used for the "ticking" audio
        # between questions and answers

        total_elapsed_time = total_elapsed_time + audio_duration

        full_audio = full_audio + AudioSegment(audio_data)

        if 'question' in text_type:
            end_delta = end_delta + timedelta(seconds=3.5)
            sub = srt.Subtitle(index = sub_index, start = total_elapsed_time, end = end_delta, content = '. . . . .')
            transcriptions.append(sub)
            subtitle_list.append(((round(total_elapsed_time.total_seconds(), 3), round(end_delta.total_seconds(), 3)), '. . . . .'))
            total_elapsed_time = total_elapsed_time + timedelta(seconds=3.5)
            full_audio = full_audio + tick_segment

    now = datetime.now()
    dt_string = now.strftime("%d_%m_%Y_%H_%M_%S_%f")

    filename = f"vid_output/{topic}_quiz_{dt_string}.mp4"
    audio_path = f"audio_output/{topic}_quiz_{dt_string}.wav"
    # audio_data = full_audio.raw_data
    full_audio.export(audio_path, format = 'wav')
    bu.generate_quiz_video(subtitle_list, answer_data, audio_path, filename)
    subtitles = srt.compose(transcriptions)

    with open('full_sub_test.srt', 'w') as sub_file:
        sub_file.write(subtitles)

    