"""T3：纯 Python 的每轮保存比例状态，不连接设备、网络、界面或文件系统。

STEP200 调 begin_round，STEP900 调 finish_round；STEP300/400 不结束本轮。
所有修改在同一把锁内完成，返回的快照只含不可变值，可安全留待人工标注后保存。
连接 ID 由将来的 WebSocket 适配层为每条连接分配，不能直接信任消息自报的 ID。
本模块只管理运行期状态，不改变原始数据、保存路径或同名覆盖规则。
"""

import threading
import uuid
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Tuple


@dataclass(frozen=True)
class RoundSnapshot:
    side: str
    round_id: Optional[str] = None
    phase: str = "idle"
    barcode: str = ""
    spec: str = ""
    initial_scale: float = 1.0
    save_scale: float = 1.0
    locked: bool = False  # 仅指首次实际修改已锁定；结束冻结由 phase 表示。
    session_id: Optional[str] = None  # STEP200 时实际在线的控制会话。
    change_request_id: Optional[int] = None
    abort_reason: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class StateSnapshot:
    backend_id: str
    revision: int
    session_id: Optional[str]
    connection_id: Optional[str]
    connected: bool
    current_scale: float
    effective_scale: float  # 断线/无前端时新轮次安全回退为 1。
    last_request_id: int
    rounds: Tuple[RoundSnapshot, ...]

    def round_for(self, side):
        for item in self.rounds:
            if item.side == side:
                return item
        raise ValueError("未知工位：{}".format(side))

    def to_dict(self):
        values = asdict(self)
        values["rounds"] = {item.side: item.to_dict() for item in self.rounds}
        return values


@dataclass(frozen=True)
class SessionAcknowledgement:
    accepted: bool
    reason: str
    snapshot: StateSnapshot

    def to_dict(self):
        return {"accepted": self.accepted, "reason": self.reason,
                "snapshot": self.snapshot.to_dict()}


@dataclass(frozen=True)
class RoundDecision:
    side: str
    round_id: Optional[str]
    outcome: str
    save_scale: float
    locked: bool


@dataclass(frozen=True)
class ScaleAcknowledgement:
    accepted: bool  # 接收当前比例不等于每侧活动轮次都采用了它；需检查 decisions。
    reason: str
    session_id: str
    request_id: int
    scale: Optional[float]
    changed: bool
    decisions: Tuple[RoundDecision, ...]
    snapshot: StateSnapshot

    def to_dict(self):
        values = asdict(self)
        values["decisions"] = {item.side: asdict(item) for item in self.decisions}
        values["snapshot"] = self.snapshot.to_dict()
        return values


class RoundStateError(ValueError):
    """生命周期调用不匹配；适配层应记录错误，不能据此覆盖另一轮状态。"""


def _identifier(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("{} 必须为 1～256 字符的非空字符串".format(name))
    return value


def _normalize_scale(scale):
    # 与 T2 相同的整数百分比口径，但不导入写入模块，避免引入 NumPy/Pandas。
    try:
        if isinstance(scale, bool):
            raise ValueError("布尔值不是比例")
        value = Decimal(str(scale))
        if not value.is_finite() or not Decimal("0.01") <= value <= Decimal("10"):
            raise ValueError("比例超出范围")
        return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (ValueError, InvalidOperation):
        raise ValueError("scale 必须是 0.01～10 的有限数值") from None


class ScaleSessionManager:
    """单后端进程的一位控制会话、全局当前比例和独立工位轮次。

    request_id 为会话内单调递增的正整数，重连继续递增。近期请求缓存精确确认；
    已淘汰的旧请求仍由高水位拒绝，不能重新执行。重放确认包含原 revision，
    将来的前端不得用旧确认回退较新的状态。
    """

    def __init__(self, sides=("left", "right"), request_cache_size=256):
        sides = tuple(sides)
        if not sides or len(sides) != len(set(sides)) or any(
            side not in ("left", "right") for side in sides
        ):
            raise ValueError("sides 必须是 left/right 的非空、无重复序列")
        if type(request_cache_size) is not int or request_cache_size < 1:
            raise ValueError("request_cache_size 必须为正整数")
        self._lock = threading.Lock()
        self._backend_id = uuid.uuid4().hex
        self._revision = 0
        self._round_counter = 0
        self._rounds = {side: RoundSnapshot(side) for side in sides}
        self._session_id = None
        self._connection_id = None
        self._connected = False
        self._current_scale = 1.0
        self._last_request_id = 0
        self._requests = OrderedDict()
        self._request_cache_size = request_cache_size
        # 仅在真正更换前端进程时增长，阻止已退役会话重新登记抢回控制权。
        self._retired_sessions = set()

    def _snapshot(self):
        # 调用者须持锁；rounds 内部也只存不可变快照，不向外暴露可变容器。
        return StateSnapshot(
            self._backend_id, self._revision, self._session_id, self._connection_id,
            self._connected, self._current_scale,
            self._current_scale if self._connected else 1.0,
            self._last_request_id, tuple(self._rounds.values()),
        )

    def get_snapshot(self):
        with self._lock:
            return self._snapshot()

    def register_session(
        self, session_id, connection_id, current_scale=1.0, *, last_request_id=0,
    ):
        """登记/恢复控制连接。新会话必须为 1；同会话恢复只同步未来轮次。

        在线控制者存在时其他连接不能抢占；同连接重复登记不重置比例。
        connection_id 由服务端适配层生成且每次重连不同；不是客户端身份认证。
        恢复时应传入前端已发出的最大 last_request_id，关闭断线前未确认请求的
        重放窗口；后续真实设置使用更大编号。恢复同步本身不锁定活动轮次。
        """
        with self._lock:
            def result(accepted, reason):
                return SessionAcknowledgement(accepted, reason, self._snapshot())

            try:
                _identifier(session_id, "session_id")
                _identifier(connection_id, "connection_id")
                scale = _normalize_scale(current_scale)
                if type(last_request_id) is not int or last_request_id < 0:
                    raise ValueError("last_request_id 必须为非负整数")
            except ValueError:
                return result(False, "invalid_session")
            if session_id in self._retired_sessions:
                return result(False, "retired_session")
            if self._connected:
                if (session_id, connection_id) == (self._session_id, self._connection_id):
                    return result(True, "already_connected")
                return result(False, "controller_busy")
            is_resume = session_id == self._session_id
            if not is_resume and scale != 1.0:
                return result(False, "new_session_requires_scale_one")
            if not is_resume and last_request_id != 0:
                return result(False, "new_session_requires_request_zero")
            if not is_resume:
                if self._session_id is not None:
                    self._retired_sessions.add(self._session_id)
                self._last_request_id = 0
                self._requests.clear()
            self._last_request_id = max(self._last_request_id, last_request_id)
            self._session_id = session_id
            self._connection_id = connection_id
            self._connected = True
            self._current_scale = scale
            self._revision += 1
            return result(True, "resumed" if is_resume else "registered")

    def disconnect_session(self, session_id, connection_id):
        """旧连接的迟到 finally 不能把刚重连的新连接标成断线。"""
        with self._lock:
            if (session_id, connection_id) != (self._session_id, self._connection_id):
                return SessionAcknowledgement(False, "stale_connection", self._snapshot())
            if not self._connected:
                return SessionAcknowledgement(True, "already_disconnected", self._snapshot())
            self._connected = False
            self._revision += 1
            return SessionAcknowledgement(True, "disconnected", self._snapshot())

    def _round(self, side):
        if side not in self._rounds:
            raise RoundStateError("未知工位：{}".format(side))
        return self._rounds[side]

    def begin_round(self, side, barcode, spec):
        with self._lock:
            previous = self._round(side)
            if previous.phase == "collecting":
                raise RoundStateError("工位 {} 的上一轮尚未结束或取消".format(side))
            if not isinstance(barcode, str) or not isinstance(spec, str):
                raise ValueError("barcode/spec 必须为字符串；允许空条码留待保存时处理")
            self._round_counter += 1
            scale = self._current_scale if self._connected else 1.0
            current = RoundSnapshot(
                side=side,
                round_id="{}:{}:{}".format(self._backend_id, side, self._round_counter),
                phase="collecting", barcode=barcode, spec=spec,
                initial_scale=scale, save_scale=scale,
                session_id=self._session_id if self._connected else None,
            )
            self._rounds[side] = current
            self._revision += 1
            return current

    def finish_round(self, side, round_id):
        with self._lock:
            current = self._round(side)
            if current.round_id is None or current.round_id != round_id:
                raise RoundStateError("finish_round 的轮次已过期或不存在")
            if current.phase == "finished":
                return current
            if current.phase != "collecting":
                raise RoundStateError("不能结束已取消的轮次")
            current = replace(current, phase="finished")
            self._rounds[side] = current
            self._revision += 1
            return current

    def abort_round(self, side, round_id, reason):
        with self._lock:
            current = self._round(side)
            if current.round_id is None or current.round_id != round_id:
                raise RoundStateError("abort_round 的轮次已过期或不存在")
            if current.phase in ("finished", "aborted"):
                return current  # 保存流程持有的已冻结结果不能被随后重置改写。
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("取消原因不能为空")
            current = replace(current, phase="aborted", abort_reason=reason)
            self._rounds[side] = current
            self._revision += 1
            return current

    def apply_scale_change(
        self, session_id, request_id, scale, expected_round_ids, *, connection_id,
    ):
        """整次设置事件只调用一次，在同一临界区检查所有工位。

        有效请求可更新当前/未来比例；只有匹配、同会话、未锁定的活动轮次采用。
        缺少某侧轮次 ID 时该侧不采用，不能把迟到消息静默套到另一轮。
        连接恢复用 register_session，同步值不会被视为采集中首次修改。
        """
        with self._lock:
            def rejected(reason, value=None):
                return ScaleAcknowledgement(
                    False, reason, session_id, request_id, value, False, (), self._snapshot(),
                )

            if not self._connected:
                return rejected("disconnected")
            if session_id != self._session_id:
                return rejected("not_controller")
            if connection_id != self._connection_id:
                return rejected("stale_connection")
            if type(request_id) is not int or request_id < 1:
                return rejected("invalid_request_id")
            try:
                value = _normalize_scale(scale)
                if not isinstance(expected_round_ids, Mapping):
                    raise ValueError("expected_round_ids 必须为字典")
                expected = dict(expected_round_ids)
                if any(side not in self._rounds for side in expected):
                    raise ValueError("未知工位")
                for rid in expected.values():
                    if rid is not None:
                        _identifier(rid, "round_id")
            except ValueError:
                return rejected("invalid_change")
            fingerprint = (value, tuple(
                (side, side in expected, expected.get(side)) for side in self._rounds
            ))
            cached = self._requests.get(request_id)
            if cached is not None:
                if cached[0] != fingerprint:
                    return rejected("request_conflict", value)
                return cached[1]  # 原确认与原 revision；绝不再执行或锁定新轮次。
            if request_id <= self._last_request_id:
                return rejected("stale_request", value)

            changed = value != self._current_scale
            self._current_scale = value
            decisions = []
            for side, current in self._rounds.items():
                if side not in expected:
                    outcome = "round_unknown"
                elif expected[side] != current.round_id:
                    outcome = "round_mismatch"
                elif current.phase != "collecting":
                    outcome = current.phase  # idle / finished / aborted
                elif current.session_id != session_id:
                    outcome = "session_mismatch"
                elif current.locked:
                    outcome = "locked"
                elif not changed:
                    outcome = "unchanged"
                else:
                    current = replace(current, save_scale=value, locked=True,
                                      change_request_id=request_id)
                    self._rounds[side] = current
                    outcome = "applied"
                decisions.append(RoundDecision(
                    side, current.round_id, outcome, current.save_scale, current.locked,
                ))
            self._last_request_id = request_id
            self._revision += 1
            acknowledgement = ScaleAcknowledgement(
                True, "accepted", session_id, request_id, value, changed,
                tuple(decisions), self._snapshot(),
            )
            self._requests[request_id] = (fingerprint, acknowledgement)
            if len(self._requests) > self._request_cache_size:
                self._requests.popitem(last=False)
            return acknowledgement
