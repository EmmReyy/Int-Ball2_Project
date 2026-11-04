; Auto-generated. Do not edit!


(cl:in-package krpc_ib2_msgs-srv)


;//! \htmlinclude MissionStart-request.msg.html

(cl:defclass <MissionStart-request> (roslisp-msg-protocol:ros-message)
  ()
)

(cl:defclass MissionStart-request (<MissionStart-request>)
  ())

(cl:defmethod cl:initialize-instance :after ((m <MissionStart-request>) cl:&rest args)
  (cl:declare (cl:ignorable args))
  (cl:unless (cl:typep m 'MissionStart-request)
    (roslisp-msg-protocol:msg-deprecation-warning "using old message class name krpc_ib2_msgs-srv:<MissionStart-request> is deprecated: use krpc_ib2_msgs-srv:MissionStart-request instead.")))
(cl:defmethod roslisp-msg-protocol:serialize ((msg <MissionStart-request>) ostream)
  "Serializes a message object of type '<MissionStart-request>"
)
(cl:defmethod roslisp-msg-protocol:deserialize ((msg <MissionStart-request>) istream)
  "Deserializes a message object of type '<MissionStart-request>"
  msg
)
(cl:defmethod roslisp-msg-protocol:ros-datatype ((msg (cl:eql '<MissionStart-request>)))
  "Returns string type for a service object of type '<MissionStart-request>"
  "krpc_ib2_msgs/MissionStartRequest")
(cl:defmethod roslisp-msg-protocol:ros-datatype ((msg (cl:eql 'MissionStart-request)))
  "Returns string type for a service object of type 'MissionStart-request"
  "krpc_ib2_msgs/MissionStartRequest")
(cl:defmethod roslisp-msg-protocol:md5sum ((type (cl:eql '<MissionStart-request>)))
  "Returns md5sum for a message object of type '<MissionStart-request>"
  "937c9679a518e3a18d831e57125ea522")
(cl:defmethod roslisp-msg-protocol:md5sum ((type (cl:eql 'MissionStart-request)))
  "Returns md5sum for a message object of type 'MissionStart-request"
  "937c9679a518e3a18d831e57125ea522")
(cl:defmethod roslisp-msg-protocol:message-definition ((type (cl:eql '<MissionStart-request>)))
  "Returns full string definition for message of type '<MissionStart-request>"
  (cl:format cl:nil "~%~%"))
(cl:defmethod roslisp-msg-protocol:message-definition ((type (cl:eql 'MissionStart-request)))
  "Returns full string definition for message of type 'MissionStart-request"
  (cl:format cl:nil "~%~%"))
(cl:defmethod roslisp-msg-protocol:serialization-length ((msg <MissionStart-request>))
  (cl:+ 0
))
(cl:defmethod roslisp-msg-protocol:ros-message-to-list ((msg <MissionStart-request>))
  "Converts a ROS message object to a list"
  (cl:list 'MissionStart-request
))
;//! \htmlinclude MissionStart-response.msg.html

(cl:defclass <MissionStart-response> (roslisp-msg-protocol:ros-message)
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

(cl:defclass MissionStart-response (<MissionStart-response>)
  ())

(cl:defmethod cl:initialize-instance :after ((m <MissionStart-response>) cl:&rest args)
  (cl:declare (cl:ignorable args))
  (cl:unless (cl:typep m 'MissionStart-response)
    (roslisp-msg-protocol:msg-deprecation-warning "using old message class name krpc_ib2_msgs-srv:<MissionStart-response> is deprecated: use krpc_ib2_msgs-srv:MissionStart-response instead.")))

(cl:ensure-generic-function 'success-val :lambda-list '(m))
(cl:defmethod success-val ((m <MissionStart-response>))
  (roslisp-msg-protocol:msg-deprecation-warning "Using old-style slot reader krpc_ib2_msgs-srv:success-val is deprecated.  Use krpc_ib2_msgs-srv:success instead.")
  (success m))

(cl:ensure-generic-function 'message-val :lambda-list '(m))
(cl:defmethod message-val ((m <MissionStart-response>))
  (roslisp-msg-protocol:msg-deprecation-warning "Using old-style slot reader krpc_ib2_msgs-srv:message-val is deprecated.  Use krpc_ib2_msgs-srv:message instead.")
  (message m))
(cl:defmethod roslisp-msg-protocol:serialize ((msg <MissionStart-response>) ostream)
  "Serializes a message object of type '<MissionStart-response>"
  (cl:write-byte (cl:ldb (cl:byte 8 0) (cl:if (cl:slot-value msg 'success) 1 0)) ostream)
  (cl:let ((__ros_str_len (cl:length (cl:slot-value msg 'message))))
    (cl:write-byte (cl:ldb (cl:byte 8 0) __ros_str_len) ostream)
    (cl:write-byte (cl:ldb (cl:byte 8 8) __ros_str_len) ostream)
    (cl:write-byte (cl:ldb (cl:byte 8 16) __ros_str_len) ostream)
    (cl:write-byte (cl:ldb (cl:byte 8 24) __ros_str_len) ostream))
  (cl:map cl:nil #'(cl:lambda (c) (cl:write-byte (cl:char-code c) ostream)) (cl:slot-value msg 'message))
)
(cl:defmethod roslisp-msg-protocol:deserialize ((msg <MissionStart-response>) istream)
  "Deserializes a message object of type '<MissionStart-response>"
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
(cl:defmethod roslisp-msg-protocol:ros-datatype ((msg (cl:eql '<MissionStart-response>)))
  "Returns string type for a service object of type '<MissionStart-response>"
  "krpc_ib2_msgs/MissionStartResponse")
(cl:defmethod roslisp-msg-protocol:ros-datatype ((msg (cl:eql 'MissionStart-response)))
  "Returns string type for a service object of type 'MissionStart-response"
  "krpc_ib2_msgs/MissionStartResponse")
(cl:defmethod roslisp-msg-protocol:md5sum ((type (cl:eql '<MissionStart-response>)))
  "Returns md5sum for a message object of type '<MissionStart-response>"
  "937c9679a518e3a18d831e57125ea522")
(cl:defmethod roslisp-msg-protocol:md5sum ((type (cl:eql 'MissionStart-response)))
  "Returns md5sum for a message object of type 'MissionStart-response"
  "937c9679a518e3a18d831e57125ea522")
(cl:defmethod roslisp-msg-protocol:message-definition ((type (cl:eql '<MissionStart-response>)))
  "Returns full string definition for message of type '<MissionStart-response>"
  (cl:format cl:nil "# Response~%bool success~%string message~%~%~%~%"))
(cl:defmethod roslisp-msg-protocol:message-definition ((type (cl:eql 'MissionStart-response)))
  "Returns full string definition for message of type 'MissionStart-response"
  (cl:format cl:nil "# Response~%bool success~%string message~%~%~%~%"))
(cl:defmethod roslisp-msg-protocol:serialization-length ((msg <MissionStart-response>))
  (cl:+ 0
     1
     4 (cl:length (cl:slot-value msg 'message))
))
(cl:defmethod roslisp-msg-protocol:ros-message-to-list ((msg <MissionStart-response>))
  "Converts a ROS message object to a list"
  (cl:list 'MissionStart-response
    (cl:cons ':success (success msg))
    (cl:cons ':message (message msg))
))
(cl:defmethod roslisp-msg-protocol:service-request-type ((msg (cl:eql 'MissionStart)))
  'MissionStart-request)
(cl:defmethod roslisp-msg-protocol:service-response-type ((msg (cl:eql 'MissionStart)))
  'MissionStart-response)
(cl:defmethod roslisp-msg-protocol:ros-datatype ((msg (cl:eql 'MissionStart)))
  "Returns string type for a service object of type '<MissionStart>"
  "krpc_ib2_msgs/MissionStart")