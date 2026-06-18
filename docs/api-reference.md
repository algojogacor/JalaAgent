# API Reference

## Python Packages

### memory-core
```python
from memory_core import FileLayer, VectorLayer, MemoryRetriever, DreamingPipeline, KnowledgeGraph
```

### skill-core
```python
from skill_core import SkillLoader, SkillScanner, SkillWorkshop
```

### agent-core
```python
from agent_core import AgentLoop, ToolRegistry, PolicyPipeline, CredentialPool
from agent_core import SandboxedShell, WorktreeIsolation, PlanMode, DiffEditor
from agent_core import CommandRegistry, get_registry
```

## REST API (jala serve)

### POST /v1/messages
```bash
curl -X POST http://localhost:8787/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"Hello"}]}'
```

### GET /v1/models
```bash
curl http://localhost:8787/v1/models
```

### POST /v1/messages/count_tokens
```bash
curl -X POST http://localhost:8787/v1/messages/count_tokens \
  -d '{"messages":[{"role":"user","content":"Hello"}],"system":"You are helpful"}'
```

## CLI Commands
```bash
jala              # Interactive chat
jala gateway      # CLI + Telegram
jala serve        # API server
jala setup        # Setup wizard
jala memory       # Memory management
jala skills       # Skills management
```
