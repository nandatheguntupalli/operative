#!/usr/bin/env python3

import threading
import webbrowser
from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO
import logging
import os
from datetime import datetime

# Configure logging for Flask and SocketIO (optional, can be noisy)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) # Reduce Flask's default logging
logging.getLogger('socketio').setLevel(logging.ERROR)
logging.getLogger('engineio').setLevel(logging.ERROR)

app = Flask(__name__, template_folder='../templates') # Point to templates dir relative to this file
app.config['SECRET_KEY'] = 'secret!' # Replace with a proper secret if needed
socketio = SocketIO(app, cors_allowed_origins="*") # Allow all origins for local dev

# Store connected SIDs
connected_clients = set()

@app.route('/')
def index():
    """Serve the main HTML dashboard page."""
    return render_template('index.html')

@app.route('/static/<path:path>')
def send_static(path):
    """Serve static files (like CSS, JS if added later)."""
    static_folder = os.path.join(os.path.dirname(__file__), '../templates/static')
    return send_from_directory(static_folder, path)

@socketio.on('connect')
def handle_connect():
    print("Log dashboard client connected")
    # Send status message to dashboard
    send_log(f"Connected to log server at {datetime.now().strftime('%H:%M:%S')}", "✅", log_type='status')

@socketio.on('disconnect')
def handle_disconnect():
    print("Log dashboard client disconnected")
    # Send status message to dashboard
    send_log(f"Disconnected from log server at {datetime.now().strftime('%H:%M:%S')}", "❌", log_type='status')

def send_log(message: str, emoji: str = "➡️", log_type: str = 'agent'):
    """Sends a log message with an emoji prefix and type to all connected clients."""
    # Ensure socketio context is available. If called from a non-SocketIO thread,
    # use socketio.emit directly.
    try:
        log_entry = f"{emoji} {message}"
        # print(f"Attempting to send log ({log_type}): {log_entry}") # Debug print if needed
        # Include log_type in the emitted data
        socketio.emit('log_message', {'data': log_entry, 'type': log_type})
        # print(f"Log emitted ({log_type}): {log_entry}") # Debug print if needed
    except Exception as e:
        # Fallback print if emit fails (e.g., server not running)
        print(f"LOG SERVER EMIT FAILED ({log_type}): {emoji} {message} (Error: {e})")


def start_log_server(host='127.0.0.1', port=5009):
    """Starts the Flask-SocketIO server in a background thread."""
    def run_server():
        print(f"Starting Operative Control Center server on http://{host}:{port}")
        # Use eventlet or gevent for production? For local dev, default Flask dev server is fine.
        # Setting log_output=False to reduce console noise from SocketIO itself
        socketio.run(app, host=host, port=port, log_output=False, use_reloader=False, allow_unsafe_werkzeug=True)

    # Check if templates directory exists
    template_dir = os.path.join(os.path.dirname(__file__), '../templates')
    if not os.path.exists(template_dir):
        print(f"Warning: Template directory not found at {template_dir}. Creating it.")
        os.makedirs(template_dir)
        # Optionally create a placeholder index.html if it's missing
        index_path = os.path.join(template_dir, 'index.html')
        if not os.path.exists(index_path):
             with open(index_path, 'w') as f:
                 f.write("<html><head><title>Operative Control Center</title></head><body><h1>Waiting for logs...</h1></body></html>")
             print(f"Created placeholder index.html at {index_path}")


    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    print("Log server thread started.")
    # Send initial status message
    send_log("Log server thread started.", "🚀", log_type='status') # Add type

def open_log_dashboard(url='http://127.0.0.1:5009'):
    """Opens the specified URL in a new tab in the default web browser."""
    try:
        print(f"Attempting to open dashboard in new tab at {url}...")
        # Use open_new_tab for better control
        webbrowser.open_new_tab(url)
        print("Browser tab requested.")
        send_log(f"Opened dashboard in browser at {url}.", "🌐", log_type='status') # Add type
    except Exception as e:
        print(f"Could not open browser automatically: {e}")
        send_log(f"Could not open browser automatically: {e}", "⚠️", log_type='status') # Add type

# Example usage (for testing this module directly)
if __name__ == '__main__':
    start_log_server()
    import time
    time.sleep(2)
    open_log_dashboard()
    # Use the new log_type argument
    send_log("Server started and dashboard opened.", "✅", log_type='status')
    time.sleep(1)
    send_log("This is a test agent log message.", "🧪", log_type='agent')
    time.sleep(1)
    send_log("This is a test console log.", "🖥️", log_type='console')
    time.sleep(1)
    send_log("This is a test network request.", "➡️", log_type='network')
    time.sleep(1)
    send_log("This is a test network response.", "⬅️", log_type='network')
    # Keep the main thread alive to let the server run
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping server.") 