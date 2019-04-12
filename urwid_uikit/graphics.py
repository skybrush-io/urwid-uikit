from urwid import LineBox


__all__ = ("PatchedLineBox", )


class PatchedLineBox(LineBox):
    """Patched version of urwid's LineBox_ that also supports being used as a
    fixed size widget.
    """

    _sizing = frozenset(["box", "fixed", "flow"])

    def keypress(self, size, key):
        if not size:
            size = self.pack(size)
        return super(PatchedLineBox, self).keypress(size, key)

    def pack(self, size, focus=False):
        if not size:
            # Fixed size; ask the decorated widget for its size and then add
            # 1 on each side. Also take into account the title (if any)
            if self.title_widget:
                min_width = len(self.title_widget.text) + 2
            else:
                min_width = 0
            if self.original_widget:
                w, h = self.original_widget.pack(size)
            else:
                w, h = 0, 0
            w = max(min_width, w)
            return (w + 2, h + 2)
        else:
            return super(PatchedLineBox, self).pack(size, focus)

    def render(self, size, focus=False):
        if not size:
            size = self.pack(size, focus)
        return super(PatchedLineBox, self).render(size, focus)
