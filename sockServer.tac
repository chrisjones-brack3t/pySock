import sys, os

sys.path.append(os.getcwd())

try:
    from twisted.application import internet, service
    from twisted.internet import task
except ImportError:
    print("Twisted library is missing. Download from http://twistedmatrix.com")
    raise SystemExit

try:
    from sockServer import InstacareFactory, SocketPolicyFactory
    from sockServer import appPort, policyPort, policyFile
except ImportError:
    print("Cannot find sockServer.py file or other import error.")
    raise SystemExit

import gc

instacare = InstacareFactory()
policy = SocketPolicyFactory(policyFile)

# this is the important bit
application = service.Application('instacare-socket-server')

instacareService = internet.TCPServer(appPort, instacare)
socketPolicyService = internet.TCPServer(policyPort, policy)

instacareService.setServiceParent(application)
socketPolicyService.setServiceParent(application)

def stats():
    statsConnections()
    statsQueueList()

def statsConnections():
    """
    Displays the number of active connections to the socket
    server. Each user connection consists of two connections.
    One for the commands and one for the security policy.
    """
    print("Connections: " + instacare.number_of_connections.__str__())
    return

def statsQueueList():
    """
    Displays a count of the queues
    """
    print("Admissions Queue Count: " + \
        instacare.admissions_queue.__len__().__str__())
    print("Nurse Queue Count: " + \
        instacare.nurse_queue.__len__().__str__())
    print("Doctor Queue Count: " + \
        instacare.doctor_queue.__len__().__str__())
    print("Scheduler Queue Count: " + \
        instacare.scheduler_queue.__len__().__str__())
    return

#t = task.LoopingCall(stats)
#t.start(5.0)
