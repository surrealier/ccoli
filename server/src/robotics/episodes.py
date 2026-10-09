"""Opt-in local episode recording. Replay does not actuate unless explicitly enabled."""
from __future__ import annotations
import copy
import json
import re
from pathlib import Path
import secrets
import threading
import time
from typing import Callable
from .models import RoboticsError, identifier, number

KINDS = frozenset({'observation', 'action', 'intervention', 'failure', 'result'})
PRIVATE_KEYS = frozenset({'api_key', 'token', 'password', 'authorization', 'audio', 'transcript'})

def _check_private(value) -> None:
    if isinstance(value, dict):
        if any(str(key).lower() in PRIVATE_KEYS for key in value):
            raise RoboticsError('private_field_not_recordable')
        for item in value.values(): _check_private(item)
    elif isinstance(value, list):
        for item in value: _check_private(item)

def validate_episode(episode: dict) -> None:
    if not isinstance(episode, dict) or type(episode.get('v')) is not int or episode.get('v') != 1:
        raise RoboticsError('invalid_episode')
    identifier(episode.get('episode_id'))
    events = episode.get('events')
    if not isinstance(events, list) or len(events) > 2000:
        raise RoboticsError('invalid_episode')
    previous = 0.0
    for event in events:
        if not isinstance(event, dict) or event.get('kind') not in KINDS or not isinstance(event.get('data'), dict):
            raise RoboticsError('invalid_episode')
        previous = number(event.get('timestamp'), previous, 1e12)
    _check_private(episode)

class EpisodeRecorder:
    def __init__(self, directory: str | Path, *, enabled: bool = False):
        self.directory = Path(directory)
        self.enabled = enabled is True
        self._episode: dict | None = None
        self._bytes = 0
        self._pending_abort: dict | None = None
        self._lock = threading.RLock()

    def set_enabled(self, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise RoboticsError('invalid_recording_setting')
        with self._lock:
            if enabled and self._pending_abort is not None:
                raise RoboticsError('recording_recovery_required')
            if not enabled and self._episode:
                raise RoboticsError('finish_recording_first')
            self.enabled = enabled

    def start(self, task: str, metadata: dict) -> str:
        with self._lock:
            if not self.enabled:
                raise RoboticsError('recording_opt_in_required')
            if self._pending_abort is not None:
                raise RoboticsError('recording_recovery_required')
            if self._episode:
                raise RoboticsError('recording_busy')
            identifier(task)
            if not isinstance(metadata, dict):
                raise RoboticsError('invalid_episode_metadata')
            _check_private(metadata)
            if len(json.dumps(metadata, allow_nan=False)) > 8192:
                raise RoboticsError('invalid_episode_metadata')
            episode_id = secrets.token_hex(12)
            self._episode = {'v': 1, 'episode_id': episode_id, 'task': task,
                             'metadata': copy.deepcopy(metadata), 'events': []}
            self._bytes = 0
            return episode_id

    def record(self, kind: str, data: dict, *, timestamp: float | None = None) -> None:
        with self._lock:
            if not self.enabled or not self._episode:
                raise RoboticsError('recording_not_started')
            if kind not in KINDS or not isinstance(data, dict):
                raise RoboticsError('invalid_episode_event')
            _check_private(data)
            previous = self._episode['events'][-1]['timestamp'] if self._episode['events'] else 0
            stamp = number(time.monotonic() if timestamp is None else timestamp, previous, 1e12)
            size = len(json.dumps(data, allow_nan=False, separators=(',', ':')).encode())
            if size > 12_000_000 or self._bytes + size > 128_000_000 or len(self._episode['events']) >= 1999:
                raise RoboticsError('episode_limit')
            self._episode['events'].append({'kind': kind, 'timestamp': stamp, 'data': copy.deepcopy(data)})
            self._bytes += size

    def _persist(self, episode: dict) -> Path:
        validate_episode(episode)
        encoded = json.dumps(episode, allow_nan=False, separators=(',', ':'))
        # The data admission limit is 128 MB; 1 MB reserves v1 event headers,
        # metadata and the bounded abort result. The written artifact is bounded.
        if len(encoded.encode()) > 129_000_000:
            raise RoboticsError('episode_limit')
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / (episode['episode_id'] + '.json')
        temporary = target.with_suffix('.'+secrets.token_hex(6)+'.tmp')
        temporary.write_text(encoded, encoding='utf-8')
        temporary.replace(target)
        return target

    def finish(self, result: dict, *, timestamp: float | None = None) -> Path:
        with self._lock:
            self.record('result', result, timestamp=timestamp)
            target = self._persist(self._episode)
            self._episode = None
            return target

    def abort(self, reason: str) -> dict:
        """Disable and preserve the active partial episode, even if disk IO fails.

        At most one unsaved aborted episode is retained. New recording cannot
        start until recover_aborted() saves it, so later failures never evict it.
        This method exposes flags and IDs, never recorded frames or exceptions.
        """
        code = reason if isinstance(reason, str) and re.fullmatch(r'[a-z_]{1,64}', reason) else 'recording_aborted'
        with self._lock:
            self.enabled = False
            episode = self._episode
            self._episode = None
            if episode is None:
                return {'enabled': False, 'episode_id': self._pending_abort['episode_id'] if self._pending_abort else None,
                        'saved_locally': False, 'preserved_in_memory': self._pending_abort is not None,
                        'recovery_required': self._pending_abort is not None}
            previous = episode['events'][-1]['timestamp'] if episode['events'] else 0
            stamp = max(previous, time.monotonic())
            if len(episode['events']) < 2000:
                episode['events'].append({'kind':'result','timestamp':stamp,
                    'data':{'status':'aborted','reason_code':code}})
            else:
                episode['abort'] = {'reason_code':code,'timestamp':stamp}
            self._pending_abort = episode
            return self.recover_aborted()

    def recover_aborted(self) -> dict:
        """Best-effort local persistence; failure keeps every event in memory."""
        with self._lock:
            episode = self._pending_abort
            if episode is None:
                return {'enabled': self.enabled, 'episode_id': None, 'saved_locally': False,
                        'preserved_in_memory': False, 'recovery_required': False}
            episode_id = episode['episode_id']
            try:
                self._persist(episode)
            except Exception:
                return {'enabled': False, 'episode_id': episode_id, 'saved_locally': False,
                        'preserved_in_memory': True, 'recovery_required': True}
            self._pending_abort = None
            return {'enabled': False, 'episode_id': episode_id, 'saved_locally': True,
                    'preserved_in_memory': False, 'recovery_required': False}
    def load(self, episode_id: str) -> dict:
        identifier(episode_id)
        with self._lock:
            if self._pending_abort and self._pending_abort['episode_id'] == episode_id:
                return copy.deepcopy(self._pending_abort)
        target = self.directory / (episode_id + '.json')
        if target.is_symlink() or target.resolve().parent != self.directory.resolve():
            raise RoboticsError('invalid_episode_path')
        if not target.is_file() or target.stat().st_size > 129_000_000:
            raise RoboticsError('episode_not_found')
        try:
            value = json.loads(target.read_text(encoding='utf-8'))
            validate_episode(value)
            if value['episode_id'] != episode_id:
                raise RoboticsError('invalid_episode')
            return value
        except (OSError, ValueError):
            raise RoboticsError('invalid_episode') from None

    def snapshot(self) -> dict:
        return {'enabled': self.enabled,
                'episode_id': self._episode['episode_id'] if self._episode else None,
                'events': len(self._episode['events']) if self._episode else 0,
                'pending_recovery_id': self._pending_abort['episode_id'] if self._pending_abort else None}

def replay_episode(episode: dict, sink: Callable[[dict], object], *, allow_actions: bool = False) -> dict:
    if type(allow_actions) is not bool:
        raise RoboticsError('invalid_replay_authorization')
    validate_episode(episode)
    skipped = emitted = 0
    for event in episode['events']:
        if event['kind'] == 'action' and not allow_actions:
            skipped += 1
        elif event['kind'] in {'observation', 'intervention', 'action'}:
            sink(copy.deepcopy(event))
            emitted += 1
    return {'episode_id': episode['episode_id'], 'events_emitted': emitted,
            'actions_skipped': skipped, 'actuated': False}