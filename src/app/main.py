from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse

app = FastAPI(title="Enterprise Knowledge AI Agent")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    # placeholder: save file and enqueue processing
    content = await file.read()
    # TODO: route to DocumentProcessor
    return JSONResponse({"filename": file.filename, "size": len(content)})
