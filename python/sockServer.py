"""
TRNXS.NET Socket Server
"""

try:
    from twisted.internet.protocol import Protocol, Factory
    from twisted.internet import reactor
except ImportError:
    print("Twisted library is missing. Download it from http://twistedmatrix.com")
    raise SystemExit

try:
    import pyamf
except ImportError:
    print("PyAMF library is missing. Download it from http://pyamf.org")

import json



class InstacareProtocol(Protocol):
    encoding = pyamf.AMF3
    
    def __init__(self):
        self.encoder = pyamf.get_encoder(self.encoding)
        self.stream = self.encoder.stream
    
    def connectionLost(self, reason):
        """
        Called when a connection is lost
        """
        pass
    
    def connectionMade(self):
        """
        Inherited from BaseProtocol
        
        Called when a connection is made
        """
        print("Connection Made")
    
    def dataReceived(self, data):
        """
        Handles all data received from client. All data from AS3/Flex
        should be sent as JSON.
        """
        data_dict = json.loads(data)
        
        if data_dict['command'] == 'getInLine':
            self.getInLine(data_dict)
        elif data_dict['command'] == 'getNext':
            self.getNext(data_dict)
        else:
            print(data_dict)

    def getInLine(self, data):
        """
        Get in line command. Sets uuid and user type then adds
        patient to the queue.
        """
        self.uuid = data['consultationId']
        self.user_type = data['user_type']
        self.status = 'queue'
        print(self.uuid)
        print(self.user_type)
        self.factory.patient_queue.append(self)
    
    def getNext(self, data):
        self.uuid = data['empId']
        self.user_type = data['user_type']
        self.status = 'queue'
        print(self.uuid)
        print(self.user_type)
        self.factory.doctor_queue.append(self)
        


class InstacareFactory(Factory):
    """
    Factory manages all connection-related events. Each successful
    connection will create a new Instacare Protocol
    """
    protocol = InstacareProtocol
    max_connections = 1000
    
    def __init__(self):
        self.number_of_connections = 0
        self.patient_queue = []
        self.doctor_queue = []



class SocketPolicyProtocol(Protocol):
    """
    Serves strict policy file for Flash Player >= 9.0.124
    
    @see: U{http://adobe.com/go/strict_policy_files}
    """
    def connectionMade(self):
        self.buffer = ''
    
    def dataReceived(self, data):
        self.buffer += data
        
        if self.buffer.startswith('<policy-file-request/>'):
            self.transport.write(self.factory.getPolicyFile(self))
            self.transport.loseConnection()

class SocketPolicyFactory(Factory):
    protocol = SocketPolicyProtocol
    
    def __init__(self, policy_file):
        """
        @param policy_file: Path to the policy file definition
        """
        self.policy_file = policy_file
    
    def getPolicyFile(self, protocol):
        return open(self.policy_file, 'rt').read()



host = 'localhost'
appPort = 8000
policyPort = 843
policyFile = 'socket-policy.xml'

if __name__ == '__main__':
    from optparse import OptionParser
    
    parser = OptionParser()
    parser.add_option("--host", default=host,
        dest="host", help="host address [default: %default]")
    parser.add_option("-a", "--app-port", default=appPort,
        dest="app_port", help="Application port number [default: %default]")
    parser.add_option("-p", "--policy-port", default=policyPort,
        dest="policy_port", help="Socket policy port number [default: %default]")
    parser.add_option("-f", "--policy-file", default=policyFile,
        dest="policy_file", help="Location of socket policy file [default: %default]")
    (opt, args) = parser.parse_args()

    print "Running Socket AMF gateway on %s:%s" % (opt.host, opt.app_port)
    print "Running Policy file server on %s:%s" % (opt.host, opt.policy_port)
    
    reactor.listenTCP(int(opt.app_port), TimerFactory(), interface=opt.host)
    reactor.listenTCP(int(opt.policy_port), SocketPolicyFactory(opt.policy_file),
        interface=opt.host)
    reactor.run()