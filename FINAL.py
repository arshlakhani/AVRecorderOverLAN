import pyaudio
from flask import Flask, Response, render_template_string
import cv2
import os
import signal
import subprocess
import sys
import threading
import time
import wave
from time import sleep
sleep(10)

def wait_for_camera(camera_index=0, retry_interval=1):
    """
    Waits until the camera is accessible.
    
    Args:
        camera_index (int): Index of the camera to check.
        retry_interval (int): Time in seconds to wait between retries.
    """
    while True:
        cap = cv2.VideoCapture(camera_index)
        if cap.isOpened():
            print("Camera is accessible.")
            cap.release()
            break
        else:
            print("Camera is not accessible. Retrying in {} seconds...".format(retry_interval))
            time.sleep(retry_interval)
def wait_for_audio(retry_interval=5):
    """
    Waits until an audio input device is accessible.
    
    Args:
        retry_interval (int): Time in seconds to wait between retries.
    """
    while True:
        audio_stream = pyaudio.PyAudio()
        num_devices = p.get_device_count()
        audio_accessible = False

        for i in range(num_devices):
            device_info = p.get_device_info_by_index(i)
            if device_info.get('maxInputChannels') > 0:
                audio_accessible = True
                break

        if audio_accessible:
            print("Audio input device is accessible.")
            p.terminate()
            break
        else:
            print("Audio input device is not accessible. Retrying in {} seconds...".format(retry_interval))
            p.terminate()
            time.sleep(retry_interval)
wait_for_camera()
# wait_for_audio()

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
    <audio controls autoplay>
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

recording_audio = False
frames_audio = []

vid = cv2.VideoCapture(0)
fourcc = cv2.VideoWriter_fourcc(*'XVID')
out = cv2.VideoWriter('output_video.avi', fourcc, 30, (int(vid.get(3)), int(vid.get(4))))

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
    while True:
        if first_run:
            data = wav_header + stream.read(CHUNK)
            first_run = False
        else:
            data = stream.read(CHUNK)
        yield data

def gen_frames():
    while True:
        success, frame = vid.read()
        if not success:
            break
        # Write frame to video file
        out.write(frame)
        # Encode the frame in JPEG format
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        # Yield the frame to the Flask server
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

def record_audio(output_audio_file):
    global recording_audio, frames_audio
    chunk = 1024
    format1 = pyaudio.paInt16
    channels = 1  # Use 1 for mono
    rate = 44100

    p = pyaudio.PyAudio()
    stream = p.open(format=format1,
                    channels=channels,
                    rate=rate,
                    input=True,
                    frames_per_buffer=chunk)

    print("Recording audio...")

    while recording_audio:
        data = stream.read(chunk)
        frames_audio.append(data)

    print("Finished recording audio.")

    stream.stop_stream()
    stream.close()
    p.terminate()

    wf = wave.open(output_audio_file, 'wb')
    wf.setnchannels(channels)
    wf.setsampwidth(p.get_sample_size(format1))
    wf.setframerate(rate)
    wf.writeframes(b''.join(frames_audio))
    wf.close()

def signal_handler(sig, frame):
    global recording_audio, audio_thread, video_thread
    print('Stopping recording...')
    recording_audio = False
    
    # Wait for threads to finish
    if audio_thread.is_alive():
        audio_thread.join()
    if video_thread.is_alive():
        video_thread.join()
    
    vid.release()
    out.release()
    
    # Ensure to flush and close video writer
    if not out.isOpened():
        out.release()
    
    merge_audio_video(video_file, audio_file, output_file)
    sys.exit(0)

def get_unique_filename(base_filename, extension):
    filename = f"{base_filename}{extension}"
    counter = 1
    while os.path.exists(os.path.join("..", filename)):
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

if __name__ == '__main__':
    recording_audio = True

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

    # Initialize threads
    audio_thread = threading.Thread(target=record_audio, args=(audio_file,))
    video_thread = threading.Thread(target=gen_frames)

    audio_thread.start()
    video_thread.start()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        app.run(host="0.0.0.0", port=3009, threaded=True)
    finally:
        recording_audio = False
        audio_thread.join()
        video_thread.join()
        vid.release()
        out.release()
        # merge_audio_video(video_file, audio_file, output_file)
