---
title: Path Parameters
category: Tutorial
---

# Path Parameters

You can declare path "parameters" or "variables" with the same syntax used by Python
format strings:

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/items/{item_id}")
async def read_item(item_id):
    return {"item_id": item_id}
```

The value of the path parameter `item_id` will be passed to your function as the
argument `item_id`.

## Path parameters with types

You can declare the type of a path parameter in the function using standard Python type
annotations:

```python
@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}
```

Here, `item_id` is declared to be an `int`. This gives you editor support, data
validation, and automatic request "parsing".

## Data validation

If you go to the browser at `http://127.0.0.1:8000/items/foo`, you will see a clear HTTP
error because the path parameter `item_id` had a value of `"foo"`, which is not an `int`.
The same error would appear if you provided a `float` instead of an `int`. FastAPI
provides data validation using type annotations, powered by Pydantic.

## Order matters

When creating path operations, you can find situations where you have a fixed path, like
`/users/me` to get data about the current user, and also a path `/users/{user_id}` to get
data about a specific user by user ID. Because path operations are evaluated in order, you
need to declare the path for `/users/me` before the one for `/users/{user_id}`.
