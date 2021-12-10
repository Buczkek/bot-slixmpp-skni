import os.path
import json
import types

import logging
import asyncio
from slixmpp import ClientXMPP
from slixmpp.exceptions import IqError, IqTimeout

import slixmpp_omemo
from slixmpp_omemo import PluginCouldNotLoad, MissingOwnKey, EncryptionPrepareException
from slixmpp_omemo import UndecidedException, UntrustedException, NoAvailableSession


import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

CONFIGFILENAME = "config.json"
COMMAND_PREFIX = '!'


class EchoBot(ClientXMPP):

    def __init__(self, jid, password):
        ClientXMPP.__init__(self, jid, password)

        self.add_event_handler("session_start", self.on_session_start)
        self.add_event_handler("message", self.on_message)

        self.commands = {}
        self.commands.setdefault('no_command', no_command_found)

        self.bind_command('echo', echo)

        # If you wanted more functionality, here's how to register plugins:
        # self.register_plugin('xep_0030') # Service Discovery
        # self.register_plugin('xep_0199') # XMPP Ping

        # Here's how to access plugins once you've registered them:
        # self['xep_0030'].add_feature('echo_demo')

        # If you are working with an OpenFire server, you will
        # need to use a different SSL version:
        # import ssl
        # self.ssl_version = ssl.PROTOCOL_SSLv3

    def on_session_start(self, event):
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

    def on_message(self, msg):
        if msg['type'] in ('chat', 'normal'):
            print(self['xep_0384'].is_encrypted(msg))
            self.process_command(msg)

    async def message(self, msg, allow_untrusted = True):

        mfrom = mto = msg['from']
        mtype = msg['type']

        try:
            encrypted = msg['omemo_encrypted']
            body = self['xep_0384'].decrypt_message(encrypted, mfrom, allow_untrusted)
            decoded = body.decode('utf8')
            if self.is_command(decoded):
                await self.handle_command(mto, mtype, decoded)
            return None
        except (MissingOwnKey,):
            # The message is missing our own key, it was not encrypted for
            # us, and we can't decrypt it.
            await self.plain_reply(
                mto, mtype,
                'Error: Message not encrypted for me.',
            )
            return None
        except (NoAvailableSession,) as exn:
            # We received a message from that contained a session that we
            # don't know about (deleted session storage, etc.). We can't
            # decrypt the message, and it's going to be lost.
            # Here, as we need to initiate a new encrypted session, it is
            # best if we send an encrypted message directly. XXX: Is it
            # where we talk about self-healing messages?
            await self.encrypted_reply(
                mto, mtype,
                'Error: Message uses an encrypted '
                'session I don\'t know about.',
            )
            return None
        except (UndecidedException, UntrustedException) as exn:
            # We received a message from an untrusted device. We can
            # choose to decrypt the message nonetheless, with the
            # `allow_untrusted` flag on the `decrypt_message` call, which
            # we will do here. This is only possible for decryption,
            # encryption will require us to decide if we trust the device
            # or not. Clients _should_ indicate that the message was not
            # trusted, or in undecided state, if they decide to decrypt it
            # anyway.
            await self.plain_reply(
                mto, mtype,
                "Error: Your device '%s' is not in my trusted devices." % exn.device,
            )
            # We resend, setting the `allow_untrusted` parameter to True.
            await self.message(msg, allow_untrusted=True)
            return None
        except (EncryptionPrepareException,):
            # Slixmpp tried its best, but there were errors it couldn't
            # resolve. At this point you should have seen other exceptions
            # and given a chance to resolve them already.
            await self.plain_reply(mto, mtype, 'Error: I was not able to decrypt the message.')
            return None
        except (Exception,) as exn:
            await self.plain_reply(mto, mtype, 'Error: Exception occured while attempting decryption.\n%r' % exn)
            raise

        return None

    def bind_command(self, command: str, function: types.FunctionType):
        assert command.isalpha(), "command name should be only made of alphabet letters"
        self.commands[command] = function
        return True

    def unbind_command(self, command):
        func = self.commands.get(command)
        if func is not None:
            self.commands.pop(command)
            return True
        return False

    def add_command_reply(self):
        pass

    def process_command(self, message):
        body = message['body']
        if not body.startswith(COMMAND_PREFIX):
            return False

        temp = body[1:].split(' ')
        command = temp[0]
        args = temp[1:]
        reply = self.commands.get(command, no_command_found)(args)
        if reply is not None:
            message.reply(reply).send()


if __name__ == '__main__':

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


def echo(args):
    msg = ' '.join(args)
    return msg


def no_command_found(args):
    return "No command found"


xmpp = EchoBot(JID, PASSWORD)
# xmpp.register_plugin('xep_0030')  # Service Discovery
# xmpp.register_plugin('xep_0199')  # XMPP Ping
xmpp.register_plugin('xep_0380')  # Explicit Message Encryption

DATA_DIR = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'omemo',
    )

os.makedirs(DATA_DIR, exist_ok=True)

try:
    xmpp.register_plugin(
        'xep_0384',
        {
            'data_dir': DATA_DIR,
        },
        module=slixmpp_omemo,
    )  # OMEMO

except (PluginCouldNotLoad,):
    print('And error occured when loading the omemo plugin.')
    sys.exit(1)

xmpp.connect()
xmpp.process(forever=True)
