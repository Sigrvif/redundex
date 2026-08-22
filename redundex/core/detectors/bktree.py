class _Node:
    __slots__ = ("items", "children")

    def __init__(self, item):
        self.items = [item]
        self.children = {}


class BKTree:
    def __init__(self, distance=None):
        if distance is None:
            from .imagehash import hamming

            distance = hamming
        self.distance = distance
        self.root = None

    def add(self, item):
        if self.root is None:
            self.root = _Node(item)
            return
        node = self.root
        while True:
            d = self.distance(item, node.items[0])
            if d == 0:
                if item not in node.items:
                    node.items.append(item)
                return
            child = node.children.get(d)
            if child is None:
                node.children[d] = _Node(item)
                return
            node = child

    def query(self, target, radius):
        found = []
        if self.root is None:
            return found
        stack = [self.root]
        while stack:
            node = stack.pop()
            d = self.distance(target, node.items[0])
            if d <= radius:
                for it in node.items:
                    found.append((d, it))
            lo, hi = d - radius, d + radius
            for dist, child in node.children.items():
                if lo <= dist <= hi:
                    stack.append(child)
        return found
