janus_bot
=========

A simple bot for JanusVR.

It will sit in the main lobby amnd take command from anyone through chat.

dependencies: python2.7, Twisted

The current commands are as follows:

The bot will say [text]

    !echo [text]

The bot will come to you

    !come

The bot will follow the user with the name [name]. If no name is specificed, the bot will follow you

    !follow [name]

The bot will stay put

    !stay

The bot will grow or shrink to normal_size*[float]    

    !scale [float]

The bot will clone the avatar of the player

    !clone [player_name]

