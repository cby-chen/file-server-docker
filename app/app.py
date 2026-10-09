import json
import os
import re
import shutil
import uuid
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, request, session

app = Flask(__name__)
ROOT = Path(os.getenv("FILE_ROOT", "/data/files")).resolve()
UPLOADS = ROOT / ".uploads"
ROOT.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(exist_ok=True)

def parse_size(value):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB)?\s*", value, re.I)
    if not match:
        raise ValueError("Invalid size: " + value)
    return int(float(match.group(1)) * {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}[(match.group(2) or "B").upper()])

CHUNK = parse_size(os.getenv("UPLOAD_CHUNK_SIZE", "16MB"))
MAX_SIZE = parse_size(os.getenv("MAX_UPLOAD_SIZE", "50GB"))
CONCURRENCY = max(1, min(32, int(os.getenv("UPLOAD_CONCURRENCY", "4"))))
SESSION_HOURS = float(os.getenv("SESSION_TIMEOUT_HOURS", "12"))
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "CHANGE_ME"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=SESSION_HOURS),
    MAX_CONTENT_LENGTH=CHUNK + 1024 * 1024,
)

def unauthorized():
    return (jsonify(ok=False, error="unauthorized"), 401) if "user" not in session else None

def clean_rel(value):
    value = (value or "").replace("\\", "/").strip("/")
    parts = []
    for part in value.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("Invalid path")
        parts.append(part)
    return "/".join(parts)

def safe_target(value):
    path = (ROOT / clean_rel(value)).resolve()
    if path != ROOT and ROOT not in path.parents:
        raise ValueError("Invalid path")
    return path

def upload_dir(upload_id):
    if not re.fullmatch(r"[a-f0-9]{32}", upload_id or ""):
        raise ValueError("Invalid upload id")
    return UPLOADS / upload_id

def upload_meta(upload_id):
    return upload_dir(upload_id) / "metadata.json"

def safe_filename(value):
    name = str(value or "").replace("\\", "/").split("/")[-1].strip()
    if name in ("", ".", "..") or any(ord(c) < 32 for c in name):
        raise ValueError("无效文件名")
    return name

@app.get("/api/auth/check")
def auth_check():
    return ("", 204) if "user" in session else ("", 401)

@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    if data.get("username") != os.getenv("FILE_USER", "admin") or data.get("password") != os.getenv("FILE_PASSWORD", "ChangeMe_123456"):
        return jsonify(ok=False, error="用户名或密码错误"), 401
    session.clear()
    session["user"] = data["username"]
    session.permanent = True
    return jsonify(ok=True, username=session["user"])

@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)

@app.get("/api/me")
def me():
    if "user" not in session:
        return jsonify(ok=False), 401
    return jsonify(ok=True, username=session["user"], session_hours=SESSION_HOURS)

@app.get("/api/config")
def config():
    if unauthorized():
        return unauthorized()
    return jsonify(ok=True, chunk_size=CHUNK, chunk_size_text=os.getenv("UPLOAD_CHUNK_SIZE", "16MB"), concurrency=CONCURRENCY, max_upload_size=MAX_SIZE, max_upload_size_text=os.getenv("MAX_UPLOAD_SIZE", "50GB"))

@app.get("/api/list")
def list_files():
    if unauthorized():
        return unauthorized()
    try:
        path = safe_target(request.args.get("path", ""))
        if not path.is_dir():
            return jsonify(ok=False, error="目录不存在"), 404
        items = []
        for item in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if item.name == ".uploads":
                continue
            stat = item.stat()
            items.append({"name": item.name, "path": item.relative_to(ROOT).as_posix(), "type": "folder" if item.is_dir() else "file", "size": stat.st_size if item.is_file() else 0, "mtime": int(stat.st_mtime)})
        return jsonify(ok=True, path=clean_rel(request.args.get("path", "")), items=items)
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 400

@app.get("/api/search")
def search():
    if unauthorized():
        return unauthorized()
    query = request.args.get("q", "").lower().strip()
    items = []
    for item in ROOT.rglob("*"):
        if item.is_file() and ".uploads" not in item.parts and (query in item.name.lower() or query in item.relative_to(ROOT).as_posix().lower()):
            stat = item.stat()
            items.append({"name": item.name, "path": item.relative_to(ROOT).as_posix(), "type": "file", "size": stat.st_size, "mtime": int(stat.st_mtime)})
            if len(items) >= 500:
                break
    return jsonify(ok=True, items=items)

@app.post("/api/folder")
def create_folder():
    if unauthorized():
        return unauthorized()
    try:
        safe_target((request.get_json() or {}).get("path", "")).mkdir(parents=True, exist_ok=False)
        return jsonify(ok=True)
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 400

@app.delete("/api/delete")
def delete_file():
    if unauthorized():
        return unauthorized()
    try:
        path = safe_target((request.get_json() or {}).get("path", ""))
        if path == ROOT or not path.exists():
            return jsonify(ok=False, error="文件不存在"), 404
        shutil.rmtree(path) if path.is_dir() else path.unlink()
        return jsonify(ok=True)
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 400

@app.post("/api/upload/init")
def upload_init():
    if unauthorized():
        return unauthorized()
    try:
        data = request.get_json() or {}
        filename = safe_filename(data.get("filename"))
        folder = clean_rel(data.get("folder", ""))
        total = int(data.get("size", 0))
        if total < 0 or total > MAX_SIZE:
            return jsonify(ok=False, error="超过最大上传大小"), 413
        destination = safe_target(f"{folder}/{filename}" if folder else filename)
        destination.parent.mkdir(parents=True, exist_ok=True)
        upload_id = uuid.uuid4().hex
        directory = upload_dir(upload_id)
        directory.mkdir()
        count = (total + CHUNK - 1) // CHUNK
        metadata = {"upload_id": upload_id, "filename": filename, "folder": folder, "size": total, "chunk_size": CHUNK, "chunk_count": count, "destination": destination.relative_to(ROOT).as_posix()}
        upload_meta(upload_id).write_text(json.dumps(metadata), encoding="utf-8")
        return jsonify(ok=True, upload_id=upload_id, filename=filename, size=total, chunk_size=CHUNK, chunk_count=count, concurrency=CONCURRENCY)
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 400

@app.get("/api/upload/status")
def upload_status():
    if unauthorized():
        return unauthorized()
    try:
        upload_id = request.args.get("upload_id", "")
        metadata = json.loads(upload_meta(upload_id).read_text(encoding="utf-8"))
        completed, uploaded_bytes = [], 0
        for index in range(metadata["chunk_count"]):
            part = upload_dir(upload_id) / f"chunk_{index:08d}.part"
            expected = min(metadata["chunk_size"], metadata["size"] - index * metadata["chunk_size"])
            if part.exists() and part.stat().st_size == expected:
                completed.append(index)
                uploaded_bytes += expected
        return jsonify(ok=True, upload_id=upload_id, filename=metadata["filename"], size=metadata["size"], chunk_size=metadata["chunk_size"], chunk_count=metadata["chunk_count"], uploaded_chunks=completed, uploaded_bytes=uploaded_bytes)
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 400

@app.put("/api/upload/chunk")
def upload_chunk():
    if unauthorized():
        return unauthorized()
    try:
        upload_id = request.args.get("upload_id", "")
        metadata = json.loads(upload_meta(upload_id).read_text(encoding="utf-8"))
        index = int(request.args.get("index", "-1"))
        if index < 0 or index >= metadata["chunk_count"]:
            return jsonify(ok=False, error="分片编号无效"), 400
        body = request.get_data()
        expected = min(metadata["chunk_size"], metadata["size"] - index * metadata["chunk_size"])
        if len(body) != expected:
            return jsonify(ok=False, error=f"分片大小错误，期望 {expected}，收到 {len(body)}"), 400
        directory = upload_dir(upload_id)
        temporary, destination = directory / f"chunk_{index:08d}.tmp", directory / f"chunk_{index:08d}.part"
        with temporary.open("wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        return jsonify(ok=True, index=index, received=len(body))
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 400

@app.post("/api/upload/complete")
def upload_complete():
    if unauthorized():
        return unauthorized()
    try:
        upload_id = (request.get_json() or {}).get("upload_id", "")
        metadata = json.loads(upload_meta(upload_id).read_text(encoding="utf-8"))
        directory = upload_dir(upload_id)
        destination = safe_target(metadata["destination"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        for index in range(metadata["chunk_count"]):
            part = directory / f"chunk_{index:08d}.part"
            expected = min(metadata["chunk_size"], metadata["size"] - index * metadata["chunk_size"])
            if not part.exists() or part.stat().st_size != expected:
                return jsonify(ok=False, error=f"分片 {index} 尚未完成", missing_chunk=index), 409
        if destination.exists():
            stem, suffix, counter = destination.stem, destination.suffix, 1
            while destination.exists():
                destination = destination.with_name(f"{stem} ({counter}){suffix}")
                counter += 1
        assembling = directory / "assembling.file"
        with assembling.open("wb") as output:
            for index in range(metadata["chunk_count"]):
                with (directory / f"chunk_{index:08d}.part").open("rb") as source:
                    shutil.copyfileobj(source, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        os.replace(assembling, destination)
        shutil.rmtree(directory, ignore_errors=True)
        return jsonify(ok=True, path=destination.relative_to(ROOT).as_posix(), size=destination.stat().st_size)
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 400

@app.delete("/api/upload/cancel")
def upload_cancel():
    if unauthorized():
        return unauthorized()
    try:
        shutil.rmtree(upload_dir(request.args.get("upload_id", "")), ignore_errors=True)
        return jsonify(ok=True)
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 400

@app.errorhandler(413)
def too_large(_error):
    return jsonify(ok=False, error="请求超过限制"), 413

@app.get("/health")
def health():
    return "ok"
