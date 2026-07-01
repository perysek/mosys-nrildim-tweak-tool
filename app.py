from app import app

if __name__ == '__main__':
    port = 5001 # Change this to your desired port
    app.run(debug=True, port=port)
