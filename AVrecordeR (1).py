#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, division
import numpy as np
import cv2
import pyaudio
import wave
import threading
import time
import subprocess
import os
from pynput import keyboard
from flask import Flask, Response, render_template

a_pressed = False
flask_thread = None

FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 5

audio1 = pyaudio.PyAudio()

def get_next_filename(directory, base_name, extension):
    files = os.listdir(directory)
    matching_files = [f for f in files if f.startswith(base_name) and f.endswith(extension)]

    if not matching_files:
        return f"{base_name}_1{extension}"

    numbers = [int(f[len(base_name)+1:-len(extension)]) for f in matching_files if f[len(base_name)+1:-len(extension)].isdigit()]
    next_number = max(numbers) + 1 if numbers else 1
    return f"{base_name}_{next_number}{extension}"

app = Flask(__name__)

def gen_frames():  
    camera = cv2.VideoCapture(0)  # use 0 for web camera
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    while True:
        success, frame = camera.read()  # read the camera frame
        if not success:
            break
        else:
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            if a_pressed:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')  # concat frame one by one and show result

@app.route('/video_feed')
def video_feed():
    if a_pressed:
        return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    else: 
        return 'None'

@app.route('/')
def index():
    return "Camera feed is available at /video_feed"

def on_press(key):
    global a_pressed
    try:
        if key.char == 'a':  # Detect 'a' key press
            a_pressed = True
    except AttributeError:
        pass

def on_release(key):
    global a_pressed
    try:
        if key.char == 'a':  # Detect 'a' key release
            a_pressed = False
    except AttributeError:
        pass

class VideoRecorder():  
    "Video class based on openCV"
    def __init__(self, name="temp_video.avi", fourcc="MJPG", sizex=640, sizey=480, camindex=0, fps=30):
        self.open = True
        self.device_index = camindex
        self.fps = fps
        self.fourcc = cv2.VideoWriter_fourcc(*fourcc)
        self.frameSize = (sizex, sizey)
        self.video_filename = name
        self.video_cap = cv2.VideoCapture(self.device_index)
        self.video_out = cv2.VideoWriter(self.video_filename, self.fourcc, self.fps, self.frameSize)
        self.frame_counts = 1
        self.start_time = time.time()

    def record(self):
        "Video starts being recorded"
        while self.open:
            ret, video_frame = self.video_cap.read()
            if ret:
                self.video_out.write(video_frame)
                self.frame_counts += 1
            else:
                break

    def stop(self):
        "Finishes the video recording therefore the thread too"
        if self.open:
            self.open = False
            self.video_out.release()
            self.video_cap.release()
            cv2.destroyAllWindows()

    def start(self):
        "Launches the video recording function using a thread"
        video_thread = threading.Thread(target=self.record)
        video_thread.start()

def genHeader(sampleRate, bitsPerSample, channels):
    datasize = 2000 * 10**6
    o = bytes("RIFF", 'ascii')                                               # (4byte) Marks file as RIFF
    o += (datasize + 36).to_bytes(4, 'little')                               # (4byte) File size in bytes excluding this and RIFF marker
    o += bytes("WAVE", 'ascii')                                              # (4byte) File type
    o += bytes("fmt ", 'ascii')                                              # (4byte) Format Chunk Marker
    o += (16).to_bytes(4, 'little')                                          # (4byte) Length of above format data
    o += (1).to_bytes(2, 'little')                                           # (2byte) Format type (1 - PCM)
    o += (channels).to_bytes(2, 'little')                                    # (2byte)
    o += (sampleRate).to_bytes(4, 'little')                                  # (4byte)
    o += (sampleRate * channels * bitsPerSample // 8).to_bytes(4, 'little')  # (4byte)
    o += (channels * bitsPerSample // 8).to_bytes(2, 'little')               # (2byte)
    o += (bitsPerSample).to_bytes(2, 'little')                               # (2byte)
    o += bytes("data", 'ascii')                                              # (4byte) Data Chunk Marker
    o += (datasize).to_bytes(4, 'little')                                    # (4byte) Data size in bytes
    return o

@app.route('/audio')
def audio():
    # start Recording
    def sound():
        CHUNK = 1024
        sampleRate = 44100
        bitsPerSample = 16
        channels = 2
        wav_header = genHeader(sampleRate, bitsPerSample, channels)

        stream = audio1.open(format=FORMAT, channels=CHANNELS,
                             rate=RATE, input=True, input_device_index=1,
                             frames_per_buffer=CHUNK)
        print("recording...")
        first_run = True
        while True:
            if first_run:
                data = wav_header + stream.read(CHUNK)
                first_run = False
            else:
                data = stream.read(CHUNK)
            yield data

    return Response(sound())

@app.route('/index')
def index_page():
    """Video streaming home page."""
    return render_template('index.html')

class AudioRecorder():
    "Audio class based on pyAudio and Wave"
    def __init__(self, filename="temp_audio.wav", rate=44100, fpb=1024, channels=2):
        self.open = True
        self.rate = rate
        self.frames_per_buffer = fpb
        self.channels = channels
        self.format = pyaudio.paInt16
        self.audio_filename = filename
        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(format=self.format,
                                      channels=self.channels,
                                      rate=self.rate,
                                      input=True,
                                      frames_per_buffer=self.frames_per_buffer)
        self.audio_frames = []

    def record(self):
        "Audio starts being recorded"
        self.stream.start_stream()
        while self.open:
            data = self.stream.read(self.frames_per_buffer) 
            self.audio_frames.append(data)

    def stop(self):
        "Finishes the audio recording therefore the thread too"
        if self.open:
            self.open = False
            self.stream.stop_stream()
            self.stream.close()
            self.audio.terminate()
            waveFile = wave.open(self.audio_filename, 'wb')
            waveFile.setnchannels(self.channels)
            waveFile.setsampwidth(self.audio.get_sample_size(self.format))
            waveFile.setframerate(self.rate)
            waveFile.writeframes(b''.join(self.audio_frames))
            waveFile.close()

    def start(self):
        "Launches the audio recording function using a thread"
        audio_thread = threading.Thread(target=self.record)
        audio_thread.start()

def start_AVrecording(filename="test"):
    global video_thread
    global audio_thread
    video_thread = VideoRecorder(name="temp_video.avi")
    audio_thread = AudioRecorder(filename="temp_audio.wav")
    audio_thread.start()
    video_thread.start()
    return filename

def stop_AVrecording(filename="test"):
    global video_thread
    global audio_thread
    audio_thread.stop() 
    frame_counts = video_thread.frame_counts
    elapsed_time = time.time() - video_thread.start_time
    recorded_fps = frame_counts / elapsed_time
    print("total frames " + str(frame_counts))
    print("elapsed time " + str(elapsed_time))
    print("recorded fps " + str(recorded_fps))
    video_thread.stop() 

    # Makes sure the threads have finished
    while threading.active_count() > 1:
        time.sleep(1)

    # Merging audio and video signal
    if abs(recorded_fps - 6) >= 0.01:    # If the fps rate was higher/lower than expected, re-encode it to the expected
        print("Re-encoding")
        cmd = "ffmpeg -r " + str(recorded_fps) + " -i temp_video.avi -pix_fmt yuv420p -r 6 temp_video2.avi"
        subprocess.call(cmd, shell=True)
        print("Muxing")
        cmd = "ffmpeg -ac 2 -y -channel_layout stereo -i temp_audio.wav -i temp_video2.avi -pix_fmt yuv420p " + filename + ".avi"
        subprocess.call(cmd, shell=True)
    else:
        print("Normal recording\nMuxing")
        cmd = "ffmpeg -ac 2 -y -channel_layout stereo -i temp_audio.wav -i temp_video.avi -pix_fmt yuv420p " + filename + ".avi"
        subprocess.call(cmd, shell=True)
        print("..")

def file_manager(filename="test"):
    "Required and wanted processing of final files"
    local_path = os.getcwd()
    if os.path.exists(os.path.join(local_path, "temp_audio.wav")):
        os.remove(os.path.join(local_path, "temp_audio.wav"))
    if os.path.exists(os.path.join(local_path, "temp_video.avi")):
        os.remove(os.path.join(local_path, "temp_video.avi"))
    if os.path.exists(os.path.join(local_path, "temp_video2.avi")):
        os.remove(os.path.join(local_path, "temp_video2.avi"))
    if os.path.exists(os.path.join(local_path, f"{filename}.avi")):
        os.remove(os.path.join(local_path, f"{filename}.avi"))

def run_flask():
    app.run(host='0.0.0.0', port=4999)

if __name__ == '__main__':
    # Setting up the listener
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    count = 0

    try:
        while True:
            if a_pressed:  # Check if 'a' key is pressed
                if count == 0:
                    start_AVrecording()
                    flask_thread = threading.Thread(target=run_flask)
                    flask_thread.start()
                    count += 1
                print("Key 'a' is pressed")
                time.sleep(1)  # Introduce a delay when the 'a' key is kept pressed
            else:
                print("Key 'a' is not pressed")
                time.sleep(0.1)  # Main loop delay to prevent high CPU usage
                if count == 1:
                    break
    except KeyboardInterrupt:
        pass
    stop_AVrecording()
    file_manager()

    listener.stop()
