from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.post("/api/github/webhooks")
async def github_webhook(request: Request):
    event = request.headers.get("X-GitHub-Event")
    
    if event == "ping":
        return JSONResponse(status_code=200, content={"status": "ok"})
        
    if event == "pull_request":
        # In the future, this will trigger the background Gemini loop
        # and integrate with the MCP + Java Evaluator endpoints
        return JSONResponse(status_code=202, content={"status": "processing"})
        
    return JSONResponse(status_code=400, content={"status": "unhandled_event"})
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
