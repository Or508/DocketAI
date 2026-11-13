"""Find where a printed label on a flat form expects its value to be written.

Pure geometry over words, ruled lines, and white cells. A label resolves to a target
only when the page draws one: a cell around the label, the cell under a header cell,
a row of digit boxes, or a rule beside the label. With no drawn target, or with ink
already in it, the label resolves to nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Box = tuple[float, float, float, float]
TargetKind = Literal["cell_below", "cell_under", "cell_beside", "comb", "underline"]

_STRIP = " \t:：.*_-–—()[]"
_EDGE = 1.5
_MIN_WIDTH = 24.0
_MIN_HEIGHT = 9.0
_MAX_CELL_HEIGHT = 90.0
_MAX_GAP = 36.0
_LINE_HEIGHT = 15.0
_COMB_MIN_BOXES = 4
_COMB_BOX_HEIGHT = 13.0


@dataclass(frozen=True)
class Word:
    box: Box
    text: str
    line: tuple[int, int]


@dataclass(frozen=True)
class Segment:
    """An axis-aligned rule. For a horizontal rule a..b are x and at is y; vertical is the reverse."""

    horizontal: bool
    at: float
    a: float
    b: float


@dataclass(frozen=True)
class LabelHit:
    label: str
    box: Box
    words: tuple[int, ...]


@dataclass(frozen=True)
class Target:
    rect: Box
    kind: TargetKind
    boxes: tuple[Box, ...] = ()


def fold(text: str) -> str:
    for mark in ("׳", "’", "‘", "`"):
        text = text.replace(mark, "'")
    for mark in ("״", "”", "“"):
        text = text.replace(mark, '"')
    return " ".join(text.casefold().strip(_STRIP).split())


def find_labels(words: list[Word], labels: list[str], *, whole: bool = True) -> list[LabelHit]:
    """Match each label as a run of neighbouring words on one line, longest label first.

    Hebrew may be extracted in logical or in visual order, so a word matches a
    token either as read or reversed, and a run is tried right-to-left and left-to-right.
    With whole=True the label must be the complete printed phrase.
    """
    wanted = sorted({fold(item) for item in labels if fold(item)}, key=lambda item: -len(item.split()))
    originals = {fold(item): item for item in labels}
    lines: dict[tuple[int, int], list[int]] = {}
    for index, word in enumerate(words):
        lines.setdefault(word.line, []).append(index)
    hits: list[LabelHit] = []
    for indexes in lines.values():
        taken: set[int] = set()
        for order in (sorted(indexes, key=lambda i: -words[i].box[0]), sorted(indexes, key=lambda i: words[i].box[0])):
            for label in wanted:
                tokens = label.split()
                for start in range(len(order) - len(tokens) + 1):
                    run = order[start : start + len(tokens)]
                    if taken.intersection(run):
                        continue
                    if not all(_token_matches(words[i].text, token) for i, token in zip(run, tokens)):
                        continue
                    if not _neighbours(words, run):
                        continue
                    if whole and _touching(words, run, [i for i in order if i not in run]):
                        continue
                    taken.update(run)
                    hits.append(LabelHit(originals[label], _union([words[i].box for i in run]), tuple(run)))
    return hits


def section_of(box: Box, sections: list[LabelHit]) -> str | None:
    """The nearest section title printed above this box on the same page."""
    above = [hit for hit in sections if hit.box[1] <= box[1] + _EDGE]
    if not above:
        return None
    return max(above, key=lambda hit: hit.box[1]).label


def resolve_target(
    hit: LabelHit,
    words: list[Word],
    segments: list[Segment],
    panels: list[Box] | None = None,
    marks: list[Box] | None = None,
) -> Target | None:
    """The drawn place for this label's value, or None. Never a guess from the label alone.

    marks are symbols on the page: they count as ink in a target, never as part of a label.
    """
    printed = [word.box for index, word in enumerate(words) if index not in hit.words]
    others = printed + list(marks or [])
    cell = _cell(hit.box, segments) or _panel(hit.box, panels or [])
    if cell is not None:
        x0, y0, x1, y1 = cell
        lx0, _ly0, _lx1, ly1 = hit.box
        boxes = _comb(cell, hit.box, segments)
        if boxes:
            if any(_inked(box, others) for box in boxes):
                return None
            return Target(_union(list(boxes)), "comb", boxes)
        # The cell's shape picks the place. Ink there means the cell is taken, not that the
        # value belongs somewhere else in it.
        below = (x0, ly1 + 1, x1, y1)
        if _usable(below):
            return None if _inked(below, others) else Target(below, "cell_below")
        under = _panel_under(cell, panels or [])
        if under is not None:
            return None if _inked(under, others) else Target(under, "cell_under")
        beside = (x0, y0, lx0 - 2, y1)
        if _usable(beside) and not _inked(beside, others):
            return Target(beside, "cell_beside")
        return None
    rule = _rule_beside(hit.box, segments, printed)
    if rule is not None:
        rect = (rule.a, rule.at - _LINE_HEIGHT, rule.b, rule.at - 0.5)
        if _usable(rect) and not _inked(rect, others):
            return Target(rect, "underline")
    return None


def _token_matches(text: str, token: str) -> bool:
    folded = fold(text)
    return folded == token or fold(text[::-1]) == token


def _neighbours(words: list[Word], run: list[int]) -> bool:
    boxes = sorted((words[i].box for i in run), key=lambda box: box[0])
    for left, right in zip(boxes, boxes[1:]):
        height = max(left[3] - left[1], right[3] - right[1])
        if right[0] - left[2] > height * 1.2:
            return False
    return True


def _touching(words: list[Word], run: list[int], rest: list[int]) -> bool:
    """A label is the whole printed phrase. A word set right against it makes it a different phrase."""
    box = _union([words[i].box for i in run])
    reach = (box[3] - box[1]) * 1.2
    for index in rest:
        other = words[index].box
        if -_EDGE <= other[0] - box[2] <= reach or -_EDGE <= box[0] - other[2] <= reach:
            return True
    return False


def _union(boxes: list[Box]) -> Box:
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _cell(label: Box, segments: list[Segment]) -> Box | None:
    """The four nearest rules that enclose the label's centre, when all four exist."""
    cx = (label[0] + label[2]) / 2
    cy = (label[1] + label[3]) / 2
    top = [s.at for s in segments if s.horizontal and s.a - _EDGE <= cx <= s.b + _EDGE and s.at <= label[1] + _EDGE]
    bottom = [s.at for s in segments if s.horizontal and s.a - _EDGE <= cx <= s.b + _EDGE and s.at >= label[3] - _EDGE]
    left = [s.at for s in segments if not s.horizontal and s.a - _EDGE <= cy <= s.b + _EDGE and s.at <= label[0] + _EDGE]
    right = [s.at for s in segments if not s.horizontal and s.a - _EDGE <= cy <= s.b + _EDGE and s.at >= label[2] - _EDGE]
    if not (top and bottom and left and right):
        return None
    cell = (max(left), max(top), min(right), min(bottom))
    if cell[3] - cell[1] > _MAX_CELL_HEIGHT:
        return None
    return cell


def _panel(label: Box, panels: list[Box]) -> Box | None:
    """The smallest white cell that holds the label."""
    holding = [
        panel
        for panel in panels
        if panel[0] - _EDGE <= label[0]
        and panel[1] - _EDGE <= label[1]
        and panel[2] + _EDGE >= label[2]
        and panel[3] + _EDGE >= label[3]
        and panel[3] - panel[1] <= _MAX_CELL_HEIGHT
    ]
    if not holding:
        return None
    return min(holding, key=lambda panel: (panel[2] - panel[0]) * (panel[3] - panel[1]))


def _panel_under(cell: Box, panels: list[Box]) -> Box | None:
    """A header cell's value cell: the white cell right under it with the same left and right edges."""
    for panel in panels:
        if abs(panel[0] - cell[0]) > 3 or abs(panel[2] - cell[2]) > 3:
            continue
        if not (-_EDGE <= panel[1] - cell[3] <= 6):
            continue
        if _usable(panel) and panel[3] - panel[1] <= _MAX_CELL_HEIGHT:
            return panel
    return None


def _comb(cell: Box, label: Box, segments: list[Segment]) -> tuple[Box, ...]:
    """Digit boxes in the cell: evenly spaced ticks that stand on one baseline."""
    ticks: dict[float, list[float]] = {}
    for segment in segments:
        if segment.horizontal or segment.b - segment.a < 3:
            continue
        if not (cell[0] - _EDGE <= segment.at <= cell[2] + _EDGE):
            continue
        if segment.a < label[1] - _EDGE or segment.b > cell[3] + _EDGE:
            continue
        ticks.setdefault(round(segment.b), []).append(segment.at)
    if not ticks:
        return ()
    bottom, xs = max(ticks.items(), key=lambda item: len(set(round(x, 1) for x in item[1])))
    edges = sorted(set(round(x, 1) for x in xs))
    widths = [right - left for left, right in zip(edges, edges[1:])]
    if len(widths) < _COMB_MIN_BOXES:
        return ()
    median = sorted(widths)[len(widths) // 2]
    if median < 7 or median > 32 or any(abs(width - median) > median * 0.25 for width in widths):
        return ()
    top = bottom - _COMB_BOX_HEIGHT
    if _overlaps_x(label, (edges[0], edges[-1])):
        top = max(top, label[3] + 0.5)
    if bottom - top < 7:
        return ()
    return tuple((left + 0.6, top, right - 0.6, bottom - 0.6) for left, right in zip(edges, edges[1:]))


def _overlaps_x(box: Box, span: tuple[float, float]) -> bool:
    return min(box[2], span[1]) - max(box[0], span[0]) > 0


def _rule_beside(label: Box, segments: list[Segment], printed: list[Box]) -> Segment | None:
    """The closest writing rule that starts to the left of the label, near its baseline.

    A symbol may stand between the label and its rule. A word may not: then the rule is that word's.
    """
    height = label[3] - label[1]
    found: list[tuple[float, Segment]] = []
    for segment in segments:
        if not segment.horizontal or segment.b - segment.a < _MIN_WIDTH:
            continue
        if not (label[3] - height * 0.5 <= segment.at <= label[3] + height * 0.6):
            continue
        gap = label[0] - segment.b
        if not (-_EDGE <= gap <= _MAX_GAP):
            continue
        if gap > 1 and _inked((segment.b, label[1], label[0], label[3]), printed):
            continue
        found.append((gap, segment))
    if not found:
        return None
    return min(found, key=lambda item: item[0])[1]


def _usable(rect: Box) -> bool:
    return rect[2] - rect[0] >= _MIN_WIDTH and rect[3] - rect[1] >= _MIN_HEIGHT


def _inked(rect: Box, others: list[Box]) -> bool:
    for box in others:
        if min(rect[2], box[2]) - max(rect[0], box[0]) > 0.5 and min(rect[3], box[3]) - max(rect[1], box[1]) > 0.5:
            return True
    return False
