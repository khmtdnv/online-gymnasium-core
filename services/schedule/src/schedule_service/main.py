from fastapi import FastAPI

app = FastAPI(title="OG1 Schedule Service")


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok"}
