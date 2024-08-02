import RPi.GPIO as GPIO
import subprocess
import time

# GPIO pin configuration
BUTTON_PIN = 18  # Change this to the GPIO pin you are using
PROGRAM_PATH = "/path/to/your/program"  # Replace with the path to your program

# Set up GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

program_process = None

def start_program(channel):
    global program_process
    if program_process is None:
        print("Button pressed. Starting program...")
        program_process = subprocess.Popen([PROGRAM_PATH], shell=True)
    else:
        print("Program is already running.")

def stop_program(channel):
    global program_process
    if program_process is not None:
        print("Button released. Stopping program...")
        program_process.terminate()
        program_process = None
    else:
        print("No program is running.")

# Set up event detection
GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING, callback=start_program, bouncetime=300)
GPIO.add_event_detect(BUTTON_PIN, GPIO.RISING, callback=stop_program, bouncetime=300)

try:
    # Keep the script running
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Program interrupted")
finally:
    GPIO.cleanup()
    if program_process is not None:
        program_process.terminate()