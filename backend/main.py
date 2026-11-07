"""Local development entry point: `python main.py`"""
import os

from app import create_app

if __name__ == '__main__':
    create_app().run(debug=False, host='0.0.0.0', port=int(os.getenv('PORT', 5000)), use_reloader=False)
