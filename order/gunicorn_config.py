# gunicorn_config.py

def on_starting(server):
    from app import app, on_start

    with app.app_context():
        on_start()
