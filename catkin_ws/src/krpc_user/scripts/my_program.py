#!/usr/bin/python3
# -*- coding:utf-8 -*-

import json
import math
import rospy
import actionlib

from geometry_msgs.msg import WrenchStamped, PoseStamped
from platform_msgs.msg import UserLogic
from platform_msgs.srv import StopProcessingUserNode, StopProcessingUserNodeResponse
from krpc_ib2_msgs.srv import MissionStart, MissionFinished, CheckPoints
from krpc_ib2_msgs.msg import CheckpointPassedAction, CheckpointPassedGoal
from ib2_msgs.msg import CtlCommandAction, CtlCommandGoal, CtlCommandResult, CtlStatusType
from ib2_msgs.msg import Navigation


class UserTemplate:

    def __init__(self):
        rospy.init_node('krpc_user')
        self.wrench_pub = rospy.Publisher('/ctl/wrench', WrenchStamped, queue_size=1)

        self.rate = rospy.Rate(20)
        self.__command = actionlib.SimpleActionClient('/ctl/command', CtlCommandAction)
        self.__checkpoint_client = actionlib.SimpleActionClient(
            '/event/checkpoint_passed', CheckpointPassedAction
        )

        self.__mission_start = rospy.ServiceProxy('/event/mission_start', MissionStart)
        self.__mission_finished = rospy.ServiceProxy('/event/mission_finished', MissionFinished)
        self.__checkpoints = rospy.ServiceProxy('/mission/get_checkpoints', CheckPoints)

        self.current_position = None
        self.current_orientation = None
        self.current_angular_velocity = None
        self.current_velocity = None

        self.navigation_sub = rospy.Subscriber(
            '/sensor_fusion/navigation', Navigation,
            self.__nav_callback, queue_size=1
        )
        self.__subscriber_start = rospy.Subscriber(
            '/ib2_user/start', UserLogic, self.__callback_start
        )
        self.__stop_processing_server = rospy.Service(
            '/ib2_user/stop', StopProcessingUserNode, self.__stop_processing
        )

        self.__started = False
        self.__action_active = False
        rospy.set_param('/ib2_user/ready', True)

    # --------------------------------------------------------------------------
    # MISSION EVENTS
    # --------------------------------------------------------------------------

    def __notify_mission_start(self):
        rospy.wait_for_service('/event/mission_start')
        res = self.__mission_start()
        rospy.loginfo(
            'mission_start result: success=%s message=%s',
            res.success, res.message
        )
        return res.success

    def __notify_mission_finished(self):
        rospy.wait_for_service('/event/mission_finished')
        res = self.__mission_finished()
        rospy.loginfo(
            'mission_finished result: success=%s message=%s',
            res.success, res.message
        )
        return res.success

    def __notify_checkpoint_passed(self, checkpoint_id):
        rospy.loginfo('notify checkpoint_id=%d passed', checkpoint_id)
        self.__checkpoint_client.wait_for_server()

        goal = CheckpointPassedGoal()
        goal.checkpoint_id = checkpoint_id
        self.__checkpoint_client.send_goal(goal)

        while not rospy.is_shutdown():
            if self.__checkpoint_client.wait_for_result(rospy.Duration(0.2)):
                result = self.__checkpoint_client.get_result()
                rospy.loginfo('checkpoint_passed result: %s', result)
                return result.success

        if rospy.is_shutdown():
            self.__checkpoint_client.cancel_goal()
            rospy.logwarn('checkpoint_passed action cancelled by node shutdown')

        return False

    def __get_checkpoint_id(self, checkpoint):
        for key in ('checkpoint_id', 'checkpointid', 'id'):
            if key in checkpoint:
                return int(checkpoint[key])
        return None

    def __wait_for_navigation(self):
        """Wait until the navigation callback has populated all required fields."""
        while not rospy.is_shutdown():
            if (self.current_position is not None and
                    self.current_orientation is not None and
                    self.current_velocity is not None and
                    self.current_angular_velocity is not None):
                return True
            self.rate.sleep()

        return False

    def __resolve_first_checkpoint_target(self):
        default_target = {
            'checkpoint_id': 1,
            'position': [0.0, 0.0, 0.0],
            'quaternion': [0.0, 0.0, 0.0, 1.0],
        }

        rospy.wait_for_service('/mission/get_checkpoints')
        res = self.__checkpoints()
        rospy.loginfo(
            'get_checkpoints result: success=%s message=%s',
            res.success, res.message
        )

        if not res.success:
            return default_target

        try:
            payload = json.loads(res.message)
            checkpoints = payload.get('checkpoints', payload.get('Checkpoints', []))
            checkpoints = [
                cp for cp in checkpoints
                if isinstance(cp, dict) and self.__get_checkpoint_id(cp) is not None
            ]

            if not checkpoints:
                rospy.logwarn('No checkpoints found in payload')
                return default_target

            checkpoint = min(checkpoints, key=self.__get_checkpoint_id)
            position = checkpoint.get('position', default_target['position'])

            if not (isinstance(position, list) and len(position) >= 3):
                rospy.logwarn('Invalid checkpoint position format')
                return default_target

            quaternion = default_target['quaternion']
            attitude = checkpoint.get('attitude')
            if isinstance(attitude, dict):
                attitude_quaternion = attitude.get('quaternion')
                if isinstance(attitude_quaternion, list) and len(attitude_quaternion) >= 4:
                    quaternion = attitude_quaternion

            return {
                'checkpoint_id': self.__get_checkpoint_id(checkpoint),
                'position': [
                    float(position[0]), float(position[1]), float(position[2])
                ],
                'quaternion': [
                    float(quaternion[0]), float(quaternion[1]),
                    float(quaternion[2]), float(quaternion[3])
                ],
            }

        except Exception as exc:
            rospy.logwarn('Failed to parse checkpoints payload: %s', exc)

        return default_target

    def __move_to_checkpoint(self, checkpoint_target):
        position = checkpoint_target['position']
        quaternion = checkpoint_target['quaternion']

        rospy.loginfo(
            'moving to checkpoint_id=%d: x=%.3f y=%.3f z=%.3f '
            'qx=%.4f qy=%.4f qz=%.4f qw=%.4f',
            checkpoint_target['checkpoint_id'],
            position[0], position[1], position[2],
            quaternion[0], quaternion[1], quaternion[2], quaternion[3]
        )

        target = PoseStamped()
        target.pose.position.x = position[0]
        target.pose.position.y = position[1]
        target.pose.position.z = position[2]
        target.pose.orientation.x = quaternion[0]
        target.pose.orientation.y = quaternion[1]
        target.pose.orientation.z = quaternion[2]
        target.pose.orientation.w = quaternion[3]

        command_type = CtlStatusType(type=CtlStatusType.MOVE_TO_ABSOLUTE_TARGET)
        goal = CtlCommandGoal(target=target, type=command_type)

        self.__action_active = True
        try:
            self.__command.send_goal(goal)
            while not rospy.is_shutdown():
                if self.__command.wait_for_result(rospy.Duration(0.2)):
                    result = self.__command.get_result()
                    rospy.loginfo('move command result: %s', result)
                    return result.type == CtlCommandResult.TERMINATE_SUCCESS

            if rospy.is_shutdown():
                self.__command.cancel_goal()
                rospy.logwarn('move command cancelled by node shutdown')

            return False
        finally:
            self.__action_active = False

    # --------------------------------------------------------------------------
    # PATHFINDING
    # --------------------------------------------------------------------------

    '''
    
    '''

    '''
    The route starts at the robot's current position (which should be the dock
    when the mission begins), visits every checkpoint, and finishes at the
    goalpoint_id supplied by /mission/get_checkpoints.

    Held-Karp stores the best cost for each visited-checkpoint subset and each
    possible last checkpoint. Unlike a closed TSP tour, this version does not
    add a final distance back to the dock.
    '''

    def __get_checkpoint_targets(self):
        targets = []
        default_position = [0.0, 0.0, 0.0]
        goalpoint_id = None

        rospy.wait_for_service('/mission/get_checkpoints')
        res = self.__checkpoints()
        rospy.loginfo(
            'get_checkpoints result: success=%s message=%s',
            res.success, res.message
        )

        if not res.success:
            return [], None

        try:
            payload = json.loads(res.message)
            checkpoints = payload.get('checkpoints', payload.get('Checkpoints', []))

            # The service payload normally exposes goalpoint_id directly. The
            # nested Goal form is also accepted for compatibility.
            goalpoint_id = payload.get('goalpoint_id')
            if goalpoint_id is None:
                goal = payload.get('Goal', payload.get('goal'))
                if isinstance(goal, dict):
                    goalpoint_id = goal.get('checkpoint_id')

            if goalpoint_id is not None:
                goalpoint_id = int(goalpoint_id)

            checkpoints = [
                cp for cp in checkpoints
                if isinstance(cp, dict) and self.__get_checkpoint_id(cp) is not None
            ]

            if not checkpoints:
                rospy.logwarn('No checkpoints found in payload')
                return [], goalpoint_id

            for checkpoint in checkpoints:
                position = checkpoint.get('position', default_position)

                if not (isinstance(position, list) and len(position) >= 3):
                    rospy.logwarn(
                        'Invalid position for checkpoint_id=%s',
                        self.__get_checkpoint_id(checkpoint)
                    )
                    return [], goalpoint_id

                quaternion = [0.0, 0.0, 0.0, 1.0]
                attitude = checkpoint.get('attitude')
                if isinstance(attitude, dict):
                    attitude_quaternion = attitude.get('quaternion')
                    if isinstance(attitude_quaternion, list) and len(attitude_quaternion) >= 4:
                        quaternion = attitude_quaternion

                targets.append({
                    'checkpoint_id': self.__get_checkpoint_id(checkpoint),
                    'position': [
                        float(position[0]), float(position[1]), float(position[2])
                    ],
                    'quaternion': [
                        float(quaternion[0]), float(quaternion[1]),
                        float(quaternion[2]), float(quaternion[3])
                    ],
                })

            return targets, goalpoint_id

        except Exception as exc:
            rospy.logwarn('Failed to parse checkpoints payload: %s', exc)
            return [], None

    def __determine_distance(self, first, second):
        first_position = first['position']
        second_position = second['position']

        dx = second_position[0] - first_position[0]
        dy = second_position[1] - first_position[1]
        dz = second_position[2] - first_position[2]

        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def __nav_callback(self, msg):
        self.current_velocity = msg.twist.linear
        self.current_angular_velocity = msg.twist.angular
        self.current_orientation = msg.pose.pose.orientation
        self.current_position = msg.pose.pose.position

    def __held_karp_approach(self, distances, start_distances, end_index):
        """Minimum open path: external start -> every node -> fixed end_index."""
        n_targets = len(distances)
        if n_targets == 0:
            return []

        if (len(start_distances) != n_targets or
                end_index < 0 or end_index >= n_targets):
            rospy.logerr('Invalid inputs to Held-Karp route calculation')
            return []

        infinity = float('inf')
        n_states = 1 << n_targets

        states = [
            [infinity] * n_targets for _ in range(n_states)
        ]
        parents = [
            [-1] * n_targets for _ in range(n_states)
        ]

        # The route begins at the robot's current position, not at a checkpoint.
        for target_index in range(n_targets):
            states[1 << target_index][target_index] = start_distances[target_index]

        for state in range(n_states):
            for last in range(n_targets):
                if not (state & (1 << last)):
                    continue

                current_cost = states[state][last]
                if math.isinf(current_cost):
                    continue

                for next_target in range(n_targets):
                    if state & (1 << next_target):
                        continue

                    new_state = state | (1 << next_target)
                    new_cost = current_cost + distances[last][next_target]

                    if new_cost < states[new_state][next_target]:
                        states[new_state][next_target] = new_cost
                        parents[new_state][next_target] = last

        complete_state = n_states - 1
        if math.isinf(states[complete_state][end_index]):
            rospy.logerr('No complete route ending at checkpoint index %d', end_index)
            return []

        # Backtrack from the required final checkpoint.
        route = []
        state = complete_state
        last = end_index

        while last != -1:
            route.append(last)
            previous = parents[state][last]
            state ^= (1 << last)
            last = previous

        route.reverse()
        return route

    def __determine_route(self):
        targets, goalpoint_id = self.__get_checkpoint_targets()

        if not targets:
            rospy.logerr('Route generation failed: no checkpoint targets')
            return []

        if goalpoint_id is None:
            rospy.logerr('Route generation failed: goalpoint_id was not provided')
            return []

        goal_indices = [
            index for index, target in enumerate(targets)
            if target['checkpoint_id'] == goalpoint_id
        ]

        if not goal_indices:
            rospy.logerr(
                'Route generation failed: goalpoint_id=%d is not in checkpoint list',
                goalpoint_id
            )
            return []

        if not self.__wait_for_navigation():
            rospy.logerr('Route generation stopped before navigation data arrived')
            return []

        # At mission start, the current navigation position is treated as the
        # dock/start position. No synthetic dock checkpoint is added to the route.
        start_position = {
            'position': [
                self.current_position.x,
                self.current_position.y,
                self.current_position.z
            ]
        }

        n_targets = len(targets)
        distances = [[0.0] * n_targets for _ in range(n_targets)]

        for i in range(n_targets):
            for j in range(i + 1, n_targets):
                distance = self.__determine_distance(targets[i], targets[j])
                distances[i][j] = distance
                distances[j][i] = distance

        start_distances = [
            self.__determine_distance(start_position, target)
            for target in targets
        ]

        goal_index = goal_indices[0]
        best_order = self.__held_karp_approach(
            distances, start_distances, goal_index
        )

        if not best_order:
            return []

        ordered_targets = [targets[index] for index in best_order]
        rospy.loginfo(
            'Computed checkpoint route (goal=%d): %s',
            goalpoint_id,
            [target['checkpoint_id'] for target in ordered_targets]
        )

        return ordered_targets

    # --------------------------------------------------------------------------
    # MOVEMENT / WRENCH CONTROL
    # --------------------------------------------------------------------------

    '''
    Translation:
      - Position error and linear velocity are treated as navigation-frame values,
        matching the built-in position controller's use of Navigation.
      - The complete PD force vector is rotated into the body frame before its
        components are clamped and published.

    Rotation:
      - The current angular velocity is assumed to be body-frame, as agreed for
        this controller's working convention.
      - The existing quaternion-error and PD torque calculations are retained.
    '''

    p_term_pos = 0.1
    d_term_pos = 0.1

    p_term_rot = 0.3
    d_term_rot = 0.3

    pos_tolerance = 0.05
    rot_tolerance = 0.05

    # Initial stopping thresholds; tune against simulator behavior if needed.
    velocity_tolerance = 0.01          # m/s
    angular_velocity_tolerance = 0.01  # rad/s

    max_force = 1.0
    max_torque = 1.0

    def __wrench_it(self, fx, fy, fz, tx, ty, tz):
        wrench = WrenchStamped()
        wrench.header.stamp = rospy.Time.now()
        # Match the built-in controller's wrench frame convention.
        self.wrench_frame = 'body'
        wrench.header.frame_id = self.wrench_frame

        wrench.wrench.force.x = fx
        wrench.wrench.force.y = fy
        wrench.wrench.force.z = fz

        wrench.wrench.torque.x = tx
        wrench.wrench.torque.y = ty
        wrench.wrench.torque.z = tz
        '''
        rospy.loginfo(
            'force published = [fx=%.4f, fy=%.4f, fz=%.4f]',
            fx, fy, fz
        )

        rospy.loginfo(
            'torque published = [tx=%.4f, ty=%.4f, tz=%.4f]',
            tx, ty, tz
        )
        '''

        self.wrench_pub.publish(wrench)

    def __force_clamp(self, val):
        return max(-self.max_force, min(self.max_force, val))

    def __torque_clamp(self, val):
        return max(-self.max_torque, min(self.max_torque, val))

    def __calcluate_error_pos(self, target):
        target_pos = target['position']

        return [
            target_pos[0] - self.current_position.x,
            target_pos[1] - self.current_position.y,
            target_pos[2] - self.current_position.z,
        ]

    def __calculate_error_rot(self, target):
        # Orientation of the AR marker at the checkpoint.
        marker_orient = target['quaternion']

        # Inverse/conjugate of the current orientation quaternion.
        current_inverted = [
            -self.current_orientation.x,
            -self.current_orientation.y,
            -self.current_orientation.z,
            self.current_orientation.w,
        ]

        # Hamilton product: current_inverse * target.
        quat_prod = []

        quat_prod.append(
            current_inverted[3] * marker_orient[0] +
            current_inverted[0] * marker_orient[3] +
            current_inverted[1] * marker_orient[2] -
            current_inverted[2] * marker_orient[1]
        )

        quat_prod.append(
            current_inverted[3] * marker_orient[1] -
            current_inverted[0] * marker_orient[2] +
            current_inverted[1] * marker_orient[3] +
            current_inverted[2] * marker_orient[0]
        )

        quat_prod.append(
            current_inverted[3] * marker_orient[2] +
            current_inverted[0] * marker_orient[1] -
            current_inverted[1] * marker_orient[0] +
            current_inverted[2] * marker_orient[3]
        )

        quat_prod.append(
            current_inverted[3] * marker_orient[3] -
            current_inverted[0] * marker_orient[0] -
            current_inverted[1] * marker_orient[1] -
            current_inverted[2] * marker_orient[2]
        )

        norm = math.sqrt(sum(component * component for component in quat_prod))
        if norm < 1e-8:
            return [0.0, 0.0, 0.0]

        quat_prod = [component / norm for component in quat_prod]

        # q and -q describe the same orientation; choose the shorter rotation.
        if quat_prod[3] < 0.0:
            quat_prod = [-component for component in quat_prod]

        half_sin = math.sqrt(
            quat_prod[0] ** 2 + quat_prod[1] ** 2 + quat_prod[2] ** 2
        )

        if half_sin < 1e-8:
            return [0.0, 0.0, 0.0]

        angle = 2.0 * math.atan2(half_sin, quat_prod[3])

        return [
            angle * quat_prod[0] / half_sin,
            angle * quat_prod[1] / half_sin,
            angle * quat_prod[2] / half_sin,
        ]

    def __rotate_vector_by_quaternion(self, vector, quaternion):
        """Rotate vector by quaternion [x, y, z, w]. Returns None if invalid."""
        qx, qy, qz, qw = quaternion

        q_norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
        if q_norm < 1e-8:
            return None

        qx /= q_norm
        qy /= q_norm
        qz /= q_norm
        qw /= q_norm

        vx, vy, vz = vector

        # Equivalent to q * [v, 0] * q^-1, optimized using cross products.
        tx = 2.0 * (qy * vz - qz * vy)
        ty = 2.0 * (qz * vx - qx * vz)
        tz = 2.0 * (qx * vy - qy * vx)

        rotated_x = vx + qw * tx + (qy * tz - qz * ty)
        rotated_y = vy + qw * ty + (qz * tx - qx * tz)
        rotated_z = vz + qw * tz + (qx * ty - qy * tx)

        return [rotated_x, rotated_y, rotated_z]

    def __calculate_trans_force(self, target):
        error_pos = self.__calcluate_error_pos(target)

        # PD force calculated in the navigation frame.
        force_nav = [
            self.p_term_pos * error_pos[0] - self.d_term_pos * self.current_velocity.x,
            self.p_term_pos * error_pos[1] - self.d_term_pos * self.current_velocity.y,
            self.p_term_pos * error_pos[2] - self.d_term_pos * self.current_velocity.z,
        ]

        # The navigation orientation q maps body vectors into navigation.
        # Its conjugate/inverse therefore maps navigation-frame force into body.
        q = self.current_orientation
        q_inverse = [-q.x, -q.y, -q.z, q.w]

        force_body = self.__rotate_vector_by_quaternion(force_nav, q_inverse)
        if force_body is None:
            rospy.logwarn_throttle(
                5.0, 'Invalid navigation orientation quaternion; publishing zero force'
            )
            return [0.0, 0.0, 0.0]

        # Clamp only after rotating, so the limits apply to body-frame components.
        return [
            self.__force_clamp(force_body[0]),
            self.__force_clamp(force_body[1]),
            self.__force_clamp(force_body[2]),
        ]

    def __calculate_rot_torque(self, target):
        error_rot = self.__calculate_error_rot(target)

        torque = [
            self.__torque_clamp(
                self.p_term_rot * error_rot[0] -
                self.d_term_rot * self.current_angular_velocity.x
            ),
            self.__torque_clamp(
                self.p_term_rot * error_rot[1] -
                self.d_term_rot * self.current_angular_velocity.y
            ),
            self.__torque_clamp(
                self.p_term_rot * error_rot[2] -
                self.d_term_rot * self.current_angular_velocity.z
            ),
        ]

        return torque

    def __move_bot(self, target):
        force = self.__calculate_trans_force(target)
        torque = self.__calculate_rot_torque(target)

        self.__wrench_it(
            force[0], force[1], force[2],
            torque[0], torque[1], torque[2]
        )
        error_pos = self.__calcluate_error_pos(target)

        rospy.loginfo_throttle(
            1.0,
            'TARGET %d | '
            'error=[%.3f, %.3f, %.3f] | '
            'velocity=[%.3f, %.3f, %.3f] | '
            'body_force=[%.4f, %.4f, %.4f]',
            target['checkpoint_id'],
            error_pos[0], error_pos[1], error_pos[2],
            self.current_velocity.x,
            self.current_velocity.y,
            self.current_velocity.z,
            force[0], force[1], force[2]
        )

    def __move_to_checkpoint_faster(self, target):
        rate = rospy.Rate(10)

        if not self.__wait_for_navigation():
            self.__wrench_it(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            return False

        while not rospy.is_shutdown():
            error_pos = self.__calcluate_error_pos(target)
            error_rot = self.__calculate_error_rot(target)

            error_pos_mag = math.sqrt(sum(value * value for value in error_pos))
            error_rot_mag = math.sqrt(sum(value * value for value in error_rot))

            velocity_n = math.sqrt(
                self.current_velocity.x ** 2 +
                self.current_velocity.y ** 2 +
                self.current_velocity.z ** 2
            )

            angular_velocity_n = math.sqrt(
                self.current_angular_velocity.x ** 2 +
                self.current_angular_velocity.y ** 2 +
                self.current_angular_velocity.z ** 2
            )
            rospy.loginfo_throttle(
                1.0,
                'CHECKPOINT %d | '
                'position_error=%.4f m | rotation_error=%.4f rad | '
                'linear_speed=%.4f m/s | angular_speed=%.4f rad/s | '
                'position=[%.3f, %.3f, %.3f]',
                target['checkpoint_id'],
                error_pos_mag,
                error_rot_mag,
                velocity_n,
                angular_velocity_n,
                self.current_position.x,
                self.current_position.y,
                self.current_position.z
            )

            if (error_pos_mag < self.pos_tolerance and
                    error_rot_mag < self.rot_tolerance and
                    velocity_n < self.velocity_tolerance and
                    angular_velocity_n < self.angular_velocity_tolerance):

                self.__wrench_it(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                rospy.loginfo(
                    'Reached checkpoint_id=%d; position_error=%.4f '
                    'rotation_error=%.4f',
                    target['checkpoint_id'], error_pos_mag, error_rot_mag
                )
                return True

            self.__move_bot(target)
            rate.sleep()

        # Stop commanding the vehicle if the loop exits during shutdown.
        self.__wrench_it(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        return False

    # --------------------------------------------------------------------------
    # MISSION FLOW
    # --------------------------------------------------------------------------

    def __run_user_flow(self, msg):
        try:
            if not self.__notify_mission_start():
                return

            if not self.__wait_for_navigation():
                rospy.logerr('Mission stopped before navigation data arrived')
                return

            route = self.__determine_route()
            if not route:
                rospy.logerr('Route generation failed')
                return

            for checkpoint_target in route:
                if not self.__move_to_checkpoint(checkpoint_target):
                    return

                if not self.__notify_checkpoint_passed(
                        checkpoint_target['checkpoint_id']):
                    return

            if not rospy.is_shutdown():
                self.__notify_mission_finished()

        except Exception as exc:
            rospy.logerr('user flow failed: %s', exc)
            self.__wrench_it(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def __callback_start(self, msg):
        if self.__started:
            rospy.logwarn('start callback is already processed')
            return

        self.__started = True
        rospy.loginfo('start %s', msg)
        self.__run_user_flow(msg)

    def __stop_processing(self, request):
        try:
            if self.__action_active:
                self.__command.cancel_goal()

            # Also stop any direct wrench command from this node.
            self.__wrench_it(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            rospy.loginfo('finish processing')

            return StopProcessingUserNodeResponse(
                result=StopProcessingUserNodeResponse.SUCCESS
            )

        except Exception as exc:
            rospy.logerr('stop processing failed: %s', exc)
            return StopProcessingUserNodeResponse(
                result=StopProcessingUserNodeResponse.ERROR
            )

    def run(self):
        rospy.spin()


if __name__ == '__main__':
    UserTemplate().run()