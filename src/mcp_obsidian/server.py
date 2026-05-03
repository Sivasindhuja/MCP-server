from fastmcp import FastMCP
import os
from dotenv import load_dotenv
from APIWrapper import Obsidian
from pydantic import BaseModel, field_validator

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

#to measure latency difference between requests and async
import time


# ========================
#  RESPONSE HELPERS
# ========================

def success(data):
    return {"success": True, "data": data}

def error(message):
    return {"success": False, "error": message}


# ========================
#  INPUT VALIDATION
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
#  FILE OPERATIONS
# ========================

@mcp.tool()
async def list_files_in_vault():
    """List all note file paths available in the Obsidian vault"""
    try:
        return success(await api.list_files_in_vault())
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def list_files_in_dir(input: DirPathInput):
    """List note file paths inside a specific directory"""
    try:
        return success(await api.list_files_in_dir(input.dirpath))
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def list_note_titles():
    """List only note file names (without content) for quick navigation"""
    try:
        files = await api.list_files_in_vault()
        titles = [f.split("/")[-1] for f in files]
        return success(titles)
    except Exception as e:
        return error(str(e))


@mcp.tool()

async def get_file_contents(input: FilePathInput):
    """Retrieve full markdown content of a note using its relative file path in the vault"""
    try:
        return success(await api.get_file_contents(input.filepath))
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def batch_get_file_contents(filepaths: list[str]):
    """Retrieve and combine contents of multiple notes"""
    try:
        return success(await api.get_batch_file_contents(filepaths))
    except Exception as e:
        return error(str(e))


# ========================
#  SEARCH
# ========================

@mcp.tool()

async def simple_search(query: str, context_length: int = 100):
    """Search for text across notes and return matching snippets with context"""
    try:
        return success(await api.search(query, context_length))
    except Exception as e:
        return error(str(e))


@mcp.tool()
async  def complex_search(query: dict):
    """Perform advanced structured search using JsonLogic queries"""
    try:
        return success(await api.search_json(query))
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def search_and_summarize(query: str):
    """
    Search for relevant notes and return a concise combined summary.
    Useful for quick insights instead of full note content.
    """
    try:
        results = await api.search(query, 100)

        if not results:
            return success("No relevant notes found.")

        combined_text = ""
        for item in results[:5]:
            combined_text += item.get("content", "") + "\n\n"

        summary = combined_text[:500]  # simple truncation

        return success({
            "summary": summary,
            "source_count": len(results)
        })

    except Exception as e:
        return error(str(e))


# ========================
#  WRITE / MODIFY
# ========================

@mcp.tool()
async def create_note(input: FilePathInput, content: str):
    """Create a new note with given content. Overwrites if file already exists."""
    try:
        await api.put_content(input.filepath, content)
        return success(f"Created note {input.filepath}")
    except Exception as e:
        return error(str(e))


@mcp.tool()

async def append_content(input: FilePathInput, content: str):
    """Append content to an existing note"""
    try:
        await api.append_content(input.filepath, content)
        return success(f"Appended content to {input.filepath}")
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def patch_content(filepath: str, operation: str, target_type: str, target: str, content: str):
    """Modify specific sections inside a note"""
    try:
        await api.patch_content(filepath, operation, target_type, target, content)
        return success(f"Patched content in {filepath}")
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def put_content(input: FilePathInput, content: str):
    """Overwrite or create a note with full content"""
    try:
        await api.put_content(input.filepath, content)
        return success(f"Updated file {input.filepath}")
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def delete_file(input: FilePathInput, confirm: bool):
    """Delete a note (requires confirm=True)"""
    try:
        if not confirm:
            return error("confirm must be true")
        await api.delete_file(input.filepath)
        return success(f"Deleted {input.filepath}")
    except Exception as e:
        return error(str(e))


# ========================
#  PERIODIC NOTES
# ========================

@mcp.tool()
async def get_periodic_note(period: str, type: str = "content"):
    """Retrieve periodic notes such as daily, weekly, or monthly notes"""
    try:
        return success(await api.get_periodic_note(period, type))
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def get_recent_periodic_notes(period: str, limit: int = 5, include_content: bool = False):
    """Retrieve recently created periodic notes"""
    try:
        return success(await api.get_recent_periodic_notes(period, limit, include_content))
    except Exception as e:
        return error(str(e))


@mcp.tool()
async def get_recent_changes(limit: int = 10, days: int = 90):
    """Retrieve recently modified notes in the vault"""
    try:
        return success(await api.get_recent_changes(limit, days))
    except Exception as e:
        return error(str(e))


# ========================
# RUN SERVER
# ========================

if __name__ == "__main__":
    mcp.run()