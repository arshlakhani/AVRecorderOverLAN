import threading
import pyaudio
import wave
import os
import cv2
import time
from flask import Flask, Response

# Flask app for live feed
app = Flask(__name__)

# Global flag to signal threads to stop
stop_event = threading.Event()

# Flag to indicate when both audio and video threads are started
audio_started = threading.Event()
video_started = threading.Event()

# Audio recording code
def record_audio():
    form_1 = pyaudio.paInt16  # 16-bit resolution
    chans = 2  # 1 channel
    samp_rate = 48000  # 44.1kHz sampling rate
    chunk = 1024  # adjust chunk size
    dev_index = 3  # correct device index for your microphone

    recordings_dir = "./recordingsaudios"  # directory to save recordings

    # Ensure the recordings directory exists
    if not os.path.exists(recordings_dir):
        os.makedirs(recordings_dir)

    # Function to get the next filename with an incrementing number
    def get_next_filename(directory, base_name, extension):
        files = os.listdir(directory)
        matching_files = [f for f in files if f.startswith(base_name) and f.endswith(extension)]
        
        if not matching_files:
            return os.path.join(directory, f"{base_name}_1{extension}")
        
        numbers = [int(f[len(base_name)+1:-len(extension)]) for f in matching_files if f[len(base_name)+1:-len(extension)].isdigit()]
        next_number = max(numbers) + 1 if numbers else 1
        return os.path.join(directory, f"{base_name}_{next_number}{extension}")

    audio = pyaudio.PyAudio()  # create pyaudio instantiation

    # Generate the next filename
    wav_output_filename = get_next_filename(recordings_dir, 'recorded_audio', '.wav')

    # create pyaudio stream
    stream = audio.open(format=form_1, rate=samp_rate, channels=chans,
                        input_device_index=dev_index, input=True,
                        frames_per_buffer=chunk)

    print("Waiting for video to start...")
    video_started.wait()  # Wait until video thread has started

    audio_started.set()  # Signal that audio thread has started

    print("Recording...")

    frames = []

    try:
        while not stop_event.is_set():
            try:
                data = stream.read(chunk, exception_on_overflow=False)
            except IOError as ex:
                if ex.args[1] != pyaudio.paInputOverflowed:
                    raise
                data = b'\x00' * len(chunk)

            frames.append(data)
    except Exception as e:
        print(f"Error during recording: {str(e)}")
    finally:
        print("Stopping audio recording...")
        # stop the stream, close it, and terminate the pyaudio instantiation
        stream.stop_stream()
        stream.close()
        audio.terminate()

        # save the audio frames as .wav file
        wavefile = wave.open(wav_output_filename, 'wb')
        wavefile.setnchannels(chans)
        wavefile.setsampwidth(audio.get_sample_size(form_1))
        wavefile.setframerate(samp_rate)
        wavefile.writeframes(b''.join(frames))
        wavefile.close()

        print(f"Audio saved as {wav_output_filename}")

# Video recording code
def record_video(camera):
    def get_next_filename(directory, base_name, extension):
        files = os.listdir(directory)
        matching_files = [f for f in files if f.startswith(base_name) and f.endswith(extension)]
        
        if not matching_files:
            return f"{base_name}_1{extension}"
        
        numbers = [int(f[len(base_name)+1:-len(extension)]) for f in matching_files if f[len(base_name)+1:-len(extension)].isdigit()]
        next_number = max(numbers) + 1 if numbers else 1
        return f"{base_name}_{next_number}{extension}"

    # Directory to save recordings
    recordings_dir = "./recordingsvideos"
    if not os.path.exists(recordings_dir):
        os.makedirs(recordings_dir)
    
    # Define the codec and create VideoWriter object
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    filename = get_next_filename(recordings_dir, 'recorded_video', '.avi')
    out = cv2.VideoWriter(os.path.join(recordings_dir, filename), fourcc, 10.0, (1280, 720))
    
    desired_fps = 10.0
    frame_time = 1 / desired_fps

    video_started.set()  # Signal that video thread has started

    audio_started.wait()  # Wait until audio thread has started

    try:
        while not stop_event.is_set():
            start_time = time.time()

            success, frame = camera.read()  # Read the camera frame
            if not success:
                break
            else:
                out.write(frame)  # Write the frame to the video file
            
            # Optional: Display the frame being recorded (remove if not needed)
            cv2.imshow('Recording', frame)
            
            # Calculate the time taken to process the frame
            processing_time = time.time() - start_time
            sleep_time = max(0, frame_time - processing_time)
            time.sleep(sleep_time)
            
            # Press 'q' on the keyboard to stop recording
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except Exception as e:
        print(f"Error during video recording: {str(e)}")
    finally:
        print("Stopping video recording...")
        # Release everything if job is finished
        out.release()
        cv2.destroyAllWindows()

# Live feed code
def live_feed(camera):
    def gen_frames():  
        while not stop_event.is_set():
            success, frame = camera.read()  # read the camera frame
            if not success:
                break
            else:
                ret, buffer = cv2.imencode('.jpg', frame)
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')  # concat frame one by one and show result

    @app.route('/video_feed')
    def video_feed():
        return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.route('/')
    def index():
        return "Camera feed is available at /video_feed"

    app.run(host='0.0.0.0', port=5999)

# Combine all parts using threading
if __name__ == '__main__':
    camera = cv2.VideoCapture(0)  # Use 0 for the web camera
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    audio_thread = threading.Thread(target=record_audio)
    video_thread = threading.Thread(target=record_video, args=(camera,))
    flask_thread = threading.Thread(target=live_feed, args=(camera,))

    # Start all threads
    audio_thread.start()
    video_thread.start()
    flask_thread.start()

    try:
        # Wait for all threads to complete
        audio_thread.join()
        video_thread.join()
        flask_thread.join()
    except KeyboardInterrupt:
        print("Program interrupted. Saving files and cleaning up...")
        stop_event.set()
        audio_thread.join()
        video_thread.join()
        flask_thread.join()
    finally:
        # Release camera resources
        camera.release()
        cv2.destroyAllWindows()
