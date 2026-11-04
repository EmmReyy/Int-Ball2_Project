; Auto-generated. Do not edit!


(cl:in-package krpc_ib2_msgs-srv)


;//! \htmlinclude MissionFinished-request.msg.html

(cl:defclass <MissionFinished-request> (roslisp-msg-protocol:ros-message)
  ()
)

(cl:defclass MissionFinished-request (<MissionFinished-request>)
  ())

(cl:defmethod cl:initialize-instance :after ((m <MissionFinished-request>) cl:&rest args)
  (cl:declare (cl:ignorable args))
  (cl:unless (cl:typep m 'MissionFinished-request)
    (roslisp-msg-protocol:msg-deprecation-warning "using old message class name krpc_ib2_msgs-srv:<MissionFinished-request> is deprecated: use krpc_ib2_msgs-srv:MissionFinished-request instead.")))
(cl:defmethod roslisp-msg-protocol:serialize ((msg <MissionFinished-request>) ostream)
  "Serializes a message object of type '<MissionFinished-request>"
)
(cl:defmethod roslisp-msg-protocol:deserialize ((msg <MissionFinished-request>) istream)
  "Deserializes a message object of type '<MissionFinished-request>"
  msg
)
(cl:defmethod roslisp-msg-protocol:ros-datatype ((msg (cl:eql '<MissionFinished-request>)))
  "Returns string type for a service object of type '<MissionFinished-request>"
  "krpc_ib2_msgs/MissionFinishedRequest")
(cl:defmethod roslisp-msg-protocol:ros-datatype ((msg (cl:eql 'MissionFinished-request)))
  "Returns string type for a service object of type 'MissionFinished-request"
  "krpc_ib2_msgs/MissionFinishedRequest")
(cl:defmethod roslisp-msg-protocol:md5sum ((type (cl:eql '<MissionFinished-request>)))
  "Returns md5sum for a message object of type '<MissionFinished-request>"
  "937c9679a518e3a18d831e57125ea522")
(cl:defmethod roslisp-msg-protocol:md5sum ((type (cl:eql 'MissionFinished-request)))
  "Returns md5sum for a message object of type 'MissionFinished-request"
  "937c9679a518e3a18d831e57125ea522")
(cl:defmethod roslisp-msg-protocol:message-definition ((type (cl:eql '<MissionFinished-request>)))
  "Returns full string definition for message of type '<MissionFinished-request>"
  (cl:format cl:nil "# Empty request~%~%~%~%"))
(cl:defmethod roslisp-msg-protocol:message-definition ((type (cl:eql 'MissionFinished-request)))
  "Returns full string definition for message of type 'MissionFinished-request"
  (cl:format cl:nil "# Empty request~%~%~%~%"))
(cl:defmethod roslisp-msg-protocol:serialization-length ((msg <MissionFinished-request>))
  (cl:+ 0
))
(cl:defmethod roslisp-msg-protocol:ros-message-to-list ((msg <MissionFinished-request>))
  "Converts a ROS message object to a list"
  (cl:list 'MissionFinished-request
))
;//! \htmlinclude MissionFinished-response.msg.html

(cl:defclass <MissionFinished-response> (roslisp-msg-protocol:ros-message)
  ((success
    :reader success
    :initarg :success
    :type cl:boolean
    :initform cl:nil)
   (message
    :reader message
    :initarg :message
    :type cl:string
    :initform ""))
)

(cl:defclass MissionFinished-response (<MissionFinished-response>)
  ())

(cl:defmethod cl:initialize-instance :after ((m <MissionFinished-response>) cl:&rest args)
  (cl:declare (cl:ignorable args))
  (cl:unless (cl:typep m 'MissionFinished-response)
    (roslisp-msg-protocol:msg-deprecation-warning "using old message class name krpc_ib2_msgs-srv:<MissionFinished-response> is deprecated: use krpc_ib2_msgs-srv:MissionFinished-response instead.")))

(cl:ensure-generic-function 'success-val :lambda-list '(m))
(cl:defmethod success-val ((m <MissionFinished-response>))
  (roslisp-msg-protocol:msg-deprecation-warning "Using old-style slot reader krpc_ib2_msgs-srv:success-val is deprecated.  Use krpc_ib2_msgs-srv:success instead.")
  (success m))

(cl:ensure-generic-function 'message-val :lambda-list '(m))
(cl:defmethod message-val ((m <MissionFinished-response>))
  (roslisp-msg-protocol:msg-deprecation-warning "Using old-style slot reader krpc_ib2_msgs-srv:message-val is deprecated.  Use krpc_ib2_msgs-srv:message instead.")
  (message m))
(cl:defmethod roslisp-msg-protocol:serialize ((msg <MissionFinished-response>) ostream)
  "Serializes a message object of type '<MissionFinished-response>"
  (cl:write-byte (cl:ldb (cl:byte 8 0) (cl:if (cl:slot-value msg 'success) 1 0)) ostream)
  (cl:let ((__ros_str_len (cl:length (cl:slot-value msg 'message))))
    (cl:write-byte (cl:ldb (cl:byte 8 0) __ros_str_len) ostream)
    (cl:write-byte (cl:ldb (cl:byte 8 8) __ros_str_len) ostream)
    (cl:write-byte (cl:ldb (cl:byte 8 16) __ros_str_len) ostream)
    (cl:write-byte (cl:ldb (cl:byte 8 24) __ros_str_len) ostream))
  (cl:map cl:nil #'(cl:lambda (c) (cl:write-byte (cl:char-code c) ostream)) (cl:slot-value msg 'message))
)
(cl:defmethod roslisp-msg-protocol:deserialize ((msg <MissionFinished-response>) istream)
  "Deserializes a message object of type '<MissionFinished-response>"
    (cl:setf (cl:slot-value msg 'success) (cl:not (cl:zerop (cl:read-byte istream))))
    (cl:let ((__ros_str_len 0))
      (cl:setf (cl:ldb (cl:byte 8 0) __ros_str_len) (cl:read-byte istream))
      (cl:setf (cl:ldb (cl:byte 8 8) __ros_str_len) (cl:read-byte istream))
      (cl:setf (cl:ldb (cl:byte 8 16) __ros_str_len) (cl:read-byte istream))
      (cl:setf (cl:ldb (cl:byte 8 24) __ros_str_len) (cl:read-byte istream))
      (cl:setf (cl:slot-value msg 'message) (cl:make-string __ros_str_len))
      (cl:dotimes (__ros_str_idx __ros_str_len msg)
        (cl:setf (cl:char (cl:slot-value msg 'message) __ros_str_idx) (cl:code-char (cl:read-byte istream)))))
  msg
)
(cl:defmethod roslisp-msg-protocol:ros-datatype ((msg (cl:eql '<MissionFinished-response>)))
  "Returns string type for a service object of type '<MissionFinished-response>"
  "krpc_ib2_msgs/MissionFinishedResponse")
(cl:defmethod roslisp-msg-protocol:ros-datatype ((msg (cl:eql 'MissionFinished-response)))
  "Returns string type for a service object of type 'MissionFinished-response"
  "krpc_ib2_msgs/MissionFinishedResponse")
(cl:defmethod roslisp-msg-protocol:md5sum ((type (cl:eql '<MissionFinished-response>)))
  "Returns md5sum for a message object of type '<MissionFinished-response>"
  "937c9679a518e3a18d831e57125ea522")
(cl:defmethod roslisp-msg-protocol:md5sum ((type (cl:eql 'MissionFinished-response)))
  "Returns md5sum for a message object of type 'MissionFinished-response"
  "937c9679a518e3a18d831e57125ea522")
(cl:defmethod roslisp-msg-protocol:message-definition ((type (cl:eql '<MissionFinished-response>)))
  "Returns full string definition for message of type '<MissionFinished-response>"
  (cl:format cl:nil "# Response~%bool success~%string message~%~%~%~%"))
(cl:defmethod roslisp-msg-protocol:message-definition ((type (cl:eql 'MissionFinished-response)))
  "Returns full string definition for message of type 'MissionFinished-response"
  (cl:format cl:nil "# Response~%bool success~%string message~%~%~%~%"))
(cl:defmethod roslisp-msg-protocol:serialization-length ((msg <MissionFinished-response>))
  (cl:+ 0
     1
     4 (cl:length (cl:slot-value msg 'message))
))
(cl:defmethod roslisp-msg-protocol:ros-message-to-list ((msg <MissionFinished-response>))
  "Converts a ROS message object to a list"
  (cl:list 'MissionFinished-response
    (cl:cons ':success (success msg))
    (cl:cons ':message (message msg))
))
(cl:defmethod roslisp-msg-protocol:service-request-type ((msg (cl:eql 'MissionFinished)))
  'MissionFinished-request)
(cl:defmethod roslisp-msg-protocol:service-response-type ((msg (cl:eql 'MissionFinished)))
  'MissionFinished-response)
(cl:defmethod roslisp-msg-protocol:ros-datatype ((msg (cl:eql 'MissionFinished)))
  "Returns string type for a service object of type '<MissionFinished>"
  "krpc_ib2_msgs/MissionFinished")