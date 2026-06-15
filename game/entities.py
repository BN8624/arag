# 전투 엔티티/상태 데이터 계약 — 모든 모듈이 공유하는 기본 자료구조
"""PAMPHLET §1 데이터 계약의 정본 구현. dataclass로 Entity/Status 정의 + 생성 헬퍼."""

from dataclasses import dataclass, field


@dataclass
class Status:
    type: str          # "burn" | "freeze" | "poison" | "shock"
    turns: int
    stacks: int = 1


@dataclass
class Entity:
    id: str
    name: str
    team: str          # "hero" | "enemy"
    max_hp: int
    hp: int
    atk: int
    defense: int
    spd: int
    gauge: float = 0.0
    statuses: list = field(default_factory=list)
    last_skill: str | None = None
    rotation_index: int = 0          # AI: 스킬 로테이션 위치
    skills: list = field(default_factory=list)  # AI: 사용할 스킬 순서

    @property
    def alive(self) -> bool:
        return self.hp > 0


def make_entity(id, name, team, max_hp, atk, defense, spd, skills=None) -> Entity:
    return Entity(id=id, name=name, team=team, max_hp=max_hp, hp=max_hp,
                  atk=atk, defense=defense, spd=spd,
                  skills=list(skills) if skills else [])


def get_status(e: Entity, stype: str) -> Status | None:
    for s in e.statuses:
        if s.type == stype:
            return s
    return None


def has_status(e: Entity, stype: str) -> bool:
    return get_status(e, stype) is not None
