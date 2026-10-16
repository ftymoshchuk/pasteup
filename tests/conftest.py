import os

# TestClient addresses every request to "testserver", which the app's Host check
# refuses by default. Set before any test module imports the app.
os.environ.setdefault("PASTEUP_ALLOWED_HOSTS", "testserver")
