from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from api import set_api

app = FastAPI()
set_api(app)

app.mount("/static", StaticFiles(directory="./frontend/static"), name="static")

@app.get('/')
def index():
    with open('./frontend/index.html', 'r') as f:
        html_content = f.read()
    return HTMLResponse(html_content)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)