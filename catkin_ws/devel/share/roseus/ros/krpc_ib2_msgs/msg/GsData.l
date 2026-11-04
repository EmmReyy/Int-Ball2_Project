;; Auto-generated. Do not edit!


(when (boundp 'krpc_ib2_msgs::GsData)
  (if (not (find-package "KRPC_IB2_MSGS"))
    (make-package "KRPC_IB2_MSGS"))
  (shadow 'GsData (find-package "KRPC_IB2_MSGS")))
(unless (find-package "KRPC_IB2_MSGS::GSDATA")
  (make-package "KRPC_IB2_MSGS::GSDATA"))

(in-package "ROS")
;;//! \htmlinclude GsData.msg.html


(defclass krpc_ib2_msgs::GsData
  :super ros::object
  :slots (_data ))

(defmethod krpc_ib2_msgs::GsData
  (:init
   (&key
    ((:data __data) "")
    )
   (send-super :init)
   (setq _data (string __data))
   self)
  (:data
   (&optional __data)
   (if __data (setq _data __data)) _data)
  (:serialization-length
   ()
   (+
    ;; string _data
    4 (length _data)
    ))
  (:serialize
   (&optional strm)
   (let ((s (if strm strm
              (make-string-output-stream (send self :serialization-length)))))
     ;; string _data
       (write-long (length _data) s) (princ _data s)
     ;;
     (if (null strm) (get-output-stream-string s))))
  (:deserialize
   (buf &optional (ptr- 0))
   ;; string _data
     (let (n) (setq n (sys::peek buf ptr- :integer)) (incf ptr- 4) (setq _data (subseq buf ptr- (+ ptr- n))) (incf ptr- n))
   ;;
   self)
  )

(setf (get krpc_ib2_msgs::GsData :md5sum-) "992ce8a1687cec8c8bd883ec73ca41d1")
(setf (get krpc_ib2_msgs::GsData :datatype-) "krpc_ib2_msgs/GsData")
(setf (get krpc_ib2_msgs::GsData :definition-)
      "string data

")



(provide :krpc_ib2_msgs/GsData "992ce8a1687cec8c8bd883ec73ca41d1")


