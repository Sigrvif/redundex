import os
import time

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt

from ..core.types import format_size

COLUMNS = ["Mark", "Name", "Folder", "Size", "Details", "Modified", "Reason"]


class ResultsModel(QtCore.QAbstractItemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._groups = []
        self._visible = []
        self._marked = set()
        self._meta = {}
        self._min_redundancy = 0
        self._node_cache = {}

    def set_result(self, result):
        self.beginResetModel()
        self._groups = list(result.groups)
        self._marked = set()
        self._meta = dict(result.meta)
        self._apply_filter()
        self.endResetModel()

    def set_min_redundancy(self, value):
        self._min_redundancy = value
        self.beginResetModel()
        self._apply_filter()
        self.endResetModel()

    def _apply_filter(self):
        self._node_cache = {}
        self._visible = [
            g for g in self._groups if g.redundancy >= self._min_redundancy
        ]

    def _node(self, key):
        node = self._node_cache.get(key)
        if node is None:
            node = key
            self._node_cache[key] = node
        return node

    def marked_paths(self):
        return sorted(self._marked)

    def group_at_row(self, row):
        return self._visible[row]

    def toggle_mark(self, index):
        node = index.internalPointer() if index.isValid() else None
        if not node or node[0] != "member":
            return
        entry = self._visible[node[1]].members[node[2]]
        if entry.path in self._marked:
            self._marked.discard(entry.path)
        else:
            self._marked.add(entry.path)
        self.dataChanged.emit(index, index)

    def mark_except(self, group_row, key):
        group = self._visible[group_row]

        def sort_key(m):
            if key == "mtime":
                return (m.mtime_ns, m.size)
            if key == "resolution":
                md = self._meta.get(m.path, {})
                return (md.get("width", 0) * md.get("height", 0), m.size)
            return (m.size, m.mtime_ns)

        keep = sorted(group.members, key=sort_key, reverse=True)[0].path
        for m in group.members:
            if m.path == keep:
                self._marked.discard(m.path)
            else:
                self._marked.add(m.path)
        gi = self.index(group_row, 0)
        self.dataChanged.emit(
            self.index(0, 0, gi), self.index(len(group.members) - 1, len(COLUMNS) - 1, gi)
        )

    def index(self, row, column, parent=QtCore.QModelIndex()):
        if not parent.isValid():
            if 0 <= row < len(self._visible):
                return self.createIndex(row, column, self._node(("group", row, -1)))
            return QtCore.QModelIndex()
        node = parent.internalPointer()
        if not node or node[0] != "group":
            return QtCore.QModelIndex()
        members = self._visible[node[1]].members
        if 0 <= row < len(members):
            return self.createIndex(row, column, self._node(("member", node[1], row)))
        return QtCore.QModelIndex()

    def parent(self, index):
        node = index.internalPointer() if index.isValid() else None
        if not node or node[0] != "member":
            return QtCore.QModelIndex()
        return self.createIndex(node[1], 0, self._node(("group", node[1], -1)))

    def rowCount(self, parent=QtCore.QModelIndex()):
        if not parent.isValid():
            return len(self._visible)
        node = parent.internalPointer()
        if not node or node[0] != "group":
            return 0
        return len(self._visible[node[1]].members)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(COLUMNS)

    def flags(self, index):
        base = super().flags(index)
        node = index.internalPointer() if index.isValid() else None
        if index.column() == 0 and node and node[0] == "member":
            return base | Qt.ItemIsUserCheckable
        return base

    def _reasons_for(self, group, path):
        return sorted(
            {
                m.reason.value
                for m in group.matches
                if m.a == path or m.b == path
            }
        )

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        if node is None:
            return None
        if node[0] == "group":
            group = self._visible[node[1]]
            if role == Qt.DisplayRole and index.column() == 1:
                return f"{len(group.members)} files, {format_size(group.redundancy)} redundant"
            if role == Qt.FontRole and index.column() == 1:
                font = QtGui.QFont()
                font.setBold(True)
                return font
            return None
        entry = self._visible[node[1]].members[node[2]]
        group = self._visible[node[1]]
        if role == Qt.CheckStateRole and index.column() == 0:
            return Qt.Checked if entry.path in self._marked else Qt.Unchecked
        if role != Qt.DisplayRole:
            return None
        if index.column() == 1:
            return os.path.basename(entry.path)
        if index.column() == 2:
            return os.path.dirname(entry.path)
        if index.column() == 3:
            return format_size(entry.size)
        if index.column() == 4:
            md = self._meta.get(entry.path, {})
            w, h = md.get("width"), md.get("height")
            dur = md.get("duration")
            parts = []
            if w and h:
                parts.append(f"{w}x{h}")
            if dur:
                parts.append(_format_duration(dur))
            return " ".join(parts)
        if index.column() == 5:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.mtime_ns / 1e9))
        if index.column() == 6:
            return ", ".join(self._reasons_for(group, entry.path))
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and index.column() == 0:
            node = index.internalPointer()
            if node and node[0] == "member":
                self.toggle_mark(index)
                return True
        return False


def _format_duration(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
