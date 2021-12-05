import os.path
import json

import logging
import asyncio
from slixmpp import ClientXMPP
from slixmpp.exceptions import IqError, IqTimeout

import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

CONFIGFILENAME = "config.json"


class EchoBot(ClientXMPP):

    def __init__(self, jid, password):
        ClientXMPP.__init__(self, jid, password)

        self.add_event_handler("session_start", self.session_start)
        self.add_event_handler("message", self.message)

        # If you wanted more functionality, here's how to register plugins:
        # self.register_plugin('xep_0030') # Service Discovery
        # self.register_plugin('xep_0199') # XMPP Ping

        # Here's how to access plugins once you've registered them:
        # self['xep_0030'].add_feature('echo_demo')

        # If you are working with an OpenFire server, you will
        # need to use a different SSL version:
        # import ssl
        # self.ssl_version = ssl.PROTOCOL_SSLv3

    def session_start(self, event):
        self.send_presence()
        self.get_roster()

        # Most get_*/set_* methods from plugins use Iq stanzas, which
        # can generate IqError and IqTimeout exceptions
        #
        # try:
        #     self.get_roster()
        # except IqError as err:
        #     logging.error('There was an error getting the roster')
        #     logging.error(err.iq['error']['condition'])
        #     self.disconnect()
        # except IqTimeout:
        #     logging.error('Server is taking too long to respond')
        #     self.disconnect()

    def message(self, msg):
        if msg['type'] in ('chat', 'normal'):
            msg.reply(f"Żyje! {msg['body']}").send()


if __name__ == '__main__':
    # Ideally use optparse or argparse to get JID,
    # password, and log level.

    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)-8s %(message)s')

    JID = ""
    PASSWORD = ""
    if os.path.exists(CONFIGFILENAME):
        with open(CONFIGFILENAME, 'r') as file:
            try:
                dane = json.load(file)
                assert type(dane) == dict
                PASSWORD = dane['password']
                JID = dane['jid']
            except json.decoder.JSONDecodeError:
                print("JSONDecodeError")
                sys.exit(1)
            except AssertionError:
                print("Bad json format")
                sys.exit(1)
    else:
        with open(CONFIGFILENAME, 'w') as file:
            json.dump({"jid": JID, "password": PASSWORD}, file, indent=4)
        print("Created config file, fill it!")
        sys.exit(1)

    xmpp = EchoBot(JID, PASSWORD)
    xmpp.connect()
    xmpp.process(forever=True)
