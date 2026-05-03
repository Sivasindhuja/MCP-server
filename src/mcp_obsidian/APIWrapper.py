import httpx
import urllib.parse
import os
from typing import Any


class Obsidian():
    def __init__(
        self,
        api_key: str,
        protocol: str = os.getenv('OBSIDIAN_PROTOCOL', 'https').lower(),
        host: str = str(os.getenv('OBSIDIAN_HOST', '127.0.0.1')),
        port: int = int(os.getenv('OBSIDIAN_PORT', '27124')),
        verify_ssl: bool = False,
    ):
        self.api_key = api_key
        self.protocol = 'http' if protocol == 'http' else 'https'
        self.host = host
        self.port = port
        self.verify_ssl = verify_ssl

        self.base_url = f'{self.protocol}://{self.host}:{self.port}'

        # ✅ async client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=10.0,
            verify=self.verify_ssl
        )

    def _get_headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.api_key}'
        }

    # ========================
    # SAFE CALL
    # ========================

    async def _safe_call(self, coro):
        try:
            return await coro
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error: {e.response.text}")
        except httpx.RequestError as e:
            raise Exception(f"Request failed: {str(e)}")

    # ========================
    # FILE OPERATIONS
    # ========================

    async def list_files_in_vault(self) -> Any:
        async def call():
            response = await self.client.get("/vault/", headers=self._get_headers())
            response.raise_for_status()
            return response.json()["files"]

        return await self._safe_call(call())

    async def list_files_in_dir(self, dirpath: str) -> Any:
        async def call():
            response = await self.client.get(
                f"/vault/{dirpath}/",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()["files"]

        return await self._safe_call(call())

    async def get_file_contents(self, filepath: str) -> Any:
        async def call():
            response = await self.client.get(
                f"/vault/{filepath}",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.text

        return await self._safe_call(call())

    async def get_batch_file_contents(self, filepaths: list[str]) -> str:
        result = []

        for filepath in filepaths:
            try:
                content = await self.get_file_contents(filepath)
                result.append(f"# {filepath}\n\n{content}\n\n---\n\n")
            except Exception as e:
                result.append(f"# {filepath}\n\nError: {str(e)}\n\n---\n\n")

        return "".join(result)

    # ========================
    # SEARCH
    # ========================

    async def search(self, query: str, context_length: int = 100) -> Any:
        async def call():
            response = await self.client.post(
                "/search/simple/",
                headers=self._get_headers(),
                params={
                    "query": query,
                    "contextLength": context_length
                }
            )
            response.raise_for_status()
            return response.json()

        return await self._safe_call(call())

    async def search_json(self, query: dict) -> Any:
        async def call():
            response = await self.client.post(
                "/search/",
                headers=self._get_headers() | {
                    'Content-Type': 'application/vnd.olrapi.jsonlogic+json'
                },
                json=query
            )
            response.raise_for_status()
            return response.json()

        return await self._safe_call(call())

    # ========================
    # WRITE / MODIFY
    # ========================

    async def append_content(self, filepath: str, content: str):
        async def call():
            response = await self.client.post(
                f"/vault/{filepath}",
                headers=self._get_headers() | {'Content-Type': 'text/markdown'},
                content=content
            )
            response.raise_for_status()

        return await self._safe_call(call())

    async def patch_content(self, filepath: str, operation: str, target_type: str, target: str, content: str):
        async def call():
            response = await self.client.patch(
                f"/vault/{filepath}",
                headers=self._get_headers() | {
                    'Content-Type': 'text/markdown',
                    'Operation': operation,
                    'Target-Type': target_type,
                    'Target': urllib.parse.quote(target)
                },
                content=content
            )
            response.raise_for_status()

        return await self._safe_call(call())

    async def put_content(self, filepath: str, content: str):
        async def call():
            response = await self.client.put(
                f"/vault/{filepath}",
                headers=self._get_headers() | {'Content-Type': 'text/markdown'},
                content=content
            )
            response.raise_for_status()

        return await self._safe_call(call())

    async def delete_file(self, filepath: str):
        async def call():
            response = await self.client.delete(
                f"/vault/{filepath}",
                headers=self._get_headers()
            )
            response.raise_for_status()

        return await self._safe_call(call())

    # ========================
    # PERIODIC NOTES
    # ========================

    async def get_periodic_note(self, period: str, type: str = "content") -> Any:
        async def call():
            headers = self._get_headers()
            if type == "metadata":
                headers['Accept'] = 'application/vnd.olrapi.note+json'

            response = await self.client.get(
                f"/periodic/{period}/",
                headers=headers
            )
            response.raise_for_status()
            return response.text

        return await self._safe_call(call())

    async def get_recent_periodic_notes(self, period: str, limit: int = 5, include_content: bool = False) -> Any:
        async def call():
            response = await self.client.get(
                f"/periodic/{period}/recent",
                headers=self._get_headers(),
                params={
                    "limit": limit,
                    "includeContent": include_content
                }
            )
            response.raise_for_status()
            return response.json()

        return await self._safe_call(call())

    async def get_recent_changes(self, limit: int = 10, days: int = 90) -> Any:
        async def call():
            query = "\n".join([
                "TABLE file.mtime",
                f"WHERE file.mtime >= date(today) - dur({days} days)",
                "SORT file.mtime DESC",
                f"LIMIT {limit}"
            ])

            response = await self.client.post(
                "/search/",
                headers=self._get_headers() | {
                    'Content-Type': 'application/vnd.olrapi.dataview.dql+txt'
                },
                content=query.encode("utf-8")
            )
            response.raise_for_status()
            return response.json()

        return await self._safe_call(call())