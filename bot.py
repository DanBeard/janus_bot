"""
Copyright (c) 2014, Daniel Beard
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of the copyright holder nor the
      names of its contributors may be used to endorse or promote products
      derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""


from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import Factory, Protocol, ClientFactory
from twisted.internet import reactor, protocol, defer
from twisted.internet.endpoints import TCP4ClientEndpoint
import json
import re
import math
#Constants
FOLLOW_DIST = 1.5  # if the update distance is less than this, it won't move (to stop clipping)

class STATES:
    SLEEPING = 0
    LOGGING_IN = 1
    STAYING = 2
    FOLLOWING = 3

class BotProtocol(LineReceiver):

    def __init__(self, userid_txt='userid.txt', name="__minion__", room_id='eab63d0ea060b828578a4ae044f24d03', owner="yawgmoth",
                 command_line_input=False):
        self.state = STATES.SLEEPING
        self.name = name
        self.room_id = room_id
        self.owner = owner
        self.listeners = []
        if userid_txt is not None:
            try:
                self.parse_avatar_txt(userid_txt)
            except Exception as e:  # emergency backup avatar
                print "Error parsing userid.txt: " + str(e)
                self.avatar_html = "<FireBoxRoom>|<Assets>|<AssetObject~id=&nullhead&~/>|<AssetObject~id=&BOT&~src=&http://varx.org/janusvr/avatars/claptrap/Claptrap5.obj&~mtl=&http://varx.org/janusvr/avatars/claptrap/Claptrap5.mtl&~/>|</Assets>|<Room>|\
                <Ghost~id=&%s&~head_id=&nullhead&~body_id=&BOT&~scale=&1.2~1.2~1.2&~col=&1.66~1.66~1.66&~lighting=&false&~eye_pos=&0~0.5~-0.25&~/>|</Room>|</FireBoxRoom>|" % (self.name)



        #avatar
        #TODO: figure out what each one of these values represents
        self.avatar_pos = [float(x) for x in
                            "-0.0822233 -0.960175 6.24151 0.00863815 -0.14263 -0.989738 0.00863815 -0.14263 -0.989738 0.00124479 0.989776 -0.142625".split(" ")]
        self.avatar_scale = 1
        #self.avatar_html = "<FireBoxRoom>|<Assets>|</Assets>|<Room>|<Ghost~id=&%s&~scale=&1.00~1.00~1.00&~/>|</Room>|</FireBoxRoom>|" % (self.name)
        #state specific variables
        self.following = None

        #apply command- response async listeners
        self.listeners.append(self.chatListener)
        self.listeners.append(self.followingListener)

        if command_line_input:
            reactor.callInThread(self._command_line_input)


    def parse_avatar_txt(self, file_name):
        with open(file_name, 'r') as user_file:
            user_txt = user_file.read()
            self.name = re.search(r"Ghost id=[\"|\']([\w ]*)[\"|\']", user_txt, flags=re.MULTILINE).group(1)
            # find everything in between < >
            tags = re.findall(r'<.*>', user_txt)
            #now join it back up adn replace everything
            self.avatar_html = '|'.join(tags).replace(' ', '~').replace('"', '&')


    def connectionMade(self):
        LineReceiver.connectionMade(self)
        self.state = STATES.LOGGING_IN
        self.login()


    def _command_line_input(self):
        """
        Blocking method. DO NOT CALL FROM REACTOR!
        Will take user input using raw_input and pass it as a chat or command
        """
        while True:
            chat = raw_input(":")
            reactor.callFromThread(self.sendChat, chat, True)

    @defer.inlineCallbacks
    def login(self):
        self.sendLine(json.dumps({"method": "logon", "data":{ "userId": self.name,"version": "25.5", "roomId": self.room_id}}))
        yield self.waitForOkay()
        self.sendLine(json.dumps({"method": "subscribe", "data": {"roomId": self.room_id}}))
        yield self.waitForOkay()
        self.sendLine(json.dumps({"method": "enter_room", "data": {"roomId": self.room_id}}))
        self.state = STATES.STAYING
        self.tick()

    def setState(self, state):
        self.state = state

    def getAvatarString(self, pos=None, scale=None):
        """
        Get the full avatar string to pass along to the server with the move command
        @param pos: (Optional) The position to be at. Will default to current position.
        Must be 12 floats, or a string of space separated floats.
        [x, y, z, pitch, yaw, roll, head_x, head_y, head_z, head_pitch, head_yaw, head_roll]
        @type pos: list[float] | str
        @param scale: (Optional) The scale of the avatar. Will default to current scale
        """
        pos = self.avatar_pos if pos is None else pos
        scale = self.avatar_scale if scale is None else scale

        if type(pos) == str:
            pos = [float(x) for x in pos.split(" ")]

        self.avatar_pos = pos
        self.avatar_scale = scale

        #TODO: Actually parse and reconstruct these instead of treating it like a magic string
        return ' '.join([str(x) for x in self.avatar_pos]) + " . " + self.avatar_html


    def tick(self):
        """
        tick the state machine
        """
        if self.state == STATES.STAYING:
            self.sendLine(json.dumps({"method": "move", "data": self.getAvatarString()}))
        elif self.state == STATES.FOLLOWING:
            pass  # we don't need to do anything, handled async
        #tick
        reactor.callLater(1.5, self.tick)

    def lineReceived(self, line):
        """
        Called by twisted when a new JSON line comes in
        """
        msg = json.loads(line)
        to_remove = []
        #go through all the listeners and eat those that return True
        for listener in self.listeners:
            if listener(msg):  # if they want to be eaten
                to_remove.append(listener)

        #only do this if we have something to remove
        if len(to_remove) > 0:
            self.listeners = [x for x in self.listeners if x not in to_remove]

    def appendListener(self, listener):
        """
        Add the listener to the listener list in a reactor-safe way
        (Don't add listeners to the list manually because you might add them while we're iterating)
        """
        reactor.callLater(0, lambda: self.listeners.append(listener))

    def do_follow(self, new_pos):
        pos = self.avatar_pos
        dist = math.sqrt((self.latest_follow_pos[0] - pos[0])**2 + (self.latest_follow_pos[1] - pos[1])**2 + (self.latest_follow_pos[2] - pos[2])**2)
        if dist > float(self.avatar_scale) * FOLLOW_DIST:
            to_send = self.getAvatarString(pos=new_pos)
            #send it .25 second later
            self.sendLine(json.dumps({"method": "move", "data": to_send}))
        else:
            self.sendLine(json.dumps({"method": "move", "data": self.getAvatarString()}))

    def followingListener(self, msg):
        """
        This listener is permanant and will update the bot's position to match self.following if we're in
        the FOLLOWING state
        """
        if self.state == STATES.FOLLOWING and self.following is not None:
            if 'data' in msg and 'userId' in msg['data'] and msg['data']['userId'] == self.following:
                if msg['method'] == 'user_moved' :

                    pos = [float(x) for x in re.split(r" \.|S ", msg['data']['position'],1)[0].strip().split(" ")]
                    #old_pos = self.avatar_pos
                    self.latest_follow_pos = pos

                    reactor.callLater(.5, self.do_follow, pos)
                    #if they called from another room we're subscribed to
                    if msg['data']['roomId'] != self.room_id:
                        self.sendLine(json.dumps({'method': 'subscribe', 'data': {'roomId': msg['data']['roomId']}}))
                        self.sendLine(json.dumps({'method': 'enter_room', 'data': {'roomId': msg['data']['roomId']}}))
                        self.room_id = msg['data']['roomId']

                elif msg['method'] == 'user_leave' :
                    if 'newRoomId' in msg['data'] is None:
                        self.state = STATES.STAYING
                    else:
                        self.sendLine(json.dumps({'method': 'subscribe', 'data': {'roomId': msg['data']['newRoomId']}}))
                        self.sendLine(json.dumps({'method': 'enter_room', 'data': {'roomId': msg['data']['newRoomId']}}))
                        self.room_id = msg['data']['newRoomId']

        #if we have an owner, always subscribe to the room they're in so we can hear them
        if self.owner is not None and msg['method'] == 'user_leave' and  msg['data']['userId'] == self.owner:
            self.sendLine(json.dumps({'method': 'subscribe', 'data': {'roomId': msg['data']['newRoomId']}}))
            
        return False  # never eat

    def clone_avatar(self, name):
        """
        Listen to move commands and make my avatar
        """
        def listener(msg):
            if msg['method'] == 'user_moved' and msg['data']['userId'] == name:
                self.avatar_html = re.split(r" \.|S ", msg['data']['position'], 1)[1]
                print "cloned" + str(self.avatar_html)
                return True
            else:
                return False

        self.appendListener(listener)

    def change_scale(self, scale):
        """
        change the scale in the avatar_html
        """
        self.avatar_html = re.sub(r'scale=&[\d\.]+~[\d\.]+~[\d\.]+', 'scale=&%s~%s~%s' % (scale, scale, scale),
                                  self.avatar_html)

    def sendChat(self, text, listen_to_self=False):
        """
        Talk bot!
        @text: The text to say
        @listen_to_self: If true will run the listener on what this bot says
        """
        self.sendLine(json.dumps({"method": "chat", "data": str(text)}))
        if listen_to_self:
            self.chatListener({"method": 'user_chat', "data": {'userId': self.name, "message": text}})
        else:
            print (":"+text)

    def chatListener(self, msg):
        """
        This will parse the chat messages of everyone and do the requested actions
        """
        if msg['method'] == 'user_chat':
            print msg['data']['userId'] + ' - ' + msg['data']['message']
            sender = msg['data']['userId']
            text = msg['data']['message']
                                  #only accept commands from our owner or from anyone if no owner
            if text[0] == '!' and (self.owner is None or self.owner == sender or sender == self.name):   # all command *must* start with !
                try:
                    if text.startswith("!echo"):
                        self.sendChat(text[5:])
                    elif text.startswith("!follow"):
                        command = text.split(" ")
                        self.following = sender if len(command) == 1 else command[1]
                        self.sendChat("Following: " + self.following)
                        self.state = STATES.FOLLOWING
                    elif text.startswith("!stay"):
                        self.state = STATES.STAYING
                    elif text.startswith("!come"):
                        self.following = sender
                        self.state = STATES.FOLLOWING
                        reactor.callLater(1, lambda: self.setState(STATES.STAYING))
                    elif text.startswith("!scale"):
                        command = text.split(" ")
                        self.change_scale(command[1])
                    elif text.startswith("!owner"):
                        command = text.split(" ")
                        self.owner = command[1]
                        self.sendChat("Owner changed to %s. Your wish is my command" % (self.owner,))
                    elif text.startswith("!clone"):
                        print "cloning..."
                        command = text.split(" ")
                        self.clone_avatar(command[1])

                except Exception as e:
                    self.sendChat("ERROR!" + str(e))

        return False  # never eat me

    def waitForOkay(self):
        """
        Returns a deferred that will callback when we get an okay
        """
        d = defer.Deferred()
        def listener(msg):
            if msg['method'] == 'okay':
                print 'okay'
                d.callback(msg)
                return True  # eat me
            else:
                return False
        self.appendListener(listener)
        return d


class BotFactory(ClientFactory):
    def buildProtocol(self, addr):
        return BotProtocol()


if __name__ == "__main__":

    reactor.connectTCP("babylon.vrsites.com", 5566, BotFactory())
    reactor.run()
