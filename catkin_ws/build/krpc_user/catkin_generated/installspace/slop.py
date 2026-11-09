#!/usr/bin/python3
# -*- coding:utf-8 -*-
"""Kibo-RPC 7th - Int-Ball2 mission program (competition version).

How the score works (Rulebook 2.3, Manual 4.3):
    Score = (sum of checkpoint points by level Lv1-Lv3 + goal points) x time multiplier
    A checkpoint counts only if position, camera centering and roll about the line of
    sight are ALL inside a band and held for 1 s. The multiplier grows with the time
    remaining when the mission is reported finished. The final ranking uses the average
    of 10 runs, so consistency matters more than one lucky run.

Strategy implemented here:
    1. Fetch + parse the checkpoints in a background thread BEFORE the mission clock
       starts (mission time is measured between mission_start and mission_finished).
    2. Order the checkpoints with an exact Held-Karp search (start -> all -> goal) using a
       travel-time model (translation vs. rotation), re-planned after every checkpoint.
    3. Fly with /ctl/command to the exact position + attitude given by the API, then
       verify with /sensor_fusion/navigation that all three judged conditions are well
       inside the Lv3 bands and the vehicle is still, hold >= HOLD_S, and only then send
       checkpoint_passed (the sample API server always answers "accepted", so the
       program must do its own verification).
    4. Learn the real leg speed online; if the remaining time cannot cover the plan, drop
       the most expensive detours so the goal is always reached and reported in time.

Everything tunable is in the CONFIG block below. Python 3.6 / ROS Melodic compatible.
"""
import json
import math
import threading
import traceback

import actionlib
import rospy
from geometry_msgs.msg import PoseStamped
from krpc_ib2_msgs.srv import MissionStart, MissionFinished, CheckPoints
from krpc_ib2_msgs.msg import CheckpointPassedAction, CheckpointPassedGoal
from ib2_msgs.msg import CtlCommandAction, CtlCommandGoal, CtlCommandResult, CtlStatusType, Navigation
from platform_msgs.msg import UserLogic
from platform_msgs.srv import StopProcessingUserNode, StopProcessingUserNodeResponse

VERSION = 'competition-1.0'

# ----------------------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------------------
TIME_LIMIT_S = 300.0          # Rulebook 2.2.2 #6
SAFETY_MARGIN_S = 5.0         # always report finished at least this long before the limit

DOCK_POS = (0.2, 0.0, 0.0)    # Rulebook Table 2.2.2-3 (used only if navigation is silent)
DOCK_QUAT = (0.0, 0.0, 0.0, 1.0)

# Travel-time prior. Only the RELATIVE weighting matters for ordering; the absolute scale
# is learned online from the first completed leg. Calibrate from the "VISIT" log lines.
PRIOR_SPEED_MPS = 0.15
PRIOR_TURN_RPS = 0.30
PRIOR_LEG_OVERHEAD_S = 3.0
PRIOR_SETTLE_S = 1.8          # hold + claim time per checkpoint before it is measured
CLAIM_S = 0.3

# Settling / verification
TOL_FRACTION = 0.7            # aim inside 70 % of the Lv3 band (nav noise margin)
HOLD_S = 1.3                  # judge needs 1 s; keep a margin
STILL_LIN_MPS = 0.06          # "stable" thresholds from /sensor_fusion/navigation twist
STILL_ANG_RPS = 0.15
SETTLE_BUDGET_S = 8.0         # max time spent refining one checkpoint
NOISY_TWIST_ACCEPT_S = 2.5    # pose inside tolerance this long => accept even if twist is noisy
MAX_FIXES = 3                 # max corrective moves per checkpoint
FIX_TIMEOUT_S = 10.0
NAV_STALE_S = 1.0
NAV_SANITY_POS_M = 0.5        # nav this far from a target we just reached => nav frame is untrusted
MIN_LEGS_BEFORE_DROP = 2      # never drop checkpoints on a single noisy timing sample

MIN_LEG_TIMEOUT_S = 25.0
LEG_TIMEOUT_FACTOR = 4.0
CLAIM_TIMEOUT_S = 5.0

DEFAULT_POS_BANDS = [(0.1, 3), (0.2, 2), (0.3, 1)]       # (radius [m], level)
# ----------------------------------------------------------------------------------------


# ------------------------------- small math helpers -------------------------------------
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(v):
    return math.sqrt(_dot(v, v))


def _unit(v):
    n = _norm(v)
    return (v[0] / n, v[1] / n, v[2] / n) if n > 1e-9 else (1.0, 0.0, 0.0)


def _dist(a, b):
    return _norm(_sub(a, b))


def _q_normalize(q):
    n = math.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2 + q[3] ** 2)
    if n < 1e-9:
        return (0.0, 0.0, 0.0, 1.0)
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


def _q_conj(q):
    return (-q[0], -q[1], -q[2], q[3])


def _q_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def _q_rotate(q, v):
    r = _q_mul(_q_mul(q, (v[0], v[1], v[2], 0.0)), _q_conj(q))
    return (r[0], r[1], r[2])


def _q_angle(a, b):
    """Smallest rotation angle [rad] between two unit quaternions."""
    d = min(1.0, abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]))
    return 2.0 * math.acos(d)


def _wrap_pi(a):
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def _look_at_quat(pos, target):
    """Attitude whose +X (camera axis) points from pos to target, Z kept 'up'."""
    x = _unit(_sub(target, pos))
    up = (0.0, 0.0, 1.0) if abs(x[2]) < 0.99 else (0.0, 1.0, 0.0)
    y = _unit(_cross(up, x))
    z = _cross(x, y)
    m00, m10, m20 = x
    m01, m11, m21 = y
    m02, m12, m22 = z
    tr = m00 + m11 + m22
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        q = ((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s)
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        q = (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        q = ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        q = ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)
    return _q_normalize(q)


# ------------------------------- checkpoint parsing -------------------------------------
def _parse_bands(raw, key, default):
    out = []
    if isinstance(raw, list):
        for band in raw:
            try:
                out.append((float(band[key]), int(band['level'])))
            except Exception:
                pass
    out.sort()
    return out if out else default


def _band_level(bands, err):
    best = 0
    for limit, level in bands:
        if err <= limit:
            best = max(best, level)
    return best


def _top_limit(bands):
    """Limit of the band that carries the highest level (the Lv3 band)."""
    return min(bands, key=lambda b: (-b[1], b[0]))[0]


def _parse_checkpoint(raw):
    cid = None
    for key in ('checkpoint_id', 'checkpointid', 'id'):
        if key in raw:
            cid = int(raw[key])
            break
    pos = raw.get('position')
    if cid is None or not (isinstance(pos, list) and len(pos) >= 3):
        return None
    pos = tuple(float(v) for v in pos[:3])

    marker = None
    marker_pose = raw.get('marker_pose')
    if isinstance(marker_pose, dict):
        mpos = marker_pose.get('position')
        if isinstance(mpos, list) and len(mpos) >= 3:
            marker = tuple(float(v) for v in mpos[:3])

    quat, cen_bands, roll_bands = None, None, None
    att = raw.get('attitude')
    if isinstance(att, dict):
        q = att.get('quaternion')
        if isinstance(q, list) and len(q) >= 4:
            quat = _q_normalize(tuple(float(v) for v in q[:4]))
        cen_bands = _parse_bands(att.get('centering_bands'), 'angle', None)
        roll_bands = _parse_bands(att.get('roll_bands'), 'angle', None)
    if quat is None:
        quat = _look_at_quat(pos, marker) if marker else DOCK_QUAT

    return {
        'id': cid,
        'pos': pos,
        'quat': quat,
        'marker': marker,
        'pos_bands': _parse_bands(raw.get('score_bands', raw.get('bands')), 'radius', DEFAULT_POS_BANDS),
        'cen_bands': cen_bands,      # None -> condition not judged
        'roll_bands': roll_bands,    # None -> condition not judged
    }


class UserTemplate:

    def __init__(self):
        rospy.init_node('krpc_user')

        # Action client
        self._command = actionlib.SimpleActionClient('/ctl/command', CtlCommandAction)
        self._checkpoint_client = actionlib.SimpleActionClient('/event/checkpoint_passed', CheckpointPassedAction)

        # Service client
        self._mission_start = rospy.ServiceProxy('/event/mission_start', MissionStart)
        self._mission_finished = rospy.ServiceProxy('/event/mission_finished', MissionFinished)
        self._checkpoints = rospy.ServiceProxy('/mission/get_checkpoints', CheckPoints)

        # Subscriber
        self._subscriber_start = rospy.Subscriber('/ib2_user/start', UserLogic, self._callback_start)  # DO NOT REMOVE THIS LINE
        # Self pose / velocity, used to verify every checkpoint before it is claimed.
        self._subscriber_nav = rospy.Subscriber('/sensor_fusion/navigation', Navigation, self._callback_nav,
                                                queue_size=1)

        # Service server
        self._stop_processing_server = rospy.Service('/ib2_user/stop', StopProcessingUserNode, self._stop_processing)  # DO NOT REMOVE THIS LINE

        self._started = False
        self._abort = threading.Event()
        self._cmd_active = False
        self._claim_active = False

        self._nav = None              # (rx_time, pos, quat, lin_speed, ang_speed)
        self._t0 = None               # mission clock (sim time) set at mission_start
        self._time_scale = None       # learned: actual leg time / modelled leg time
        self._legs_measured = 0
        self._nav_ok = True           # False once navigation proved inconsistent with /ctl/command
        self._settle_s = PRIOR_SETTLE_S
        self._prep = None
        self._prep_done = threading.Event()
        self._results = []

        prep_thread = threading.Thread(target=self._prepare)
        prep_thread.daemon = True
        prep_thread.start()

        rospy.set_param('/ib2_user/ready', True)  # DO NOT REMOVE THIS LINE
        rospy.loginfo('user program %s ready', VERSION)

    # ====================================================================================
    # Preparation (runs before the mission clock starts)
    # ====================================================================================
    def _prepare(self):
        try:
            for _ in range(60):
                if rospy.is_shutdown() or self._abort.is_set():
                    break
                self._prep = self._fetch_checkpoints()
                if self._prep is not None:
                    break
                rospy.sleep(1.0)
        except Exception as exc:
            rospy.logerr('prepare failed: %s', exc)
        finally:
            self._prep_done.set()

    def _fetch_checkpoints(self):
        try:
            rospy.wait_for_service('/mission/get_checkpoints', timeout=5.0)
            res = self._checkpoints()
        except Exception as exc:
            rospy.logwarn('get_checkpoints call failed: %s', exc)
            return None
        if not res.success:
            rospy.logwarn('get_checkpoints returned failure: %s', res.message)
            return None
        try:
            payload = json.loads(res.message)
            raw = payload.get('checkpoints', payload.get('Checkpoints', []))
            parsed = [_parse_checkpoint(r) for r in raw if isinstance(r, dict)]
            cps = [c for c in parsed if c is not None]
            if not cps:
                rospy.logwarn('no usable checkpoints in payload')
                return None
            goal_id = payload.get('goalpoint_id')
            goal_id = int(goal_id) if goal_id is not None else None
            rospy.loginfo('checkpoints loaded: count=%d goal_id=%s ids=%s',
                          len(cps), goal_id, [c['id'] for c in cps])
            return {'checkpoints': cps, 'goal_id': goal_id}
        except Exception as exc:
            rospy.logwarn('failed to parse checkpoints: %s', exc)
            return None

    # ====================================================================================
    # Notifications
    # ====================================================================================
    def _call_event_service(self, name, proxy, attempts):
        for _ in range(attempts):
            if rospy.is_shutdown() or self._abort.is_set():
                break
            try:
                rospy.wait_for_service(name, timeout=5.0)
                res = proxy()
                rospy.loginfo('%s result: success=%s message=%s', name, res.success, res.message)
                if res.success:
                    return True
            except Exception as exc:
                rospy.logwarn('%s failed: %s', name, exc)
        return False

    def _notify_mission_start(self):
        return self._call_event_service('/event/mission_start', self._mission_start, 3)

    def _notify_mission_finished(self):
        return self._call_event_service('/event/mission_finished', self._mission_finished, 2)

    def _notify_checkpoint_passed(self, checkpoint_id):
        rospy.loginfo('notify checkpoint_id=%d passed', checkpoint_id)
        if not self._checkpoint_client.wait_for_server(rospy.Duration(5.0)):
            rospy.logwarn('checkpoint_passed server unavailable')
            return False
        goal = CheckpointPassedGoal()
        goal.checkpoint_id = int(checkpoint_id)
        self._claim_active = True
        try:
            self._checkpoint_client.send_goal(goal)
            t_end = rospy.get_time() + CLAIM_TIMEOUT_S
            while not rospy.is_shutdown() and not self._abort.is_set():
                if self._checkpoint_client.wait_for_result(rospy.Duration(0.1)):
                    result = self._checkpoint_client.get_result()
                    rospy.loginfo('checkpoint_passed result: %s', result)
                    return bool(result.success)
                if rospy.get_time() > t_end:
                    break
            self._checkpoint_client.cancel_goal()
            rospy.logwarn('checkpoint_passed cancelled (timeout/abort)')
            return False
        finally:
            self._claim_active = False

    # ====================================================================================
    # Navigation
    # ====================================================================================
    def _callback_nav(self, data):
        try:
            p = data.pose.pose.position
            o = data.pose.pose.orientation
            lin = data.twist.linear
            ang = data.twist.angular
            self._nav = (rospy.get_time(), (p.x, p.y, p.z), _q_normalize((o.x, o.y, o.z, o.w)),
                         math.sqrt(lin.x ** 2 + lin.y ** 2 + lin.z ** 2),
                         math.sqrt(ang.x ** 2 + ang.y ** 2 + ang.z ** 2))
        except Exception as exc:
            rospy.logwarn_throttle(5.0, 'bad navigation message: %s', exc)

    def _fresh_nav(self):
        nav = self._nav
        if nav is not None and rospy.get_time() - nav[0] <= NAV_STALE_S:
            return nav
        return None

    # ====================================================================================
    # Time model + planning
    # ====================================================================================
    def _time_left(self):
        if self._t0 is None:
            return TIME_LIMIT_S
        return TIME_LIMIT_S - SAFETY_MARGIN_S - (rospy.get_time() - self._t0)

    def _stopping(self):
        return rospy.is_shutdown() or self._abort.is_set()

    def _scale(self):
        return self._time_scale if self._time_scale is not None else 1.0

    @staticmethod
    def _base_time(a, b):
        """Modelled travel time between two (pos, quat) poses; translation and rotation overlap."""
        move = _dist(a[0], b[0]) / PRIOR_SPEED_MPS
        turn = _q_angle(a[1], b[1]) / PRIOR_TURN_RPS
        return max(move, turn) + PRIOR_LEG_OVERHEAD_S

    def _learn_leg(self, base, actual):
        if base <= 0.0 or actual <= 0.0:
            return
        self._legs_measured += 1
        ratio = min(5.0, max(0.2, actual / base))
        self._time_scale = ratio if self._time_scale is None else 0.5 * self._time_scale + 0.5 * ratio

    def _learn_settle(self, actual):
        self._settle_s = 0.5 * self._settle_s + 0.5 * min(actual, SETTLE_BUDGET_S + 3.0)

    def _estimate(self, cur, order, goal):
        total, prev = 0.0, cur
        path = list(order) + ([goal] if goal is not None else [])
        for cp in path:
            node = (cp['pos'], cp['quat'])
            total += self._scale() * self._base_time(prev, node) + self._settle_s + CLAIM_S
            prev = node
        return total

    def _best_order(self, cur, nodes, goal):
        """Held-Karp: cheapest order cur -> all nodes -> goal (goal fixed last if present)."""
        n = len(nodes)
        if n <= 1:
            return list(nodes)
        pts = [(c['pos'], c['quat']) for c in nodes]
        c0 = [self._base_time(cur, pts[j]) for j in range(n)]
        g = (goal['pos'], goal['quat']) if goal is not None else None
        cg = [self._base_time(pts[j], g) if g is not None else 0.0 for j in range(n)]
        cc = [[0.0 if i == j else self._base_time(pts[i], pts[j]) for j in range(n)] for i in range(n)]

        if n > 12:  # defensive: nearest-neighbour if the layout is unexpectedly large
            left, order, prev = list(range(n)), [], None
            while left:
                j = min(left, key=lambda k: c0[k] if prev is None else cc[prev][k])
                order.append(j)
                left.remove(j)
                prev = j
            return [nodes[j] for j in order]

        inf = float('inf')
        full = 1 << n
        dp = [[inf] * n for _ in range(full)]
        par = [[-1] * n for _ in range(full)]
        for j in range(n):
            dp[1 << j][j] = c0[j]
        for mask in range(1, full):
            row = dp[mask]
            for j in range(n):
                base = row[j]
                if base == inf:
                    continue
                cj = cc[j]
                for k in range(n):
                    if (mask >> k) & 1:
                        continue
                    nm = mask | (1 << k)
                    v = base + cj[k]
                    if v < dp[nm][k]:
                        dp[nm][k] = v
                        par[nm][k] = j
        last = min(range(n), key=lambda j: dp[full - 1][j] + cg[j])
        order, mask, j = [], full - 1, last
        while j != -1:
            order.append(j)
            pj = par[mask][j]
            mask ^= (1 << j)
            j = pj
        order.reverse()
        return [nodes[j] for j in order]

    def _worst_detour(self, cur, order, goal):
        path = [cur] + [(c['pos'], c['quat']) for c in order]
        if goal is not None:
            path.append((goal['pos'], goal['quat']))
        worst, worst_cost = order[0], -1.0
        for i, cp in enumerate(order):
            prev, mid = path[i], path[i + 1]
            nxt = path[i + 2] if i + 2 < len(path) else None
            if nxt is None:
                cost = self._base_time(prev, mid)
            else:
                cost = self._base_time(prev, mid) + self._base_time(mid, nxt) - self._base_time(prev, nxt)
            if cost > worst_cost:
                worst, worst_cost = cp, cost
        return worst

    def _plan(self, cur, remaining, goal):
        order = self._best_order(cur, remaining, goal)
        if self._legs_measured < MIN_LEGS_BEFORE_DROP:   # not calibrated yet: never drop on a guess
            return order
        left = self._time_left()
        while order and self._estimate(cur, order, goal) > left:
            worst = self._worst_detour(cur, order, goal)
            rospy.logwarn('time budget: dropping checkpoint %d (est %.1fs > left %.1fs)',
                          worst['id'], self._estimate(cur, order, goal), left)
            order.remove(worst)
            order = self._best_order(cur, order, goal)
        return order

    # ====================================================================================
    # Motion
    # ====================================================================================
    def _cancel_move(self):
        try:
            self._command.cancel_goal()
            if not self._command.wait_for_result(rospy.Duration(5.0)):
                rospy.logwarn('cancel did not complete')
        except Exception as exc:
            rospy.logwarn('cancel failed: %s', exc)

    def _move(self, pos, quat, timeout):
        target = PoseStamped()
        target.pose.position.x, target.pose.position.y, target.pose.position.z = pos
        (target.pose.orientation.x, target.pose.orientation.y,
         target.pose.orientation.z, target.pose.orientation.w) = quat
        goal = CtlCommandGoal(target=target, type=CtlStatusType(type=CtlStatusType.MOVE_TO_ABSOLUTE_TARGET))
        self._cmd_active = True
        try:
            if not self._command.wait_for_server(rospy.Duration(5.0)):
                rospy.logwarn('/ctl/command server unavailable')
                return False
            self._command.send_goal(goal)
            t_end = rospy.get_time() + timeout
            while not self._stopping():
                if self._command.wait_for_result(rospy.Duration(0.1)):
                    result = self._command.get_result()
                    ok = result is not None and result.type == CtlCommandResult.TERMINATE_SUCCESS
                    if not ok:
                        rospy.logwarn('move command result: %s', result)
                    return ok
                if rospy.get_time() > t_end:
                    rospy.logwarn('move timed out after %.1fs, cancelling', timeout)
                    break
            self._cancel_move()
            return False
        finally:
            self._cmd_active = False

    # ====================================================================================
    # Verification of the three judged conditions
    # ====================================================================================
    @staticmethod
    def _errors(cp, nav):
        _, pos, quat, lin, ang = nav
        pos_err = _dist(pos, cp['pos'])
        q_err = _q_mul(_q_conj(cp['quat']), quat)
        roll = abs(_wrap_pi(2.0 * math.atan2(q_err[0], q_err[3])))
        if cp['marker'] is not None:
            los = _q_rotate(quat, (1.0, 0.0, 0.0))
            to_marker = _unit(_sub(cp['marker'], pos))
            cen = math.acos(max(-1.0, min(1.0, _dot(los, to_marker))))
        else:  # no marker position: use the swing part of the attitude error
            twist = _q_normalize((q_err[0], 0.0, 0.0, q_err[3]))
            swing = _q_mul(q_err, _q_conj(twist))
            cen = _q_angle(swing, (0.0, 0.0, 0.0, 1.0))
        cen, roll = math.degrees(cen), math.degrees(roll)

        levels = [_band_level(cp['pos_bands'], pos_err)]
        if cp['cen_bands']:
            levels.append(_band_level(cp['cen_bands'], cen))
        if cp['roll_bands']:
            levels.append(_band_level(cp['roll_bands'], roll))
        return {'pos': pos_err, 'cen': cen, 'roll': roll, 'lin': lin, 'ang': ang, 'level': min(levels)}

    def _settle(self, cp, moved_ok):
        """Refine until all conditions are comfortably inside Lv3 and still for HOLD_S.
        Returns the estimated level (0-3), or -1 if navigation is unavailable."""
        tol_pos = TOL_FRACTION * _top_limit(cp['pos_bands'])
        tol_cen = TOL_FRACTION * _top_limit(cp['cen_bands']) if cp['cen_bands'] else None
        tol_roll = TOL_FRACTION * _top_limit(cp['roll_bands']) if cp['roll_bands'] else None

        t_begin = rospy.get_time()
        hold_start, within_since, fixes, last_level = None, None, 0, None
        while not self._stopping():
            now = rospy.get_time()
            if now - t_begin > SETTLE_BUDGET_S or self._time_left() <= 0.0:
                break
            nav = self._fresh_nav() if self._nav_ok else None
            if nav is None:                                   # blind fallback
                if not moved_ok and fixes < 1:
                    fixes += 1
                    moved_ok = self._move(cp['pos'], cp['quat'], FIX_TIMEOUT_S)
                    continue
                rospy.logwarn('no fresh navigation: holding blind for %.1fs', HOLD_S)
                rospy.sleep(HOLD_S)
                return -1
            err = self._errors(cp, nav)
            if moved_ok and fixes == 0 and err['pos'] > NAV_SANITY_POS_M:
                rospy.logerr('navigation disagrees with /ctl/command by %.2fm at cp %d: nav frame untrusted, '
                             'switching to blind mode', err['pos'], cp['id'])
                self._nav_ok = False
                continue
            last_level = err['level']
            within = (err['pos'] <= tol_pos
                      and (tol_cen is None or err['cen'] <= tol_cen)
                      and (tol_roll is None or err['roll'] <= tol_roll))
            still = err['lin'] <= STILL_LIN_MPS and err['ang'] <= STILL_ANG_RPS
            within_since = (within_since or now) if within else None
            if within and still:
                if hold_start is None:
                    hold_start = now
                if now - hold_start >= HOLD_S:
                    return err['level']
            elif within and now - within_since >= NOISY_TWIST_ACCEPT_S:
                rospy.logwarn('cp %d: twist looks noisy (lin=%.3f ang=%.3f) but pose stable for %.1fs: accepting',
                              cp['id'], err['lin'], err['ang'], now - within_since)
                return err['level']
            else:
                hold_start = None
                if not within and still and fixes < MAX_FIXES:
                    fixes += 1
                    rospy.loginfo('fix %d for cp %d: pos=%.3f cen=%.1f roll=%.1f', fixes, cp['id'],
                                  err['pos'], err['cen'], err['roll'])
                    self._move(cp['pos'], cp['quat'], FIX_TIMEOUT_S)
            rospy.sleep(0.05)
        return last_level if last_level is not None else -1

    # ====================================================================================
    # Mission
    # ====================================================================================
    def _visit(self, cur, cp):
        t_a = rospy.get_time()
        base = self._base_time(cur, (cp['pos'], cp['quat']))
        timeout = min(max(self._time_left(), 1.0),
                      max(MIN_LEG_TIMEOUT_S, LEG_TIMEOUT_FACTOR * self._scale() * base))
        moved_ok = self._move(cp['pos'], cp['quat'], timeout)
        t_b = rospy.get_time()
        if moved_ok:
            self._learn_leg(base, t_b - t_a)

        level = self._settle(cp, moved_ok)
        claimed = False
        if level != 0 and not self._stopping():
            claimed = self._notify_checkpoint_passed(cp['id'])
        else:
            rospy.logwarn('cp %d not claimed (estimated level %s)', cp['id'], level)
        t_c = rospy.get_time()
        self._learn_settle(t_c - t_b)

        self._results.append((cp['id'], level, claimed))
        rospy.loginfo('VISIT id=%d move_ok=%s leg=%.1fs (model %.1fs, scale %.2f) settle=%.1fs '
                      'est_level=%s claimed=%s elapsed=%.1fs left=%.1fs',
                      cp['id'], moved_ok, t_b - t_a, base, self._scale(), t_c - t_b, level, claimed,
                      rospy.get_time() - (self._t0 if self._t0 is not None else t_a), self._time_left())

    def _execute(self, data):
        by_id = {}
        for cp in data['checkpoints']:
            by_id[cp['id']] = cp
        goal = by_id.get(data['goal_id']) if data['goal_id'] is not None else None
        if data['goal_id'] is not None and goal is None:
            rospy.logwarn('goal id %s is not among the checkpoints: ending at the last one', data['goal_id'])
        remaining = [cp for cp in by_id.values() if cp is not goal]

        nav = self._fresh_nav()
        cur = (nav[1], nav[2]) if nav is not None else (DOCK_POS, DOCK_QUAT)

        order = self._best_order(cur, remaining, goal)
        rospy.loginfo('initial plan: %s -> goal %s (model total %.1fs)', [c['id'] for c in order],
                      goal['id'] if goal else None, self._estimate(cur, order, goal))

        while remaining and not self._stopping() and self._time_left() > 0.0:
            order = self._plan(cur, remaining, goal)
            if not order:
                break
            remaining = list(order)
            nxt = remaining.pop(0)
            self._visit(cur, nxt)
            cur = (nxt['pos'], nxt['quat'])

        if goal is not None and not self._stopping() and self._time_left() > 0.0:
            self._visit(cur, goal)

    def _run_user_flow(self, msg):
        started = False
        try:
            self._prep_done.wait(20.0)
            if self._prep is None:
                self._prep = self._fetch_checkpoints()
            if self._prep is None:
                rospy.logerr('no checkpoint data available; ending mission without moving')

            if not self._notify_mission_start():
                return
            started = True
            self._t0 = rospy.get_time()

            if self._prep is not None:
                self._execute(self._prep)
        except Exception as exc:
            rospy.logerr('user flow failed: %s\n%s', exc, traceback.format_exc())
        finally:
            if started and not rospy.is_shutdown():
                self._notify_mission_finished()
                rospy.loginfo('SUMMARY version=%s elapsed=%.1fs results(id,level,claimed)=%s',
                              VERSION, rospy.get_time() - self._t0, self._results)

    def _callback_start(self, msg):
        if self._started:
            rospy.logwarn('start callback is already processed')
            return
        self._started = True

        rospy.loginfo('start %s', msg)
        worker = threading.Thread(target=self._run_user_flow, args=(msg,))
        worker.daemon = True
        worker.start()

    def _stop_processing(self, request):
        try:
            self._abort.set()
            if self._cmd_active:
                self._cancel_move()
            if self._claim_active:
                self._checkpoint_client.cancel_goal()
            rospy.loginfo('finish processing')
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.SUCCESS)
        except Exception as exc:
            rospy.logerr('stop processing failed: %s', exc)
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.ERROR)

    def run(self):
        rospy.spin()


if __name__ == '__main__':
    UserTemplate().run()
