;; Auto-generated. Do not edit!


(when (boundp 'krpc_ib2_msgs::MissionStart)
  (if (not (find-package "KRPC_IB2_MSGS"))
    (make-package "KRPC_IB2_MSGS"))
  (shadow 'MissionStart (find-package "KRPC_IB2_MSGS")))
(unless (find-package "KRPC_IB2_MSGS::MISSIONSTART")
  (make-package "KRPC_IB2_MSGS::MISSIONSTART"))
(unless (find-package "KRPC_IB2_MSGS::MISSIONSTARTREQUEST")
  (make-package "KRPC_IB2_MSGS::MISSIONSTARTREQUEST"))
(unless (find-package "KRPC_IB2_MSGS::MISSIONSTARTRESPONSE")
  (make-package "KRPC_IB2_MSGS::MISSIONSTARTRESPONSE"))

(in-package "ROS")





(defclass krpc_ib2_msgs::MissionStartRequest
  :super ros::object
  :slots ())

(defmethod krpc_ib2_msgs::MissionStartRequest
  (:init
   (&key
    )
   (send-super :init)
   self)
  (:serialization-length
   ()
   (+
    0
    ))
  (:serialize
   (&optional strm)
   (let ((s (if strm strm
              (make-string-output-stream (send self :serialization-length)))))
     ;;
     (if (null strm) (get-output-stream-string s))))
  (:deserialize
   (buf &optional (ptr- 0))
   ;;
   self)
  )

(defclass krpc_ib2_msgs::MissionStartResponse
  :super ros::object
  :slots (_success _message ))

(defmethod krpc_ib2_msgs::MissionStartResponse
  (:init
   (&key
    ((:success __success) nil)
    ((:message __message) "")
    )
   (send-super :init)
   (setq _success __success)
   (setq _message (string __message))
   self)
  (:success
   (&optional __success)
   (if __success (setq _success __success)) _success)
  (:message
   (&optional __message)
   (if __message (setq _message __message)) _message)
  (:serialization-length
   ()
   (+
    ;; bool _success
    1
    ;; string _message
    4 (length _message)
    ))
  (:serialize
   (&optional strm)
   (let ((s (if strm strm
              (make-string-output-stream (send self :serialization-length)))))
     ;; bool _success
       (if _success (write-byte -1 s) (write-byte 0 s))
     ;; string _message
       (write-long (length _message) s) (princ _message s)
     ;;
     (if (null strm) (get-output-stream-string s))))
  (:deserialize
   (buf &optional (ptr- 0))
   ;; bool _success
     (setq _success (not (= 0 (sys::peek buf ptr- :char)))) (incf ptr- 1)
   ;; string _message
     (let (n) (setq n (sys::peek buf ptr- :integer)) (incf ptr- 4) (setq _message (subseq buf ptr- (+ ptr- n))) (incf ptr- n))
   ;;
   self)
  )

(defclass krpc_ib2_msgs::MissionStart
  :super ros::object
  :slots ())

(setf (get krpc_ib2_msgs::MissionStart :md5sum-) "937c9679a518e3a18d831e57125ea522")
(setf (get krpc_ib2_msgs::MissionStart :datatype-) "krpc_ib2_msgs/MissionStart")
(setf (get krpc_ib2_msgs::MissionStart :request) krpc_ib2_msgs::MissionStartRequest)
(setf (get krpc_ib2_msgs::MissionStart :response) krpc_ib2_msgs::MissionStartResponse)

(defmethod krpc_ib2_msgs::MissionStartRequest
  (:response () (instance krpc_ib2_msgs::MissionStartResponse :init)))

(setf (get krpc_ib2_msgs::MissionStartRequest :md5sum-) "937c9679a518e3a18d831e57125ea522")
(setf (get krpc_ib2_msgs::MissionStartRequest :datatype-) "krpc_ib2_msgs/MissionStartRequest")
(setf (get krpc_ib2_msgs::MissionStartRequest :definition-)
      "---
# Response
bool success
string message

")

(setf (get krpc_ib2_msgs::MissionStartResponse :md5sum-) "937c9679a518e3a18d831e57125ea522")
(setf (get krpc_ib2_msgs::MissionStartResponse :datatype-) "krpc_ib2_msgs/MissionStartResponse")
(setf (get krpc_ib2_msgs::MissionStartResponse :definition-)
      "---
# Response
bool success
string message

")



(provide :krpc_ib2_msgs/MissionStart "937c9679a518e3a18d831e57125ea522")


