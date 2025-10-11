from flask import Flask
from app.main.routes import main_bp
import os

app = Flask(__name__)

# --- Secret Key Configuration ---
# IMPORTANT: In a real application, use environment variables for the secret key.
# For example: app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_default_fallback_key')
app.config['SECRET_KEY'] = os.urandom(24)

# --- Blueprint Registration ---
# Register the blueprint from routes.py to organize the routes.
app.register_blueprint(main_bp)

if __name__ == '__main__':
    # The debug flag is useful during development. Turn it off for production.
    app.run(debug=True, host='0.0.0.0', port=8080)
