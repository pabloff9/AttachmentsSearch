"""
This code was based on GPLv3-licensed unity_gdrive_daemon.py, Copyright 2012 Canonical Ltd.
and has been modified to suit this project.

All modifications are Copyright 2013, Pablo Almeida de Andrade.

GPLv3

"""


import sys
from gi.repository import GLib, GObject, Gio
from gi.repository import Accounts, Signon
from gi.repository import GData



class SignOnAuthorizer(GObject.Object, GData.Authorizer):
    __g_type_name__ = "SignOnAuthorizer"
    def __init__(self, account_service):
        GObject.Object.__init__(self)
        self._account_service = account_service
        self._main_loop = None
        self._token = None

    def do_process_request(self, domain, message):
        message.props.request_headers.replace('Authorization', 'OAuth %s' % (self._token, ))

    def do_is_authorized_for_domain(self, domain):
        return True if self._token else False

    def do_refresh_authorization(self, cancellable):
        if self._main_loop:
            print("Authorization already in progress")
            return False

        old_token = self._token
        # Get the global account settings
        auth_data = self._account_service.get_auth_data()
        identity = auth_data.get_credentials_id()
        session_data = auth_data.get_parameters()
        self._auth_session = Signon.AuthSession.new(identity, auth_data.get_method())
        self._main_loop = GObject.MainLoop()
        self._auth_session.process(session_data,
                auth_data.get_mechanism(),
                self.login_cb, None)
        if self._main_loop:
            self._main_loop.run()
        if self._token == old_token:
            print("Got the same token")
            return False
        else:
            print("Got token: %s" % (self._token, ))
            return True
        
    
    

    def login_cb(self, session, reply, error, user_data):
            print("login finished")
            self._main_loop.quit()
            self._main_loop = None
            if error:
                print("Got authentication error:", error.message)
                return
            if "AuthToken" in reply:
                self._token = reply["AuthToken"]
            elif "AccessToken" in reply:
                self._token = reply["AccessToken"]
            else:
                print("Didn't find token in session:", reply)

if __name__ == "__main__":

    GObject.MainLoop().run()
