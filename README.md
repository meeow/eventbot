# eventbot
Discord bot to streamline the organization of events for the members of a server.

## Dependencies
* python3
* discord.py rewrite (https://discordpy.readthedocs.io/en/rewrite/index.html#)
* mongoDB (local or hosted)

## Installation
The bot is currently configured for hosting using Heroku and Mlab (free tiers for both are fine). 
To host on a local machine:
    
    1. Check that all the dependencies are satisfied.
    
    2. Assign BOT_TOKEN to the actual value of your bot's token
    
    3. Remove MLAB_USER, MLAB_PASS, and `db.authenticate(MLAB_USER, MLAB_PASS)`
    
    4. Change `client = MongoClient("ds018498.mlab.com", 18498)` to `client = MongoClient()` if running MongoDB locally

You can create a bot user and get a token at https://discordapp.com/developers/applications/

## Commands
Run `!help` after adding the bot to your server.
