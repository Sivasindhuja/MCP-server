from fastmcp import FastMCP
import os
from dotenv import load_dotenv
from APIWrapper import Obsidian
from pydantic import BaseModel, field_validator
import time
import httpx

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

@mcp.tool()
async def list_files_in_vault():
    try:
        return success(await api.list_files_in_vault())
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def list_files_in_dir(input: DirPathInput):
    try:
        return success(await api.list_files_in_dir(input.dirpath))
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def list_note_titles():
    try:
        files = await api.list_files_in_vault()
        titles = [f.split("/")[-1] for f in files]
        return success(titles)
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def get_file_contents(input: FilePathInput):
    try:
        return success(await api.get_file_contents(input.filepath))
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def batch_get_file_contents(filepaths: list[str]):
    try:
        return success(await api.get_batch_file_contents(filepaths))
    except Exception as e:
        return error(str(e))

# ========================
# SEARCH
# ========================

@mcp.tool()
async def simple_search(query: str, context_length: int = 100):
    try:
        return success(await api.search(query, context_length))
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def complex_search(query: dict):
    try:
        return success(await api.search_json(query))
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def search_and_summarize(query: str):
    try:
        results = await api.search(query, 100)

        if not results:
            return success("No relevant notes found.")

        combined_text = ""
        for item in results[:5]:
            combined_text += item.get("content", "") + "\n\n"

        summary = combined_text[:500]

        return success({
            "summary": summary,
            "source_count": len(results)
        })

    except Exception as e:
        return error(str(e))

# ========================
# WRITE / MODIFY
# ========================

@mcp.tool()
async def create_note(input: FilePathInput, content: str):
    try:
        await api.put_content(input.filepath, content)
        return success(f"Created note {input.filepath}")
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def append_content(input: FilePathInput, content: str):
    try:
        await api.append_content(input.filepath, content)
        return success(f"Appended content to {input.filepath}")
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def patch_content(filepath: str, operation: str, target_type: str, target: str, content: str):
    try:
        await api.patch_content(filepath, operation, target_type, target, content)
        return success(f"Patched content in {filepath}")
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def put_content(input: FilePathInput, content: str):
    try:
        await api.put_content(input.filepath, content)
        return success(f"Updated file {input.filepath}")
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def delete_file(input: FilePathInput, confirm: bool):
    try:
        if not confirm:
            return error("confirm must be true")
        await api.delete_file(input.filepath)
        return success(f"Deleted {input.filepath}")
    except Exception as e:
        return error(str(e))

# ========================
# CIRCUIT BREAKER + HEALTH CHECK
# ========================

@mcp.tool()
async def check_connection():
    """
    Verify API connectivity with circuit breaker protection
    """

    global circuit
    now = time.time()

    # ------------------------
    # CIRCUIT OPEN CHECK
    # ------------------------
    if circuit["state"] == "OPEN":
        if now - circuit["last_failure_time"] < RECOVERY_TIME:
            return error({
                "status": "circuit_open",
                "message": "Service temporarily unavailable. Skipping request.",
                "retry_after_sec": RECOVERY_TIME
            })
        else:
            circuit["state"] = "HALF_OPEN"

    start_time = time.time()

    try:
        files = await api.list_files_in_vault()
        latency = round((time.time() - start_time) * 1000, 2)

        # RESET CIRCUIT ON SUCCESS
        circuit["failures"] = 0
        circuit["state"] = "CLOSED"

        return success({
            "status": "healthy",
            "latency_ms": latency,
            "checks": {
                "api_key": True,
                "host_reachable": True,
                "response_valid": isinstance(files, list)
            },
            "file_count": len(files),
            "host": api.base_url,
            "circuit_state": circuit["state"]
        })

    except httpx.HTTPStatusError as e:
        failure_type = "AUTH_OR_HTTP_ERROR"
        reason = e.response.text
        status_code = e.response.status_code

    except httpx.RequestError as e:
        failure_type = "NETWORK_ERROR"
        reason = str(e)
        status_code = None

    except Exception as e:
        failure_type = "UNKNOWN_ERROR"
        reason = str(e)
        status_code = None

    # ------------------------
    # FAILURE HANDLING
    # ------------------------
    latency = round((time.time() - start_time) * 1000, 2)

    circuit["failures"] += 1
    circuit["last_failure_time"] = time.time()

    if circuit["failures"] >= FAILURE_THRESHOLD:
        circuit["state"] = "OPEN"

    return error({
        "status": "unhealthy",
        "latency_ms": latency,
        "failure_type": failure_type,
        "status_code": status_code,
        "reason": reason,
        "host": api.base_url,
        "circuit_state": circuit["state"],
        "failure_count": circuit["failures"]
    })

# ========================
# RUN SERVER
# ========================

if __name__ == "__main__":
    mcp.run()