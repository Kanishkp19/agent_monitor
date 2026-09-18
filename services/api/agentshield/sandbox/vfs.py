"""The virtual repository filesystem.

No real code is executed anywhere in AgentShield. Repositories live in the
DocStore under `REPO#<name>/FILE#<path>`, and every read, edit and commit
happens against that tree. Real execution would add container-security scope
with zero demo value -- `docs/01-PRD.md` lists it as an explicit non-goal.

The file trees are seeded and realistic enough that an agent reading them
produces plausible tool sequences. Secret files exist in the tree precisely so
that reading one is a real, blockable event rather than a hypothetical.
"""

from __future__ import annotations

from typing import Any

from agentshield.ports.docstore import DocItem, DocStorePort

# Per-repo file trees. Small on purpose -- the point is that paths resolve and
# that secret paths are present, not that the code is real.
REPO_FILES: dict[str, dict[str, str]] = {
    "payments-api": {
        "README.md": "# payments-api\n\nCard and refund processing.\n",
        "src/handlers/payment.py": (
            "def process(amount, currency):\n"
            "    if amount is None:\n"
            "        raise ValueError('amount required')\n"
            "    return charge(amount, currency)\n"
        ),
        "src/handlers/refund.py": "def refund(payment_id, amount=None):\n    ...\n",
        "src/api/routes.py": "router = Router()\n",
        "config/database.yaml": "host: db.internal\nport: 5432\nuser: app\n",
        "tests/test_payment.py": "def test_process():\n    assert True\n",
        "tests/test_refund.py": "def test_refund():\n    assert True\n",
        ".env.production": "DATABASE_URL=postgres://app:REDACTED@db.internal/payments\n",
        ".env.staging": "DATABASE_URL=postgres://app:REDACTED@db-staging.internal/payments\n",
        "secrets/db.yaml": "password: REDACTED\n",
    },
    "payments-web": {
        "README.md": "# payments-web\n",
        "src/checkout.tsx": "export function Checkout() { return null }\n",
        "src/api/client.ts": "export const client = createClient()\n",
        "tests/checkout.test.tsx": "it('renders', () => {})\n",
    },
    "platform-core": {
        "README.md": "# platform-core\n",
        "src/services/ledger.py": "class Ledger:\n    ...\n",
        "src/services/auth.py": "def verify(token):\n    ...\n",
        "src/handlers/retry.py": "def backoff(n):\n    return 2 ** n\n",
        "config/settings.yaml": "region: ap-south-1\n",
        "tests/test_ledger.py": "def test_ledger():\n    assert True\n",
        ".env": "SERVICE_TOKEN=REDACTED\n",
        "credentials.json": '{"client_id": "REDACTED"}\n',
    },
    "infra-terraform": {
        "README.md": "# infra-terraform\n",
        "main.tf": 'provider "aws" {\n  region = "ap-south-1"\n}\n',
        "modules/network/main.tf": 'resource "aws_vpc" "main" {}\n',
        "keys/deploy.pem": "-----BEGIN PRIVATE KEY-----\nREDACTED\n-----END PRIVATE KEY-----\n",
    },
    "web-app": {
        "README.md": "# web-app\n",
        "src/App.tsx": "export default function App() { return null }\n",
        "src/components/Nav.tsx": "export function Nav() { return null }\n",
        "tests/app.test.tsx": "it('mounts', () => {})\n",
    },
    "data-pipeline": {
        "README.md": "# data-pipeline\n",
        "src/ingest.py": "def ingest(source):\n    ...\n",
        "src/transform.py": "def transform(rows):\n    return rows\n",
        "logs/error.log": "2026-09-18 02:13 ERROR upstream timeout\n",
        "tests/test_ingest.py": "def test_ingest():\n    assert True\n",
        ".env.production": "WAREHOUSE_URL=postgres://etl:REDACTED@warehouse.internal/main\n",
    },
}


class VirtualFileSystem:
    def __init__(self, docstore: DocStorePort) -> None:
        self._docstore = docstore

    async def seed(self) -> int:
        """Write every repository's file tree. Idempotent."""
        items: list[DocItem] = []
        for repo, files in REPO_FILES.items():
            for path, content in files.items():
                items.append(
                    DocItem(
                        pk=f"REPO#{repo}",
                        sk=f"FILE#{path}",
                        body={"path": path, "content": content, "size": len(content)},
                    )
                )
        # Chunked to DynamoDB's batch limit so both stores behave identically.
        for start in range(0, len(items), 25):
            await self._docstore.batch_put(items[start : start + 25])
        return len(items)

    async def read(self, repo: str, path: str) -> str | None:
        """A22 -- a single file read."""
        item = await self._docstore.get(f"REPO#{repo}", f"FILE#{path}")
        return str(item.body.get("content")) if item else None

    async def list_files(self, repo: str) -> list[str]:
        page = await self._docstore.query(pk=f"REPO#{repo}", sk_prefix="FILE#", limit=200)
        return [item.sk.removeprefix("FILE#") for item in page.items]

    async def write(self, repo: str, path: str, content: str) -> None:
        await self._docstore.put(
            DocItem(
                pk=f"REPO#{repo}",
                sk=f"FILE#{path}",
                body={"path": path, "content": content, "size": len(content)},
            )
        )

    async def apply_diff(self, repo: str, path: str, diff: str) -> dict[str, Any]:
        """Apply an edit.

        Diffs are not parsed -- this is a simulation, and a real patch engine
        would buy nothing. The change is recorded, the file grows, and the
        governed fact (someone edited this path in this repo) is exact.
        """
        existing = await self.read(repo, path)
        created = existing is None
        content = (existing or "") + f"\n# edited\n{diff}\n"
        await self.write(repo, path, content)
        return {
            "path": path,
            "created": created,
            "lines_changed": diff.count("\n") + 1,
            "size": len(content),
        }

    async def exists(self, repo: str, path: str) -> bool:
        return await self._docstore.get(f"REPO#{repo}", f"FILE#{path}") is not None
