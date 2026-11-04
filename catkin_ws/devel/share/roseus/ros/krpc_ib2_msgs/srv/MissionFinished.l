;; Auto-generated. Do not edit!


(when (boundp 'krpc_ib2_msgs::MissionFinished)
  (if (not (find-package "KRPC_IB2_MSGS"))
    (make-package "KRPC_IB2_MSGS"))
  (shadow 'MissionFinished (find-package "KRPC_IB2_MSGS")))
(unless (find-package "KRPC_IB2_MSGS::MISSIONFINISHED")
  (make-package "KRPC_IB2_MSGS::MISSIONFINISHED"))
(unless (find-package "KRPC_IB2_MSGS::MISSIONFINISHEDREQUEST")
  (make-package "KRPC_IB2_MSGS::MISSIONFINISHEDREQUEST"))
(unless (find-package "KRPC_IB2_MSGS::MISSIONFINISHEDRESPONSE")
  (make-package "KRPC_IB2_MSGS::MISSIONFINISHEDRESPONSE"))

(in-package "ROS")





(defclass krpc_ib2_msgs::MissionFinishedRequest
  :super ros::object
  :slots ())

(defmethod krpc_ib2_msgs::MissionFinishedRequest
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

(defclass krpc_ib2_msgs::MissionFinishedResponse
  :super ros::object
  :slots (_success _message ))

(defmethod krpc_ib2_msgs::MissionFinishedResponse
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

(defclass krpc_ib2_msgs::MissionFinished
  :super ros::object
  :slots ())

(setf (get krpc_ib2_msgs::MissionFinished :md5sum-) "937c9679a518e3a18d831e57125ea522")
(setf (get krpc_ib2_msgs::MissionFinished :datatype-) "krpc_ib2_msgs/MissionFinished")
(setf (get krpc_ib2_msgs::MissionFinished :request) krpc_ib2_msgs::MissionFinishedRequest)
(setf (get krpc_ib2_msgs::MissionFinished :response) krpc_ib2_msgs::MissionFinishedResponse)

(defmethod krpc_ib2_msgs::MissionFinishedRequest
  (:response () (instance krpc_ib2_msgs::MissionFinishedResponse :init)))

(setf (get krpc_ib2_msgs::MissionFinishedRequest :md5sum-) "937c9679a518e3a18d831e57125ea522")
(setf (get krpc_ib2_msgs::MissionFinishedRequest :datatype-) "krpc_ib2_msgs/MissionFinishedRequest")
(setf (get krpc_ib2_msgs::MissionFinishedRequest :definition-)
      "# Empty request

---
# Response
bool success
string message

")

(setf (get krpc_ib2_msgs::MissionFinishedResponse :md5sum-) "937c9679a518e3a18d831e57125ea522")
(setf (get krpc_ib2_msgs::MissionFinishedResponse :datatype-) "krpc_ib2_msgs/MissionFinishedResponse")
(setf (get krpc_ib2_msgs::MissionFinishedResponse :definition-)
      "# Empty request

---
# Response
bool success
string message

")



(provide :krpc_ib2_msgs/MissionFinished "937c9679a518e3a18d831e57125ea522")


