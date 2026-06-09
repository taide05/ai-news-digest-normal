from fastapi.templating import Jinja2Templates
from web.filters import highlight, nl2br

templates = Jinja2Templates(directory="web/templates")
templates.env.filters["highlight"] = highlight
templates.env.filters["nl2br"] = nl2br
