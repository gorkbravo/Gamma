__all__ = ["app", "create_app"]


def __getattr__(name: str):
    if name == "app":
        from src.api.main import app

        return app
    if name == "create_app":
        from src.api.main import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
