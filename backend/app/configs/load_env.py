import os

import openai
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()
openai.api_key = os.environ.get("OPENAI_API_KEY")
openai_api_key = openai.api_key
openai.api_base = os.environ.get('OPENAI_API_BASE')
openai_api_base = openai.api_base
index_save_directory = os.environ.get('INDEX_SAVE_DIRECTORY')
SAVE_PATH = os.environ.get('SAVE_PATH')
LOAD_PATH = os.environ.get('LOAD_PATH')
FILE_PATH = os.environ.get('FILE_PATH')

index_save_directory = os.path.join(PROJECT_ROOT, index_save_directory)
SAVE_PATH = os.path.join(PROJECT_ROOT, SAVE_PATH)
LOAD_PATH = os.path.join(PROJECT_ROOT, LOAD_PATH)
FILE_PATH = os.path.join(PROJECT_ROOT, FILE_PATH)
access_stats_path = os.path.join(PROJECT_ROOT,'../access_stats.pkl')