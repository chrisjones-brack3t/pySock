"""
TRNXS.NET Socket Server
"""

try:
    from twisted.internet.protocol import Protocol, Factory
    from twisted.internet import reactor, task
except ImportError:
    print("Twisted library is missing. Download it from http://twistedmatrix.com")
    raise SystemExit

try:
    import pyamf
except ImportError:
    print("PyAMF library is missing. Download it from http://pyamf.org")

import json, uuid, datetime

class InstacareProtocol(Protocol):
    encoding = pyamf.AMF3

    def __init__(self):
        self.encoder = pyamf.get_encoder(self.encoding)
        self.stream = self.encoder.stream

    def connectionLost(self, reason):
        """
        Called when a connection is lost
        """
        self.factory.number_of_connections -= 1
        pass

    def connectionMade(self):
        """
        Inherited from BaseProtocol

        Called when a connection is made
        """
        self.factory.number_of_connections += 1
        print("Connection Made")

    def dataReceived(self, data):
        """
        Handles all data received from client. All data from AS3/Flex
        should be sent as JSON.
        """
        try:
            data_dict = json.loads(data)
        except ValueError:
            print("Policy Request")
            return

        data_dict = json.loads(data)

        if data_dict['command'] == 'getInLine':
            self.getInLine(data_dict)
        elif data_dict['command'] == 'getNext':
            self.getNext(data_dict)
        elif data_dict['command'] == 'setupNewUser':
            self.setupNewUser(data_dict)
        elif data_dict['command'] == 'chat':
            self.chat(data_dict)
        elif data_dict['command'] == 'setupConsultationUser':
            self.setupConsultationUser(data_dict)
        else:
            print(data_dict)

    def chat(self, data):
        """
        Handles all chat communication between patient and employee
        """
        print("Send Chat message")

    def setupConsultationUser(self, data):
        """
        Setup new consultation connection
        """
        if data['user_type'] == 'patient':
            self.uuid = data['consultationId']
            self.user_type = 'patient'
            self.conference_id = data['conferenceId']
            print("ID: " + self.uuid.__str__())
            print("User Type: " + self.user_type)
        else:
            self.uuid = data['empId']
            self.user_type = data['user_type']
            self.conference_id = data['conferenceId']
            print("ID: " + self.uuid.__str__())
            print("User Type: " + self.user_type)

    def setupNewUser(self, data):
        """
        Initial user connection.
        """
        if data['user_type'] == 'patient':
            self.uuid = data['consultationId']
            self.user_type = data['user_type']

            try:
                self.status = data['status']
            except KeyError:
                self.status = False

            self.consultation_id = False
            self.queue_position = False
            print("ID: " + self.uuid.__str__())
            print("User Type: " + self.user_type)
            self.addToQueue()
        else:
            self.uuid = data['empId']
            self.user_type = data['user_type']
            self.status = 'queue'
            self.conference_id = False
            print("ID: " + self.uuid.__str__())
            print("User Type: " + self.user_type)

    def addToQueue(self):
        """
        Add user to proper queue based on user type
        """
        if self.status is False:
            self.factory.scheduler_queue.append(self)
        elif self.status == 'nurse_queue':
            self.factory.nurse_queue.append(self)
        elif self.status == 'doctor_queue':
            self.factory.doctor_queue.append(self) 
 
    def getNext(self, data):
        """
        Handles
        """
        if self.user_type == 'scheduler':
            queue = self.factory.scheduler_queue
        elif self.user_type == 'nurse':
            queue = self.factory.nurse_queue
        elif self.user_type == 'doctor':
            queue = self.factory.doctor_queue

        if len(queue) > 0:
            patient = queue.pop(0)
            consultation = ConsultationSession(patient, self)
            self.factory.consultations[consultation.id] = consultation
            response = {'command': 'connectConsultation',
                'consultID': patient.uuid.__str__(),
                'conferenceID': consultation.id.__str__()}
            self.transport.write(json.dumps(response))
            patient.transport.write(json.dumps(response))
            print(self.factory.consultations)

#        if len(self.factory.patient_queue) > 0:
#            patient = self.factory.patient_queue.pop(0)
#            consultation = ConsultationSession(patient, self)
#            self.factory.consultations[consultation.id] = consultation
#            print(consultation.employee.uuid)
#            print(consultation.patient.uuid)
#            print(self.factory.consultations)
        else:
            print("No Patients")

        print("ID: " + self.uuid.__str__())
        print("C_ID: " + self.conference_id.__str__())
        print("User Type: " + self.user_type)
        print("GET NEXT")
        print('')
#        self.uuid = data['empId']
#        self.user_type = data['user_type']
#        self.status = 'queue'
#        print(self.uuid)
#        print(self.user_type)
#        self.factory.doctor_queue.append(self)

class ConsultationSession:
    """
    Handles connecting a patient with a doctor, nurse or scheduler
    """

    def __init__(self, patient, employee):
        self.patient = patient
        self.employee = employee
        self.id = uuid.uuid4()
        self.created_on = datetime.datetime.now()
        patient.consultation_id = self.id
        employee.consultation_id = self.id

class InstacareFactory(Factory):
    """
    Factory manages all connection-related events. Each successful
    connection will create a new Instacare Protocol
    """
    protocol = InstacareProtocol
    max_connections = 1000

    def __init__(self):
        self.number_of_connections = 0
        self.scheduler_queue = []
        self.nurse_queue = []
        self.doctor_queue = []
        self.consultations = {}



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

def cleanUp(protocol):
    """
    Looks for dead connections and removes them
    """
    print(protocol.factory.consultations)

#pdb.set_trace()
#    import gc
#    for o in gc.get_objects():
#        if isinstance(o, InstacareFactory):
#            print(o.consultations)
#    print("cleanUp method ran")

#clean = task.LoopingCall(cleanUp)
#clean.start(3.0)


#if __name__ == '__main__':
#    from optparse import OptionParser
#    
#    parser = OptionParser()
#    parser.add_option("--host", default=host,
#        dest="host", help="host address [default: %default]")
#    parser.add_option("-a", "--app-port", default=appPort,
#        dest="app_port", help="Application port number [default: %default]")
#    parser.add_option("-p", "--policy-port", default=policyPort,
#        dest="policy_port", help="Socket policy port number [default: %default]")
#    parser.add_option("-f", "--policy-file", default=policyFile,
#        dest="policy_file", help="Location of socket policy file [default: %default]")
#    (opt, args) = parser.parse_args()
#
#    print "Running Socket AMF gateway on %s:%s" % (opt.host, opt.app_port)
#    print "Running Policy file server on %s:%s" % (opt.host, opt.policy_port)
#    
#    reactor.listenTCP(int(opt.app_port), TimerFactory(), interface=opt.host)
#    reactor.listenTCP(int(opt.policy_port), SocketPolicyFactory(opt.policy_file),
#        interface=opt.host)
#    reactor.run()
