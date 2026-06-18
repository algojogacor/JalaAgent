"""Integration test: policy pipeline across all 4 approval modes."""

import pytest
from agent_core.models import ActionCategory, ApprovalMode
from agent_core.policy import PolicyDecision, PolicyPipeline


class TestPolicyPipeline:
    def test_paranoid_asks_everything(self) -> None:
        pp = PolicyPipeline(mode=ApprovalMode.PARANOID)
        for cat in ActionCategory:
            assert pp.check(cat) == PolicyDecision.ASK

    def test_yolo_allows_everything(self) -> None:
        pp = PolicyPipeline(mode=ApprovalMode.YOLO)
        for cat in ActionCategory:
            assert pp.check(cat) == PolicyDecision.ALLOW

    def test_normal_file_read_auto(self) -> None:
        pp = PolicyPipeline(mode=ApprovalMode.NORMAL)
        assert pp.check(ActionCategory.FILE_READ) == PolicyDecision.ALLOW
        assert pp.check(ActionCategory.NETWORK_GET) == PolicyDecision.ALLOW

    def test_normal_destructive_asks(self) -> None:
        pp = PolicyPipeline(mode=ApprovalMode.NORMAL)
        assert pp.check(ActionCategory.FILE_DELETE) == PolicyDecision.ASK
        assert pp.check(ActionCategory.SHELL_EXEC) == PolicyDecision.ASK

    def test_custom_file_delete_auto(self) -> None:
        pp = PolicyPipeline(mode=ApprovalMode.CUSTOM, custom_rules={"file_delete": "auto"})
        assert pp.check(ActionCategory.FILE_DELETE) == PolicyDecision.ALLOW

    def test_custom_deny_wins(self) -> None:
        pp = PolicyPipeline(mode=ApprovalMode.CUSTOM, custom_rules={"shell_exec": "deny"})
        assert pp.check(ActionCategory.SHELL_EXEC) == PolicyDecision.DENY

    def test_mode_switching(self) -> None:
        pp = PolicyPipeline(mode=ApprovalMode.NORMAL)
        assert pp.check(ActionCategory.SHELL_EXEC) == PolicyDecision.ASK
        pp.mode = ApprovalMode.YOLO
        assert pp.check(ActionCategory.SHELL_EXEC) == PolicyDecision.ALLOW


class TestCredentialPoolIntegration:
    def test_pool_rotation_trigger(self) -> None:
        from agent_core.credentials import CredentialPool
        pool = CredentialPool()
        pool.add("test", "key1", metadata={"tier": "primary"})
        pool.add("test", "key2", metadata={"tier": "backup"})
        assert len(pool._pools["test"]) == 2

@pytest.mark.asyncio
class TestCredentialPoolAsync:
    async def test_acquire_and_fallback(self) -> None:
        from agent_core.credentials import CredentialPool
        pool = CredentialPool()
        pool.add("test", "key-primary")
        pool.add("test", "key-backup")
        cred = await pool.acquire("test")
        assert cred is not None
        assert cred.key in ("key-primary", "key-backup")
