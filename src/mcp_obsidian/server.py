from fastmcp import FastMCP
import os
from dotenv import load_dotenv
from APIWrapper import Obsidian
from pydantic import BaseModel, field_validator
import time
import httpx
from functools import wraps

# Load environment variables
load_dotenv()

# Initialize MCP server
mcp = FastMCP("obsidian-server")

# Load config
api_key = os.getenv("OBSIDIAN_API_KEY")
host = os.getenv("OBSIDIAN_HOST", "127.0.0.1")

if not api_key:
    raise ValueError("OBSIDIAN_API_KEY environment variable required")

# Create Obsidian API client
api = Obsidian(api_key=api_key, host=host)

# ========================
# CIRCUIT BREAKER STATE
# ========================

circuit = {
    "failures": 0,
    "state": "CLOSED",  # CLOSED, OPEN, HALF_OPEN
    "last_failure_time": 0
}

FAILURE_THRESHOLD = 3
RECOVERY_TIME = 10  # seconds

# ========================
# RESPONSE HELPERS
# ========================

def success(data):
    return {"success": True, "data": data}

def error(message):
    return {"success": False, "error": message}

# ========================
# DECORATOR (CIRCUIT)
# ========================

def circuit_protected(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        global circuit
        now = time.time()

        # BLOCK if OPEN
        if circuit["state"] == "OPEN":
            if now - circuit["last_failure_time"] < RECOVERY_TIME:
                return error({
                    "status": "circuit_open",
                    "message": "Service unavailable. Skipping API call.",
                    "retry_after_sec": RECOVERY_TIME
                })
            else:
                circuit["state"] = "HALF_OPEN"

        try:
            result = await func(*args, **kwargs)

            # SUCCESS → reset circuit
            circuit["failures"] = 0
            circuit["state"] = "CLOSED"

            return result

        except Exception as e:
            # FAILURE → update circuit
            circuit["failures"] += 1
            circuit["last_failure_time"] = time.time()

            if circuit["failures"] >= FAILURE_THRESHOLD:
                circuit["state"] = "OPEN"

            return error({
                "status": "failed",
                "reason": str(e),
                "circuit_state": circuit["state"],
                "failure_count": circuit["failures"]
            })

    return wrapper

# ========================
# INPUT VALIDATION
# ========================

class FilePathInput(BaseModel):
    filepath: str

    @field_validator("filepath")
    def validate_filepath(cls, v):
        if not v or not v.strip():
            raise ValueError("filepath is required")
        if ".." in v:
            raise ValueError("invalid filepath")
        return v


class DirPathInput(BaseModel):
    dirpath: str

    @field_validator("dirpath")
    def validate_dirpath(cls, v):
        if not v or not v.strip():
            raise ValueError("dirpath is required")
        return v

# ========================
# FILE OPERATIONS
# ========================

@circuit_protected
@mcp.tool()
async def list_files_in_vault():
    return success(await api.list_files_in_vault())


@circuit_protected
@mcp.tool()
async def list_files_in_dir(input: DirPathInput):
    return success(await api.list_files_in_dir(input.dirpath))


@circuit_protected
@mcp.tool()
async def list_note_titles():
    files = await api.list_files_in_vault()
    titles = [f.split("/")[-1] for f in files]
    return success(titles)


@circuit_protected
@mcp.tool()
async def get_file_contents(input: FilePathInput):
    return success(await api.get_file_contents(input.filepath))


@circuit_protected
@mcp.tool()
async def batch_get_file_contents(filepaths: list[str]):
    return success(await api.get_batch_file_contents(filepaths))

# ========================
# SEARCH
# ========================

@circuit_protected
@mcp.tool()
async def simple_search(query: str, context_length: int = 100):
    return success(await api.search(query, context_length))


@circuit_protected
@mcp.tool()
async def complex_search(query: dict):
    return success(await api.search_json(query))


@circuit_protected
@mcp.tool()
async def search_and_summarize(query: str):
    results = await api.search(query, 100)

    if not results:
        return success("No relevant notes found.")

    combined_text = ""
    for item in results[:5]:
        combined_text += item.get("content", "") + "\n\n"

    return success({
        "summary": combined_text[:500],
        "source_count": len(results)
    })

# ========================
# WRITE / MODIFY
# ========================

@circuit_protected
@mcp.tool()
async def create_note(input: FilePathInput, content: str):
    await api.put_content(input.filepath, content)
    return success(f"Created note {input.filepath}")


@circuit_protected
@mcp.tool()
async def append_content(input: FilePathInput, content: str):
    await api.append_content(input.filepath, content)
    return success(f"Appended content to {input.filepath}")


@circuit_protected
@mcp.tool()
async def patch_content(filepath: str, operation: str, target_type: str, target: str, content: str):
    await api.patch_content(filepath, operation, target_type, target, content)
    return success(f"Patched content in {filepath}")


@circuit_protected
@mcp.tool()
async def put_content(input: FilePathInput, content: str):
    await api.put_content(input.filepath, content)
    return success(f"Updated file {input.filepath}")


@circuit_protected
@mcp.tool()
async def delete_file(input: FilePathInput, confirm: bool):
    if not confirm:
        return error("confirm must be true")

    await api.delete_file(input.filepath)
    return success(f"Deleted {input.filepath}")

# ========================
# HEALTH CHECK (NO DECORATOR)
# ========================

@mcp.tool()
async def check_connection():
    start_time = time.time()

    try:
        files = await api.list_files_in_vault()
        latency = round((time.time() - start_time) * 1000, 2)

        return success({
            "status": "healthy",
            "latency_ms": latency,
            "file_count": len(files),
            "host": api.base_url,
            "circuit_state": circuit["state"]
        })

    except Exception as e:
        latency = round((time.time() - start_time) * 1000, 2)

        return error({
            "status": "unhealthy",
            "latency_ms": latency,
            "reason": str(e),
            "host": api.base_url,
            "circuit_state": circuit["state"]
        })

# ========================
# RUN SERVER
# ========================

if __name__ == "__main__":
    mcp.run()