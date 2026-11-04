
(cl:in-package :asdf)

(defsystem "krpc_ib2_msgs-msg"
  :depends-on (:roslisp-msg-protocol :roslisp-utils :actionlib_msgs-msg
               :std_msgs-msg
)
  :components ((:file "_package")
    (:file "CheckpointPassedAction" :depends-on ("_package_CheckpointPassedAction"))
    (:file "_package_CheckpointPassedAction" :depends-on ("_package"))
    (:file "CheckpointPassedActionFeedback" :depends-on ("_package_CheckpointPassedActionFeedback"))
    (:file "_package_CheckpointPassedActionFeedback" :depends-on ("_package"))
    (:file "CheckpointPassedActionGoal" :depends-on ("_package_CheckpointPassedActionGoal"))
    (:file "_package_CheckpointPassedActionGoal" :depends-on ("_package"))
    (:file "CheckpointPassedActionResult" :depends-on ("_package_CheckpointPassedActionResult"))
    (:file "_package_CheckpointPassedActionResult" :depends-on ("_package"))
    (:file "CheckpointPassedFeedback" :depends-on ("_package_CheckpointPassedFeedback"))
    (:file "_package_CheckpointPassedFeedback" :depends-on ("_package"))
    (:file "CheckpointPassedGoal" :depends-on ("_package_CheckpointPassedGoal"))
    (:file "_package_CheckpointPassedGoal" :depends-on ("_package"))
    (:file "CheckpointPassedResult" :depends-on ("_package_CheckpointPassedResult"))
    (:file "_package_CheckpointPassedResult" :depends-on ("_package"))
    (:file "GsData" :depends-on ("_package_GsData"))
    (:file "_package_GsData" :depends-on ("_package"))
  ))