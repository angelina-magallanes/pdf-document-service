import json
import os

import httpx

with httpx.Client(base_url="http://documents:8000", timeout=5) as client:
    assert client.get("/health/ready").status_code == 200
    assert client.get("/documents").status_code == 401
    assert client.get("/documents", headers={"Authorization": "Bearer incorrect"}).status_code == 401
    response = client.get("/documents", headers={"Authorization": "Bearer " + os.environ["DOCUMENTS_API_TOKEN"]})
    assert response.status_code == 200
    print(json.dumps({"public_health": 200, "missing_token": 401, "incorrect_token": 401, "authenticated_list": 200}))
