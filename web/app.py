from ui.constants import UI_PORT
from ui.main import bootstrap, get_app

app = get_app()

if __name__ == "__main__":
    bootstrap()
    app.run(host="0.0.0.0", port=UI_PORT, debug=False)
