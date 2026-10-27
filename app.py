from flask import Flask

import config
import db as db_module
from routes.admin import bp as admin_bp
from routes.auth import bp as auth_bp
from routes.public import bp as public_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(config)

    db_module.init_app(app)
    with app.app_context():
        db_module.init_db()

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(public_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
