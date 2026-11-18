from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

ROOT_ID = "ROOT"


def operation_id(actor: str, counter: int) -> str:
    safe_actor = "".join(character for character in str(actor) if character.isalnum() or character in "._-")
    if not safe_actor or counter < 1:
        raise ValueError("CRDT actor and counter must be valid.")
    return f"{counter:020d}:{safe_actor}"


@dataclass(frozen=True)
class TextOperation:
    op_id: str
    actor: str
    counter: int
    kind: str
    parent_id: str = ROOT_ID
    target_id: str = ""
    value: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TextOperation":
        item = cls(
            op_id=str(payload["op_id"]),
            actor=str(payload["actor"]),
            counter=int(payload["counter"]),
            kind=str(payload["kind"]),
            parent_id=str(payload.get("parent_id", ROOT_ID)),
            target_id=str(payload.get("target_id", "")),
            value=str(payload.get("value", "")),
        )
        if item.op_id != operation_id(item.actor, item.counter):
            raise ValueError("CRDT operation id does not match actor/counter.")
        if item.kind not in {"insert", "delete"}:
            raise ValueError("Unsupported CRDT operation kind.")
        if item.kind == "insert" and len(item.value) != 1:
            raise ValueError("Insert operations must contain exactly one Unicode character.")
        if item.kind == "delete" and not item.target_id:
            raise ValueError("Delete operations require target_id.")
        return item


class TextCRDT:
    """Small deterministic RGA-style text CRDT.

    Insert nodes are ordered by operation id among siblings. Deletes are
    tombstones. Operations are append-only, idempotent and converge regardless
    of delivery order once the same operation set is present.
    """

    def __init__(self, operations: Iterable[TextOperation | dict[str, Any]] = ()) -> None:
        self._operations: dict[str, TextOperation] = {}
        for operation in operations:
            self.apply(operation)

    def apply(self, operation: TextOperation | dict[str, Any]) -> bool:
        item = operation if isinstance(operation, TextOperation) else TextOperation.from_dict(operation)
        existing = self._operations.get(item.op_id)
        if existing is not None:
            if existing != item:
                raise ValueError("Conflicting CRDT operation with the same op_id.")
            return False
        self._operations[item.op_id] = item
        return True

    def merge(self, other: "TextCRDT") -> "TextCRDT":
        merged = TextCRDT(self.operations())
        for operation in other.operations():
            merged.apply(operation)
        return merged

    def operations(self) -> tuple[TextOperation, ...]:
        return tuple(self._operations[key] for key in sorted(self._operations))

    def _insertions(self) -> dict[str, TextOperation]:
        return {key: value for key, value in self._operations.items() if value.kind == "insert"}

    def _deleted(self) -> set[str]:
        return {value.target_id for value in self._operations.values() if value.kind == "delete"}

    def sequence(self) -> list[tuple[str, str, bool]]:
        insertions = self._insertions()
        children: dict[str, list[str]] = {}
        for op_id, operation in insertions.items():
            parent = operation.parent_id if operation.parent_id == ROOT_ID or operation.parent_id in insertions else ROOT_ID
            children.setdefault(parent, []).append(op_id)
        for values in children.values():
            values.sort()
        deleted = self._deleted()
        output: list[tuple[str, str, bool]] = []
        visiting: set[str] = set()

        def walk(parent: str) -> None:
            for op_id in children.get(parent, []):
                if op_id in visiting:
                    raise ValueError("CRDT operation graph contains a cycle.")
                visiting.add(op_id)
                operation = insertions[op_id]
                output.append((op_id, operation.value, op_id in deleted))
                walk(op_id)
                visiting.remove(op_id)

        walk(ROOT_ID)
        return output

    def text(self) -> str:
        return "".join(value for _, value, deleted in self.sequence() if not deleted)

    def visible_ids(self) -> list[str]:
        return [op_id for op_id, _, deleted in self.sequence() if not deleted]

    def local_insert(self, actor: str, counter_start: int, index: int, text: str) -> tuple[TextOperation, ...]:
        if index < 0 or index > len(self.visible_ids()):
            raise IndexError(index)
        parent = ROOT_ID if index == 0 else self.visible_ids()[index - 1]
        operations: list[TextOperation] = []
        counter = counter_start
        for character in text:
            item = TextOperation(operation_id(actor, counter), actor, counter, "insert", parent_id=parent, value=character)
            self.apply(item)
            operations.append(item)
            parent = item.op_id
            counter += 1
        return tuple(operations)

    def local_delete(self, actor: str, counter_start: int, index: int, length: int = 1) -> tuple[TextOperation, ...]:
        visible = self.visible_ids()
        if index < 0 or length < 0 or index + length > len(visible):
            raise IndexError(index)
        operations = []
        for offset, target in enumerate(visible[index:index + length]):
            counter = counter_start + offset
            item = TextOperation(operation_id(actor, counter), actor, counter, "delete", target_id=target)
            self.apply(item)
            operations.append(item)
        return tuple(operations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "biointel.text-crdt.rga.v1",
            "operations": [item.to_dict() for item in self.operations()],
            "text": self.text(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TextCRDT":
        if payload.get("schema") != "biointel.text-crdt.rga.v1":
            raise ValueError("Unsupported CRDT schema.")
        document = cls(payload.get("operations", []))
        expected = payload.get("text")
        if expected is not None and str(expected) != document.text():
            raise ValueError("CRDT serialized text does not match operation set.")
        return document
