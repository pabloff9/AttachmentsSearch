import imaplib
import email.header
import re
import urllib.request
import json
import emailParsing


#FIXME: "if there are no search results, the application crashes.

"""
This class encapsulates an IMAP connection to the Gmail server.
"""
class GmailConnection:
    
    """
    This class represents a list of UIDs (message unique identifiers).
    It is used by internal methods of the GmailConnection class to pass
    and receive lists of UIDs, that are usually returned as binary space-separated
    strings from IMAP search functions, so this class makes it easier to deal with
    them as actual lists and to convert them to comma-separated strings of UIDs,
    as expected by IMAP calls.
    """
    class EmailUidsList:
        uidsList = []
        
        """
        The constructor expects a string that looks like the result
        of a search call to the imap server, that is, a space-separated
        bytes string.
        """
        def __init__(self, searchResult):
            
            if (searchResult[0] != "OK"):
                raise Exception
            
            self.uidsList = searchResult[1][0].decode().split(" ")
            
        
        """
        This method converts the list of UIDs into a string of comma separated
        UIDs, as expected by IMAP calls, such as fetch.
        """    
        def toCommaSeparated(self):
#             return "".join(str(self.uidsList))
            string = ""
            if (len(self.uidsList) != 0):
                string += self.uidsList[0]
                for i in range(1, len(self.uidsList)):
                    string += "," + self.uidsList[i]
            
            return string
                
        
        
     
    connection = None
    authenticationManager = None
    emailAddress = None
    credentials = None
    
    
    def __init__(self):
               
        self.credentials = self.getAccountCredentials() 
        self.emailAddress = self.getEmailAddress(self.credentials)
        self.authenticateToIMAP()

    """
    Query Ubuntu Online Accounts for the credentials of a registered Gmail account.
    """
    def getAccountCredentials(self):
        
        from googleAuthorization import SignOnAuthorizer
        from gi.repository import Accounts, GObject
         
        manager = Accounts.Manager()
        googleService = None
        for account_service in manager.get_enabled_account_services():
                if (account_service.get_account().get_provider_name() == 'google'):
                    googleService = account_service
                    break
         
        authorizer = SignOnAuthorizer(googleService)
         
        authorizer.do_refresh_authorization(True)
        
        if (not authorizer.do_is_authorized_for_domain("imap.gmail.com")):
            raise Exception
        
        return authorizer
    
    """
    Gets and returns the authenticated user's email address.
    """
    def getEmailAddress(self, authorizer):
        
        apiAddress = "https://www.googleapis.com/oauth2/v1/userinfo?access_token="
        url = apiAddress + authorizer._token
        response = urllib.request.urlopen(url).read()
        
        parsedJSON = json.loads(response.decode())
        
        return parsedJSON["email"]
    
    """
    Authenticates to the user's email account via IMAP.
    """
    def authenticateToIMAP(self):
        
        auth_string = 'user=%s\1auth=Bearer %s\1\1' % (self.emailAddress, self.credentials._token)
         
        self.connection = imaplib.IMAP4_SSL("imap.gmail.com")
        self.connection.authenticate('XOAUTH2', lambda x: auth_string)
    
    
    """
    Searches messages with attachments.
    The second parameter is used to narrow down the search.
    Any Gmail specific keywords, like "is:unread" is valid,
    and any combination of them as well.
    """
    def search(self, keywords=None):
#         result = self.connection.uid("search", None, "SUBJECT Teste")
        
        if (keywords != None):
            result = self.connection.uid("search", None, 'X-GM-RAW "has:attachment ' + keywords + '"')
        else:
            result = self.connection.uid("search", None, 'X-GM-RAW "has:attachment"')
        return self.EmailUidsList(result)
    
    
    """
    Returns a list of attachment details, which are a tuple of 
    (UID, indexOfTheAttachmentInTheMessage, filename, encoding) for every attachment
    found in the given emailUidsList.
    """
    def getAttachmentsDetails(self, emailUidsList):
        attachmentDetailsList = []
    
        structures = self.fetchBodyStructures(emailUidsList)
        
        for indexInTheList, structure in enumerate(structures):
            pattern = re.compile('ATTACHMENT" \("FILENAME" "(.*?)"\)\)')
            m = pattern.findall(str(structure))
            
            emailUid = emailUidsList.uidsList[indexInTheList]
             
            if len(m) > 0:
                for indexInTheMessage, group in enumerate(m):
                    decodedThing = email.header.decode_header(group)
                    if (decodedThing[0][1] != None):
                        encoding = decodedThing[0][1]
                        filename = decodedThing[0][0]
                        attachmentDetailsList.append((emailUid, indexInTheMessage, filename, encoding))
                    else:
                        attachmentDetailsList.append((emailUid, indexInTheMessage, group, None))
            else:
                continue
        
        return attachmentDetailsList
    
    
    """
    Selects the user's All Mail folder.
    """
    def selectAllMailFolder(self):
        result, folders = self.connection.list()
        
        if (result != 'OK'):
            raise Exception
        
        
        allMailFolderName = None
        for folder in folders:
            
            if (b'\All)' in folder):
                splitted = folder.split(b"[Gmail]")
                allMailFolderName = '"'+ "[Gmail]" + splitted[-1].decode("utf-8")
                #print('Gotcha. Folder name: "' + str(allMailFolderName))
                break
        self.connection.select(allMailFolderName)
        
    """
    Fetches messages from the server.
    This method returns a list of email.message objects.
    """
    def fetchMessages(self, emailUidsList):
        result, data = self.connection.uid("fetch", emailUidsList.toCommaSeparated(), '(RFC822)');
        
        if (result != "OK"):
            raise Exception
        
        emails = []
                
        for i in range(len(data)):
            if (i % 2 == 0):
                emails.append(email.message_from_bytes(data[i][0]))
        
        
        return emails
    
    def fetchSingleMessage(self, uid):
        result, data = self.connection.uid("fetch", uid.encode(), '(RFC822)')
        
        if (result != "OK"):
            raise Exception
        
        return email.message_from_bytes(data[0][1])
    
    
    """
    Downloads a attachment from a given attachment details tuple, which is a tuple
    of (UID, indexInTheMessage, filename, encoding).
    The result is a tuple of the type (filename, byteString), where byteString is the 
    content of the file.
    """
    def downloadAttachment(self, attachmentDetails):
        
        #FIXME: This method assumes there's only one attachment with a certain name in the message,
        # which may not be true
        
        #Download the message
        uid = attachmentDetails[0]
        message = self.fetchSingleMessage(uid)
        
        #Parse the message to find the attachment
        
        for part in message.walk():
            
            filenameHeader = part.get_filename()
            if (filenameHeader != None):
                                
                filename, encoding = email.header.decode_header(filenameHeader)[0]                
                
                if (filename == attachmentDetails[2]):
                    if (encoding != None):
                        filename = filename.decode(encoding)
                        attachment = part.get_payload(decode=True)
                    break

        #Copy the attachment to a bytes string
        return (filename, attachment)
        
    
    """
    Fetches the BODYSTRUCTURE of messages from the server.
    This method returns a list of BODYSTRUCTURE strings.
    """
    def fetchBodyStructures(self, emailUidsList):
        result, data = self.connection.uid("fetch", emailUidsList.toCommaSeparated(), 'BODYSTRUCTURE')
        if (result != "OK"):
            raise Exception
        else:
            return data

    

def getAttachment(email):
    import emailParsing
    
    return emailParsing.parse(email)["attachments"]


def fetchASingleMessageMatchingASearch(connection, keywords):
    results = gmail.search(keywords)
    aMessageUID = results.uidsList[0]
    result, data = connection.connection.uid("fetch", aMessageUID, '(RFC822)');
    return data

gmail = GmailConnection()
gmail.selectAllMailFolder()

while (True):

    messagesIds = gmail.search(input("\nSearch keywords: "))    
    list = gmail.getAttachmentsDetails(messagesIds)
    
    for i, item in enumerate(list):
        print(str(i) +": "+ str(item[2]))
    
    filename, attachment = gmail.downloadAttachment(list[int(input("\nChoose the index: "))])
    
    open("/home/pablo/" + filename, "wb").write(attachment)
      
#     for attachment in :
#         print(attachment)
#         anexos.write(str(attachment) + "\n")
#     anexos.flush()
#     messagesIds = gmail.search(input("\nSearch keywords: "))
#      
#     message = gmail.fetchMessages(messagesIds)[0]
#      
#     from io import StringIO
#      
#     content = emailParsing.parse(StringIO(str(message)))
#      
#     print(content)
#      
#     result = fetchASingleMessageMatchingASearch(gmail, "docx")
#     message = result[0][1]
#     open("/home/pablo/email.txt", "wb").write(message)
#     
#     emailobj = email.message_from_bytes(message)
#     
#     print(emailobj.is_multipart())
#     
     
     


