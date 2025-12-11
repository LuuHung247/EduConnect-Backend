from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pathlib import Path
import json
from dotenv import load_dotenv
import os
from app.utils.cache import init_cache
# Load environment variables from .env file
load_dotenv()

try:
    from flask_swagger_ui import get_swaggerui_blueprint
except Exception:
    get_swaggerui_blueprint = None


def create_app(config_object=None):
    """Application factory for the Flask app."""
    app = Flask(__name__, static_folder=None)
    CORS(app)
    if config_object:
        app.config.from_object(config_object)

    # register blueprints
    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)
    
    # API blueprints ported from Node
    from app.blueprints.users import bp as users_bp
    from app.blueprints.series import bp as series_bp
    from app.blueprints.lessons import bp as lessons_bp
    
    # Register blueprints
    app.register_blueprint(users_bp)
    app.register_blueprint(series_bp)
    app.register_blueprint(lessons_bp)
    
    # Initialize cache
    from app.utils.cache import init_cache
    # init_cache(app)
    
    # Setup Swagger UI with flask-swagger-ui
    if get_swaggerui_blueprint is not None:
        SWAGGER_URL = '/apidocs'  # URL for exposing Swagger UI
        API_URL = '/apispec.json'  # URL for the OpenAPI spec (can also be /static/openapi.yaml)
        
        # Call factory function to create our blueprint
        swaggerui_blueprint = get_swaggerui_blueprint(
            SWAGGER_URL,
            API_URL,
            config={
                'app_name': "EduConnectBackend API",
                'defaultModelsExpandDepth': -1,  # Hide schemas section by default
                'docExpansion': 'list',  # 'list', 'full', or 'none'
                'filter': True,  # Enable filtering
            }
        )
        
        app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
        
        # Serve the OpenAPI YAML file
        @app.route('/apispec.json')
        def apispec():
            """Serve OpenAPI specification from YAML file"""
            try:
                import yaml
                yaml_path = Path(__file__).parent / 'static' / 'openapi.yaml'
                
                if not yaml_path.exists():
                    return jsonify({
                        "openapi": "3.0.0",
                        "info": {
                            "title": "EduConnectBackend API",
                            "version": "0.1.0",
                            "description": "OpenAPI spec file not found"
                        },
                        "paths": {}
                    }), 404
                
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    spec = yaml.safe_load(f)
                
                return jsonify(spec)
            except Exception as e:
                print(f"Error loading API spec: {e}")
                return jsonify({
                    "openapi": "3.0.0",
                    "info": {
                        "title": "EduConnectBackend API",
                        "version": "0.1.0",
                        "description": f"Error: {str(e)}"
                    },
                    "paths": {}
                }), 500
        
        # Optional: serve YAML directly if you prefer
        @app.route('/static/openapi.yaml')
        def serve_openapi_yaml():
            """Serve the raw YAML file"""
            try:
                yaml_path = Path(__file__).parent / 'static'
                return send_from_directory(yaml_path, 'openapi.yaml')
            except Exception as e:
                return f"Error: {str(e)}", 404
                    
    else:
        print("Warning: flask-swagger-ui not installed. Swagger UI disabled.")

    return app


# Expose a module-level app for gunicorn/wrappers
app = create_app()