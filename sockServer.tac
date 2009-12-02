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
    from sockServer import InstacareProtocol, killItWithFire
    from sockServer import appPort, policyPort
except ImportError:
    print("Cannot find sockServer.py file.")
    raise SystemExit

import gc

instacare = InstacareFactory()
policy = SocketPolicyFactory('socket-policy.xml')

# this is the important bit
application = service.Application('instacare-socket-server')

instacareService = internet.TCPServer(appPort, instacare)
socketPolicyService = internet.TCPServer(policyPort, policy)

instacareService.setServiceParent(application)
socketPolicyService.setServiceParent(application)

# Setup Looping call to clean up dead protocol connections
l = task.LoopingCall(killItWithFire)
l.start(3.0)
