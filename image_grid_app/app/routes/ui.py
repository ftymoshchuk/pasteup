import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.services.cover_collage import COVER_COLLAGE_TEMPLATE_OPTIONS
from mullion import DEFAULT_DPI

# Prefills the input-folder field so a regular workflow does not need retyping on
# every launch. It is read from the environment rather than written here because
# any real value is somebody's home directory.
INPUT_FOLDER_ENV_VAR = "IMAGE_GRID_INPUT_FOLDER"

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


@router.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "defaults": {
                "input_folder": os.environ.get(INPUT_FOLDER_ENV_VAR, ""),
                # app.js derives the output folder from the input folder on load.
                "output_folder": "",
                "page_width": 3000,
                "page_height": 3000,
                "gap": 30,
                "margin": 60,
                "format": "JPG",
                "page_unit": "px",
                "dpi": DEFAULT_DPI,
            },
            "cover_collage_templates": [
                {"value": value, "name": name, "label": label}
                for value, name, label in COVER_COLLAGE_TEMPLATE_OPTIONS
            ],
        },
    )
