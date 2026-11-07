#!/usr/bin/python3
# -*- coding:utf-8 -*-
import json
import math
import itertools
import rospy
import actionlib
from geometry_msgs.msg import WrenchStamped
from platform_msgs.msg import UserLogic
from platform_msgs.srv import StopProcessingUserNode, StopProcessingUserNodeResponse
from geometry_msgs.msg import PoseStamped
from krpc_ib2_msgs.srv import MissionStart, MissionFinished, CheckPoints
from krpc_ib2_msgs.msg import CheckpointPassedAction, CheckpointPassedGoal
from ib2_msgs.msg import CtlCommandAction, CtlCommandGoal, CtlCommandResult, CtlStatusType


class UserTemplate:

    def __init__(self):
        rospy.init_node('krpc_user')
        self.wrench_pub = rospy.Publisher('/ctl/wrench', WrenchStamped, queue_size=1)

        self.rate = rospy.Rate(20)
        self.__command = actionlib.SimpleActionClient('/ctl/command', CtlCommandAction)
        self.__checkpoint_client = actionlib.SimpleActionClient('/event/checkpoint_passed', CheckpointPassedAction)

        self.__mission_start = rospy.ServiceProxy('/event/mission_start', MissionStart)
        self.__mission_finished = rospy.ServiceProxy('/event/mission_finished', MissionFinished)
        self.__checkpoints = rospy.ServiceProxy('/mission/get_checkpoints', CheckPoints)

        self.current_position = None
        self.current_orientation = None
        self.navigation_sub = rospy.Subscriber('/sensor_fusion/navigation',Navigation,self.__nav_callback,queue_size=1)

        self.__subscriber_start = rospy.Subscriber('/ib2_user/start', UserLogic, self.__callback_start)

        self.__stop_processing_server = rospy.Service('/ib2_user/stop', StopProcessingUserNode, self.__stop_processing)

        self.__started = False
        self.__action_active = False
        rospy.set_param('/ib2_user/ready', True)

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

    def __get_checkpoint_targets(self):
        targets = []
        default_target = {
            'checkpoint_id': 1,
            'position': [0.0, 0.0, 0.0],
            'quaternion': [0.0, 0.0, 0.0, 1.0],
        }
        rospy.wait_for_service('/mission/get_checkpoints')
        res = self.__checkpoints()
        rospy.loginfo('get_checkpoints result: success=%s message=%s', res.success, res.message)
        if not res.success:
            return []

        try:
            payload = json.loads(res.message)
            checkpoints = payload.get('checkpoints', payload.get('Checkpoints', []))
            goalpoint_id = payload.get('goalpoint_id')
            checkpoints = [cp for cp in checkpoints if isinstance(cp, dict) and self.__get_checkpoint_id(cp) is not None]
            if not checkpoints:
                rospy.logwarn('No checkpoints found in payload')
                return []

            for checkpoint in checkpoints:
                position = checkpoint.get('position', default_target['position'])

                if not (isinstance(position, list) and len(position) >= 3):
                    rospy.logwarn('Invalid checkpoint position format')
                    return []

                quaternion = [0.0, 0.0, 0.0, 1.0]
                attitude = checkpoint.get('attitude')

                if isinstance(attitude, dict):
                    attitude_quaternion = attitude.get('quaternion')
                    if isinstance(attitude_quaternion, list) and len(attitude_quaternion) >= 4:
                        quaternion = attitude_quaternion

                target = {
                    'checkpoint_id': self.__get_checkpoint_id(checkpoint),
                    'position': [float(position[0]), float(position[1]), float(position[2])],
                    'quaternion': [float(quaternion[0]), float(quaternion[1]), float(quaternion[2]), float(quaternion[3])],
                }
                targets.append(target)
            return targets

        except Exception as e:
            rospy.logwarn('Failed to parse checkpoints payload: %s', e)
            return []

    def __determine_distance(self, first, second):

        first = first['position']
        second = second['position']

        distance = math.sqrt(
            (second[0] - first[0])**2 +
            (second[1] - first[1])**2 +
            (second[2] - first[2])**2
        )

        return distance
    
    def __nav_callback(self, msg):
        self.current_orientation = msg.pose.pose.orientation
        self.current_position = msg.pose.pose.position

#==================================EXPERIMENTAL============================================

    #the values too sensitive, calibrate further, kysw
    p_term_pos = 0.1
    d_term_pos = 0.1

    p_term_rot = 0.1
    d_term_rot = 0.1


    def __wrench_it(self, fx, fy, fz, tx, ty, tz):
        wrench = WrenchStamped()

        wrench.header.stamp = rospy.Time.now()
        wrench.header.frame_id = "body"

        wrench.wrench.force.x = fx
        wrench.wrench.force.y = fy
        wrench.wrench.force.z = fz

        wrench.wrench.torque.x = tx
        wrench.wrench.torque.y = ty
        wrench.wrench.torque.z = tz

        self.wrench_pub.publish(wrench)

    def __calcluate_error_pos(self, target):

        target_pos = target["position"]
        error_pos = []

        error_pos.append((target_pos[0] - self.current_position.x))
        error_pos.append((target_pos[1] - self.current_position.y))
        error_pos.append((target_pos[2] - self.current_position.z))
                
        return 0

    def __calculate_error_rot(self, target):

        marker_orient = target["marker_pose"]["quaternion"]

        dot_prod = (self.current_orientation.x * marker_orient[0]) + (self.current_orientation.y * marker_orient[1]) + (self.current_orientation.x * marker_orient[2])  + (self.current_orientation.x * marker_orient[3]) 

        if dot_prod < 0:
            marker_orient = [-a for a in marker_orient]

        inverted_current_orient = [-marker_orient[0], -marker_orient[1], -marker_orient[2]]

        err = (self.current_orientation.x * marker_orient[3]) - (self.current_orientation.x * marker_orient[2]) - (self.current_orientation.x * marker_orient[1]) + (self.current_orientation.x * marker_orient[0])

        return err
        

    #def __move_to_checkpoint_faster(self, checkpoint_target, marker_orientation):



#==========================================================================================

    def __held_karp_approach(self, distances):

        best_order = []
        n_distances = len(distances)
        random_big_ahh_num = 9999999.0

        if n_distances == 0:
            return []

        states = [[random_big_ahh_num] * n_distances for _ in range(1 << n_distances)]
        saved_states = [[-1] * n_distances for _ in range(1 << n_distances)]

        states[1][0] = 0.0

        for state in range(1 << n_distances):

            if not (state & 1):
                continue

            for last in range(n_distances):

                if not (state & (1 << last)):
                    continue

                if states[state][last] == random_big_ahh_num:
                    continue

                for next_target in range(n_distances):

                    if state & (1 << next_target):
                        continue

                    new_state = state | (1 << next_target)
                    new_cost = states[state][last] + distances[last][next_target]

                    if new_cost < states[new_state][next_target]:

                        states[new_state][next_target] = new_cost
                        saved_states[new_state][next_target] = last

        complete_state = (1 << n_distances) - 1

        best_cost = random_big_ahh_num
        best_last = -1

        if n_distances == 1:
            return 0.0, [0]

        for last in range(1, n_distances):

            total_cost = states[complete_state][last] + distances[last][0]

            if total_cost < best_cost:
                best_cost = total_cost
                best_last = last

        if best_last == -1:
            return []

        mask = complete_state
        last = best_last

        while last != 0:

            best_order.append(last)

            previous = saved_states[mask][last]

            mask ^= (1 << last)
            last = previous

        best_order.append(0)

        best_order.reverse()

        return best_order

    def __determine_route(self):
        targets = self.__get_checkpoint_targets()
        n_targets = len(targets)
        ordered_targets = []

        distances = [[0.0] * n_targets for _ in range(n_targets)]

        for i in range(n_targets):
            for j in range(i+1, n_targets):
                d = self.__determine_distance(targets[i], targets[j])
                distances[i][j] = d
                distances[j][i] = d
        n_distances = len(distances)

        best_order = self.__held_karp_approach(distances)

        if not best_order:
            return []

        ordered_targets = [targets[i] for i in best_order]

        return ordered_targets

    def __run_user_flow(self, msg):
        try:
            if not self.__notify_mission_start():
                return

            route = self.__determine_route()

            if not route:
                rospy.logerr("Route generation failed")
                return

            for checkpoint_target in route:
                if not self.__move_to_checkpoint(checkpoint_target):
                    return
                if not self.__notify_checkpoint_passed(checkpoint_target['checkpoint_id']):
                    return

            if not rospy.is_shutdown():
                self.__notify_mission_finished()
        except Exception as exc:
            rospy.logerr('user flow failed: %s', exc)

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
            rospy.loginfo('finish processing')
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.SUCCESS)
        except Exception as exc:
            rospy.logerr('stop processing failed: %s', exc)
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.ERROR)

    def run(self):
        rospy.spin()


if __name__ == '__main__':
    UserTemplate().run()
