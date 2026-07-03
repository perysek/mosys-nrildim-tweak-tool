import os

from app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '5001'))
    # Debug/reloader is OFF by default. The Werkzeug debugger exposes an
    # interactive console (remote code execution) and the reloader spawns a
    # child that holds the port — neither is acceptable on a server that can
    # write to the production MOSYS DB. Opt in for local dev with FLASK_DEBUG=1.
    debug = os.environ.get('FLASK_DEBUG', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    app.run(host=os.environ.get('HOST', '127.0.0.1'), port=port,
            debug=debug, threaded=True)
