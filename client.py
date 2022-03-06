import socket
import watchdog
import sys
import time
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
import os
import utils as cs


# derscribes a change
class Change:
    def __init__(self, changeType1, path1):
        self.changeType = changeType1
        self.path = path1


# basically wait for the client to send ANY message (will be an OK message logically)
def waitForOK():
    OK_message = s.recv(1028)
    return


# sends the connected server a file
def sendFile(folder, file):
    filePath = folder + getOSSlash() + file
    message = cs.FILE_CREATION_MESSAGE + "$" + filePath.replace(FOLDER_PATH, '', 1) + "$" + str(
        os.path.getsize(filePath))
    send(message.encode())
    waitForOK()
    f = open(filePath, "rb")
    s.send(f.read())
    waitForOK()


# works also when files are deleted, as opposed to OS commands
def isFile(path):
    if "." in path:
        return True
    return False


# clones recursively all files, folders in path to server
def clone(path):
    # get files + folders
    for x in os.walk(path):
        folder = x[0]
        sendEmptyFolder(folder)
        for file in x[2]:
            sendFile(folder, file)
    send(cs.END_CLONE.encode())


# sends an empty folder to server
def sendEmptyFolder(folderPath):
    # we give str of CHANGETYPE, PATH, SIZE
    message = cs.FOLDER_CREATION_MESSAGE + "$" + folderPath.replace(FOLDER_PATH, '', 1) + "$0"
    send(message.encode())
    waitForOK()


# watchdog creation event
def on_created(event):
    path = event.src_path
    # if it's on ignore list -> don't document it
    for ignore in ignoreList:
        if ignore in path:
            return
    if isFile(path):
        change = Change(cs.FILE_CREATION_MESSAGE, path)
    else:
        change = Change(cs.FOLDER_CREATION_MESSAGE, path)
    updateList.append(change)


# watchdogg deletion event
def on_deleted(event):
    path = event.src_path
    # if it's on ignore list -> don't document it
    for ignore in ignoreList:
        if ignore in path:
            return
    if isFile(path):
        change = Change(cs.FILE_DELETION_MESSAGE, path)
    else:
        change = Change(cs.FOLDER_DELETION_MESSAGE, path)
    updateList.append(change)


# watchdog modified event -> treat it as delete->create
def on_modified(event):
    path = event.src_path
    # if it's on ignore list -> don't document it
    for ignore in ignoreList:
        # basically a sub therefore "in"
        if ignore in path:
            return
    if isFile(path):
        change1 = Change(cs.FILE_DELETION_MESSAGE, path)
        change2 = Change(cs.FILE_CREATION_MESSAGE, path)
        updateList.append(change1)
        updateList.append(change2)
    else:
        pass


# watchdog move event. has to be treated as delete->create to fully utilize the tidyUpdateList method!
def on_moved(event):
    path1 = event.src_path
    path2 = event.dest_path
    # if it's on ignore list -> don't document it
    for ignore in ignoreList:
        if ignore in path1 or ignore in path2:
            return
    if isFile(path1):
        change1 = Change(cs.FILE_DELETION_MESSAGE, path1)
        change2 = Change(cs.FILE_CREATION_MESSAGE, path2)
        updateList.append(change1)
        updateList.append(change2)
    else:
        change1 = Change(cs.FOLDER_DELETION_MESSAGE, path1)
        change2 = Change(cs.FOLDER_CREATION_MESSAGE, path2)
        updateList.append(change1)
        updateList.append(change2)


# gets the OS preferred file hierarchy slash
def getOSSlash():
    if os.name == 'posix':
        return "/"
    else:
        return "\\"


# gets: relative path in server OS, outputs the relative path (in our system) in our OS
def normalizePath(path):
    windowsSlash = "\\"
    linuxSlash = "/"
    if os.name == 'posix':
        # IF LINUX
        path = path.replace(windowsSlash, linuxSlash)
        path = FOLDER_PATH + linuxSlash + path
    else:
        # IF WINDOWS
        path = path.replace(linuxSlash, windowsSlash)
        path = FOLDER_PATH + windowsSlash + path
    return path


# a method for sending data to server
def send(data):
    s.send(data)


# a method to send an OK message to server
def sendOK():
    send(cs.OK_MESSAGE.encode())


# a method to prepare client to receive the clone from server
def getServerClone():
    global ignoreList
    while True:
        header = s.recv(1028).decode()
        if header == cs.END_CLONE:
            break
        # if we are here ti means we are cloning
        # we get str of CHANGETYPE, PATH, SIZE
        changeType, path, size = header.split('$')
        # We get relative path from the user directory, we need to get relative path to our directory
        path = normalizePath(path)
        # ignore this file on watchdog
        ignoreList.append(path)
        # get size of change
        size = int(size)

        # IT CREATING FILE
        if changeType == cs.FILE_CREATION_MESSAGE:
            sendOK()
            bytesRead = 0
            f = open(path, "wb")
            while bytesRead < size:
                data = s.recv(1028)
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
    # don't ignore more!
    ignoreList = []


# a method to connect to server first time
def connectToServer():
    global MY_ID
    s.connect((SERVER_IP, SERVER_PORT))
    if hasID:
        s.send(MY_ID.encode())
    else:
        s.send(b"I have no ID")

        MY_ID = s.recv(128).decode()
    FC = s.recv(1028).decode()
    if FC == cs.FC_NEW_ID:
        clone(FOLDER_PATH)
    else:  # FC == cs.FC_OLD_ID_NEW_PC
        sendOK()
        getServerClone()
    s.close()


# a method that deletes a folder in path with all it's content
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
        # watchdog sometimes has unexpected behavior when it comes to alerting user of deletion of folders


# request updates from server
def requestUpdates():
    global ignoreList
    global MY_ID
    global s
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((SERVER_IP, SERVER_PORT))
    s.send(MY_ID.encode())
    FC = s.recv(1028).decode()
    sendOK()
    # we are supposed to be an old PC + old ID -> here if we just want updates!
    if FC == cs.FC_OLD_ID_OLD_PC:
        while True:
            header = s.recv(1028).decode()
            if header == cs.END_UPDATES:
                break
            # if we are here ti means we are updating
            # we get str of CHANGETYPE, PATH, SIZE
            changeType, path, size = header.split('$')
            # avoids weird behavior of double slash
            path = path[1:]
            # We get relative path from the user directory, we need to get relative path to our directory
            path = normalizePath(path)
            # ignore this file on watchdog
            # avoids weird behavior that gets double OSSlash only here
            oslash = getOSSlash()
            ignoreList.append(path.replace(oslash + oslash, oslash))
            # get size of change
            size = int(size)

            # IT CREATING FILE
            if changeType == cs.FILE_CREATION_MESSAGE:
                sendOK()
                bytesRead = 0
                f = open(path, "wb")
                while bytesRead < size:
                    data = s.recv(1028)
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
    # finished updating -> don't ignore anything!
    time.sleep(0.5)
    ignoreList = []


# send updates to server
def sendUpdates():
    global updateList
    i = 0
    while i < len(updateList):
        change = updateList[i]
        changeType = change.changeType
        path = change.path
        if changeType == cs.FILE_CREATION_MESSAGE:
            # sometimes watchdog has weird behavior and notifies on file creation that doesn't exist
            try:
                fileSize = os.path.getsize(path)
                # NOTIFY FOR CREATION
                send((cs.FILE_CREATION_MESSAGE + "$" + path.replace(FOLDER_PATH + getOSSlash(), '', 1) + "$" + str(
                    fileSize)).encode())
                waitForOK()
                # start streaming data
                bytesRead = 0
                f = open(path, "rb")
                send(f.read())
                waitForOK()
            except:
                pass
        elif changeType == cs.FOLDER_CREATION_MESSAGE:
            send((cs.FOLDER_CREATION_MESSAGE + "$" + path.replace(FOLDER_PATH + getOSSlash(), '', 1) + "$0").encode())
            waitForOK()
        elif changeType == cs.FILE_DELETION_MESSAGE:
            send((cs.FILE_DELETION_MESSAGE + "$" + path.replace(FOLDER_PATH + getOSSlash(), '', 1) + "$0").encode())
            waitForOK()
        elif changeType == cs.FOLDER_DELETION_MESSAGE:
            send((cs.FOLDER_DELETION_MESSAGE + "$" + path.replace(FOLDER_PATH + getOSSlash(), '', 1) + "$0").encode())
            waitForOK()
        else:
            send((cs.REVERTED_CHANGE + "$ $0").encode())
            # here if its not relevant anymore
            waitForOK()
        i += 1
    send(cs.END_UPDATES.encode())
    # empty the update list!
    updateList.clear()


# start the watchdog monitoring
def startMonitoring(path):
    patterns = ["*"]
    ignore_patterns = None
    ignore_directories = False
    case_sensitive = True
    my_event_handler = PatternMatchingEventHandler(patterns, ignore_patterns, ignore_directories, case_sensitive)
    my_event_handler.on_created = on_created
    my_event_handler.on_deleted = on_deleted
    my_event_handler.on_modified = on_modified
    my_event_handler.on_moved = on_moved

    go_recursively = True
    my_observer = Observer()
    my_observer.schedule(my_event_handler, path, recursive=go_recursively)
    my_observer.start()


# does the cycles
def startCycles():
    while True:
        doCycle()
        time.sleep(CYCLE_TIME)


# if file was created then deleted-> we just report that nothing happened!
def tidyUpdateList():
    for update in updateList:
        if update.changeType == cs.FILE_DELETION_MESSAGE:
            didCreate = False
            path = update.path
            lastIndex = updateList.index(update) - 1
            while lastIndex >= 0:
                tempChange = updateList[lastIndex]
                if tempChange.path == path:
                    if tempChange.changeType == cs.FILE_CREATION_MESSAGE:
                        didCreate = True
                    tempChange.changeType = cs.REVERTED_CHANGE
                lastIndex -= 1
                if didCreate:
                    update.changeType = cs.REVERTED_CHANGE


# individual cycle logic
def doCycle():
    # gets updated by server
    requestUpdates()
    # prepares to update server by tidying up the changes
    tidyUpdateList()
    # sends the updates
    sendUpdates()
    # disconnects to allow next user
    s.close()


# VARS
# all the files being worked on right now should be ignored by watchdog
ignoreList = []
# list of updates we need to send to server
updateList = []
# ARGS
SERVER_IP = sys.argv[1]
SERVER_PORT = int(sys.argv[2])
FOLDER_PATH = sys.argv[3]
CYCLE_TIME = float(sys.argv[4])

# if has additional arg
if len(sys.argv) > 5:
    MY_ID = sys.argv[5]
    hasID = True
else:
    hasID = False

# Actual program! xD

# bind socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# connect to server and send ID
connectToServer()
# start watchdog
startMonitoring(FOLDER_PATH)
# start the cycles
startCycles()
