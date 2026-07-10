import os
import openai
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

index_save_directory = ''
SAVE_PATH = ''
LOAD_PATH = ''
FEEDBACK_PATH = ''
LOG_PATH = ''
FILE_PATH = ''
access_stats_path = ''
openai_api_key = ''
openai_api_base = ''
openai_model = ''
VERBOSE = False


def reload_env_variables():
    load_dotenv(os.path.join(os.path.dirname(PROJECT_ROOT), '.env'), override=True)
    global index_save_directory, SAVE_PATH, LOAD_PATH, FEEDBACK_PATH, LOG_PATH, FILE_PATH, access_stats_path, \
        openai_api_key, openai_api_base, openai_model, VERBOSE

    openai.api_key = os.environ.get("OPENAI_API_KEY")
    openai_api_key = openai.api_key

    openai_api_base = os.environ.get('OPENAI_API_BASE') or 'https://api.openai.com/v1'
    openai.api_base = openai_api_base

    openai_model = os.environ.get('OPENAI_MODEL', 'sensenova-6.7-flash-lite')
    VERBOSE = os.environ.get('VERBOSE', 'False').lower() in ('true', '1', 't')

    index_save_directory = os.environ.get('INDEX_SAVE_DIRECTORY', '../../data/indexes/')
    SAVE_PATH = os.environ.get('SAVE_PATH', '../../data/upload_files')
    LOAD_PATH = os.environ.get('LOAD_PATH', '../../data/temp/')
    FEEDBACK_PATH = os.environ.get('FEEDBACK_PATH', '../../feedback/')
    LOG_PATH = os.environ.get('LOG_PATH', '../../log/')
    FILE_PATH = os.environ.get('FILE_PATH', '../../data/export/')

    index_save_directory = os.path.join(PROJECT_ROOT, index_save_directory)
    SAVE_PATH = os.path.join(PROJECT_ROOT, SAVE_PATH)
    LOAD_PATH = os.path.join(PROJECT_ROOT, LOAD_PATH)
    FEEDBACK_PATH = os.path.join(PROJECT_ROOT, FEEDBACK_PATH)
    LOG_PATH = os.path.join(PROJECT_ROOT, LOG_PATH)
    FILE_PATH = os.path.join(PROJECT_ROOT, FILE_PATH)
    access_stats_path = os.path.join(PROJECT_ROOT, '../access_stats.json')


MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.md', '.csv', '.xlsx'}
COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'False').lower() in ('true', '1', 't')
COOKIE_MAX_AGE = int(os.environ.get('COOKIE_MAX_AGE', '86400'))

# Initialize variables on import
reload_env_variables()
