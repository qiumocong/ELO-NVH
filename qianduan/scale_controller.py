"""T5：共用的前端比例同步控制器；全部状态只在 Qt 主线程更新。

显示设置已经应用后才调用 change_scale。确认只代表比例同步，不代表文件已保存。
重连仅同步未来比例，不重放断线期间的设置来锁定旧轮次。
"""

import copy
import math
import uuid

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


class ScaleController(QObject):
    changed = pyqtSignal()
    round_changed = pyqtSignal(str)
    legacy_clear_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session_id = uuid.uuid4().hex
        self.display_scale = 1.0
        self.source = None
        self.remote = False
        self.connected = False
        self.connection_serial = 0
        self.supported = None
        self.snapshot = None
        self.status = "local"
        self.detail = ""
        self._backend_id = None
        self._revision = -1
        self._round_keys = {}
        self._registered_backend = None
        self._registered = False
        self._registering = False
        self._request_id = 0
        self._pending = {}
        self._decisions = {}
        self._deferred_info = set()
        self._links = []
        self._capability_timer = QTimer(self)
        self._capability_timer.setSingleShot(True)
        self._capability_timer.setInterval(1500)
        self._capability_timer.timeout.connect(self._legacy_backend)
        self._ack_timer = QTimer(self)
        self._ack_timer.setSingleShot(True)
        self._ack_timer.setInterval(6000)
        self._ack_timer.timeout.connect(self._ack_timeout)

    def attach(self, source):
        for signal, slot in self._links:
            signal.disconnect(slot)
        self._links.clear()
        self.source = source
        self.remote = bool(getattr(source, "supports_scale_protocol", False))
        self.connection_serial = -1
        self._capability_timer.stop()
        self._ack_timer.stop()
        self._pending.clear()
        self._registered = self._registering = False
        self._deferred_info.clear()
        if self.remote:
            for signal, slot in (
                (source.scale_connection_changed, self.on_connection),
                (source.scale_state_received, self.on_state),
                (source.scale_ack_received, self.on_ack),
                (source.scale_send_failed, self.on_send_failed),
            ):
                signal.connect(slot)
                self._links.append((signal, slot))
            self.on_connection(source.connected, source.connection_serial)
        else:
            self.connected = False
            self.supported = None
            self.status = "local"
            self.changed.emit()

    def on_connection(self, connected, serial):
        if serial < self.connection_serial:
            return
        self.connected = connected
        self.connection_serial = serial
        self._registered = self._registering = False
        self._pending.clear()
        self._decisions.clear()
        self._ack_timer.stop()
        self._capability_timer.stop()
        self.detail = ""
        if connected:
            self.supported = None
            self.status = "connecting"
            self._capability_timer.start()
        else:
            self.status = "disconnected"
        # 保留 round_keys/snapshot：同一轮重连不清屏，旧值只能作为上次确认展示。
        self.changed.emit()

    def clear_on_info(self, side):
        """只由已有数据的窗口调用；初次连接先等待独立比例快照辨别协议。"""
        if not self.remote or self.supported is False:
            return True
        if self.supported is None:
            self._deferred_info.add(side)
        return False

    def _legacy_backend(self):
        if not self.connected or self.supported is True:
            return
        self.supported = False
        self.status = "unsupported"
        for side in tuple(self._deferred_info):
            self.legacy_clear_requested.emit(side)
        self._deferred_info.clear()
        self.changed.emit()

    def _ack_timeout(self):
        if self._registering or self._pending:
            self.status = "failed"
            self.detail = "响应超时"
            self.changed.emit()

    def _current_packet(self, packet):
        return (self.connected and packet.get("_connection_serial") == self.connection_serial
                and type(packet.get("protocol_version")) is int
                and packet["protocol_version"] == 1)

    def _accept_snapshot(self, values, allow_new_backend=False):
        if not isinstance(values, dict):
            return False
        backend = values.get("backend_id")
        revision = values.get("revision")
        rounds = values.get("rounds")
        if not isinstance(backend, str) or not backend or type(revision) is not int or revision < 0:
            return False
        if not isinstance(rounds, dict) or any(
            not isinstance(rounds.get(side), dict) for side in ("left", "right")
        ):
            return False
        try:
            for scale in [values["current_scale"]] + [rounds[s]["save_scale"] for s in ("left", "right")]:
                if type(scale) not in (int, float) or not math.isfinite(scale) or not 0.01 <= scale <= 10:
                    return False
            for side in ("left", "right"):
                current = rounds[side]
                if current.get("phase") not in ("idle", "collecting", "finished", "aborted"):
                    return False
                if current.get("round_id") is not None and not isinstance(current["round_id"], str):
                    return False
                if type(current.get("locked")) is not bool:
                    return False
        except (KeyError, TypeError, ValueError):
            return False
        if backend != self._backend_id:
            if not allow_new_backend:
                return False
            self._backend_id, self._revision = backend, -1
            self._registered = self._registering = False
            self._registered_backend = None
            self._request_id = 0
            self._pending.clear()
            self._decisions.clear()
            self.status = "connecting"
        if revision < self._revision:
            return False
        self._revision = revision
        self.snapshot = copy.deepcopy(values)
        for side, current in rounds.items():
            if side not in ("left", "right"):
                continue
            key = (backend, current.get("round_id"))
            previous = self._round_keys.get(side)
            self._round_keys[side] = key
            if previous != key and (current.get("round_id") is not None or previous is not None):
                self._decisions.pop(side, None)
                self.round_changed.emit(side)
        return True

    def _send(self, packet):
        if not self.source.send_scale_message(packet, self.connection_serial):
            self.status, self.detail = "failed", "发送失败"
            return False
        self._ack_timer.start()
        return True

    def _register(self):
        self._registering = True
        self.status = "registering"
        resume = self._registered_backend == self._backend_id
        self._send({
            "type": "scale_session", "protocol_version": 1, "session_id": self.session_id,
            "current_scale": self.display_scale if resume else 1.0,
            "last_request_id": self._request_id if resume else 0,
        })

    def on_state(self, packet):
        if not self._current_packet(packet):
            return
        if not self._accept_snapshot(packet.get("snapshot"), allow_new_backend=True):
            return
        self.supported = True
        self._capability_timer.stop()
        self._deferred_info.clear()
        if not self._registered and not self._registering and self.status != "observer":
            self._register()
        elif self._registered and not self._pending and self.status != "failed":
            self.status = "synced"
        self.changed.emit()

    def _send_change(self, expected):
        self._request_id += 1
        self._pending[self._request_id] = self.display_scale
        self.status, self.detail = "pending", ""
        self._send({
            "type": "scale_change", "protocol_version": 1, "session_id": self.session_id,
            "request_id": self._request_id, "scale": self.display_scale,
            "expected_round_ids": expected,
        })

    def change_scale(self, scale):
        if scale == self.display_scale:
            return
        self.display_scale = float(scale)
        if self.remote and self.connected and self._registered and self.supported is True:
            self._send_change({side: current["round_id"] for side, current in self.snapshot["rounds"].items()})
        self.changed.emit()

    def on_ack(self, packet):
        if not self._current_packet(packet):
            return
        values = packet.get("snapshot")
        if not isinstance(values, dict) or values.get("backend_id") != self._backend_id:
            return
        # 旧请求可带回旧 revision。它可以结束对应等待，但不能回退界面快照。
        self._accept_snapshot(values)
        action = packet.get("action")
        if action == "scale_session":
            if not self._registering:
                return
            self._registering = False
            if packet.get("accepted") is True:
                self._registered = True
                self._registered_backend = self._backend_id
                self.status, self.detail = "synced", ""
                # 首次接入、后端重启或登记等待期间发生修改，只同步未来比例。
                if self.snapshot["current_scale"] != self.display_scale:
                    self._send_change({})
            else:
                self.status = "observer" if packet.get("reason") in (
                    "controller_busy", "retired_session",
                ) else "failed"
                self.detail = "其他界面控制" if self.status == "observer" else "登记未成功"
        elif action == "scale_change":
            if packet.get("session_id") != self.session_id:
                return
            request = packet.get("request_id")
            if type(request) is not int or request not in self._pending:
                return
            if packet.get("accepted") is True:
                self._pending = {key: value for key, value in self._pending.items() if key > request}
                if not self._pending:
                    for side, decision in packet.get("decisions", {}).items():
                        current = self.snapshot["rounds"].get(side, {})
                        if decision.get("round_id") == current.get("round_id"):
                            self._decisions[side] = decision.get("outcome")
                    self.status, self.detail = "synced", ""
            else:
                self._pending.pop(request, None)
                self.status, self.detail = "failed", "修改未确认"
        if not self._pending and not self._registering:
            self._ack_timer.stop()
        self.changed.emit()

    def on_send_failed(self, failure):
        if failure.get("connection_serial") != self.connection_serial or not self.connected:
            return
        message = failure.get("message", {})
        if (message.get("type") == "scale_session" and self._registering) or (
            message.get("type") == "scale_change" and message.get("request_id") in self._pending
        ):
            self.status, self.detail = "failed", "发送失败"
            self.changed.emit()

    def side_text(self, side):
        display = "显示比例：{:g}%".format(self.display_scale * 100)
        if not self.remote:
            return display + "\n仅显示模式"
        if self.supported is False:
            return display + "\n副本比例不可用（未检测到支持）"
        current = (self.snapshot or {}).get("rounds", {}).get(side, {})
        trusted = self.connected and self.supported is True and self.status in ("synced", "observer")
        if current.get("round_id") is None:
            saved = "本轮保存比例：—（待开始）"
        else:
            phase = {"finished": "已结束", "aborted": "已取消"}.get(current["phase"])
            phase = phase or ("已锁定" if current.get("locked") else "未锁定")
            saved = "本轮保存比例：{:g}% · {}".format(
                current["save_scale"] * 100, phase if trusted else "上次确认",
            )
        status = {
            "connecting": "等待后端确认", "registering": "登记中，尚未同步",
            "pending": "比例修改待确认", "disconnected": "连接中断，尚未同步",
            "failed": self.detail or "尚未同步", "observer": "仅查看：其他界面控制",
            "synced": "已同步",
        }.get(self.status, "尚未同步")
        if self.status == "synced" and self._decisions.get(side) in (
            "finished", "round_mismatch", "round_unknown", "session_mismatch", "aborted",
        ):
            status = "已同步，本轮未采用本次修改"
        return display + "\n" + saved + "\n" + status
