import os
from dotenv import load_dotenv

def load_config():
    # Load sandbox first to check the flag
    load_dotenv('.env.sandbox')
    sandbox_mode = os.getenv('SANDBOX', 'false').lower() == 'true'

    # Load the correct environment
    env_file = '.env.sandbox' if sandbox_mode else '.env.live'
    load_dotenv(env_file, override=True)

    return {
        'SANDBOX_MODE': sandbox_mode,
        'TRADIER_TOKEN': os.getenv('TRADIER_TOKEN'),
        'TRADIER_ACCOUNT_ID': os.getenv('TRADIER_ACCOUNT_ID'),
        'TRADIER_BASE_URL': os.getenv('TRADIER_BASE_URL'),
        'TELEGRAM_BOT_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN'),
        'TELEGRAM_CHAT_ID': os.getenv('TELEGRAM_CHAT_ID'),
    }

