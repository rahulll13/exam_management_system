from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import Config

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize plugins
    db.init_app(app)
    migrate.init_app(app, db)

    # Import models so Flask-Migrate sees them
    from app import models

    # --- THE CRITICAL FIX IS HERE ---
    # 1. Import the Blueprint
    from app.api.routes import api_bp
    
    # 2. Register the Blueprint
    # This tells Flask: "Take all routes in api_bp and add '/api' to the front"
    app.register_blueprint(api_bp, url_prefix='/api')
    # --------------------------------

    return app