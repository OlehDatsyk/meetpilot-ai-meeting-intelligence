"""Keyword retrieval over meeting records, always restricted to workspaces the user belongs to.

Candidates are found with case-insensitive substring matching and ranked by a TF-IDF style score computed
over the candidate set. There is no semantic (embedding) search.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .models import Meeting, Speaker, TranscriptSegment

STOPWORDS = set("""a about above after again against all am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having he her
here hers herself him himself his how i if in into is it its itself just me more most my myself no nor not now of off
on once only or other our ours ourselves out over own same she should so some such than that the their theirs them
themselves then there these they this those through to too under until up very was we were what when where which
while who whom why will with would you your yours yourself yourselves meeting meetings discussed discuss said say
tell summarise summarize summary anything everything something anyone someone did does please give show list""".split())


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def query_terms(text: str, max_terms: int = 8) -> list[str]:
    out: list[str] = []
    for w in re.findall(r"[\w][\w'-]*", text.lower()):
        w = w.strip("'-")
        if (len(w) >= 3 or w.isdigit()) and w not in STOPWORDS and w not in out:
            out.append(w)
    return out[:max_terms]


@dataclass
class SegmentHit:
    segment: TranscriptSegment
    meeting: Meeting
    score: float


def search_segments(db: Session, workspace_ids: list[str], terms: list[str], *, meeting_id: str | None = None,
                    project_id: str | None = None, limit: int = 12, candidate_limit: int = 600) -> list[SegmentHit]:
    if not terms or not workspace_ids:
        return []
    conds = [TranscriptSegment.text.ilike(f"%{escape_like(t)}%", escape="\\") for t in terms]
    speaker_ids = select(Speaker.id).where(or_(*[Speaker.display_name.ilike(f"%{escape_like(t)}%", escape="\\")
                                                 for t in terms]))
    stmt = (select(TranscriptSegment, Meeting).join(Meeting, TranscriptSegment.meeting_id == Meeting.id)
            .options(selectinload(TranscriptSegment.speaker))
            .where(TranscriptSegment.workspace_id.in_(workspace_ids),
                   or_(*conds, TranscriptSegment.speaker_id.in_(speaker_ids))))
    if meeting_id:
        stmt = stmt.where(TranscriptSegment.meeting_id == meeting_id)
    if project_id:
        stmt = stmt.where(Meeting.project_id == project_id)
    rows = db.execute(stmt.order_by(Meeting.meeting_date.desc()).limit(candidate_limit)).all()
    if not rows:
        return []
    texts = [(seg.text + " " + (seg.speaker.display_name or "" if seg.speaker else "")).lower() for seg, _ in rows]
    n = len(rows)
    idf = {t: math.log(1 + n / (1 + sum(1 for x in texts if t in x))) for t in terms}
    hits = []
    for (seg, meeting), text in zip(rows, texts, strict=True):
        matched = [t for t in terms if t in text]
        score = sum(text.count(t) * idf[t] for t in matched) * (1 + 0.5 * (len(matched) - 1))
        score /= math.sqrt(max(20, len(text)) / 20)  # mild length normalisation
        hits.append(SegmentHit(seg, meeting, score))
    hits.sort(key=lambda h: (-h.score, h.meeting.meeting_date, h.segment.position))
    return hits[:limit]
