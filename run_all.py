import subprocess
import time
import sys

def run_both():
    try:
        process_1 = subprocess.Popen([sys.executable,'main.py'])
        print("Stated data collection")

        time.sleep(30) # time to collect some data in db

        process_2 = subprocess.Popen([sys.executable,'app.py'])
        print("Statrd Frontend")

        process_1.wait()
        process_2.wait()
    except KeyboardInterrupt:
        print("Interrupted..")
        process_1.terminate()
        process_2.terminate()

if __name__=='__main__':
    run_both()