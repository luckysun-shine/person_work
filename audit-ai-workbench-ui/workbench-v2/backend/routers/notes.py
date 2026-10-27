"""API routes: notes."""
import json
import re

from fastapi import APIRouter, HTTPException, Query, Response, status

from .. import common as C
from ..ai_client import AINotConfigured, AIRequestError, ai_ready, enhance_note_assist
from ..db import new_id, transaction, utc_now
from ..schemas import BatchIds, NoteCreate, NoteAssistRequest, NoteUpdate

router = APIRouter(tags=["notes"])

@router.get("/api/notes")
def list_notes(
    q: str | None = None,
    note_type: str | None = Query(default=None, alias="type"),
    favorite: bool | None = None,
    archived: bool | None = False,
) -> list[dict]:
    conditions: list[str] = []
    parameters: list = []
    if q:
        conditions.append("(title LIKE ? OR content LIKE ? OR tags_json LIKE ?)")
        keyword = f"%{q}%"
        parameters.extend([keyword, keyword, keyword])
    if note_type:
        conditions.append("type = ?")
        parameters.append(note_type)
    if favorite is True:
        conditions.append("is_favorite = 1")
    if archived is False:
        conditions.append("COALESCE(is_archived, 0) = 0")
    elif archived is True:
        conditions.append("is_archived = 1")
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    return C.fetch_all(
        f"SELECT * FROM work_notes{where} ORDER BY is_favorite DESC, updated_at DESC, created_at DESC",
        tuple(parameters),
    )


NOTE_CLASSIFIERS = {
    "口径说明": ("口径", "统计", "范围", "截止", "定义", "排除", "字段", "计算"),
    "问题排查": ("问题", "异常", "报错", "失败", "排查", "原因", "修复", "缺失", "重复", "数据质量"),
    "模型维护": ("模型", "规则", "阈值", "命中", "复核", "版本", "调度", "存储过程"),
    "项目复盘": ("项目", "复盘", "进展", "交付", "总结", "里程碑", "验收"),
}
NOTE_TAGS = C.NOTE_TAGS


def text_features(value: str) -> set[str]:
    features: set[str] = set()
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_.-]*|\d+|[\u4e00-\u9fff]+", value.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            if len(token) == 1:
                features.add(token)
            else:
                features.update(token[index:index + 2] for index in range(len(token) - 1))
        else:
            features.add(token)
    return features


def similarity_score(left: str, right: str) -> float:
    left_features, right_features = text_features(left), text_features(right)
    if not left_features or not right_features:
        return 0
    return len(left_features & right_features) / len(left_features | right_features)


@router.post("/api/notes/assist")
def assist_note(payload: NoteAssistRequest) -> dict:
    combined = f"{payload.title}\n{payload.content}".strip()
    if not combined:
        raise HTTPException(status_code=400, detail="请先填写标题或内容")
    class_scores = {
        note_type: sum(2 if keyword in payload.title else 1 for keyword in keywords if keyword in combined)
        for note_type, keywords in NOTE_CLASSIFIERS.items()
    }
    suggested_type = max(class_scores, key=class_scores.get)
    best_score = class_scores[suggested_type]
    if best_score == 0:
        suggested_type = "随手记录"
    tags = [tag for tag in NOTE_TAGS if tag.lower() in combined.lower()]
    if suggested_type != "随手记录" and suggested_type not in tags:
        tags.append(suggested_type)
    relation_match = re.search(r"\b(?:DR|M|Q|P|T)-[A-Za-z0-9]+\b", combined, re.IGNORECASE)
    similar: list[dict] = []
    for note in C.fetch_all("SELECT * FROM work_notes ORDER BY updated_at DESC"):
        if payload.exclude_id and note["id"] == payload.exclude_id:
            continue
        score = similarity_score(combined, f"{note['title']}\n{note['content']}\n{' '.join(note.get('tags', []))}")
        if score >= 0.08:
            similar.append({
                "id": note["id"],
                "title": note["title"],
                "type": note["type"],
                "score": round(score * 100),
                "shared_tags": [tag for tag in note.get("tags", []) if tag.lower() in combined.lower()],
            })
    similar.sort(key=lambda item: item["score"], reverse=True)
    confidence = min(96, 45 + best_score * 12) if best_score else 35
    result = {
        "suggested_type": suggested_type,
        "suggested_tags": tags[:8],
        "suggested_relation": relation_match.group(0).upper() if relation_match else None,
        "confidence": confidence,
        "similar_notes": similar[:5],
        "reason": "根据标题与正文中的业务关键词、编号和历史记录相似度生成，应用前可人工调整。",
        "ai_generated": False,
    }
    ai_settings = C.load_ai_settings()
    if ai_ready(ai_settings):
        try:
            result = enhance_note_assist(ai_settings, payload.title, payload.content, result)
        except (AINotConfigured, AIRequestError) as exc:
            result["ai_error"] = str(exc)
    return result


@router.post("/api/notes", status_code=status.HTTP_201_CREATED)
def create_note(payload: NoteCreate) -> dict:
    note_id = new_id("N")
    now = utc_now()
    with transaction() as connection:
        connection.execute(
            """INSERT INTO work_notes
            (id,type,title,content,tags_json,related_entity_type,related_entity_id,is_favorite,is_archived,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                note_id,
                payload.type,
                payload.title,
                payload.content,
                json.dumps(payload.tags, ensure_ascii=False),
                payload.related_entity_type,
                payload.related_entity_id,
                1 if payload.is_favorite else 0,
                1 if payload.is_archived else 0,
                now,
                now,
            ),
        )
    return C.fetch_one("SELECT * FROM work_notes WHERE id = ?", (note_id,))


@router.post("/api/notes/batch-delete")
def batch_delete_notes(payload: BatchIds) -> dict:
    return C.batch_delete_records("work_notes", payload.ids)


@router.get("/api/notes/{note_id}")
def get_note(note_id: str) -> dict:
    note = C.fetch_one("SELECT * FROM work_notes WHERE id = ?", (note_id,))
    if not note:
        raise HTTPException(status_code=404, detail="工作记录不存在")
    note["revisions"] = C.fetch_all(
        "SELECT * FROM work_note_revisions WHERE note_id = ? ORDER BY created_at DESC LIMIT 30",
        (note_id,),
    )
    return note


@router.get("/api/notes/{note_id}/revisions")
def list_note_revisions(note_id: str) -> list[dict]:
    if not C.fetch_one("SELECT id FROM work_notes WHERE id = ?", (note_id,)):
        raise HTTPException(status_code=404, detail="工作记录不存在")
    return C.fetch_all(
        "SELECT * FROM work_note_revisions WHERE note_id = ? ORDER BY created_at DESC LIMIT 50",
        (note_id,),
    )


@router.patch("/api/notes/{note_id}")
def update_note(note_id: str, payload: NoteUpdate) -> dict:
    current = C.fetch_one("SELECT * FROM work_notes WHERE id = ?", (note_id,))
    if not current:
        raise HTTPException(status_code=404, detail="工作记录不存在")
    changes = payload.model_dump(exclude_unset=True)
    if "tags" in changes:
        changes["tags_json"] = json.dumps(changes.pop("tags"), ensure_ascii=False)
    if "is_favorite" in changes:
        changes["is_favorite"] = 1 if changes["is_favorite"] else 0
    if "is_archived" in changes:
        changes["is_archived"] = 1 if changes["is_archived"] else 0
    content_changed = any(key in changes for key in ("title", "content", "tags_json", "type"))
    with transaction() as connection:
        if content_changed:
            connection.execute(
                """INSERT INTO work_note_revisions
                (id,note_id,type,title,content,tags_json,created_at) VALUES (?,?,?,?,?,?,?)""",
                (
                    new_id("NR"),
                    note_id,
                    current.get("type") or "",
                    current.get("title") or "",
                    current.get("content") or "",
                    json.dumps(current.get("tags") or [], ensure_ascii=False),
                    utc_now(),
                ),
            )
        if changes:
            changes["updated_at"] = utc_now()
            assignments = ", ".join(f"{field} = ?" for field in changes)
            connection.execute(
                f"UPDATE work_notes SET {assignments} WHERE id = ?",
                (*changes.values(), note_id),
            )
    return get_note(note_id)


@router.delete("/api/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: str) -> Response:
    return C.delete_record("work_notes", note_id, "工作记录不存在")

