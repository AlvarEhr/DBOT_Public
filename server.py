from flask import Flask, request, Response
import threading
from time import time
import os

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
def index():
    return 'Result: [OK].'

def run_server(host, port):
    print(f'Server is connecting to http://{host}:{port}')
    app.run(host=host, port=port)

def keep_alive(host='0.0.0.0', port=None):
    if port is None:
        port = int(os.environ.get('REPLIT_PORT', 3000))
    server_thread = threading.Thread(target=run_server, args=(host, port))
    server_thread.start()
    print(f'Server is now ready! | {int(time() * 1000)}')

if __name__ == '__main__':
    keep_alive()