from flask import Flask, request, jsonify
import subprocess

app = Flask(__name__)

@app.route('/add-download', methods=['POST'])
def add_download():
    data = request.json
    url = data.get('url')
    if url:
        # This launches your existing downloader and passes the URL
        subprocess.Popen(['python3', '/home/tanjim/linux-downloader/download_manager.py', url])
        return jsonify({"status": "sent to manager"}), 200
    return jsonify({"error": "no url"}), 400

if __name__ == '__main__':
    app.run(port=5000)
