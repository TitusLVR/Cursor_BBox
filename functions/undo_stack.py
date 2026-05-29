"""Generic two-stack undo/redo for modal operators.

Usage:

    self.undo_stack = OperatorUndoStack()

    # Before any mutating action:
    self.undo_stack.push(self._snapshot())
    do_mutation()

    # Ctrl+Z:
    snap = self.undo_stack.pop_undo(self._snapshot())
    if snap is not None:
        self._restore(snap)

    # Ctrl+Shift+Z:
    snap = self.undo_stack.pop_redo(self._snapshot())
    if snap is not None:
        self._restore(snap)

`_snapshot()` and `_restore()` are operator-specific — define them so they
capture / re-apply whichever state the operator wants reversible.
"""
from __future__ import annotations


class OperatorUndoStack:
    """Two-stack undo/redo. `push()` clears the redo stack (Blender's
    convention). Both stacks are bounded to `limit` entries."""

    def __init__(self, limit: int = 64):
        self._undo: list = []
        self._redo: list = []
        self._limit = max(1, int(limit))

    def push(self, snapshot) -> None:
        self._undo.append(snapshot)
        if len(self._undo) > self._limit:
            self._undo.pop(0)
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def pop_undo(self, current):
        """Pop the most recent undo snapshot. `current` is pushed onto
        the redo stack so a subsequent redo can return to here. Returns
        the popped snapshot, or None if nothing to undo."""
        if not self._undo:
            return None
        self._redo.append(current)
        if len(self._redo) > self._limit:
            self._redo.pop(0)
        return self._undo.pop()

    def pop_redo(self, current):
        """Symmetric to `pop_undo`."""
        if not self._redo:
            return None
        self._undo.append(current)
        if len(self._undo) > self._limit:
            self._undo.pop(0)
        return self._redo.pop()

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
