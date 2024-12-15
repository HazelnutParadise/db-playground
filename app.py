from fastapi import FastAPI
from api import api

app = FastAPI()
api(app)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)