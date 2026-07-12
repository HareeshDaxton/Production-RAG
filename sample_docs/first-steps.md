---
title: First Steps
category: Tutorial
---

# First Steps

The simplest FastAPI file looks like this:

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}
```

## Run it

Run the live server with Uvicorn:

```console
uvicorn main:app --reload
```

The command `uvicorn main:app` refers to:

- `main`: the file `main.py` (the Python "module").
- `app`: the object created inside `main.py` with the line `app = FastAPI()`.
- `--reload`: make the server restart after code changes. Use it only for development.

## Check it

Open your browser at `http://127.0.0.1:8000`. You will see the JSON response:

```json
{"message": "Hello World"}
```

## Interactive API docs

Now go to `http://127.0.0.1:8000/docs`. You will see the automatic interactive API
documentation provided by Swagger UI. An alternative documentation page using ReDoc is
available at `http://127.0.0.1:8000/redoc`.
