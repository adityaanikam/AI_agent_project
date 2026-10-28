"""
Runs the graph for one upload and mirrors its progress into the processing records
"""

import logging
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.core.memory import MemoryManager
from app.core.router import ActionRouter
from app.graph.builder import Agents, GraphSettings, build_graph
from app.llm import get_chat_model

logger = logging.getLogger(__name__)

# Graph state keys copied to the processing record after every step
RECORD_FIELDS = ("classification", "agent_output", "actions_triggered", "status", "error")

# Statuses of runs that were cut off mid-way, e.g. by a crash or restart
INCOMPLETE_STATUSES = ["pending", "running", "classified", "processed"]

# Each retry of an action is one graph step, so allow more than the default 25
RECURSION_LIMIT = 100


class RunStateError(Exception):
    """The run is not in a state that allows the requested operation"""


def sqlite_checkpointer(path: str) -> SqliteSaver:
    """Checkpointer that stores every graph step in a SQLite file"""
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


class GraphRunner:
    """Starts, resumes and reviews graph runs; one thread per process_id"""

    def __init__(self, graph, memory: MemoryManager):
        self.graph = graph
        self.memory = memory
        self._active = set()
        self._lock = threading.Lock()

    @staticmethod
    def config(process_id: str) -> Dict[str, Any]:
        return {"configurable": {"thread_id": process_id}, "recursion_limit": RECURSION_LIMIT}

    def start(self, process_id: str, filename: str, content: bytes) -> str:
        self.memory.update_record(process_id, {"status": "running"})
        return self._run(process_id, {"process_id": process_id, "filename": filename, "content": content})

    def pending_review(self, process_id: str) -> Optional[Dict[str, Any]]:
        """What the paused run is asking the reviewer, or None"""
        snapshot = self.graph.get_state(self.config(process_id))
        return snapshot.interrupts[0].value if snapshot.interrupts else None

    def review(self, process_id: str, decision: Dict[str, Any]) -> str:
        """Resume a run paused for review with the reviewer's decision"""
        if self.pending_review(process_id) is None:
            raise RunStateError("run is not waiting for review")
        self.memory.update_record(process_id, {"status": "running"})
        return self._run(process_id, Command(resume=decision))

    def can_resume(self, process_id: str) -> bool:
        """True when a checkpoint has steps left to run and no review is pending"""
        snapshot = self.graph.get_state(self.config(process_id))
        return bool(snapshot.next) and not snapshot.interrupts

    def resume(self, process_id: str) -> str:
        """Continue a crashed or failed run from its last checkpoint"""
        if not self.can_resume(process_id):
            raise RunStateError("run has no unfinished checkpoint to resume")
        self.memory.update_record(process_id, {"status": "running", "error": None})
        return self._run(process_id, None)

    def resume_incomplete(self) -> List[str]:
        """Resume every run left unfinished by a crash or restart"""
        resumed = []
        for record in self.memory.get_by_status(INCOMPLETE_STATUSES):
            if self.can_resume(record.process_id):
                self.resume(record.process_id)
                resumed.append(record.process_id)
            elif self.pending_review(record.process_id) is None:
                self.memory.update_record(record.process_id, {
                    "status": "error",
                    "error": "Interrupted before the first checkpoint; upload the file again"
                })
        return resumed

    def _run(self, process_id: str, graph_input: Any) -> str:
        with self._lock:
            if process_id in self._active:
                raise RunStateError("run is already in progress")
            self._active.add(process_id)
        config = self.config(process_id)
        try:
            for update in self.graph.stream(graph_input, config, stream_mode="updates"):
                for node, values in update.items():
                    if node == "__interrupt__" or not values:
                        continue
                    fields = {k: values[k] for k in RECORD_FIELDS if k in values}
                    if fields:
                        self.memory.update_record(process_id, fields)
            if self.graph.get_state(config).interrupts:
                self.memory.update_record(process_id, {"status": "awaiting_review"})
                return "awaiting_review"
            return self.memory.get_record(process_id).status
        except Exception as e:
            logger.exception(f"Error processing {process_id}")
            self.memory.update_record(process_id, {"status": "error", "error": str(e)})
            return "error"
        finally:
            with self._lock:
                self._active.discard(process_id)


def create_runner(memory: MemoryManager, llm: Optional[BaseChatModel] = None,
                  router: Optional[ActionRouter] = None,
                  checkpoint_path: Optional[str] = None,
                  settings: Optional[GraphSettings] = None) -> GraphRunner:
    """Runner wired from environment settings unless parts are passed in"""
    settings = settings or GraphSettings.from_env()
    graph = build_graph(
        Agents.with_llm(llm or get_chat_model()),
        router or ActionRouter(),
        settings,
        checkpointer=sqlite_checkpointer(checkpoint_path or os.getenv("FLOWBIT_CHECKPOINT_DB", "checkpoints.db"))
    )
    return GraphRunner(graph, memory)
