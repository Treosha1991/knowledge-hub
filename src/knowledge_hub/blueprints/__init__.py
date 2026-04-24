from flask import Flask

from .auth import bp as auth_bp
from .api import bp as api_bp
from .main import bp as main_bp
from .projects import bp as projects_bp
from .prompt_templates import bp as prompt_templates_bp
from .session_logs import bp as session_logs_bp
from .snapshots import bp as snapshots_bp
from .workspaces import bp as workspaces_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(session_logs_bp)
    app.register_blueprint(prompt_templates_bp)
    app.register_blueprint(snapshots_bp)
    app.register_blueprint(workspaces_bp)
