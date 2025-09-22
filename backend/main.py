from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from internal.api import api_router

app = FastAPI(docs_url=None, redoc_url=None)
app.include_router(api_router)


@app.get('/')
def index() -> HTMLResponse:
    with open('../frontend/index.html', 'r') as f:
        html_content: str = f.read()
    return HTMLResponse(html_content)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
