import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Path for storing profile pictures
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'app/static/profile_pics')
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # Limit uploads to 2MB (Security)