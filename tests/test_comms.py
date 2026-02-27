"""Tests for the communication layer."""

import asyncio
import pytest

from verifai.comms.message_bus import MessageBus
from verifai.comms.dialogue import DialogueManager, DialogueState
from verifai.models.messages import PlanRequest, PlanResponse, ReviewFeedback


class TestMessageBus:
    def test_subscribe_and_publish(self):
        bus = MessageBus()
        received = []

        async def handler(msg):
            received.append(msg)

        bus.subscribe("test_channel", handler)

        msg = PlanRequest(
            sender="a", recipient="b", component_name="comp"
        )

        asyncio.get_event_loop().run_until_complete(bus.publish("test_channel", msg))
        assert len(received) == 1
        assert received[0].sender == "a"

    def test_send_routes_to_recipient(self):
        bus = MessageBus()
        received = []

        async def handler(msg):
            received.append(msg)

        bus.subscribe("agent_b", handler)

        msg = PlanRequest(
            sender="agent_a", recipient="agent_b", component_name="comp"
        )

        asyncio.get_event_loop().run_until_complete(bus.send(msg))
        assert len(received) == 1

    def test_history(self):
        bus = MessageBus()
        msg = PlanRequest(sender="a", recipient="b", component_name="c")
        asyncio.get_event_loop().run_until_complete(bus.publish("ch", msg))
        assert len(bus.history) == 1

    def test_get_history_for(self):
        bus = MessageBus()
        msg1 = PlanRequest(sender="a", recipient="b", component_name="c1")
        msg2 = PlanRequest(sender="b", recipient="c", component_name="c2")
        asyncio.get_event_loop().run_until_complete(bus.publish("ch", msg1))
        asyncio.get_event_loop().run_until_complete(bus.publish("ch", msg2))

        hist_b = bus.get_history_for("b")
        assert len(hist_b) == 2  # b is recipient of msg1, sender of msg2


class TestDialogueManager:
    def test_full_dialogue_flow(self):
        mgr = DialogueManager(max_revisions=3)

        request = PlanRequest(
            sender="orchestrator",
            recipient="env_agent",
            component_name="test_env",
        )

        entry = mgr.start_dialogue(request)
        assert entry.state == DialogueState.IN_PROGRESS

        response = PlanResponse(
            sender="env_agent",
            recipient="orchestrator",
            correlation_id=request.id,
            component_name="test_env",
            proposed_code="class test_env extends uvm_env;",
        )
        entry = mgr.record_response(response)
        assert entry.state == DialogueState.AWAITING_REVIEW

        feedback = ReviewFeedback(
            sender="orchestrator",
            recipient="env_agent",
            correlation_id=request.id,
            component_name="test_env",
            approved=True,
        )
        entry = mgr.record_feedback(feedback)
        assert entry.state == DialogueState.APPROVED

    def test_revision_cycle(self):
        mgr = DialogueManager(max_revisions=2)

        request = PlanRequest(
            sender="orchestrator",
            recipient="agent",
            component_name="comp",
        )
        mgr.start_dialogue(request)

        response = PlanResponse(
            sender="agent", recipient="orchestrator",
            correlation_id=request.id, component_name="comp",
        )
        mgr.record_response(response)

        # First rejection
        feedback = ReviewFeedback(
            sender="orchestrator", recipient="agent",
            correlation_id=request.id, component_name="comp",
            approved=False, issues=["wrong ports"],
        )
        entry = mgr.record_feedback(feedback)
        assert entry.state == DialogueState.REVISION_REQUESTED

        # Second rejection -> should fail
        entry = mgr.record_feedback(feedback)
        assert entry.state == DialogueState.FAILED

    def test_active_dialogues(self):
        mgr = DialogueManager()

        r1 = PlanRequest(sender="o", recipient="a1", component_name="c1")
        r2 = PlanRequest(sender="o", recipient="a2", component_name="c2")
        mgr.start_dialogue(r1)
        mgr.start_dialogue(r2)

        assert len(mgr.get_active_dialogues()) == 2

        # Approve first dialogue
        resp = PlanResponse(sender="a1", recipient="o", correlation_id=r1.id, component_name="c1")
        mgr.record_response(resp)
        fb = ReviewFeedback(sender="o", recipient="a1", correlation_id=r1.id, component_name="c1", approved=True)
        mgr.record_feedback(fb)

        assert len(mgr.get_active_dialogues()) == 1
