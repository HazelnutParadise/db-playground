from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from api import set_api

app = FastAPI()
set_api(app)

@app.get('/ico')
def ico():
    with open('./frontend/favicon.ico', 'rb') as f:
        ico_content = f.read()
    return ico_content

@app.get('/')
def index():
    with open('./frontend/index.html', 'r') as f:
        html_content = f.read()
    return HTMLResponse(html_content)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)