from flask import Flask, Response, render_template_string
import cv2
import threading
import os
import pyaudio
import wave
import ffmpeg
import signal
import sys

app = Flask(__name__)
cap = cv2.VideoCapture(0)
recording = False
out_video = None
audio_thread = None
video_thread = None
recording_audio = False
frames_audio = []

# HTML template for the video feed page
html_template = '''
<!DOCTYPE html>
<html>
<head>
    <title>Camera Feed</title>
</head>
<body>
    <h1>Camera Feed</h1>
    <img src="{{ url_for('video_feed') }}" width="640" height="480">
</body>
</html>
'''


def generate_frames():
    global cap, recording, out_video
    while True:
        success, frame = cap.read()
        if not success:
            break
        if recording and out_video is not None:
            out_video.write(frame)
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


def record_audio(output_file):
    global recording_audio, frames_audio
    chunk = 1024
    format = pyaudio.paInt16
    channels = 1  # Use 1 for mono
    rate = 44100

    p = pyaudio.PyAudio()

    stream = p.open(format=format,
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

    wf = wave.open(output_file, 'wb')
    wf.setnchannels(channels)
    wf.setsampwidth(p.get_sample_size(format))
    wf.setframerate(rate)
    wf.writeframes(b''.join(frames_audio))
    wf.close()


def record_video(output_file, fps=27.0, resolution=(640, 480)):
    global cap, recording, out_video

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_video = cv2.VideoWriter(output_file, cv2.VideoWriter.fourcc(*'MJPG'), fps, (frame_width, frame_height))

    print("Recording video...")

    while recording:
        ret, frame = cap.read()
        if ret:
            out_video.write(frame)
        else:
            break

    print("Finished recording video.")

    cap.release()
    out_video.release()


def merge_audio_video(video_file, audio_file, output_file):
    input_video = ffmpeg.input(video_file)
    input_audio = ffmpeg.input(audio_file)
    ffmpeg.output(input_video, input_audio, output_file, vcodec='copy', acodec='aac').run()
    os.remove(video_file)
    os.remove(audio_file)


@app.route('/')
def index():
    return render_template_string(html_template)


@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


def get_unique_filename(directory, base_filename, extension):
    """
    Generate a unique filename by appending an incrementing number suffix.
    """
    filename = f"{base_filename}{extension}"
    counter = 1
    while os.path.exists(os.path.join(directory, filename)):
        filename = f"{base_filename}{counter}{extension}"
        counter += 1
    return filename

directory = '.'  # Change this to the directory where you want to save your files

# Define your base filenames and extensions
video_base = 'output_video'
audio_base = 'output_audio'
output_base = 'final_output'
video_ext = '.avi'
audio_ext = '.wav'
output_ext = '.mp4'

# Get unique filenames
video_file = get_unique_filename(directory, video_base, video_ext)
audio_file = get_unique_filename(directory, audio_base, audio_ext)
output_file = get_unique_filename(directory, output_base, output_ext)


def signal_handler(sig, frame):
    global recording, recording_audio, audio_thread, video_thread
    print('Stopping recording...')
    recording = False
    recording_audio = False
    audio_thread.join()
    video_thread.join()
    # video_file = 'output_video.avi'
    # audio_file = 'output_audio.wav'
    # output_file = 'final_output.mp4'
    merge_audio_video(video_file, audio_file, output_file)
    sys.exit(0)


if __name__ == "__main__":
    recording = True
    recording_audio = True
    # video_file = 'output_video.avi'
    # audio_file = 'output_audio.wav'

    audio_thread = threading.Thread(target=record_audio, args=(audio_file,))
    video_thread = threading.Thread(target=record_video, args=(video_file,))

    audio_thread.start()
    video_thread.start()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    app.run(host='0.0.0.0', port=3009, debug=True)
