可行，而且**非常适合交给 Codex 实现第一版 PoC**。但你要给 Codex 的不是一句“帮我实现 metadata DB”，而是一份明确的工程说明文档，包括目标、边界、目录结构、API、数据库 schema、测试方式和不允许做什么。

尤其要强调：**第一版不是做完整产品，而是做 workspace-local PoC**。

也就是：

```text
project/
  .metamirror/
    metadata.db
    derived/
    trash/
    audit.jsonl
  metamirror/
    ...
```

这样 Codex 可以在一个 repo 里完成。

VS Code 支持 workspace 级 `.vscode/mcp.json` 配置 MCP server；OpenAI 文档也说明 Codex 可以通过配置连接 MCP server，VS Code/Copilot Agent mode 也可以使用 `.vscode/mcp.json` 添加 MCP server。([OpenAI Platform][1]) Codex 也能读取 `AGENTS.md` 作为项目内开发指导，OpenAI 对 Codex 的介绍中明确提到 Codex 可由仓库中的 `AGENTS.md` 指导。([OpenAI][2])

## 我建议你给 Codex 的实现任务

你可以让 Codex 实现一个 Python 项目：

```text
MetaMirror: A Metadata-First AI-Safe Local File Mirror
```

第一版目标：

```text
1. 监听一个 workspace 文件夹
2. 自动同步文件 metadata 到 SQLite
3. 支持基础搜索和重复文件检测
4. 记录文件创建、修改、移动、删除事件
5. AI 只能创建删除 proposal，不能直接删除文件
6. 用户 approve 后才 soft-delete 到 .metamirror/trash/
7. 暴露 CLI，后续再接 MCP server
```

第一版先做 CLI，成功后再做 MCP。这样 Codex 更容易实现和测试。

## 可以直接交给 Codex 的文档

下面这段可以保存成 `IMPLEMENTATION_SPEC.md`，然后让 Codex 按它实现。

````markdown
# MetaMirror Implementation Spec

## Goal

Build a workspace-local proof of concept for MetaMirror: a metadata-first, AI-safe local filesystem mirror.

MetaMirror continuously synchronizes files in a workspace into a local SQLite metadata database. AI tools should interact with the metadata database and safe operation APIs instead of directly deleting, moving, or overwriting raw files.

The first version should be a CLI-based PoC. MCP integration can be added after the core works.

## Core Principle

Do not expose destructive raw filesystem operations as direct AI tools.

Allowed:
- search metadata
- inspect file metadata
- inspect generated summary
- find duplicates
- propose delete
- list proposals
- approve/reject proposals

Not allowed:
- direct hard delete
- direct overwrite
- direct move/rename of raw files
- arbitrary shell command execution

## Workspace Layout

For any workspace, create:

```text
.metamirror/
  metadata.db
  audit.jsonl
  derived/
    summaries/
  trash/
````

The user's files remain in their original folders. MetaMirror should not require moving files into a special folder.

## Python Package Layout

```text
metamirror/
  __init__.py
  cli.py
  db.py
  scanner.py
  watcher.py
  extractor.py
  policy.py
  proposals.py
  audit.py
  utils.py

tests/
  test_scan.py
  test_events.py
  test_duplicates.py
  test_proposals.py
```

## Database Schema

Use SQLite.

### files

```sql
CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    extension TEXT,
    mime_type TEXT,
    size_bytes INTEGER,
    sha256 TEXT,
    created_at TEXT,
    modified_at TEXT,
    last_seen_at TEXT,
    status TEXT DEFAULT 'active',
    dirty INTEGER DEFAULT 0,
    metadata_status TEXT DEFAULT 'basic_only'
);
```

Status values:

* active
* missing
* deleted
* soft_deleted

Metadata status values:

* basic_only
* queued
* indexing
* ready
* stale
* failed
* skipped

### file_metadata

```sql
CREATE TABLE IF NOT EXISTS file_metadata (
    file_id TEXT PRIMARY KEY,
    title TEXT,
    summary TEXT,
    tags TEXT,
    entities TEXT,
    topics TEXT,
    language TEXT,
    doc_type TEXT,
    summary_generated_at TEXT,
    extractor_version TEXT,
    FOREIGN KEY(file_id) REFERENCES files(file_id)
);
```

### file_policy

```sql
CREATE TABLE IF NOT EXISTS file_policy (
    file_id TEXT PRIMARY KEY,
    sensitivity TEXT DEFAULT 'normal',
    ai_can_read_metadata INTEGER DEFAULT 1,
    ai_can_read_summary INTEGER DEFAULT 1,
    ai_can_read_full_content INTEGER DEFAULT 0,
    ai_can_create_derived INTEGER DEFAULT 1,
    ai_can_modify_original INTEGER DEFAULT 0,
    ai_can_delete_original INTEGER DEFAULT 0,
    raw_read_requires_approval INTEGER DEFAULT 1,
    delete_requires_approval INTEGER DEFAULT 1,
    retention_policy TEXT DEFAULT 'manual_approval',
    FOREIGN KEY(file_id) REFERENCES files(file_id)
);
```

### file_events

```sql
CREATE TABLE IF NOT EXISTS file_events (
    event_id TEXT PRIMARY KEY,
    file_id TEXT,
    event_type TEXT NOT NULL,
    old_path TEXT,
    new_path TEXT,
    actor TEXT,
    reason TEXT,
    evidence TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(file_id) REFERENCES files(file_id)
);
```

Event types:

* created
* modified
* moved
* missing
* deleted
* soft_deleted
* restored
* ai_proposed_delete
* user_approved_delete
* user_rejected_delete

### action_proposals

```sql
CREATE TABLE IF NOT EXISTS action_proposals (
    proposal_id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    file_id TEXT NOT NULL,
    proposed_target TEXT,
    reason TEXT,
    evidence TEXT,
    status TEXT DEFAULT 'pending',
    created_by TEXT DEFAULT 'ai',
    created_at TEXT,
    approved_at TEXT,
    executed_at TEXT,
    FOREIGN KEY(file_id) REFERENCES files(file_id)
);
```

Proposal status values:

* pending
* approved
* rejected
* executed
* expired

## CLI Commands

Use Typer or argparse.

Required commands:

```bash
metamirror init <workspace>
metamirror scan <workspace>
metamirror watch <workspace>
metamirror search <workspace> "query"
metamirror duplicates <workspace>
metamirror recent <workspace> --days 7
metamirror propose-delete <workspace> <file_id> --reason "..." --evidence "..."
metamirror proposals <workspace>
metamirror approve <workspace> <proposal_id>
metamirror reject <workspace> <proposal_id>
metamirror status <workspace>
```

## Behavior

### init

Creates `.metamirror/`, `metadata.db`, `derived/`, `trash/`, and `audit.jsonl`.

### scan

Performs a full scan of the workspace, excluding:

* `.git/`
* `.metamirror/`
* `node_modules/`
* `.venv/`
* `__pycache__/`
* `.DS_Store`

For each file:

* compute basic metadata
* compute sha256 for files smaller than 100MB
* for files larger than 100MB, set sha256 to NULL and metadata_status to `basic_only`
* insert or update `files`
* insert default policy if missing
* create `created` or `modified` events

If a DB record exists but the file no longer exists, mark it as `missing`.

### search

Search over:

* filename
* path
* summary
* tags

Return:

* file_id
* path
* filename
* summary
* tags
* status
* metadata_status
* sensitivity

### duplicates

Group active files by `sha256` and show groups where count > 1.

### propose-delete

Creates a pending delete proposal. This must not delete or move the raw file.

Also write:

* action_proposals row
* file_events row with event_type = `ai_proposed_delete`
* audit.jsonl entry

### approve

Only for pending delete proposals.

Execution behavior:

* move the raw file into `.metamirror/trash/<date>/<filename>`
* update files.status = `soft_deleted`
* update proposal.status = `executed`
* write `soft_deleted` and `user_approved_delete` events
* write audit.jsonl entry

Never hard delete.

### reject

Sets proposal.status = `rejected`, writes a `user_rejected_delete` event, and writes audit.jsonl.

## Summary Extraction

For MVP:

* `.txt`, `.md`, `.py`, `.sql`, `.json`, `.yaml`: read first 4KB and create a simple summary placeholder.
* `.pdf`, `.docx`, images, videos: do not parse deeply in v0.1. Store basic metadata only.
* For unsupported files, set metadata_status = `basic_only`.

Do not call external LLM APIs in v0.1.

## Safety Requirements

* Never hard delete files.
* Never expose arbitrary shell execution.
* Never scan `.metamirror/`.
* Never modify raw files except when approving a soft-delete proposal.
* All destructive actions must go through `action_proposals`.
* All operations should write audit records.

## Tests

Implement tests for:

1. `init` creates the expected directories and DB.
2. `scan` inserts files into the DB.
3. deleted local files become `missing`, not removed from DB.
4. duplicate files are detected by sha256.
5. `propose-delete` creates a proposal but does not delete the file.
6. `approve` moves file to `.metamirror/trash/` and marks it `soft_deleted`.
7. `.metamirror/` and `.git/` are excluded from scanning.

## Future MCP Integration

After CLI works, add an MCP server exposing safe tools:

* search_files
* get_file_metadata
* get_file_summary
* find_duplicates
* list_recent_changes
* propose_delete
* list_pending_proposals
* approve_proposal
* reject_proposal

Do not expose:

* delete_file
* overwrite_file
* move_file
* run_shell

````

## 给 Codex 的 prompt

你可以直接这样发给 Codex：

```text
Please implement the project described in IMPLEMENTATION_SPEC.md.

Focus on a working Python PoC, not a full product.

Requirements:
1. Use SQLite for `.metamirror/metadata.db`.
2. Implement the CLI commands listed in the spec.
3. Implement safe proposal-based deletion only. Never hard delete files.
4. Add tests for scan, missing files, duplicate detection, proposal creation, and approval-based soft delete.
5. Keep the code modular and easy to extend with an MCP server later.
6. Do not implement external LLM calls in v0.1.
7. Do not scan `.metamirror/`, `.git/`, `node_modules/`, `.venv/`, or `__pycache__/`.
8. After implementation, run tests and show me the CLI usage examples.
````

## 我建议的执行顺序

让 Codex 分三步做，不要一次性全做太多：

第一步：

```text
init + scan + SQLite schema + status
```

第二步：

```text
search + duplicates + recent + events
```

第三步：

```text
propose-delete + approve/reject + tests
```

MCP server 放到第四步。这样更稳。

## 结论

可行，而且这个任务非常适合 Codex：边界清楚、模块明确、测试容易。第一版不要让 Codex 同时做 GUI、MCP、LLM summary、vector search、系统级 daemon。先做一个 **workspace-local `.metamirror/metadata.db` + CLI + proposal workflow**，证明核心 idea。

[1]: https://platform.openai.com/docs/docs-mcp?utm_source=chatgpt.com "Docs MCP | OpenAI API"
[2]: https://openai.com/index/introducing-codex/?utm_source=chatgpt.com "Introducing Codex | OpenAI"
