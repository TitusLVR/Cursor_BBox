"""Async subprocess management for collision decomposition tools.

Launches external processes (V-HACD, CoACD) without blocking Blender,
streams their stdout/stderr to the System Console in real-time, and
imports results when the process finishes.
"""

import bpy
import threading
import queue
import os
import re
import sys
import shutil
import time


# ------------------------------------------------------------------ #
#  Visual progress-bar helpers                                        #
# ------------------------------------------------------------------ #

_BAR_WIDTH = 20
_BAR_FILL = '\u2588'   # █
_BAR_EMPTY = '\u2591'   # ░
_BAR_BLOCK = 4          # sliding-block width for indeterminate mode
_PCT_RE = re.compile(r'(\d+(?:\.\d+)?)\s*%')


def _bar_determinate(percent):
    """Return a filled bar like [████████░░░░░░░░░░░░] 45%"""
    p = max(0.0, min(100.0, percent))
    filled = int(_BAR_WIDTH * p / 100)
    return f"[{_BAR_FILL * filled}{_BAR_EMPTY * (_BAR_WIDTH - filled)}] {p:5.1f}%"


def _bar_indeterminate(tick):
    """Return an animated bouncing-block bar for unknown progress."""
    travel = _BAR_WIDTH - _BAR_BLOCK
    cycle = travel * 2
    pos = tick % cycle
    if pos >= travel:
        pos = cycle - pos
    bar = list(_BAR_EMPTY * _BAR_WIDTH)
    for i in range(_BAR_BLOCK):
        bar[pos + i] = _BAR_FILL
    return f"[{''.join(bar)}]"


def _clear_progress_line():
    """Clear the current progress-bar line in the System Console."""
    sys.stdout.write('\r' + ' ' * 120 + '\r')
    sys.stdout.flush()


# ------------------------------------------------------------------ #
#  Job dataclass                                                      #
# ------------------------------------------------------------------ #

class _DecompJob:
    """Tracks a single running decomposition subprocess."""
    __slots__ = (
        'process', 'temp_dir', 'result_path', 'obj_name',
        'tool_name', 'prefix', '_queue', '_reader',
        'return_code', 'all_output',
        'start_time', 'line_count', '_tick', '_last_status', '_percent',
    )

    def __init__(self, process, temp_dir, result_path,
                 obj_name, tool_name, prefix):
        self.process = process
        self.temp_dir = temp_dir
        self.result_path = result_path
        self.obj_name = obj_name
        self.tool_name = tool_name
        self.prefix = prefix
        self._queue = queue.Queue()
        self._reader = None
        self.return_code = None
        self.all_output = []
        self.start_time = time.time()
        self.line_count = 0
        self._tick = 0
        self._last_status = ''
        self._percent = -1.0

    def start_reader(self):
        """Spawn a daemon thread that reads stdout line-by-line."""
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        try:
            for raw in iter(self.process.stdout.readline, ''):
                line = raw.rstrip('\r\n')
                if line:
                    self._queue.put(line)
        except (ValueError, OSError):
            pass

    def drain_and_print(self):
        """Drain queued lines and render a visual progress bar."""
        while True:
            try:
                line = self._queue.get_nowait()
                self.all_output.append(line)
                self.line_count += 1
                stripped = line.strip()
                if stripped:
                    self._last_status = stripped
                    m = _PCT_RE.search(stripped)
                    if m:
                        self._percent = float(m.group(1))
            except queue.Empty:
                break

        self._tick += 1
        elapsed = time.time() - self.start_time

        if self._percent >= 0:
            vis = _bar_determinate(self._percent)
        else:
            vis = _bar_indeterminate(self._tick)

        status = self._last_status
        if len(status) > 40:
            status = status[:37] + '...'

        out = f"[{self.tool_name}] {self.obj_name}: {vis} {elapsed:.1f}s"
        if status:
            out += f"  {status}"

        sys.stdout.write(f"\r{out:<120}")
        sys.stdout.flush()

    def drain_remaining(self):
        """Drain all remaining output without updating the progress bar."""
        while True:
            try:
                line = self._queue.get_nowait()
                self.all_output.append(line)
                self.line_count += 1
            except queue.Empty:
                break

    def poll(self):
        if self.return_code is not None:
            return True
        rc = self.process.poll()
        if rc is not None:
            self.return_code = rc
            return True
        return False

    def cleanup(self):
        try:
            if self.temp_dir and os.path.isdir(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def kill(self):
        try:
            self.process.kill()
        except Exception:
            pass
        self.cleanup()


# ------------------------------------------------------------------ #
#  Module-level state                                                 #
# ------------------------------------------------------------------ #

_jobs: list = []
_timer_registered: bool = False
_tick_count: int = 0


# ------------------------------------------------------------------ #
#  Public helpers                                                     #
# ------------------------------------------------------------------ #

def is_busy():
    """True while any decomposition subprocess is still running."""
    return bool(_jobs)


def get_status_lines():
    """Return short status strings suitable for the N-panel."""
    return [
        f"{j.tool_name}: processing '{j.obj_name}'\u2026"
        for j in _jobs
    ]


def submit(process, temp_dir, result_path, obj_name, tool_name, prefix):
    """Register a new async decomposition job and start the monitor timer."""
    global _timer_registered

    job = _DecompJob(process, temp_dir, result_path,
                     obj_name, tool_name, prefix)
    job.start_reader()
    _jobs.append(job)

    print(f"[{tool_name}] Started processing '{obj_name}'")

    if not _timer_registered:
        _timer_registered = True
        bpy.app.timers.register(_tick, first_interval=0.15)

    _redraw_viewports()


def cancel_all():
    """Kill every running job and stop the timer."""
    global _timer_registered
    for job in _jobs:
        job.kill()
    _jobs.clear()
    _timer_registered = False
    _clear_progress_line()
    _redraw_viewports()
    print("[Cursor BBox] All decomposition jobs cancelled")


# ------------------------------------------------------------------ #
#  Timer callback                                                     #
# ------------------------------------------------------------------ #

def _tick():
    global _timer_registered, _tick_count
    _tick_count += 1

    if not _jobs:
        _timer_registered = False
        return None

    finished = []
    for job in _jobs:
        job.drain_and_print()
        if job.poll():
            finished.append(job)

    total_hulls = 0
    for job in finished:
        _jobs.remove(job)
        total_hulls += _finish_job(job)

    if finished:
        _redraw_viewports()

    if not _jobs:
        _timer_registered = False
        _clear_progress_line()
        if total_hulls > 0:
            print(f"[Cursor BBox] Decomposition complete — "
                  f"{total_hulls} hull(s) created")
        return None

    if _tick_count % 10 == 0:
        _redraw_viewports()

    return 0.1


# ------------------------------------------------------------------ #
#  Internal helpers                                                   #
# ------------------------------------------------------------------ #

def _finish_job(job):
    """Import the result of a finished job. Returns hull count."""
    from .collision_io import import_obj_as_new_objects, organize_hull_objects
    from .utils import ensure_cbb_collection

    job.drain_remaining()
    _clear_progress_line()

    elapsed = time.time() - job.start_time

    if job.return_code != 0:
        tail = "\n".join(job.all_output[-8:]) if job.all_output else "(no output)"
        print(f"[{job.tool_name}] FAILED on '{job.obj_name}' "
              f"(exit {job.return_code}, {elapsed:.1f}s):\n{tail}")
        job.cleanup()
        return 0

    if not os.path.isfile(job.result_path):
        print(f"[{job.tool_name}] No output file for '{job.obj_name}' ({elapsed:.1f}s)")
        job.cleanup()
        return 0

    try:
        ctx = bpy.context
        saved_selected = list(ctx.selected_objects)
        saved_active = ctx.view_layer.objects.active

        coll = ensure_cbb_collection(ctx)
        new_objs = import_obj_as_new_objects(job.result_path)
        count = organize_hull_objects(ctx, new_objs, job.obj_name,
                                      job.prefix, coll)

        print(f"[{job.tool_name}] Created {count} hull(s) for '{job.obj_name}' ({elapsed:.1f}s)")

        # Restore the user's selection state
        bpy.ops.object.select_all(action='DESELECT')
        for obj in saved_selected:
            try:
                obj.select_set(True)
            except Exception:
                pass
        if saved_active:
            try:
                ctx.view_layer.objects.active = saved_active
            except Exception:
                pass

        job.cleanup()
        return count

    except Exception as exc:
        print(f"[{job.tool_name}] Import error for '{job.obj_name}': {exc}")
        job.cleanup()
        return 0


def _redraw_viewports():
    """Tag all 3D viewports for redraw so the N-panel refreshes."""
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass
