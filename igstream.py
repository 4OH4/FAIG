#!/usr/bin/env python3

#  Copyright (c) Lightstreamer Srl.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import sys
import logging
import threading
import time
import traceback

# log = logging.getLogger()

# Modules aliasing and function utilities to support a
# very coarse version differentiation between Python 2 and Python 3.
PY3 = sys.version_info[0] == 3
PY2 = sys.version_info[0] == 2

if PY3:
    from urllib.request import urlopen as _urlopen
    from urllib.parse import (urlparse as parse_url, urljoin, urlencode)


    def _url_encode(params):
        return urlencode(params).encode("utf-8")


    def _iteritems(d):
        return iter(d.items())


    def wait_for_input():
        input("{0:-^80}\n".format("HIT CR TO UNSUBSCRIBE AND DISCONNECT FROM \
LIGHTSTREAMER"))

else:
    from urllib import (urlopen as _urlopen, urlencode)
    from urlparse import urlparse as parse_url
    from urlparse import urljoin


    def _url_encode(params):
        return urlencode(params)


    def _iteritems(d):
        return d.iteritems()


    def wait_for_input():
        raw_input("{0:-^80}\n".format("HIT CR TO UNSUBSCRIBE AND DISCONNECT FROM \
LIGHTSTREAMER"))

CONNECTION_URL_PATH = "lightstreamer/create_session.txt"
BIND_URL_PATH = "lightstreamer/bind_session.txt"
CONTROL_URL_PATH = "lightstreamer/control.txt"

OP = {
    'ADD': 'add',  # Request parameter to create and activate a new Table.
    'DELETE': 'delete',  # Request parameter to delete a previously created Table.
    'DESTROY': "destroy"  # Request parameter to force closure of an existing session.
}

# List of possible server responses
PROBE_CMD = "PROBE"
END_CMD = "END"
LOOP_CMD = "LOOP"
ERROR_CMD = "ERROR"
SYNC_ERROR_CMD = "SYNC ERROR"
OK_CMD = "OK"


class Subscription(object):
    """Represents a Subscription to be submitted to a Lightstreamer Server."""

    def __init__(self, mode, items, fields, adapter=""):
        self.logger = logging.getLogger('Subscription')
        self.logger.debug('igstream.py Subscription __init__')
        self.item_names = items
        self._items_map = {}
        self.field_names = fields
        self.adapter = adapter
        self.mode = mode
        self.snapshot = "true"
        self._listeners = []
        self._results = []

    def _decode(self, value, last):
        """Decode the field value according to
        Lightstremar Text Protocol specifications.
        """
        self.logger.debug('igstream.py Subscription _decode')
        if value == "$":
            return u''
        elif value == "#":
            return None
        elif not value:
            return last
        elif value[0] in "#$":
            value = value[1:]

        return value

    def addlistener(self, listener):
        self.logger.debug('igstream.py Subscription __init__')
        self._listeners.append(listener)

    def notifyupdate(self, item_line):
        """Invoked by LSClient each time Lightstreamer Server pushes
        a new item event.
        """
        self.logger.debug('igstream.py Subscription notifyupdate')
        # Tokenize the item line as sent by Lightstreamer
        toks = item_line.rstrip('\r\n').split('|')
        undecoded_item = dict(list(zip(self.field_names, toks[1:])))

        # Retrieve the previous item stored into the map, if present.
        # Otherwise create a new empty dict.
        item_pos = int(toks[0])
        curr_item = self._items_map.get(item_pos, {})
        # Update the map with new values, merging with the
        # previous ones if any.
        self._items_map[item_pos] = dict([
            (k, self._decode(v, curr_item.get(k))) for k, v
            in list(undecoded_item.items())
        ])
        # Make an item info as a new event to be passed to listeners
        item_info = {
            'pos': item_pos,
            'name': self.item_names[item_pos - 1],
            'values': self._items_map[item_pos]
        }

        self._results.append(item_info)
        # Update each registered listener with new event
        for on_item_update in self._listeners:
            on_item_update(item_info)


class LSClient(object):
    """Manages the communication with Lightstreamer Server"""

    def __init__(self, base_url, adapter_set="", user="", password=""):
        self.logger = logging.getLogger('LSClient')
        self.logger.debug('igstream.py LSClient __init__')
        self._base_url = parse_url(base_url)
        self._adapter_set = adapter_set
        self._user = user
        self._password = password
        self._session = {}
        self._subscriptions = {}
        self._current_subscription_key = 0
        self._stream_connection = None
        self._stream_connection_thread = None
        self._bind_counter = 0

    def _encode_params(self, params):
        """Encode the parameter for HTTP POST submissions, but
        only for non empty values..."""
        self.logger.debug('igstream.py LSClient _encode_params')
        return _url_encode(
            dict([(k, v) for (k, v) in _iteritems(params) if v])
        )

    def _call(self, base_url, url, body):
        """Open a network connection and performs HTTP Post
        with provided body.
        """
        self.logger.debug('igstream.py LSClient _call')
        # Combines the "base_url" with the
        # required "url" to be used for the specific request.
        url = urljoin(base_url.geturl(), url)
        return _urlopen(url, data=self._encode_params(body))

    def _set_control_link_url(self, custom_address=None):
        """Set the address to use for the Control Connection
        in such cases where Lightstreamer is behind a Load Balancer.
        """
        self.logger.debug('igstream.py LSClient _set_control_link_url')
        if custom_address is None:
            self._control_url = self._base_url
        else:
            parsed_custom_address = parse_url("//" + custom_address)
            self._control_url = parsed_custom_address._replace(
                scheme=self._base_url[0]
            )

    def _control(self, params):
        """Create a Control Connection to send control commands
        that manage the content of Stream Connection.
        """
        self.logger.debug('igstream.py LSClient _control')
        params["LS_session"] = self._session["SessionId"]
        response = self._call(self._control_url, CONTROL_URL_PATH, params)
        return response.readline().decode("utf-8").rstrip()

    def _read_from_stream(self):
        """Read a single line of content of the Stream Connection."""
        self.logger.debug('igstream.py LSClient _read_from_stream')
        line = self._stream_connection.readline().decode("utf-8").rstrip()
        self.logger.debug(line)
        return line

    def connect(self):
        """Establish a connection to Lightstreamer Server to create
        a new session.
        """
        self.logger.debug('igstream.py LSClient connect')
        self._stream_connection = self._call(
            self._base_url,
            CONNECTION_URL_PATH,
            {
                "LS_op2": 'create',
                "LS_cid": 'mgQkwtwdysogQz2BJ4Ji kOj2Bg',
                "LS_adapter_set": self._adapter_set,
                "LS_user": self._user,
                "LS_password": self._password}
        )

        while 1:
            stream_line = self._read_from_stream()
            self._handle_stream(stream_line)
            if ':' not in stream_line:
                break

    def bind(self):
        """Replace a completely consumed connection in listening for an active
        Session.
        """
        self.logger.debug('igstream.py LSClient bind')
        self._stream_connection = self._call(
            self._control_url,
            BIND_URL_PATH,
            { "LS_session": self._session["SessionId"] }
        )

        self._bind_counter += 1
        stream_line = self._read_from_stream()
        self._handle_stream(stream_line)

    def _handle_stream(self, stream_line):
        self.logger.debug('igstream.py LSClient _handle_stream')
        if stream_line == OK_CMD:
            # Parsing session inkion
            while 1:
                next_stream_line = self._read_from_stream()
                if next_stream_line:
                    [param, value] = next_stream_line.split(':', 1)
                    self._session[param] = value
                else:
                    break

            # Setup of the control link url
            self._set_control_link_url(self._session.get("ControlAddress"))

            # Start a new thread to handle real time updates sent
            # by Lightstreamer Server on the stream connection.
            self._stream_connection_thread = threading.Thread(
                name="STREAM-CONN-THREAD-{0}".format(self._bind_counter),
                target=self._receive
                # args=(self._results[self._current_subscription_key])
            )
            self._stream_connection_thread.setDaemon(True)
            self._stream_connection_thread.start()
        else:
            lines = self._stream_connection.readlines()
            lines.insert(0, stream_line)
            self.logger.error("Server response error: \n{0}".format("".join(lines)))
            raise IOError()

    def _join(self):
        """Await the natural STREAM-CONN-THREAD termination."""
        self.logger.debug('igstream.py LSClient _join')
        if self._stream_connection_thread:
            self.logger.debug("igstream.py LSClient _join: Waiting for thread to terminate")
            self._stream_connection_thread.join()
            self._stream_connection_thread = None
            self.logger.debug("igstream.py LSClient _join: Thread terminated")

    def disconnect(self):
        """Request to close the session previously opened with
        the connect() invocation.
        """
        self.logger.debug('igstream.py LSClient disconnect')
        if self._stream_connection is not None:
            # Close the HTTP connection
            self._stream_connection.close()
            self.logger.debug("igstream.py LSClient disconnect: Connection closed")
            print("DISCONNECTED FROM LIGHTSTREAMER")
        else:
            self.logger.warning("No connection to Lightstreamer")

    def destroy(self):
        """Destroy the session previously opened with
        the connect() invocation.
        """
        self.logger.debug('igstream.py LSClient destroy')
        if self._stream_connection is not None:
            server_response = self._control({"LS_op": OP['DESTROY']})
            if server_response == OK_CMD:
                # There is no need to explicitly close the connection,
                # since it is handled by thread completion.
                self._join()
            else:
                self.logger.warning("No connection to Lightstreamer")

    def subscribe(self, subscription):
        """
        Perform a subscription request to Lightstreamer Server.
        :param subscription:
        :return: _current_subscription_key (int)
                success (bool)
        """
        self.logger.debug('igstream.py LSClient subscribe')
        # Register the Subscription with a new subscription key
        self._current_subscription_key += 1
        self._subscriptions[self._current_subscription_key] = subscription

        try:
            # Send the control request to perform the subscription
            server_response = self._control({"LS_session": self._session['SessionId'],
                                             "LS_table": self._current_subscription_key,
                                             "LS_op": OP['ADD'],
                                             # "LS_data_adapter": subscription.adapter,
                                             "LS_mode": subscription.mode,
                                             "LS_schema": " ".join(subscription.field_names),
                                             "LS_id": " ".join(subscription.item_names)})
            success = server_response == 'OK'
            self.logger.debug("igstream.py LSClient subscribe: {0} Server response ---> <{1}>".format(subscription.item_names, server_response))
        except:
            success = False
            self.logger.warning("igstream.py LSClient subscribe: {0} : errors occured during subscribe, did not complete".format(subscription.item_names))
        
        return self._current_subscription_key, success

    def unsubscribe(self, subcription_key):
        """Unregister the Subscription associated to the
        specified subscription_key.
        """
        self.logger.debug('igstream.py LSClient unsubscribe')
        if subcription_key in self._subscriptions:
            server_response = self._control({
                "LS_Table": subcription_key,
                "LS_op": OP['DELETE']
            })
            self.logger.debug("igstream.py LSClient unsubscribe: Server response ---> <{0}>".format(server_response))

            if server_response == OK_CMD:
                del self._subscriptions[subcription_key]
                self.logger.debug("igstream.py LSClient unsubscribe: Unsubscribed successfully")
            else:
                self.logger.warning("Server error:" + server_response)
        else:
            self.logger.warning("No subscription key {0} found!".format(subcription_key))

    def _forward_update_message(self, update_message):
        """Forwards the real time update to the relative
        Subscription instance for further dispatching to its listeners.
        """
        self.logger.debug('igstream.py LSClient _forward_update_message')
        self.logger.debug(
            "igstream.py LSClient _forward_update_message: Received update message ---> <{0}>".format(update_message))
        tok = update_message.split(',', 1)
        table, item = int(tok[0]), tok[1]
        if table in self._subscriptions:
            self._subscriptions[table].notifyupdate(item)
        else:
            self.logger.warning("No subscription found!")

    def _receive(self):
        self.logger.debug('igstream.py LSClient _receive')
        rebind = False
        receive = True
        while receive:
            self.logger.debug("igstream.py LSClient _receive: Waiting for a new message")
            try:
                message = self._read_from_stream()
                self.logger.debug("igstream.py LSClient _receive: Received message ---> <{0}>".format(message))
            except Exception:
                self.logger.error("Communication error")
                print(traceback.format_exc())
                message = None

            if message is None:
                receive = False
                self.logger.warning("No new message received")
            elif message == PROBE_CMD:
                # Skipping the PROBE message, keep on receiving messages.
                self.logger.debug("igstream.py LSClient _receive: PROBE message")
            elif message.startswith(ERROR_CMD):
                # Terminate the receiving loop on ERROR message
                receive = False
                self.logger.error("ERROR")
            elif message.startswith(LOOP_CMD):
                # Terminate the the receiving loop on LOOP message.
                # A complete implementation should proceed with
                # a rebind of the session.
                self.logger.debug("igstream.py LSClient _receive: LOOP")
                receive = False
                rebind = True
            elif message.startswith(SYNC_ERROR_CMD):
                # Terminate the receiving loop on SYNC ERROR message.
                # A complete implementation should create a new session
                # and re-subscribe to all the old items and relative fields.
                self.logger.error("SYNC ERROR")
                receive = False
            elif message.startswith(END_CMD):
                # Terminate the receiving loop on END message.
                # The session has been forcibly closed on the server side.
                # A complete implementation should handle the
                # "cause_code" if present.
                self.logger.info("Connection closed by the server")
                receive = False
            elif message.startswith("Preamble"):
                # Skipping Preamble message, keep on receiving messages.
                self.logger.debug("igstream.py LSClient _receive: Preamble")
            else:
                self._forward_update_message(message)

        if not rebind:
            self.logger.debug("igstream.py LSClient _receive: Closing connection")
            # Clear internal data structures for session
            # and subscriptions management.
            self._stream_connection.close()
            self._stream_connection = None
            self._session.clear()
            self._subscriptions.clear()
            self._current_subscription_key = 0
        else:
            self.logger.debug("igstream.py LSClient _receive: Binding to this active session")
            self.bind()


class IGStream(object):

    def __init__(self, igclient=None, loginresponse=None):
        from igclient import IGClient

        self.logger = logging.getLogger('IGStream')
        self.logger.debug('igstream.py IGStream __init__')

        # logging.basicConfig(level=logging.INFO)

        # reuse login if possible,  else create session
        if igclient == None or loginresponse == None:
            igclient = IGClient()
            loginresponse = igclient.session()
        self.igclient = igclient
        self.loginresponse = loginresponse
        SERVER = self.loginresponse['lightstreamerEndpoint']
        ACCOUNTID = self.loginresponse['currentAccountId']
        PASSWORD = 'CST-' + self.igclient.auth['CST'] + '|XST-' + self.igclient.auth['X-SECURITY-TOKEN']

        # Establishing a new connection to Lightstreamer Server
        self.logger.debug("igstream.py IGStream: Starting connection")
        self.lightstreamer_client = LSClient(SERVER, "", ACCOUNTID, PASSWORD)
        try:
            self.lightstreamer_client.connect()
        except Exception as e:
            print("Unable to connect to Lightstreamer Server: {}".format(SERVER))
            print(traceback.format_exc())
            sys.exit(1)

    def fetch_one(self, subscription):
        self.logger.debug('igstream.py IGStream fetch_one')

        # we may get more than one, or none, in which case this blocks
        # so yeah, fetch_one is a terrible name
        results = None

        # we're going to need a blank listen
        def do_nothing(self):
            pass

        # set the subscription
        sub_key, success = self.subscribe(subscription=subscription, listener=do_nothing)

        if success:
            # wait for input THIS IS BLOCKING
            count = 0
            while count < 1000:  # if nothing after 10s, bail
                count += 1
                if len(self.lightstreamer_client._subscriptions[sub_key]._results) > 0:

                    # grab the results before we lose it on unsubscribe
                    results = self.lightstreamer_client._subscriptions[sub_key]._results
                    results = results[0]

                    break
                else:
                    time.sleep(0.01)

        # clean up
        self.unsubscribe(sub_key)

        return results

    def subscribe(self, subscription, listener):
        self.logger.debug('igstream.py IGStream subscribe')

        # Adding the "on_item_update" function to Subscription
        subscription.addlistener(listener)

        # Registering the Subscription
        sub_key, success = self.lightstreamer_client.subscribe(subscription)
        return sub_key, success

    def unsubscribe(self, sub_key):
        self.logger.debug('igstream.py IGStream unsubscribe')
        # Unsubscribing from Lightstreamer by using the subscription key
        self.lightstreamer_client.unsubscribe(sub_key)

    def disconnect(self):
        self.logger.debug('igstream.py IGStream disconnect')
        # Disconnecting
        self.lightstreamer_client.disconnect()
