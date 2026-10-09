"""Locally timestamped, bounded observations with explicit data provenance."""
from __future__ import annotations
import copy
import json
import threading
import time
from typing import Any, Callable
from .models import RoboticsError, identifier, integer, number

class ObservationStore:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic, max_age_s: float = 2):
        self.clock = clock
        self.max_age_s = number(max_age_s, .01, 60)
        self._items: dict[tuple[str, str], dict] = {}
        self._times: dict[tuple[str, str], list[float]] = {}
        self._sources: dict[tuple[str, str], dict] = {}
        self._lock = threading.RLock()

    def register_source(self, kind: str, source_id: str, *, driver_id: str,
                        provenance: str = 'measured') -> None:
        """Only a local device adapter may bind a measured source; no HTTP route."""
        if kind not in {'rgb', 'joint', 'sensor', 'objects'} or provenance not in {'measured', 'simulated'}:
            raise RoboticsError('invalid_observation_source')
        identifier(source_id)
        identifier(driver_id)
        key = (kind, source_id)
        with self._lock:
            old = self._sources.get(key)
            if old and old['driver_id'] == driver_id and old['provenance'] == provenance:
                return
            if old:
                raise RoboticsError('unregister_source_first')
            if len(self._sources) >= 32:
                raise RoboticsError('too_many_observation_sources')
            self._sources[key] = {'driver_id': driver_id, 'provenance': provenance,
                                  'registered_at': self.clock()}
            self._items.pop(key, None)
            self._times.pop(key, None)

    def unregister_source(self, kind: str, source_id: str) -> None:
        with self._lock:
            self._sources.pop((kind, source_id), None)
            self._items.pop((kind, source_id), None)
            self._times.pop((kind, source_id), None)
    def update(self, kind: str, source_id: str, data: dict, *, sequence: int,
               provenance: str, captured_at: float | None = None, calibration: dict | None = None) -> dict:
        if kind not in {'rgb', 'joint', 'sensor', 'objects'}:
            raise RoboticsError('invalid_observation_kind')
        identifier(source_id)
        sequence = integer(sequence, 1, 0xffffffff)
        if provenance not in {'measured', 'commanded', 'simulated'} or not isinstance(data, dict):
            raise RoboticsError('invalid_observation')
        now = self.clock()
        captured = now if captured_at is None else number(captured_at, 0, now + .2)
        if captured > now + .2:
            raise RoboticsError('future_observation')
        if kind == 'rgb':
            identifier(data.get('frame_id'))
            width = integer(data.get('width'), 1, 1280)
            height = integer(data.get('height'), 1, 720)
            rgb = data.get('rgb')
            if not isinstance(rgb, list) or len(rgb) != width * height * 3:
                raise RoboticsError('invalid_rgb_dimension')
            if any(type(pixel) is not int or not 0 <= pixel <= 255 for pixel in rgb):
                raise RoboticsError('invalid_rgb_pixel')
        elif kind == 'joint':
            angles = data.get('angles')
            if not isinstance(angles, list) or not 1 <= len(angles) <= 8:
                raise RoboticsError('invalid_joint_dimension')
            for angle in angles:
                number(angle, -360, 360)
        elif kind == 'objects':
            objects = data.get('objects')
            if not isinstance(objects, list) or len(objects) > 64:
                raise RoboticsError('invalid_objects')
            for item in objects:
                if not isinstance(item, dict):
                    raise RoboticsError('invalid_objects')
                identifier(item.get('id'))
                identifier(item.get('location'))
                number(item.get('confidence'), 0, 1)
        try:
            if len(json.dumps(data, allow_nan=False, separators=(',', ':')).encode()) > 12_000_000:
                raise RoboticsError('observation_too_large')
            if calibration is not None and not isinstance(calibration, dict):
                raise RoboticsError('invalid_calibration_snapshot')
            if calibration is not None and len(json.dumps(calibration, allow_nan=False)) > 8192:
                raise RoboticsError('invalid_calibration_snapshot')
        except (TypeError, ValueError):
            raise RoboticsError('invalid_observation') from None
        key = (kind, source_id)
        with self._lock:
            binding = self._sources.get(key)
            if binding and (provenance != binding['provenance'] or captured < binding['registered_at']):
                raise RoboticsError('observation_source_mismatch')
            previous = self._items.get(key)
            if previous and (sequence <= previous['sequence'] or captured < previous['captured_at']):
                raise RoboticsError('out_of_order_observation')
            if key not in self._items and len(self._items) >= 32:
                raise RoboticsError('too_many_observation_sources')
            value = {'kind': kind, 'source_id': source_id, 'data': copy.deepcopy(data),
                'sequence': sequence, 'provenance': provenance, 'captured_at': captured,
                'received_at': now, 'calibration': copy.deepcopy(calibration),
                'driver_id': binding['driver_id'] if binding else None}
            self._items[key] = value
            samples = self._times.setdefault(key, [])
            samples.append(now)
            self._times[key] = samples[-128:]
            return copy.deepcopy(value)

    def get(self, kind: str, source_id: str, *, max_age_s: float | None = None,
            require_measured: bool = False) -> dict:
        limit = self.max_age_s if max_age_s is None else number(max_age_s, .01, 60)
        with self._lock:
            value = self._items.get((kind, source_id))
            if not value:
                raise RoboticsError('observation_missing')
            if self.clock() - value['captured_at'] > limit:
                raise RoboticsError('observation_stale')
            if require_measured and value['provenance'] != 'measured':
                raise RoboticsError('measurement_required')
            result = copy.deepcopy(value)
            result['age_s'] = self.clock() - value['captured_at']
            return result

    def snapshot(self, *, include_frames: bool = False) -> list[dict]:
        with self._lock:
            results = []
            for key, value in self._items.items():
                result = {k: copy.deepcopy(v) for k, v in value.items() if k != 'data'}
                result['age_s'] = self.clock() - value['captured_at']
                result['stale'] = result['age_s'] > self.max_age_s
                samples = self._times[key]
                result['observation_hz'] = (len(samples)-1)/(samples[-1]-samples[0]) if len(samples)>1 and samples[-1]>samples[0] else None
                if value['kind'] == 'rgb' and not include_frames:
                    result['data'] = {k: v for k, v in value['data'].items() if k != 'rgb'}
                else:
                    result['data'] = copy.deepcopy(value['data'])
                results.append(result)
            return results

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._times.clear()