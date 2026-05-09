"""État machine observable. Centralise la dernière position connue, l'état Grbl
et les overrides pour que tous les widgets puissent s'abonner via Qt signals.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from .grbl_link import GrblStatus

AXIS_NAMES_DEFAULT = ("X", "Y", "Z", "A", "B", "C")


class MachineState(QObject):
    state_changed = Signal(str)
    mpos_changed = Signal(tuple)
    wpos_changed = Signal(tuple)
    feed_changed = Signal(float)
    spindle_changed = Signal(float)
    overrides_changed = Signal(int, int, int)  # feed, rapid, spindle
    pins_changed = Signal(str)
    buffers_changed = Signal(int, int)
    raw_status_changed = Signal(GrblStatus)

    def __init__(self, axis_count: int = 4, axis_names: tuple[str, ...] = ("X", "Y", "Z", "A")):
        super().__init__()
        self.axis_count = axis_count
        self.axis_names = axis_names
        self._state = "Unknown"
        self._mpos: tuple[float, ...] = tuple([0.0] * axis_count)
        self._wpos: tuple[float, ...] = tuple([0.0] * axis_count)
        self._feed = 0.0
        self._spindle = 0.0
        self._overrides = (100, 100, 100)
        self._pins = ""

    @property
    def state(self) -> str:
        return self._state

    @property
    def mpos(self) -> tuple[float, ...]:
        return self._mpos

    @property
    def wpos(self) -> tuple[float, ...]:
        return self._wpos

    @property
    def overrides(self) -> tuple[int, int, int]:
        return self._overrides

    @Slot(GrblStatus)
    def update_from_status(self, st: GrblStatus) -> None:
        if st.state and st.state != self._state:
            self._state = st.state
            self.state_changed.emit(self._state)
        if st.mpos and st.mpos != self._mpos:
            # Pad/truncate to axis_count.
            self._mpos = tuple(
                st.mpos[i] if i < len(st.mpos) else 0.0 for i in range(self.axis_count)
            )
            self.mpos_changed.emit(self._mpos)
        if st.wpos and st.wpos != self._wpos:
            self._wpos = tuple(
                st.wpos[i] if i < len(st.wpos) else 0.0 for i in range(self.axis_count)
            )
            self.wpos_changed.emit(self._wpos)
        if st.feed != self._feed:
            self._feed = st.feed
            self.feed_changed.emit(self._feed)
        if st.spindle != self._spindle:
            self._spindle = st.spindle
            self.spindle_changed.emit(self._spindle)
        if st.overrides != self._overrides:
            self._overrides = st.overrides
            self.overrides_changed.emit(*self._overrides)
        if st.pins != self._pins:
            self._pins = st.pins
            self.pins_changed.emit(self._pins)
        self.buffers_changed.emit(st.planner_buf, st.rx_buf)
        self.raw_status_changed.emit(st)
