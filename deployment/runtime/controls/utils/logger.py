import logging
import os
import time

def setup_logging():
    """Setup logging to write to combined.log and error.log files with UTC timestamps"""
    
    # Force logging timestamps to use UTC
    logging.Formatter.converter = time.gmtime

    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Create handlers
    combined_handler = logging.FileHandler('logs/combined.log')
    error_handler = logging.FileHandler('logs/error.log')
    console_handler = logging.StreamHandler()
    error_handler.setLevel(logging.ERROR)
    
    # Set format (timestamp will now be in UTC)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    combined_handler.setFormatter(formatter)
    error_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        handlers=[combined_handler, error_handler, console_handler]
    )
