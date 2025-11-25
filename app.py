#!/usr/bin/env python3
"""
Entry point for running the Flask application.
Run with: python3 app.py
"""
import os
from app import app

if __name__ == '__main__':
    # Get configuration from environment variables
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1', 'yes']
    
    print(f"Starting Flask server on {host}:{port}")
    print(f"Debug mode: {debug}")
    print(f"API Documentation available at: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/apidocs/")
    
    app.run(
        host=host,
        port=port,
        debug=False
    )