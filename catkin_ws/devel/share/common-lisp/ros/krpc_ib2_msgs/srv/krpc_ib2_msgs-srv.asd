
(cl:in-package :asdf)

(defsystem "krpc_ib2_msgs-srv"
  :depends-on (:roslisp-msg-protocol :roslisp-utils )
  :components ((:file "_package")
    (:file "CheckPoints" :depends-on ("_package_CheckPoints"))
    (:file "_package_CheckPoints" :depends-on ("_package"))
    (:file "MissionFinished" :depends-on ("_package_MissionFinished"))
    (:file "_package_MissionFinished" :depends-on ("_package"))
    (:file "MissionStart" :depends-on ("_package_MissionStart"))
    (:file "_package_MissionStart" :depends-on ("_package"))
  ))