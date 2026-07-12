---
title: Query Parameters
category: Tutorial
---

# Query Parameters

When you declare other function parameters that are not part of the path parameters, they
are automatically interpreted as "query" parameters:

```python
from fastapi import FastAPI

app = FastAPI()

fake_items_db = [{"item_name": "Foo"}, {"item_name": "Bar"}, {"item_name": "Baz"}]


@app.get("/items/")
async def read_item(skip: int = 0, limit: int = 10):
    return fake_items_db[skip : skip + limit]
```

The query is the set of key-value pairs that go after the `?` in a URL, separated by `&`
characters. For example, in the URL `http://127.0.0.1:8000/items/?skip=0&limit=10` the
query parameters are `skip` (with a value of `0`) and `limit` (with a value of `10`).

## Defaults

As query parameters are not a fixed part of a path, they can be optional and can have
default values. In the example above they have default values of `skip=0` and `limit=10`.

## Optional parameters

You can declare optional query parameters by setting their default to `None`:

```python
@app.get("/items/{item_id}")
async def read_item(item_id: str, q: str | None = None):
    if q:
        return {"item_id": item_id, "q": q}
    return {"item_id": item_id}
```

## Required query parameters

When you want to make a query parameter required, you just do not declare any default
value. For example, if `needy` has no default, it is a required query parameter.
