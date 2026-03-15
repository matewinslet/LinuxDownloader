#!/usr/bin/env python3
import sys
import json
import struct
import subprocess

# This function reads the message sent from Firefox
def get_message():
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) == 0:
        sys.exit(0)
    message_length = struct.unpack('@I', raw_length)[0]
    message = sys.stdin.buffer.read(message_length).decode('utf-8')
    return json.loads(message)

def main():
    while True:
        try:
            received_data = get_message()
            url = received_data.get("url")
            
            if url:
                # This triggers your existing downloader script
                # Replace 'downloader.py' with the actual name of your PyQt6 script
                subprocess.Popen(['python3', '/home/tanjim/linux-downloader/linux_downloader.py', url])
                
        except EOFError:
            break

if __name__ == "__main__":
    main()
