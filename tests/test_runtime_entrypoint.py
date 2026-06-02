import main
from app.main import app as canonical_app
from app.main import create_app as canonical_create_app
from backend.app.main import app as backend_app
from backend.app.main import create_app as backend_create_app


def test_main_entrypoint_uses_top_level_app_namespace():
    assert main.app is canonical_app
    assert main.create_app is canonical_create_app
    assert main.create_app.__module__ == "app.main"


def test_backend_main_is_compatibility_reexport():
    assert backend_app is canonical_app
    assert backend_create_app is canonical_create_app
