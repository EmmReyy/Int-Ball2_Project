#!/usr/bin/python3
# -*- coding:utf-8 -*-
import csv
import os
import threading
import time
import json
import math
import itertools
import rospy
import actionlib
from platform_msgs.msg import UserLogic
from platform_msgs.srv import StopProcessingUserNode, StopProcessingUserNodeResponse
from geometry_msgs.msg import PoseStamped
from krpc_ib2_msgs.srv import MissionStart, MissionFinished, CheckPoints
from krpc_ib2_msgs.msg import CheckpointPassedAction, CheckpointPassedGoal
from ib2_msgs.msg import CtlCommandAction, CtlCommandGoal, CtlCommandResult, CtlStatusType, Navigation
from geometry_msgs.msg import WrenchStamped

# Optional IF examples. Uncomment only what your program uses.
# from std_msgs.msg import Time
# from platform_msgs.msg import UserNodeStatus
# from sensor_msgs.msg import Image
# from ib2_msgs.msg import Navigation


class UserTemplate:

    def __init__(self):
        rospy.init_node('krpc_user')

        # Action client
        self.__command = actionlib.SimpleActionClient('/ctl/command', CtlCommandAction)
        self.__checkpoint_client = actionlib.SimpleActionClient('/event/checkpoint_passed', CheckpointPassedAction)

        # Service client
        self.__mission_start = rospy.ServiceProxy('/event/mission_start', MissionStart)
        self.__mission_finished = rospy.ServiceProxy('/event/mission_finished', MissionFinished)
        self.__checkpoints = rospy.ServiceProxy('/mission/get_checkpoints', CheckPoints)
        self.__wrench_pub = rospy.Publisher('/ctl/wrench', WrenchStamped, queue_size=1)

        # Subscriber
        self.__subscriber_start = rospy.Subscriber('/ib2_user/start', UserLogic, self.__callback_start)  # DO NOT REMOVE THIS LINE
        self.__nav_lock = threading.Lock()
        self.__latest_navigation = None
        self.__latest_navigation_received = None
        self.__controller_active = False
        self.__stop_requested = threading.Event()

        self.__subscriber_nav = rospy.Subscriber(
            '/sensor_fusion/navigation',
            Navigation,
            self.__callback_nav,
            queue_size=1
        )

        # Optional subscriber examples.
        # /sensor_fusion/navigation provides the current Int-Ball2 pose, velocity and acceleration.
        # self.__subscriber_nav = rospy.Subscriber('/sensor_fusion/navigation', Navigation, self.__callback_nav)
        # /camera_main/image_raw provides the main camera image.
        # self.__subscriber_camera = rospy.Subscriber('/camera_main/image_raw', Image, self.__callback_camera_image)

        # Service server
        self.__stop_processing_server = rospy.Service('/ib2_user/stop', StopProcessingUserNode, self.__stop_processing) # DO NOT REMOVE THIS LINE

        self.__started = False
        self.__action_active = False
        rospy.set_param('/ib2_user/ready', True) # DO NOT REMOVE THIS LINE

    def __callback_nav(self, msg):
        with self.__nav_lock:
            self.__latest_navigation = msg
            self.__latest_navigation_received = time.monotonic()

    def __notify_mission_start(self):
        rospy.wait_for_service('/event/mission_start')
        res = self.__mission_start()
        rospy.loginfo('mission_start result: success=%s message=%s', res.success, res.message)
        return res.success

    def __notify_mission_finished(self):
        rospy.wait_for_service('/event/mission_finished')
        res = self.__mission_finished()
        rospy.loginfo('mission_finished result: success=%s message=%s', res.success, res.message)
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

    def __resolve_first_checkpoint_target(self):
        default_target = {
            'checkpoint_id': 1,
            'position': [0.0, 0.0, 0.0],
            'quaternion': [0.0, 0.0, 0.0, 1.0],
        }
        rospy.wait_for_service('/mission/get_checkpoints')
        res = self.__checkpoints()
        rospy.loginfo('get_checkpoints result: success=%s message=%s', res.success, res.message)
        if not res.success:
            return default_target

        try:
            payload = json.loads(res.message)
            checkpoints = payload.get('checkpoints', payload.get('Checkpoints', []))

            checkpoints = [cp for cp in checkpoints if isinstance(cp, dict) and self.__get_checkpoint_id(cp) is not None]
            if not checkpoints:
                rospy.logwarn('No checkpoints found in payload')
                return default_target

            nav = rospy.wait_for_message('/sensor_fusion/navigation', Navigation, timeout=10.0)
            current = nav.pose.pose.position

            checkpoints = [
                cp for cp in checkpoints
                if isinstance(cp.get('position'), list) and len(cp['position']) >= 3
            ]

            if not checkpoints:
                rospy.logwarn('No valid checkpoint positions found')
                return default_target

            checkpoint = max(
                checkpoints,
                key=lambda cp: sum(
                    (float(cp['position'][i]) - [current.x, current.y, current.z][i]) ** 2
                    for i in range(3)
                )
            )
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
                'position': [float(position[0]), float(position[1]), float(position[2])],
                'quaternion': [float(quaternion[0]), float(quaternion[1]), float(quaternion[2]), float(quaternion[3])],
            }
        except Exception as e:
            rospy.logwarn('Failed to parse checkpoints payload: %s', e)

        return default_target

    def __move_to_checkpoint(self, checkpoint_target):
        position = checkpoint_target['position']
        quaternion = checkpoint_target['quaternion']
        rospy.loginfo(
            'moving to checkpoint_id=%d: x=%.3f y=%.3f z=%.3f qx=%.4f qy=%.4f qz=%.4f qw=%.4f',
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


    #=============== MY ADDITIONS UwU ============================

    MOVE_DISTANCE = 0.25
    MOVE_TIMEOUT = 60.0
    TRANSLATION_SPEED_THRESHOLD = 0.01
    ROTATION_ANGLE_DEGREES = 90.0
    ROTATION_TIMEOUT = 30.0
    ROTATION_SPEED_THRESHOLD = 0.02
    ROTATION_REPETITIONS = 3
    CSV_PATH = '/mnt/krps_logs/motion_benchmark.csv'
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)

    def __callback_benchmark_nav(self, data):
        position = data.pose.pose.position
        velocity = data.twist.linear
        angular = data.twist.angular

        sample = {
            'stamp': data.pose.header.stamp.to_sec(),
            'received': time.monotonic(),
            'frame_id': data.pose.header.frame_id,
            'x': position.x,
            'y': position.y,
            'z': position.z,
            'vx': velocity.x,
            'vy': velocity.y,
            'vz': velocity.z,
            'speed': math.sqrt(
                velocity.x**2 +
                velocity.y**2 +
                velocity.z**2
            ),
            'wx': angular.x,
            'wy': angular.y,
            'wz': angular.z,
            'angular_speed': math.sqrt(
                angular.x**2 +
                angular.y**2 +
                angular.z**2
            )
        }

        with self.__nav_lock:
            self.__latest_nav = sample

            if self.__recording:
                self.__samples.append(sample.copy())

    def __wait_for_benchmark_nav(self):
        deadline = time.monotonic() + 15.0

        while not rospy.is_shutdown():
            with self.__nav_lock:
                sample = self.__latest_nav.copy() if self.__latest_nav is not None else None

            if sample is not None:
                if time.monotonic() - sample['received'] < 1.0:
                    return sample

            if time.monotonic() > deadline:
                raise RuntimeError('Navigation data unavailable')

            time.sleep(0.05)

        raise RuntimeError('ROS shutdown while waiting for navigation')

    def __save_motion_samples(self, samples):
        os.makedirs(os.path.dirname(self.CSV_PATH), exist_ok=True)

        with open(self.CSV_PATH, 'w', newline='') as file:
            writer = csv.writer(file)

            writer.writerow([
                'simulation_time',
                'wall_time',
                'frame_id',
                'x', 'y', 'z',
                'vx', 'vy', 'vz',
                'linear_speed',
                'wx', 'wy', 'wz',
                'angular_speed'
            ])

            first_stamp = samples[0]['stamp']
            first_received = samples[0]['received']

            for sample in samples:
                writer.writerow([
                    sample['stamp'] - first_stamp,
                    sample['received'] - first_received,
                    sample['frame_id'],
                    sample['x'],
                    sample['y'],
                    sample['z'],
                    sample['vx'],
                    sample['vy'],
                    sample['vz'],
                    sample['speed'],
                    sample['wx'],
                    sample['wy'],
                    sample['wz'],
                    sample['angular_speed']
                ])

        rospy.loginfo('Motion data saved to %s', self.CSV_PATH)

    def __measure_translation(self):

        self.__nav_lock = threading.Lock()
        self.__latest_nav = None
        self.__samples = []
        self.__recording = False

        self.__subscriber_nav = rospy.Subscriber(
            '/sensor_fusion/navigation',
            Navigation,
            self.__callback_benchmark_nav,
            queue_size=100
        )

        if not self.__command.wait_for_server(rospy.Duration(10.0)):
            raise RuntimeError('Movement action server unavailable')

        start_nav = self.__wait_for_benchmark_nav()

        rospy.loginfo(
            'POINT A: x=%.4f y=%.4f z=%.4f',
            start_nav['x'],
            start_nav['y'],
            start_nav['z']
        )

        target = PoseStamped()
        target.header.stamp = rospy.Time.now()
        target.header.frame_id = 'body'

        target.pose.position.x = self.MOVE_DISTANCE
        target.pose.position.y = 0.0
        target.pose.position.z = 0.0

        target.pose.orientation.x = 0.0
        target.pose.orientation.y = 0.0
        target.pose.orientation.z = 0.0
        target.pose.orientation.w = 1.0

        command_type = CtlStatusType(
            type=CtlStatusType.MOVE_TO_RELATIVE_TARGET
        )

        goal = CtlCommandGoal(
            target=target,
            type=command_type
        )

        with self.__nav_lock:
            self.__samples = [start_nav.copy()]
            self.__recording = True

        start_sim = rospy.Time.now().to_sec()
        start_wall = time.monotonic()

        self.__action_active = True

        finished = False
        result = None
        end_sim = start_sim
        end_wall = start_wall

        try:
            self.__command.send_goal(goal)

            rospy.loginfo(
                'Moving %.3f meters along body X',
                self.MOVE_DISTANCE
            )

            finished = self.__command.wait_for_result(
                rospy.Duration(self.MOVE_TIMEOUT)
            )

            end_sim = rospy.Time.now().to_sec()
            end_wall = time.monotonic()

            if finished:
                result = self.__command.get_result()
                rospy.loginfo('Movement result: %s', result)
                time.sleep(0.15)
            else:
                rospy.logerr('Movement timed out')
                self.__command.cancel_goal()

                if not self.__command.wait_for_result(rospy.Duration(10.0)):
                    rospy.logerr('Movement cancellation not confirmed')

        finally:
            with self.__nav_lock:
                self.__recording = False
                samples = list(self.__samples)

            self.__action_active = False

        if len(samples) < 2:
            rospy.logerr('Insufficient navigation samples')
            return False

        command_elapsed_sim = end_sim - start_sim
        command_elapsed_wall = end_wall - start_wall

        moving_indices = [
            i for i, sample in enumerate(samples)
            if sample['speed'] >= self.TRANSLATION_SPEED_THRESHOLD
        ]

        if len(moving_indices) < 2:
            rospy.logerr('Insufficient translational samples')
            self.__save_motion_samples(samples)
            return False

        first_move = moving_indices[0]
        last_move = moving_indices[-1]

        translation_samples = samples[first_move:last_move + 1]

        translation_elapsed_sim = (
            translation_samples[-1]['stamp'] -
            translation_samples[0]['stamp']
        )

        translation_elapsed_wall = (
            translation_samples[-1]['received'] -
            translation_samples[0]['received']
        )

        travel_time = (
            translation_elapsed_sim
            if translation_elapsed_sim > 0.0
            else translation_elapsed_wall
        )

        if travel_time <= 0.0:
            rospy.logerr('Invalid translation duration')
            self.__save_motion_samples(samples)
            return False

        path_distance = 0.0

        for previous, current in zip(translation_samples, translation_samples[1:]):
            path_distance += math.sqrt(
                (current['x'] - previous['x'])**2 +
                (current['y'] - previous['y'])**2 +
                (current['z'] - previous['z'])**2
            )

        first = translation_samples[0]
        last = translation_samples[-1]

        displacement = math.sqrt(
            (last['x'] - first['x'])**2 +
            (last['y'] - first['y'])**2 +
            (last['z'] - first['z'])**2
        )

        average_path_speed = path_distance / travel_time
        average_displacement_speed = displacement / travel_time

        peak_speed = max(sample['speed'] for sample in translation_samples)

        self.__save_motion_samples(samples)

        rospy.loginfo('=========== DISTANCE SHIT ===========')

        rospy.loginfo('THe distance: %.4f m', self.MOVE_DISTANCE)
        rospy.loginfo('the displacement displacement: %.4f m', displacement)
        rospy.loginfo('actual path length: %.4f m', path_distance)
        rospy.loginfo('translation simulation duration: %.4f s', translation_elapsed_sim)
        rospy.loginfo('translation wall duration: %.4f s', translation_elapsed_wall)
        rospy.loginfo('total command simulation duration: %.4f s', command_elapsed_sim)
        rospy.loginfo('total command wall duration: %.4f s', command_elapsed_wall)
        rospy.loginfo('average path speed: %.4f m/s', average_path_speed)
        rospy.loginfo('average displacement speed: %.4f m/s', average_displacement_speed)
        rospy.loginfo('peak linear speed: %.4f m/s', peak_speed)
        rospy.loginfo('navigation samples: %d', len(samples))

        rospy.loginfo('====================================')

        translation_success = (
            finished and
            result is not None and
            result.type == CtlCommandResult.TERMINATE_SUCCESS
        )

        if not translation_success:
            return False

        return self.__measure_rotation_speed()

    def __measure_rotation_speed(self):

        self.__wait_for_benchmark_nav()

        with self.__nav_lock:
            self.__samples = []
            self.__recording = True

        rotation_angles = []
        for _ in range(self.ROTATION_REPETITIONS):
            rotation_angles.extend([
                self.ROTATION_ANGLE_DEGREES,
                -self.ROTATION_ANGLE_DEGREES
            ])

        results = []
        previous_completion = None

        try:
            for index, angle_degrees in enumerate(rotation_angles, 1):

                angle_radians = math.radians(angle_degrees)

                target = PoseStamped()
                target.header.stamp = rospy.Time.now()
                target.header.frame_id = 'body'

                target.pose.position.x = 0.0
                target.pose.position.y = 0.0
                target.pose.position.z = 0.0

                target.pose.orientation.x = 0.0
                target.pose.orientation.y = 0.0
                target.pose.orientation.z = math.sin(angle_radians / 2.0)
                target.pose.orientation.w = math.cos(angle_radians / 2.0)

                command_type = CtlStatusType(
                    type=CtlStatusType.MOVE_TO_RELATIVE_TARGET
                )

                goal = CtlCommandGoal(
                    target=target,
                    type=command_type
                )

                with self.__nav_lock:
                    sample_start = len(self.__samples)

                send_wall = time.monotonic()

                self.__action_active = True
                self.__command.send_goal(goal)

                rospy.loginfo(
                    'rotation %d/%d: rotated at angle=%+.1f degrees',
                    index,
                    len(rotation_angles),
                    angle_degrees
                )

                deadline = time.monotonic() + self.ROTATION_TIMEOUT
                finished = False

                while not rospy.is_shutdown():
                    remaining = deadline - time.monotonic()

                    if remaining <= 0.0:
                        break

                    if self.__command.wait_for_result(
                        rospy.Duration(min(0.05, remaining))
                    ):
                        finished = True
                        break

                if not finished:
                    self.__command.cancel_goal()
                    self.__command.wait_for_result(rospy.Duration(5.0))
                    self.__action_active = False
                    rospy.logerr('Rotation %d timed out', index)
                    return False

                result = self.__command.get_result()
                completion_wall = time.monotonic()
                self.__action_active = False

                if result is None or result.type != CtlCommandResult.TERMINATE_SUCCESS:
                    rospy.logerr('Rotation %d failed: %s', index, result)
                    return False

                with self.__nav_lock:
                    turn_samples = [
                        sample.copy()
                        for sample in self.__samples[sample_start:]
                    ]

                turn_samples = [
                    sample for sample in turn_samples
                    if sample['received'] >= send_wall
                ]

                moving_indices = [
                    i for i, sample in enumerate(turn_samples)
                    if abs(sample['wz']) >= self.ROTATION_SPEED_THRESHOLD
                ]

                if len(moving_indices) < 2:
                    rospy.logerr('Insufficient rotation samples for rotation %d', index)
                    return False

                first_move = moving_indices[0]
                last_move = moving_indices[-1]

                rotation_samples = turn_samples[first_move:last_move + 1]

                first = rotation_samples[0]
                last = rotation_samples[-1]

                duration_sim = last['stamp'] - first['stamp']
                duration_wall = last['received'] - first['received']

                rotation_time = (
                    duration_sim if duration_sim > 0.0
                    else duration_wall
                )

                if rotation_time <= 0.0:
                    rospy.logerr('Invalid rotation duration')
                    return False

                angle_rotated = 0.0

                for previous, current in zip(
                    rotation_samples,
                    rotation_samples[1:]
                ):
                    dt_sim = current['stamp'] - previous['stamp']
                    dt_wall = current['received'] - previous['received']
                    dt = dt_sim if dt_sim > 0.0 else dt_wall

                    angle_rotated += (
                        (abs(previous['wz']) + abs(current['wz'])) / 2.0
                    ) * dt

                average_angular_speed = angle_rotated / rotation_time

                peak_angular_speed = max(
                    abs(sample['wz'])
                    for sample in rotation_samples
                )

                command_latency = first['received'] - send_wall

                switch_delay = (
                    first['received'] - previous_completion
                    if previous_completion is not None
                    else None
                )

                command_gap = (
                    send_wall - previous_completion
                    if previous_completion is not None
                    else None
                )

                signed_average_wz = sum(
                    sample['wz'] for sample in rotation_samples
                ) / len(rotation_samples)

                results.append({
                    'commanded_angle': angle_degrees,
                    'actual_angle': math.degrees(angle_rotated),
                    'duration': rotation_time,
                    'average_speed': average_angular_speed,
                    'peak_speed': peak_angular_speed,
                    'command_latency': command_latency,
                    'switch_delay': switch_delay,
                    'command_gap': command_gap,
                    'signed_average_wz': signed_average_wz
                })

                previous_completion = completion_wall

        finally:
            with self.__nav_lock:
                self.__recording = False

            self.__action_active = False

        if not results:
            return False

        average_angle = sum(result['actual_angle'] for result in results) / len(results)
        average_rotation_time = sum(result['duration'] for result in results) / len(results)
        average_speed = sum(result['average_speed'] for result in results) / len(results)
        peak_speed = max(result['peak_speed'] for result in results)

        switch_delays = [
            result['switch_delay'] for result in results
            if result['switch_delay'] is not None
        ]

        rospy.loginfo('=========== ROTATION SHIT ===========')

        rospy.loginfo('completed rotations: %d', len(results))
        rospy.loginfo('average angle rotated: %.2f degrees', average_angle)
        rospy.loginfo('average rotation duration: %.4f s', average_rotation_time)
        rospy.loginfo('average angular speed: %.4f rad/s (%.2f deg/s)',
                      average_speed, math.degrees(average_speed))
        rospy.loginfo('peak angular speed: %.4f rad/s (%.2f deg/s)',
                      peak_speed, math.degrees(peak_speed))

        if switch_delays:
            rospy.loginfo('average switching delay: %.4f s',
                          sum(switch_delays) / len(switch_delays))
            rospy.loginfo('fastest switching delay: %.4f s', min(switch_delays))
            rospy.loginfo('slowest switching delay: %.4f s', max(switch_delays))

        rospy.loginfo('====================================')

        return len(results) == len(rotation_angles)

    def __measure_combined_motion(self):

        self.__nav_lock = threading.Lock()
        self.__latest_nav = None
        self.__samples = []
        self.__recording = False

        self.__subscriber_nav = rospy.Subscriber(
            '/sensor_fusion/navigation',
            Navigation,
            self.__callback_benchmark_nav,
            queue_size=100
        )

        if not self.__command.wait_for_server(rospy.Duration(10.0)):
            raise RuntimeError('Movement action server unavailable')

        start_nav = self.__wait_for_benchmark_nav()

        rospy.loginfo(
            'START POSE: x=%.4f y=%.4f z=%.4f',
            start_nav['x'],
            start_nav['y'],
            start_nav['z']
        )

        target = PoseStamped()
        target.header.stamp = rospy.Time.now()
        target.header.frame_id = 'body'

        target.pose.position.x = 2.25
        target.pose.position.y = 0.0
        target.pose.position.z = 0.0

        angle = math.radians(90.0)

        target.pose.orientation.x = 0.0
        target.pose.orientation.y = 0.0
        target.pose.orientation.z = math.sin(angle / 2.0)
        target.pose.orientation.w = math.cos(angle / 2.0)

        command_type = CtlStatusType(
            type=CtlStatusType.MOVE_TO_RELATIVE_TARGET
        )

        goal = CtlCommandGoal(
            target=target,
            type=command_type
        )

        with self.__nav_lock:
            self.__samples = [start_nav.copy()]
            self.__recording = True

        start_wall = time.monotonic()
        start_sim = rospy.Time.now().to_sec()

        self.__action_active = True

        finished = False
        result = None

        try:
            rospy.loginfo(
                'COMBINED TEST: translating 0.25 m along body X '
                'while rotating +90 degrees around body Z'
            )

            self.__command.send_goal(goal)

            finished = self.__command.wait_for_result(
                rospy.Duration(60.0)
            )

            end_wall = time.monotonic()
            end_sim = rospy.Time.now().to_sec()

            if finished:
                result = self.__command.get_result()
                rospy.loginfo('Combined movement result: %s', result)
            else:
                rospy.logerr('Combined movement timed out')
                self.__command.cancel_goal()

                if not self.__command.wait_for_result(rospy.Duration(10.0)):
                    rospy.logerr('Movement cancellation not confirmed')

            time.sleep(0.3)

        finally:
            with self.__nav_lock:
                self.__recording = False
                samples = list(self.__samples)

            self.__action_active = False

        if len(samples) < 2:
            rospy.logerr('Insufficient navigation samples')
            return False

        self.__save_motion_samples(samples)

        linear_indices = [
            i for i, sample in enumerate(samples)
            if sample['speed'] >= self.TRANSLATION_SPEED_THRESHOLD
        ]

        angular_indices = [
            i for i, sample in enumerate(samples)
            if abs(sample['wz']) >= self.ROTATION_SPEED_THRESHOLD
        ]

        if len(linear_indices) < 2:
            rospy.logerr('Insufficient translational movement detected')
            return False

        if len(angular_indices) < 2:
            rospy.logerr('Insufficient rotational movement detected')
            return False

        linear_start = samples[linear_indices[0]]['received']
        linear_end = samples[linear_indices[-1]]['received']

        angular_start = samples[angular_indices[0]]['received']
        angular_end = samples[angular_indices[-1]]['received']

        translation_duration = linear_end - linear_start
        rotation_duration = angular_end - angular_start

        overlap_start = max(linear_start, angular_start)
        overlap_end = min(linear_end, angular_end)

        overlap_duration = max(0.0, overlap_end - overlap_start)

        shorter_duration = min(
            translation_duration,
            rotation_duration
        )

        overlap_percentage = (
            overlap_duration / shorter_duration * 100.0
            if shorter_duration > 0.0
            else 0.0
        )

        command_duration = end_wall - start_wall

        path_distance = 0.0

        for previous, current in zip(samples, samples[1:]):
            path_distance += math.sqrt(
                (current['x'] - previous['x'])**2 +
                (current['y'] - previous['y'])**2 +
                (current['z'] - previous['z'])**2
            )

        angular_distance = 0.0

        for previous, current in zip(samples, samples[1:]):
            dt = current['received'] - previous['received']

            angular_distance += (
                (abs(previous['wz']) + abs(current['wz'])) / 2.0
            ) * dt

        angular_distance_degrees = math.degrees(angular_distance)

        rospy.loginfo('========== CONCURRENT MOMOVEMENT TEST ==========')
        rospy.loginfo('Command duration: %.3f seconds', command_duration)
        rospy.loginfo('Simulation duration: %.3f seconds', end_sim - start_sim)
        rospy.loginfo('Measured translation duration: %.3f seconds', translation_duration)
        rospy.loginfo('Measured rotation duration: %.3f seconds', rotation_duration)
        rospy.loginfo('Measured path distance: %.4f meters', path_distance)
        rospy.loginfo('Measured rotation: %.2f degrees', angular_distance_degrees)
        rospy.loginfo('Translation started: %.3f seconds after command', linear_start - start_wall)
        rospy.loginfo('Rotation started: %.3f seconds after command', angular_start - start_wall)
        rospy.loginfo('Translation ended: %.3f seconds after command', linear_end - start_wall)
        rospy.loginfo('Rotation ended: %.3f seconds after command', angular_end - start_wall)
        rospy.loginfo('OVERLAP DURATION: %.3f seconds', overlap_duration)
        rospy.loginfo('OVERLAP OF SHORTER MOVEMENT: %.1f%%', overlap_percentage)
        rospy.loginfo('==========================================')

        success = (
            finished and
            result is not None and
            result.type == CtlCommandResult.TERMINATE_SUCCESS
        )

        if overlap_duration > 0.1:
            rospy.loginfo('RESULT: Translation and rotation overlapped.')
        else:
            rospy.logwarn('RESULT: No significant translation/rotation overlap detected.')

        return success
        #=============== END OF MY ADDITIONS :3 ======================

#========================== EXPERIMENTAL SHIT ====================================
    @staticmethod
    def quaternion_multiply(q1, q2):
        x1, y1, z1, w1 = q1
        x2, y2, z2, w2 = q2

        return (
            w1*x2 + x1*w2 + y1*z2 - z1*y2,
            w1*y2 - x1*z2 + y1*w2 + z1*x2,
            w1*z2 + x1*y2 - y1*x2 + z1*w2,
            w1*w2 - x1*x2 - y1*y2 - z1*z2
        )

    @staticmethod
    def rotate_vector(q, v):
        q_inv = (-q[0], -q[1], -q[2], q[3])
        vq = (v[0], v[1], v[2], 0.0)

        result = UserTemplate.quaternion_multiply(
            UserTemplate.quaternion_multiply(q, vq),
            q_inv
        )

        return result[:3]

    @staticmethod
    def clamp_vector(v, maximum):
        magnitude = math.sqrt(sum(x*x for x in v))

        if magnitude > maximum:
            scale = maximum / magnitude
            return tuple(x * scale for x in v)

        return v

    def move_and_rotate(
        self,
        current_position,
        current_orientation,
        linear_velocity,
        angular_velocity,
        target_position,
        target_orientation
    ):
        kp_position = 0.08
        kd_position = 0.15

        kp_rotation = 0.04
        kd_rotation = 0.08

        max_force = 0.1
        max_torque = 0.01

        q = current_orientation

        position_error = tuple(
            target_position[i] - current_position[i]
            for i in range(3)
        )

        position_error_body = self.rotate_vector(
            (-q[0], -q[1], -q[2], q[3]),
            position_error
        )

        force = tuple(
            kp_position * position_error_body[i]
            - kd_position * linear_velocity[i]
            for i in range(3)
        )

        q_error = self.quaternion_multiply(
            (-q[0], -q[1], -q[2], q[3]),
            target_orientation
        )

        if q_error[3] < 0:
            q_error = tuple(-x for x in q_error)

        angle = 2.0 * math.acos(
            max(-1.0, min(1.0, q_error[3]))
        )

        sin_half = math.sqrt(
            max(0.0, 1.0 - q_error[3]**2)
        )

        if sin_half > 1e-6:
            rotation_error = tuple(
                q_error[i] / sin_half * angle
                for i in range(3)
            )
        else:
            rotation_error = (0.0, 0.0, 0.0)

        torque = tuple(
            kp_rotation * rotation_error[i]
            - kd_rotation * angular_velocity[i]
            for i in range(3)
        )

        force = self.clamp_vector(force, max_force)
        torque = self.clamp_vector(torque, max_torque)

        msg = WrenchStamped()
        msg.header.stamp = rospy.Time.now()
        msg.header.frame_id = "body"

        msg.wrench.force.x = force[0]
        msg.wrench.force.y = force[1]
        msg.wrench.force.z = force[2]

        msg.wrench.torque.x = torque[0]
        msg.wrench.torque.y = torque[1]
        msg.wrench.torque.z = torque[2]

        self.__wrench_pub.publish(msg)

    def move_and_rotate(self, nav, target_position, target_orientation):
        kp_position = 0.08
        kd_position = 0.15
        kp_rotation = 0.04
        kd_rotation = 0.08

        max_force = 0.1
        max_torque = 0.01

        q = (
            nav.pose.pose.orientation.x,
            nav.pose.pose.orientation.y,
            nav.pose.pose.orientation.z,
            nav.pose.pose.orientation.w
        )

        position = (
            nav.pose.pose.position.x,
            nav.pose.pose.position.y,
            nav.pose.pose.position.z
        )

        velocity = (
            nav.twist.linear.x,
            nav.twist.linear.y,
            nav.twist.linear.z
        )

        angular_velocity = (
            nav.twist.angular.x,
            nav.twist.angular.y,
            nav.twist.angular.z
        )

        # Translation
        position_error = tuple(
            target_position[i] - position[i] for i in range(3)
        )

        position_error_body = self.rotate_vector(
            (-q[0], -q[1], -q[2], q[3]),
            position_error
        )

        force = tuple(
            kp_position * position_error_body[i]
            - kd_position * velocity[i]
            for i in range(3)
        )

        force = self.clamp_vector(force, max_force)

        # Rotation
        q_error = self.quaternion_multiply(
            (-q[0], -q[1], -q[2], q[3]),
            target_orientation
        )

        if q_error[3] < 0:
            q_error = tuple(-v for v in q_error)

        angle = 2.0 * math.atan2(
            math.sqrt(q_error[0]**2 + q_error[1]**2 + q_error[2]**2),
            q_error[3]
        )

        magnitude = math.sqrt(
            q_error[0]**2 + q_error[1]**2 + q_error[2]**2
        )

        if magnitude > 1e-6:
            rotation_error = tuple(
                q_error[i] / magnitude * angle for i in range(3)
            )
        else:
            rotation_error = (0.0, 0.0, 0.0)

        torque = tuple(
            kp_rotation * rotation_error[i]
            - kd_rotation * angular_velocity[i]
            for i in range(3)
        )

        torque = self.clamp_vector(torque, max_torque)

        # Publish both simultaneously
        wrench = WrenchStamped()
        wrench.header.stamp = rospy.Time.now()
        wrench.header.frame_id = "body"

        wrench.wrench.force.x = force[0]
        wrench.wrench.force.y = force[1]
        wrench.wrench.force.z = force[2]

        wrench.wrench.torque.x = torque[0]
        wrench.wrench.torque.y = torque[1]
        wrench.wrench.torque.z = torque[2]

        self.__force_and_torque_publisher.publish(wrench)

    def __stop_wrench(self):
        msg = WrenchStamped()
        msg.header.frame_id = "body"

        for _ in range(3):
            msg.header.stamp = rospy.Time.now()
            self.__wrench_pub.publish(msg)
            rospy.sleep(0.05)
#=========================================================

    def __run_user_flow(self, msg):
        try:
            self.wrench_pub = rospy.Publisher(
            '/ctl/wrench',
            WrenchStamped,
            queue_size=1)

            wrench = WrenchStamped()
            wrench.header.stamp = rospy.Time.now()
            wrench.header.frame_id = "body"
    

            self.wrench_pub.publish(wrench)
        except Exception as exc:
            rospy.logerr('user flow failed: %s', exc)


    def __callback_start(self, msg):
        if self.__started:
            rospy.logwarn('start callback is already processed')
            return
        self.__started = True

        rospy.loginfo('start %s', msg)
        self.__run_user_flow(msg)

    # Optional subscriber callback examples.
    # def __callback_nav(self, data):
    #     position = data.pose.pose.positionm
    #     orientation = data.pose.pose.orientation
    #     rospy.loginfo('current pose: x=%.3f y=%.3f z=%.3f qx=%.4f qy=%.4f qz=%.4f qw=%.4f',
    #                   position.x, position.y, position.z,m
    #                   orientation.x, orientation.y, orientation.z, orientation.w)
    #
    # def __callback_camera_image(self, data):
    #     rospy.loginfo('camera image: width=%d height=%d encoding=%s',
    #                   data.width, data.height, data.encoding)

    def __stop_processing(self, request):
        try:
            self.__stop_requested.set()

            if self.__action_active:
                self.__command.cancel_goal()

            if self.__controller_active:
                self.__stop_wrench()

            rospy.loginfo('finish processing')
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.SUCCESS)

        except Exception as exc:
            rospy.logerr('stop processing failed: %s', exc)
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.ERROR)

    def run(self):
        rospy.spin()


if __name__ == '__main__':
    UserTemplate().run()
