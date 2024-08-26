from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
import azure.cognitiveservices.speech as speechsdk
import pandas as pd
from pydub import AudioSegment
from openai import AzureOpenAI
from moviepy.editor import *
from moviepy.video.tools.subtitles import SubtitlesClip
from moviepy.config import change_settings

def process_boundary_event(evt):
    result = {label[1:]: val for label, val in evt.__dict__.items()}
    result["boundary_type"] = result["boundary_type"].name
    
    return result

def get_key(vault_name, secret_name):

    KVUri = f"https://{vault_name}.vault.azure.net"
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=KVUri, credential=credential)
    key = client.get_secret(secret_name).value
    
    return key

def text_to_speech(speech_type, speech_key, service_region, text):

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
    speech_config.speech_synthesis_voice_name = speech_type
    speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)

    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

    word_boundaries = []

    speech_synthesizer.synthesis_word_boundary.connect(lambda evt: word_boundaries.append(process_boundary_event(evt)))

    result = speech_synthesizer.speak_text_async(text).get()

    word_boundary_df = pd.concat([pd.DataFrame(d, index = [0]) for d in word_boundaries])
    word_boundary_df['duration_milliseconds'] = word_boundary_df['duration_milliseconds']
    word_boundary_df = word_boundary_df[['audio_offset', 'duration_milliseconds', 'boundary_type', 'text']]
    word_boundary_df = word_boundary_df.reset_index()
    
    return [word_boundary_df, result.audio_data, result.audio_duration, text]


def generate_text(openai_key, messages):
    client = AzureOpenAI(
    azure_endpoint = "https://eastus.api.cognitive.microsoft.com/openai/deployments/gpt-35-turbo/chat/completions?api-version=2023-03-15-preview", 
    api_key=openai_key,  
    api_version="2024-03-01-preview"
    )

    response = client.chat.completions.create(
        model="brainrot-openai-deployment", # Model = should match the deployment name you chose for your 0125-Preview model deployment
        response_format={ "type": "text" },
        messages = messages
        )

    result = response.choices[0].message.content

    return result

def generate_quiz_video(subtitles, answer_data, audio_path, output_path):
    # background video
    text_x_offset = 0.08
    vid = VideoFileClip(filename='vid_folder/vid.mp4').resize(width=1080, height=1920)

    # subtitles
    generator = lambda txt: TextClip(txt, font='Impact', fontsize=120, color='white', stroke_width=3, stroke_color='black')
    subtitle_clip = SubtitlesClip(subtitles, generator)

    title_card = TextClip('GENIUS QUIZ', font='Impact', fontsize=200, color='white', stroke_width=3, stroke_color='black', bg_color='red').set_position(('center', 'center'))
    title_card = title_card.set_duration(1)

    permanent_texts = [
        TextClip('Easy', font='Impact', fontsize=120, color='green', stroke_width=3, stroke_color='black').set_position((text_x_offset, 0.05), relative = True),
        TextClip('Moderate', font='Impact', fontsize=120, color='yellow', stroke_width=3, stroke_color='black').set_position((text_x_offset, 0.35), relative = True),
        TextClip('IMPOSSIBLE', font='Impact', fontsize=120, color='red', stroke_width=3, stroke_color='black').set_position((text_x_offset, 0.65), relative = True)
    ]

    question_font_size = 80
    # question_line = [f'Q{x}. ' for x in range(1,6)]
    question_texts = [
        TextClip('Q1. ', font='Impact', fontsize=question_font_size, color='white', stroke_width=3, stroke_color='black').set_position((text_x_offset, 0.15), relative = True),
        TextClip('Q2. ', font='Impact', fontsize=question_font_size, color='white', stroke_width=3, stroke_color='black').set_position((text_x_offset, 0.25), relative = True),
        TextClip('Q3. ', font='Impact', fontsize=question_font_size, color='white', stroke_width=3, stroke_color='black').set_position((text_x_offset, 0.45), relative = True),
        TextClip('Q4. ', font='Impact', fontsize=question_font_size, color='white', stroke_width=3, stroke_color='black').set_position((text_x_offset, 0.55), relative = True),
        TextClip('Q5. ', font='Impact', fontsize=question_font_size, color='white', stroke_width=3, stroke_color='black').set_position((text_x_offset, 0.75), relative = True)
    ]

    answer_texts = [
        TextClip(f'Q1. {answer_data[0][0]}', font='Impact', fontsize=question_font_size, color='white', stroke_width=3, stroke_color='black').set_position((text_x_offset, 0.15), relative = True).set_start(answer_data[0][1]),
        TextClip(f'Q2. {answer_data[1][0]}', font='Impact', fontsize=question_font_size, color='white', stroke_width=3, stroke_color='black').set_position((text_x_offset, 0.25), relative = True).set_start(answer_data[1][1]),
        TextClip(f'Q3. {answer_data[2][0]}', font='Impact', fontsize=question_font_size, color='white', stroke_width=3, stroke_color='black').set_position((text_x_offset, 0.45), relative = True).set_start(answer_data[2][1]),
        TextClip(f'Q4. {answer_data[3][0]}', font='Impact', fontsize=question_font_size, color='white', stroke_width=3, stroke_color='black').set_position((text_x_offset, 0.55), relative = True).set_start(answer_data[3][1]),
        TextClip(f'Q5. {answer_data[4][0]}', font='Impact', fontsize=question_font_size, color='white', stroke_width=3, stroke_color='black').set_position((text_x_offset, 0.75), relative = True).set_start(answer_data[4][1])
    ]
    # audio clips

    ding_audio = AudioFileClip('assets/ding.mp3').fx(afx.volumex, 0.5)

    ding_clips = [
        ding_audio.set_start(answer_data[x][1]) for x in range(0,5)
    ]
    
    final_audio_clips = []
    audio_clip = AudioFileClip(audio_path)
    background_music_clip = AudioFileClip('assets/L_Theme.mp3').fx(afx.volumex, 0.1)
    final_audio_clips.extend(ding_clips)
    final_audio_clips.append(audio_clip)
    final_audio_clips.append(background_music_clip)
    final_audio = CompositeAudioClip(final_audio_clips)

    final_clips = [vid]
    final_clips.extend(permanent_texts)
    final_clips.extend(question_texts)
    final_clips.extend(answer_texts)
    final_clips.append(title_card)
    final_clips.append(subtitle_clip.set_pos(('center','center')))
    # set subtitles, audio, and trim video size
    result = CompositeVideoClip([vid, subtitle_clip.set_pos(('center','center'))])
    result = CompositeVideoClip(final_clips)
    result.audio = final_audio
    result = result.subclip(0, audio_clip.duration + 1)

    # write to file
    result.write_videofile(output_path, audio_codec = 'aac', fps=30)
    return