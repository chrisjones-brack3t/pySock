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

import json, uuid, datetime, os

class InstacareProtocol(Protocol):
    encoding = pyamf.AMF3

    def __init__(self):
        self.encoder = pyamf.get_encoder(self.encoding)
        self.stream = self.encoder.stream
        self.last_active = datetime.datetime.now()
        self.in_conference = False

    def connectionLost(self, reason):
        """
        Called when a connection is lost
        """
        print("Instacare Protocol connection lost")
        self.queueCleanup()
        self.factory.number_of_connections -= 1

    def connectionMade(self):
        """
        Inherited from BaseProtocol

        Called when a connection is made
        """
        self.factory.number_of_connections += 1
        print("Connection Made")

    def queueCleanup(self):
        """
        When a connection is lost clear out user in
        specified queue.
        """
        try:
            if self.uuid:
                queue = eval('self.factory.' + self.status)

                if self in queue:
                    queue.remove(self)
        except AttributeError:
            # Do nothing, policy connection, let it die
            pass

    def dataReceived(self, data):
        """
        Handles all data received from client. All data from AS3/Flex
        should be sent as JSON.

        First connection to port is actually a xml security check. All
        connections after that should be JSON encoded.
        """
        try:
            data_dict = json.loads(data)
        except ValueError:
            if data.__str__() == '<policy-file-request/>':
                print("POLICY CONNECTION TO WRONG PORT.")
                self.factory.loseConnection()
            else:
                print("Invalid data. Not JSON or policy request.")
                self.factory.loseConnection()
            return

        data_dict = json.loads(data)
        self.last_active = datetime.datetime.now() # Update active timestamp

        if data_dict['command'] == 'setupNewUser':
            self.setupNewUser(data_dict)
        elif data_dict['command'] == 'setupConsultationUser':
            self.setupConsultationUser(data_dict)
        elif data_dict['command'] == 'getNext':
            self.getNext(data_dict)
        elif data_dict['command'] == 'newChatMsg':
            self.chat(data_dict)
        elif data_dict['command'] == 'pushPatient':
            self.pushPatient(data_dict)
        else:
            print(data_dict)

    def chat(self, data):
        """
        Handles all chat communication between patient and employee
        """
        consultation = self.factory.consultations[self.conference_id.__str__()]
        time_response = datetime.datetime.now().strftime('%H:%M')

        if self.user_type == 'patient':
            user = 'Patient[' + time_response + ']: '
        else:
            user = 'Employee[' + time_response + ']: '

        response = {'command': 'newChatMsg',
            'chatMsg': user + data['chatMsg']}
        consultation.patient.transport.write(json.dumps(response))
        consultation.employee.transport.write(json.dumps(response))

    def pushPatient(self, data):
        """
        End consultation and push patient on to the next queue.

        Clear employee conference ID and tell employee connection to
        get next patient.

        Patient has conference ID cleared and status variable set to
        which queue to place them in on reconnect. This var is passed
        from javascript to an AS3 var which finally gets written back
        to the socket on reconnect.
        """
        consultation = self.factory.consultations[self.conference_id.__str__()]

        if self.user_type == 'admissions':
            consultation.patient.status = 'nurse_queue'
        elif self.user_type == 'nurse':
            consultation.patient.status = 'doctor_queue'
        elif self.user_type == 'doctor':
            consultation.patient.status = 'scheduler_queue'
        elif self.user_type == 'scheduler':
            consultation.patient.status = 'done'

        # Clear conference ID from both users
        consultation.patient.conference_id = None
        consultation.employee.conference_id = None

        # Create responses for both users
        patient_response = {'command': 'pushPatient', 
            'status': consultation.patient.status}
        employee_response = {'command': 'resetEmployee'}

        # Send reponse to users
        consultation.patient.transport.write(json.dumps(patient_response))
        consultation.employee.transport.write(json.dumps(employee_response))

        # Close socket connections
        consultation.patient.transport.loseConnection()
        consultation.employee.transport.loseConnection()

        # Clean up. Delete consultation from dictionary on factory
        # All references to object should be gone at this point so 
        # garbage collection should take care of this.
        del self.factory.consultations[consultation.id.__str__()]
        del consultation

    def setupConsultationUser(self, data):
        """
        Setup new consultation connection

        This method handles setting the reconneted user after
        coming from the queue.
        """
        self.in_conference = True
        self.conference_id = data['conferenceId']

        if data['user_type'] == 'patient':
            self.uuid = data['consultationId']
            self.user_type = 'patient'
        else:
            self.uuid = data['empId']
            self.user_type = data['user_type']

        check = self.checkForConsultationExistance(data)
        if check:
            print("""
-----------------------------------------------------------------------
 Consultation Reconnect
 User Type: %s
 User ID: %s
 Consultation to reconnect to: %s
-----------------------------------------------------------------------
            """ % (self.user_type, self.uuid.__str__(), self.conference_id))

            self.setupConsultationReconnect()

    def checkForConsultationExistance(self, data):
        """
        HACK!

        Method verifies that the consultation id passed from the URL
        exists. This is meant to handle the patient or employee hitting
        the back button in the browser.

        Temporary fix until Flex interface is rebuilt.
        """

        consultation = data['conferenceId']
        try:
            consultation = self.factory.consultations[data['conferenceId']]
            return True
        except KeyError:
            if self.user_type == 'patient':
                response = {'command':'handleConsultationError',
                    'status':'admissions_queue'}
            else:
                response = {'command':'handleConsultationError',
                    'status':''}
            self.transport.write(json.dumps(response))
            return False

    def setupConsultationReconnect(self):
        """
        Hack since we lose connections

        Find consultation session from previous connection and
        override the patient or employee with the new connection

        Consultation is held on the InstacareFactory so that we can
        reconnect the users in a consultation
        """
        try:
            consultation = self.factory.consultations[self.conference_id]
            if self.user_type == 'patient':
                consultation.patient = self
            else:
                consultation.employee = self

            print("""
-----------------------------------------------------------------------
 User Replaced in Consultation
 User Type: %s
 User ID: %s
 Consultation ID: %s
-----------------------------------------------------------------------
            """ % (self.user_type, self.uuid.__str__(), \
                    consultation.id.__str__()))

        except KeyError:
            print("Consultation with ID of %s was not found" % \
                self.conference_id.__str__())

    def setupNewUser(self, data):
        """
        Initial user connection.

        Sets up new users or employees on first queue connection
        """
        if data['user_type'] == 'patient':
            self.uuid = data['consultationId']
            self.user_type = data['user_type']
            self.status = data['status']
            self.consultation_id = False
            self.in_conference = False
            self.addToQueue()
        else:
            self.uuid = data['empId']
            self.user_type = data['user_type']
            self.status = 'queue'
            self.conference_id = False
            self.in_conference = False

    def addToQueue(self):
        """
        Add user to proper queue based on user type
        """
        if self.status == 'admissions_queue':
            self.factory.admissions_queue.append(self)
        elif self.status == 'nurse_queue':
            self.factory.nurse_queue.append(self)
        elif self.status == 'doctor_queue':
            self.factory.doctor_queue.append(self)
        elif self.status == 'scheduler_queue':
            self.factory.scheduler_queue.append(self)

    def getNext(self, data):
        """
        Loop for employees that checks for new patients in their
        respective queues. Once found user is popped out of queue list
        and connected to a consultation session.
        """
        if self.user_type == 'admissions':
            queue = self.factory.admissions_queue
        elif self.user_type == 'nurse':
            queue = self.factory.nurse_queue
        elif self.user_type == 'doctor':
            queue = self.factory.doctor_queue
        elif self.user_type == 'scheduler':
            queue = self.factory.scheduler_queue

        if len(queue) > 0:
            patient = queue.pop(0)
            consultation = ConsultationSession(patient, self)
            self.factory.consultations[consultation.id.__str__()] = consultation
            print("""
-----------------------------------------------------------------------
 Found Patient in Queue
 Popped patient out of %s Queue
 Patient ID: %s
 Created Consultation
 Consultation UUID: %s
 Consultation %s added to InstacareFactory
 Consultation Users:
   Employee ID: %s
   Patient ID: %s
-----------------------------------------------------------------------
            """ % (self.user_type, patient.uuid.__str__(), \
                    consultation.id.__str__(), \
                    consultation.id.__str__(), \
                    consultation.employee.uuid.__str__(), \
                    consultation.patient.uuid.__str__()))

            response = {'command': 'connectConsultation',
                'consultID': patient.uuid.__str__(),
                'conferenceID': consultation.id.__str__()}
            self.transport.write(json.dumps(response))
            patient.transport.write(json.dumps(response))
            self.transport.loseConnection()
            patient.transport.loseConnection()
        else:
            print("No users in %s queue" % self.user_type)

class ConsultationSession:
    """
    Handles connecting a patient with a doctor, admissions, nurse or scheduler

    This class is responsible for providing a simple object to communicate
    to both users involved in a conference. Each conference object is given a
    unique UUID.
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

    This factory acts a singleton or a service in Twisted terms. Each new
    connection to this class creates a new InstacareProtocol.
    """
    protocol = InstacareProtocol
    max_connections = 1000

    def __init__(self):
        self.number_of_connections = 0
        self.admissions_queue = []
        self.nurse_queue = []
        self.doctor_queue = []
        self.scheduler_queue = []
        self.consultations = {}

class SocketPolicyProtocol(Protocol):
    """
    Serves strict policy file for Flash Player >= 9.0.124

    @see: U{http://adobe.com/go/strict_policy_files}
    """
    buffer = ''
    def connectionLost(self, reason):
        """
        Called when a connection is lost
        """
        print("Policy connection lost or closed.")

    def connectionMade(self):
        """
        Inherited from BaseProtocol

        Called when a connection is made
        """
        print("Policy Connection Made")

    def dataReceived(self, data):
        self.buffer += data

        if self.buffer.startswith('<policy-file-request/>'):
            self.transport.write(self.factory.getPolicyFile(self))
            self.transport.loseConnection()
        else:
            print("Unknown connection, not asking for policy file.")
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


ROOT_PATH = os.path.dirname(__file__)
host = 'localhost'
appPort = 8000
policyPort = 843
policyFile = ROOT_PATH + '/crossdomain.xml'

#class KillItWithFire:
#    """
#    Garbage cleanup. Checks for lingering open connections
#    and closes them if they are past the alotted time.
#    """

#    def __init__(self):
#        """
#        Set idle connection time limits in seconds
#        """
#        self.queue_time = 30
#        self.conference_time = 60

#    def kill(self):
#        """
#        Find all InstacareProtocol objects
#        """
#        print("Running garbage collector.")
#        for obj in gc.get_objects():
#            if isinstance(obj, InstacareProtocol):
#                if obj.in_conference:
#                    self.killConferenceConnection(obj)
#                else:
#                    self.killQueueConnection(obj)

#    def killQueueConnection(self, protocol):
#        """
#        """
#        time_limit = datetime.datetime.now() - \
#            datetime.timedelta(seconds=self.queue_time)
#        if protocol.last_active <= time_limit:
#            print("KILL QUEUE CONNECTION WITH FIRE")
#            #protocol.transport.loseConnection()
#        else:
#            print("QUEUE CONNECTION CAN LIVE FOR NOW")

#    def killConferenceConnection(self, protocol):
#        """
#        """
#        time_limit = datetime.datetime.now() - \
#            datetime.timedelta(seconds=self.conference_time)
#        if protocol.last_active <= time_limit:
#            print("KILL CONFERENCE CONNECTION WITH FIRE")
#            #protocol.transport.loseConnection()
#        else:
#            print("CONFERENCE CONNECTION CAN LIVE FOR NOW")

