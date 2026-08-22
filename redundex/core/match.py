from .types import Group


class UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def build_groups(entries, matches, quality=None):
    quality = quality or {}
    uf = UnionFind(entries.keys())
    for m in matches:
        if m.a in entries and m.b in entries:
            uf.union(m.a, m.b)
    root_matches = {}
    for m in matches:
        if m.a in entries and m.b in entries:
            root_matches.setdefault(uf.find(m.a), []).append(m)
    clusters = {}
    for path in entries:
        clusters.setdefault(uf.find(path), []).append(path)
    groups = []
    for root, members in clusters.items():
        if len(members) < 2:
            continue
        use_quality = all(p in quality for p in members)
        if use_quality:
            members.sort(
                key=lambda p: (quality[p], entries[p].mtime_ns),
                reverse=True,
            )
        else:
            members.sort(
                key=lambda p: (entries[p].size, entries[p].mtime_ns),
                reverse=True,
            )
        gmatches = root_matches.get(root, [])
        best_size = entries[members[0]].size
        redundancy = sum(entries[p].size for p in members) - best_size
        groups.append(
            Group(
                members=[entries[p] for p in members],
                matches=gmatches,
                redundancy=redundancy,
            )
        )
    groups.sort(key=lambda g: g.redundancy, reverse=True)
    return groups
