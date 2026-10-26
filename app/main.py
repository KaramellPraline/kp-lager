from app.config import load_settings
from app.web import create_app

app = create_app(load_settings())
