"""
BGSBU Interacts - Root Entry Point
====================================
Thin wrapper that adds src/ to the module path and delegates to the
application factory inside src/app.py.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from app import create_app

app = create_app()

if __name__ == '__main__':
    print(" * BGSBU Interacts running at http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
