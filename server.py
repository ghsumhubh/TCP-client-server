import socket
import sys
import os
import string
import random
import utils as cs


# EACH CHANGE DESCRIBES:
# WHAT CHANGE TYPE:
# WHAT PATH
class Change:
    def __init__(self, changeType1, path1):
        self.changeType = changeType1
        self.path = path1


# EACH PC DESCRIBES:
# ITS IP
# ITS PROGRESS IN UPDATE
# WHAT USER IT BELONGS TO
class PC:
    def __init__(self, ip, user1):
        self.ip = ip
        self.progress = 0
        self.user = user1


# EACH USER DESCRIBES:
# HIS ID
# HIS FOLDER NAME
# HIS CHANGE LIST
# HIS PCS
class User:  #
    def __init__(self, id1, folderName1):
        self.id = id1
        self.folderName = folderName1
        self.changeList = []
        self.pcs = []

    def addPC(self, pc1):
        self.pcs.append(pc1)


# waits for client to send ANY message
def waitForOK():
    OK_message = client_socket.recv(1028)
    return


# gets the operating system preferred slash for folder hierarchy
def getOSSlash():
    if os.name == 'posix':
        return "/"
    else:
        return "\\"


# sends file to a user
def sendFile(folder, file, user):
    filePath = folder + getOSSlash() + file
    message = cs.FILE_CREATION_MESSAGE + "$" + filePath.replace(user.folderName, '', 1) + "$" + str(
        os.path.getsize(filePath))
    send(message.encode())
    waitForOK()

    f = open(filePath, "rb")
    while True:
        bytes = f.read(1028)
        if bytes == b"":
            break
        send(bytes)
    waitForOK()


# sends an empty folder to the user
def sendEmptyFolder(folderPath, user):
    # we give str of CHANGETYPE, PATH, SIZE
    message = cs.FOLDER_CREATION_MESSAGE + "$" + folderPath.replace(user.folderName, '', 1) + "$0"
    send(message.encode())
    waitForOK()


# clones the entire directory to the user: used only once
def clone(path, user):
    for x in os.walk(path):
        folder = x[0]
        sendEmptyFolder(folder, user)
        for file in x[2]:
            sendFile(folder, file, user)
    send(cs.END_CLONE.encode())


# checks if an ID is in the system
def isIDInSystem():
    global client_ID
    for user in users:
        if user.id == client_ID:
            return True
    return False


# generates a 128 char long ID
def generateID():
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(128))


# gets the ID from the user -> if doesn't have, then gives him one and prints it on screen
def getID():
    global client_ID
    client_ID = client_socket.recv(129).decode()
    if len(client_ID) < 128:
        client_ID = generateID()
        print(client_ID)
        client_socket.send(client_ID.encode())  # notify user of new ID


# checks if a pc exists
def doesPCExist(id, ip):
    user = userByID(id)
    for pc in user.pcs:
        if pc.ip[0] == ip[0]:
            return True
    return False


# handles a request from existing ID
def handleExistingID():
    if doesPCExist(client_ID, client_address):
        handleExistingPC()
    else:
        handleNewPCOldID()


# gets a PC by it's ip and ID
def pcByIDAndIP(id, ip):
    user = userByID(client_ID)
    pcList = user.pcs
    for pc in pcList:
        if pc.ip[0] == ip[0]:
            return pc
    # shouldn't be here!
    return 0


# deletes a folder on the server
def deleteFolder(path):
    try:
        subdirectories = [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))]
        for subdirectory in subdirectories:
            deleteFolder(path + getOSSlash() + subdirectory)
        files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
        for file in files:
            os.remove(path + getOSSlash() + file)
        os.rmdir(path)
    except:
        pass
        # to negate watchdog's unexpected behavior with file deletion


# logs a change that the client sent
def logChange(changeType, path, user):
    changeForHistory = Change(changeType, path)
    user.changeList.append(changeForHistory)
    # avoid situations that we need to make then instantly delete a file
    if changeType == cs.FILE_DELETION_MESSAGE:
        for change in user.changeList:
            if change.path == path and change != changeForHistory:
                change.changeType = cs.REVERTED_CHANGE


# get updated by the client
def receiveUpdates():
    user = userByID(client_ID)
    while True:
        header = client_socket.recv(1028).decode()
        if header == cs.END_UPDATES:
            break
        pcByIDAndIP(client_ID, client_address).progress += 1  # if the pc updates us, it is already updated!
        # if we are here ti means we are updating
        # we get str of CHANGETYPE, PATH, SIZE
        changeType, path, size = header.split('$')
        # so we can log it later when other users ask for changes

        # We get relative path from the user directory, we need to get relative path to our directory
        path = normalizePath(path, user)
        logChange(changeType, path, user)
        # get size of change
        size = int(size)

        # IT CREATING FILE
        if changeType == cs.FILE_CREATION_MESSAGE:
            sendOK()
            bytesRead = 0
            f = open(path, "wb")
            while bytesRead < size:
                data = client_socket.recv(1028)
                f.write(data)
                bytesRead += len(data)
            f.close()
        # IF CREATING FOLDER
        elif changeType == cs.FOLDER_CREATION_MESSAGE:
            # if needs to create new folder
            try:
                os.mkdir(path)
            except:
                pass
        elif changeType == cs.FILE_DELETION_MESSAGE:
            # if need to delete file
            try:
                os.remove(path)
            except:
                pass
        elif changeType == cs.FOLDER_DELETION_MESSAGE:
            # if need to delete folder
            deleteFolder(path)
        sendOK()
        # accepts that is ready for next file/folder


# sends update to the client
def sendUpdates():
    pc = pcByIDAndIP(client_ID, client_address)
    user = pc.user
    while pc.progress < len(user.changeList):
        change = user.changeList[pc.progress]
        # change = Change(1,2)
        changeType = change.changeType
        path = change.path
        if changeType == cs.FILE_CREATION_MESSAGE:
            fileSize = os.path.getsize(path)
            # NOTIFY FOR CREATION
            send((cs.FILE_CREATION_MESSAGE + "$" + path.replace(user.folderName, '', 1) + "$" + str(fileSize)).encode())
            waitForOK()
            # start streaming data
            bytesRead = 0
            f = open(path, "rb")
            send(f.read())
            waitForOK()
        elif changeType == cs.FOLDER_CREATION_MESSAGE:
            send((cs.FOLDER_CREATION_MESSAGE + "$" + path.replace(user.folderName, '', 1) + "$0").encode())
            waitForOK()
        elif changeType == cs.FILE_DELETION_MESSAGE:
            send((cs.FILE_DELETION_MESSAGE + "$" + path.replace(user.folderName, ' ', 1) + "$0").encode())
            waitForOK()
        elif changeType == cs.FOLDER_DELETION_MESSAGE:
            send((cs.FOLDER_DELETION_MESSAGE + "$" + path.replace(user.folderName, ' ', 1) + "$0").encode())
            waitForOK()
        pc.progress += 1
    send(cs.END_UPDATES.encode())


# handles existing PC (with existing ID)
def handleExistingPC():
    send(cs.FC_OLD_ID_OLD_PC.encode())
    waitForOK()
    sendUpdates()
    receiveUpdates()


# handles new PC but old ID: clone the folder to pc
def handleNewPCOldID():
    # notify user its old ID but new PC -> so he should prepare to recieve clone
    send(cs.FC_OLD_ID_NEW_PC.encode())
    waitForOK()
    # add PC to user and updates it's progress to the latest
    user = userByID(client_ID)
    newPC = PC(client_address, user)
    user.addPC(newPC)
    newPC.progress = len(user.changeList)
    # IF pc gave us ID -> it means its an existing client so we just need to clone without more messages
    clone(user.folderName, user)


# gets a user by their ID
def userByID(ID):
    for user in users:
        if user.id == ID:
            return user
    # shouldn't be here!
    return 0


# gets a relative path from user OS, and translates it to relative path in the user's folder in the server OS
def normalizePath(path, user):
    windowsSlash = "\\"
    linuxSlash = "/"
    if os.name == 'posix':
        # IF LINUX
        path = path.replace(windowsSlash, linuxSlash)
        path = user.folderName + linuxSlash + path
    else:
        # IF WINDOWS
        path = path.replace(linuxSlash, windowsSlash)
        path = user.folderName + windowsSlash + path
    return path


# sends an OK message to user
def sendOK():
    send(cs.OK_MESSAGE.encode())


# gets the folder from the user
def getUserClone(user):
    while True:
        header = client_socket.recv(1028).decode()
        if header == cs.END_CLONE:
            break
        # if we are here ti means we are cloning
        # we get str of CHANGETYPE, PATH, SIZE
        changeType, path, size = header.split('$')
        # We get relative path from the user directory, we need to get relative path to our directory
        path = normalizePath(path, user)
        # get size of change
        size = int(size)

        # IT CREATING FILE
        if changeType == cs.FILE_CREATION_MESSAGE:
            sendOK()
            bytesRead = 0
            f = open(path, "wb")
            while bytesRead < size:
                data = client_socket.recv(1028)
                f.write(data)
                bytesRead += len(data)
            f.close()
        # IF CREATING FOLDER
        elif changeType == cs.FOLDER_CREATION_MESSAGE:
            # if needs to create new folder
            try:
                os.mkdir(path)
            except:
                pass

        sendOK()
        # accepts that is ready for next file/folder


# sends data to user
def send(data):
    client_socket.send(data)


# handles new ID (new PC as well)
def handleNewID():
    # notify PC it has new ID
    send(cs.FC_NEW_ID.encode())

    # make new user + PC
    global current_Folder_Number
    newUser = User(client_ID, str(current_Folder_Number))
    current_Folder_Number += 1
    newPC = PC(client_address, newUser)
    newUser.addPC(newPC)
    users.append(newUser)

    # CLONE THE FOLDER INTO SERVER
    getUserClone(newUser)
    # done cloning -> close connection to allow next user
    client_socket.close()


######################
# START OF CODE     #
#####################
# list of all users
users = []

# folder number we are at rn
current_Folder_Number = 0
# default client ID
client_ID = 0
# server setup
# ARGS
MY_PORT = int(sys.argv[1])
# setup TCP server
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(('', MY_PORT))
# Up to 20 clients waiting at one time, can be changed to support more
server.listen(20)

# main loop
while True:
    # accept a client
    client_socket, client_address = server.accept()
    # get/assigns the ID
    getID()
    # handle based on if new ID/PC
    if isIDInSystem():
        handleExistingID()
    else:
        handleNewID()
    # close the connection to allow next user
    client_socket.close()
