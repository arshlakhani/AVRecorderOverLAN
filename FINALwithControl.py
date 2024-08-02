import requests
import time
import pyaudio
from flask import Flask, Response, render_template_string
import cv2
import os
import signal
import subprocess
import sys
import threading
import wave
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options

app = Flask(__name__)

html_temp = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="ie=edge">
    <title>Audio Streaming</title>
</head>
<body>
    <h1>Audio Streaming</h1>
    <img src="/video_feed" width="640" height="480">
    <audio id="audio" controls autoplay>
        <source src="{{ url_for('audio') }}" type="audio/x-wav">
        Your browser does not support the audio element.
    </audio>
</body>
</html>
'''

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000  # Updated sample rate
CHUNK = 2048

audio_stream = pyaudio.PyAudio()
recording_audio = True
frames_audio = []

vid = cv2.VideoCapture(0)
if not vid.isOpened():
    print("Error: Camera not detected.")
    sys.exit()

fourcc = cv2.VideoWriter_fourcc(*'XVID')
width = int(vid.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(vid.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"Video Resolution: {width}x{height}")
out = cv2.VideoWriter('output_video.avi', fourcc, 20.0, (width, height))

def genHeader(sampleRate, bitsPerSample, channels):
    datasize = 2000 * 10 ** 6
    o = bytes("RIFF", 'ascii')
    o += (datasize + 36).to_bytes(4, 'little')
    o += bytes("WAVE", 'ascii')
    o += bytes("fmt ", 'ascii')
    o += (16).to_bytes(4, 'little')
    o += (1).to_bytes(2, 'little')
    o += (channels).to_bytes(2, 'little')
    o += (sampleRate).to_bytes(4, 'little')
    o += (sampleRate * channels * bitsPerSample // 8).to_bytes(4, 'little')
    o += (channels * bitsPerSample // 8).to_bytes(2, 'little')
    o += (bitsPerSample).to_bytes(2, 'little')
    o += bytes("data", 'ascii')
    o += (datasize).to_bytes(4, 'little')
    return o

def Sound():
    bitspersample = 16
    wav_header = genHeader(RATE, bitspersample, CHANNELS)
    stream = audio_stream.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True,
                               input_device_index=None, frames_per_buffer=CHUNK)
    first_run = True
    print("Starting audio recording...")
    while recording_audio:
        if first_run:
            data = wav_header + stream.read(CHUNK)
            first_run = False
        else:
            data = stream.read(CHUNK)
        frames_audio.append(data)
        yield data
    print("Stopping audio recording...")
    stream.stop_stream()
    stream.close()

def gen_frames():
    print("Starting video streaming...")
    while True:
        success, frame = vid.read()
        if not success:
            print("Error: Failed to capture video frame.")
            break
        # Write frame to video file
        out.write(frame)
        # Encode the frame in JPEG format
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            print("Error: Failed to encode video frame.")
            break
        frame = buffer.tobytes()
        # Yield the frame to the Flask server
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

def record_audio(output_audio_file):
    global frames_audio
    print(f"Saving audio to {output_audio_file}...")
    wf = wave.open(output_audio_file, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(audio_stream.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames_audio))
    wf.close()

def signal_handler(sig, frame):
    global recording_audio
    print('Stopping recording...')
    recording_audio = False
    time.sleep(2)  # Give time to ensure all frames are processed
    record_audio('output_audio.wav')
    vid.release()
    out.release()
    sys.exit(0)

def get_unique_filename(base_filename, extension):
    filename = f"{base_filename}{extension}"
    counter = 1
    while os.path.exists(filename):
        filename = f"{base_filename}{counter}{extension}"
        counter += 1
    return filename

def merge_audio_video(video_file1, audio_file1, output_file1):
    command = [
        'ffmpeg',
        '-i', video_file1,
        '-i', audio_file1,
        '-c:v', 'copy',
        '-c:a', 'aac',
        output_file1
    ]
    print(f"Merging audio and video: {video_file1} + {audio_file1} -> {output_file1}")
    try:
        subprocess.run(command, check=True)
        print("Merge successful!")
        if os.path.exists(video_file1):
            os.remove(video_file1)
        if os.path.exists(audio_file1):
            os.remove(audio_file1)
    except subprocess.CalledProcessError as e:
        print("Error during merging:", e)

@app.route('/')
def index():
    return render_template_string(html_temp)

@app.route("/audio")
def audio():
    return Response(Sound(), mimetype="audio/x-wav")

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def check_url(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            print(f"URL {url} is online.")
            return True
    except requests.ConnectionError:
        print(f"Error: Failed to connect to {url}.")
    return False

def execute_code():
    # Your code to execute when the URL is online
    print("URL is online! Executing code...")
    portnum = 5001 #int(input('What port do you want?'))
    
    # Define your base filenames and extensions
    video_base = 'output_video'
    audio_base = 'output_audio'
    output_base = 'final_output'
    video_ext = '.avi'
    audio_ext = '.wav'
    output_ext = '.mp4'

    # Get unique filenames
    video_file = get_unique_filename(video_base, video_ext)
    audio_file = get_unique_filename(audio_base, audio_ext)
    output_file = get_unique_filename(output_base, output_ext)

    # Start Flask server in a separate thread
    video_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=portnum, threaded=True))
    video_thread.start()

    # Start audio recording
    global recording_audio
    recording_audio = True
    audio_thread = threading.Thread(target=record_audio, args=(audio_file,))
    audio_thread.start()

    # Wait for the server to start
    time.sleep(5)

    # Selenium WebDriver setup
    chrome_driver_path = r"C:\Users\Arsh\Downloads\chrome-win64\chrome-win64\chrome.exe"  # Path to your ChromeDriver
    chrome_options = Options()
    chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
    # No headless mode, to show the browser window
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')

    service = ChromeService(executable_path=chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # Open the URL with Selenium WebDriver
        url = 'http://192.168.29.210:5000'
        print(f"Opening URL {url} in browser...")
        
        driver.get(url)
        

        # Wait for the page to load and play the audio
        time.sleep(5)  # Increased sleep time

        # Wait for user to stop the program
        print("Press Ctrl+C to stop.")
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Wait for Flask server to finish
        video_thread.join()
    finally:
        driver.quit()
        # Merge audio and video
        merge_audio_video(video_file, audio_file, output_file)

if __name__ == '__main__':
    url_to_check = "http://192.168.29.210:5000"
    check_interval = 2  # Check every 2 seconds

    while True:
        if check_url(url_to_check):
            ask = input('Person available! Should I start the call? (y/n): ')
            if ask.lower() == 'y':
                execute_code()
                break
            else:
                print("Waiting for confirmation...")
        else:
            print(f"URL {url_to_check} is not online. Retrying in {check_interval} seconds...")
        time.sleep(check_interval)
