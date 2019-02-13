import discord, datetime, asyncio, pytz, logging
from logging import info, warning, debug, error, critical
from discord.ext import commands
from pymongo import MongoClient
from bson.codec_options import CodecOptions
from bson.objectid import ObjectId
from os import environ
from pytz import timezone
from dateparser import parse

__python__ = 3.6
__author__ = "github.com/meeow/eventbot" 
__version__ = '2.2.1'

# Files in this repo:
# - eventbot.py (this file!)
# - Procfile 
# - requirements.txt
# - README.md

# TODO:
# - Add command to set custom time in advance to send reminder
# - Add ability to send /tts reminders
# - Add way to unset reminders
# - Change customization options via discord interface (e.g. change command prefix)
# - Unit tests
# - Refactor link (find event by key)

# Nice to have:
# - Chronological order !show_all 
# - Destroy background tasks more cleanly
# - Auto-prune stale events
# - Cleaner param input

# Bugs:
# - May have unexpected behavior if another user reacts before the bot clears the previous user's reaction
# - Cannot make 2 events of the same name even if it is owned by a different guild
# - It is possible to set a reminder for an event which has been deleted

# Version history:
# Older versions: see README.md
# v2.0 (build 247)
#   - Add flag to simplify switching between local and heroku hosting
#   - Major overhaul db logic to fix bugs when bot was used in multiple servers
#   - Minor refactoring/cleanup
#   - Add more command aliases for !show (!s, !sh) and !schedule (!sch)
# v2.0.1 (build 248)
#   - Underline event name when showing
#   - Fix factory
# v2.02 (build 249)
#   - Fix reschedule
# v2.03 (build 250)
#   - Edit `!edit` help docs
#   - Fix unschedule_past
# v2.04 
#   - Fix !teardown
#   - Start to implement event linking
# v2.1 beta (build 266)
#   - First (incomplete) release of linking
# v2.1 beta 2 (build 267)
#   - Minor refactor (no more tz param in pprint_event)
#   - Do not print author/description for linked event
# v2.2
#   - Minor refactor (Remove some default params, comments)
#   - Add id_to_name
# v2.2.1
#   - Add help docs for !join 
# v2.2.2
#   - Add more emoji options for yes and no reactions

# Todo: configurable admin level

# ==== Logging config ====
logging.basicConfig(level=logging.INFO)

def log_command(ctx):
    info("{} ({}): {}".format(ctx.message.author.name, ctx.message.guild.name, ctx.message.content))

# ==== Database and Context Setup ====

HEROKU = 1

# Heroku environment variables 
if HEROKU:
    client = MongoClient("ds018498.mlab.com", 18498)
    db = client.eventbot
    BOT_TOKEN = environ['BOT_TOKEN'] 
    MLAB_USER = environ['MONGOUSER']
    MLAB_PASS = environ['MONGOPASS']
    db.authenticate(MLAB_USER, MLAB_PASS)
else:
    client = MongoClient()
    db = client.eventbot
    BOT_TOKEN = open('../bot_token.txt', 'r').read().strip('\n')

EVENTS = db.events.with_options(codec_options=CodecOptions(tz_aware=True))
CONFIG = db.config.with_options(codec_options=CodecOptions(tz_aware=True))

# ==== Bot default options ====
bot = commands.Bot(command_prefix='!')

# Change seconds before deleting error messages 
TEMP_MESSAGE_DURATION = 5.0 

# Add more statuses to future events simply by changing this
STATUSES = {"Yes":['😃', '😀', '☺️', '😄', '😁', '🙂', '😺', '😸'], 
            "Partly":["😐", '😑'], 
            "Maybe":["🤔"], 
            "No":['😦', '🙁', '☹️', '😟', '😕', '😞', '😠', '😫', '😾']}

# By default, send reminders for events this number of minutes before start time
REMINDER_TIME = 20
# Emoji used to issue a shortcut reminder request
REMINDER_EMOJI = '⏰'
# Interval to check for reminders which need sending, in seconds
REMINDER_CYCLE = 10

# Interval to check for stale events, in seconds
STALE_CHECK_CYCLE = REMINDER_CYCLE

# Timezone
DEFAULT_TZ = timezone('US/Eastern')
VALID_TZ = set(pytz.all_timezones)
US_TZ = set([tz for tz in pytz.all_timezones if tz.startswith('US')])

# Top 'x' number of roles in the server's role hierarchy allowed to perform admin commands
DEFAULT_ADMIN_LEVEL = 1 
# Do not allow non admins to modify these fields using !edit
RESTRICTED = {"Author", "Metadata", "Time", "Date"}


# ==== Helper Functions: MongoDB interface ====

def get_collection(guild_id):
    guild_id = str(guild_id)
    return db[guild_id].with_options(codec_options=CodecOptions(tz_aware=True))

# int id: value of _id field of target mongodb document 
# * key: name of field to update
# * value: value to update field with
# collection collection: mongoDB collection to target
def update_field(id, key, value, collection=EVENTS):
    if collection == EVENTS:
        warning("Falling back to default events collection!")
        
    result = collection.update_one(
    {
        '_id': id
    },
    {
        '$set': 
        {
            key: value
        }
    }, upsert=False)
    return result


# ==== Helper Functions: Server config ====

# int guild_id: id of guild to find mongodb _id of
def config_to_id(guild_id):
    guild = CONFIG.find_one({'ID': guild_id})
    guild_id = guild['_id']
    return guild_id

# int guild_id: guild_id of guild whose name to return
def id_to_name(guild_id):
    guild_id = int(guild_id)
    return bot.get_guild(guild_id)

# int guild_id: guild_id of guild whose config to return
def get_config(guild_id):
    config = CONFIG.find_one({'ID': guild_id})
    return config

# int guild_id: name of server to search for
def guild_config_exists(guild_id):
    return bool(CONFIG.find({"ID": guild_id}).limit(1).count())

# int guild_id: guild_id of server to create config document for
def new_guild_config(guild_id):
    guild = {"ID": guild_id}
    CONFIG.insert_one(guild)


# ==== Helper Functions: Permissions ====

def get_admin_level(guild_id):
    config = get_config(guild_id)
    if config and 'Admin' in config:
        return int(config['Admin'])    
    else:
        return DEFAULT_ADMIN_LEVEL

def set_admin_level(guild_id, level):
    level = int(level)
    if level not in range(0,30):
        return "Invalid role level."
    if not guild_config_exists(guild_id):
        new_guild_config(guild_id)

    config_id = config_to_id(guild_id)
    update_field(config_id, 'Admin', level, collection=CONFIG)
    info('Admin level set to: {} ({})'.format(level, guild_id))
    return True

# Context ctx: context of command which calls this function
def is_admin(ctx):
    admin_role = get_admin_level(ctx.message.guild.id)
    role_index = len(ctx.message.guild.roles) - admin_role
    if ctx.message.author.roles[-1].position >= role_index:
        return True
    else:
        return False

# Context ctx: context of command which calls this function
# string name: name of event to check authorship of
def is_author(ctx, name):
    collection = get_collection(ctx.message.guild.id)
    if not event_exists(name, collection): 
        return False
    event = get_event(name, collection)
    msg_author = ctx.message.author.name + '#' + ctx.message.author.discriminator
    return msg_author == event['Author']

def pprint_insufficient_privileges():
    msg = "Error: You have insufficient privileges to perform this action."
    return msg


# ==== Helper Functions: Datetime ====

# datetime time: time to search for conflicts
def time_exists(time, collection=EVENTS):
    events = collection.find({"Time": time})
    return events.count()

# datetime time: time to determine if it is in the past
def is_past(time):
    present = datetime.datetime.now(DEFAULT_TZ)
    return time.astimezone(DEFAULT_TZ) < present

# Datetime time: datetime object to convert to formatted string
def pprint_time(time, tz=DEFAULT_TZ):
    if time.tzinfo is None or time.tzinfo.utcoffset(time) is None: 
        info("Localizing naive time {} to {}".format(time, tz))  
        time = tz.localize(time)
    else:
        time = time.astimezone(tz)

    msg = time.strftime("%A %-m/%-d %-I:%M%p %Z") 
    return msg

# int guild_id: guild_id of server to set timezone for
# timezone: timezone matching VALID_TZ
def set_timezone(guild_id, timezone):
    if timezone not in VALID_TZ:
        return False
    if not guild_config_exists(guild_id):
        new_guild_config(guild_id)

    config_id = config_to_id(guild_id)
    update_field(config_id, 'Timezone', timezone, collection=CONFIG)
    info('Server set to timezone: {}'.format(timezone))
    return True

# int guild_id: id of server to get timezone of
def get_timezone(guild_id):
    config = get_config(guild_id)
    if config and 'Timezone' in config:
        return pytz.timezone(config['Timezone'])
    else:
        return DEFAULT_TZ

# string inp: user datetime input
def input_to_datetime(inp, tz=DEFAULT_TZ):
    time = parse(inp)
    bot_localtime = datetime.datetime.now(tz)

    if time.tzinfo is None: #or time.tzinfo.utcoffset(time) is None:
        time = tz.localize(time)
    return time


# ==== Helper Functions: Events general ====

# string name: name of event to search for
def event_exists(name, collection=EVENTS):
    if collection == EVENTS:
        warning("Falling back to default events collection!")
    return bool(collection.find({"Name": name}).limit(1).count())

# string name: name of event to return
def get_event(name, collection):
    event = collection.find_one({'Name': name})
    return event

# string name: name of event to find id of
def get_event_id(name, collection):
    event = collection.find_one({'Name': name})
    event_id = event['_id']
    return event_id

# User user: User object to convert to user.name + user.discriminator
def user_to_username(user):
    return "{}#{}".format(user.name, user.discriminator)

# Client client: discord client in guild
# string username: Return User object in guild matching username
def username_to_user(client, username):
    for user in client.users:
        if user.name + '#' + user.discriminator == username:
            return user

# string emoji: reaction emoji from discord event
def emoji_to_status(emoji):
    matched_status = ''
    for status in STATUSES:
        if emoji in STATUSES[status]:
            matched_status = status
            return matched_status

    return matched_status

def pprint_attendance_instructions():
    msg = '```Update your plans by reacting to this message using the corresponding emoji.'
    msg += '\nRequest a 20 minute heads-up via DM by also reacting {}. You must be able to receive DMs from non-friends.```'.format(REMINDER_EMOJI)
    return msg

# string name: invalid search string
def pprint_event_not_found(name):
    msg = "Warning: Cannot find event called {}.".format(name)
    return msg

# context ctx: used to get discord guild name
# string name: name of event to create
# string datetime: string parseable by dateparser
# string description: descrption of event
def new_event(ctx, name, datetime, description='No description.'):
    guild_id = ctx.message.guild.id
    collection = get_collection(guild_id)
    time = input_to_datetime(datetime, tz=get_timezone(guild_id))
    timezone = get_timezone(guild_id)
    author = ctx.message.author.name + '#' + ctx.message.author.discriminator

    if event_exists(name, collection):
        return name + " already exists in upcoming events."
    elif is_past(time):
        warning("Failed to schedule event at {}".format(time))
        return "The specified date/time occurred in the past."
    if time_exists(time, collection):
        warning("Failed to schedule event at {}".format(time))
        return "There is already an event scheduled for {}".format(pprint_time(time))

    event = {'Name': name,
            'Author': author,
            'Time': time,
            'Description': description,
            'Metadata': {"Reminders": {}, "GuildID": ctx.message.guild.id}
    }

    for status in STATUSES.keys():
        event[status] = []

    collection.insert_one(event)

    msg = pprint_event(name, collection=collection) + pprint_attendance_instructions()
    return msg 

# string name: name of event to delete
def delete_event(name, collection):
    if event_exists(name, collection):
        result = collection.remove({"Name": name})
        msg = "Removed {}.".format(name)
    else:
        msg = pprint_event_not_found(name)
    return msg

# int guild_id: guild id whose events to delete
def delete_past_events(guild_id):
    msg = ''
    collection = get_collection(guild_id)

    cursor = collection.find({})
    for event in cursor:
        if is_past(event['Time']):
            msg += "{} - {}\n".format(event['Name'], pprint_time(event['Time']))
            delete_event(event['Name'], collection)
            info("Deleted {}.".format(event['Name']))

    if msg:
        msg = "The following past events were deleted: \n\n" + msg
    else:
        msg = "No past events were found."
    return msg

# string name: name of event to pretty print
# bool verbose: print only name and time if False
def pprint_event(name, collection, verbose=True):
    tz = get_timezone(int(str(collection.name)))

    def pprint_raw_event(event, opposing=False):
        msg = ''
        for field in event:
            val = event[field]
            if field == "Name":
                msg += "__**{}**__\n".format(val)                
            elif field == "_id":
                msg += ''
            elif field == "Time":
                msg += "**{}:** {}\n".format(field, pprint_time(val, tz=tz)) 
            elif verbose:
                
                if field in STATUSES and isinstance(val, list):
                    status = field
                    if val:
                        attendee_list = ', '.join(val)
                    else:
                        attendee_list = 'None yet!'
                    msg += "{} **{} ({}):** {}\n".format(STATUSES[status][0], status, len(val), attendee_list)
                elif opposing or field == 'Metadata':
                    continue # do not show 
                elif not val:
                    msg += "**{}:** {}\n".format(field, 'None')
                else:
                    msg += "**{}:** {}\n".format(field, val)
        return msg

    if event_exists(name, collection) == False:
        return pprint_event_not_found(name)

    event = get_event(name, collection)
    msg = pprint_raw_event(event)

    if 'Link' in event['Metadata'] and verbose:
        key = event['Metadata']['Link']
        linked_event = get_linked_event(key)
        if linked_event == None:
            msg += "**Former linked event has been deleted.**\n"
            msg += "**Link key:** `{} {}\n\n`".format(event['_id'], collection.name)
        else:
            msg += "\n**Opposing team ({}) status: **\n".format(id_to_name(key[key.find(' ')+1:])) 
            msg += pprint_raw_event(linked_event, opposing=True)
    elif verbose:
        msg += "**Link key:** `{} {}\n\n`".format(event['_id'], collection.name)

    return msg + '\n'

# Guild guild: guild to print events for
def pprint_all_events(guild_id):
    msg = 'Showing all events. Use command `!show [event name]` for detailed info.\n\n'
    found_events = ''
    collection = get_collection(guild_id)

    cursor = collection.find({})
    for event in cursor:
        found_events += pprint_event(event['Name'], verbose=False, collection=collection)

    if not found_events:
        msg = 'No events found.'
    else:
        msg += found_events
    return msg

# string event_name: name of event to change status of
# string user: username#discriminator of user to change status of
# string status: new status
def set_attendance(event_name, user, status, collection=EVENTS):
    if not event_exists(event_name, collection):
        return pprint_event_not_found(event_name)
    
    if not isinstance(user, str):
        user_name = user_to_username(user)
    else:
        user_name = user

    event = get_event(event_name, collection)
    event_id = get_event_id(event_name, collection)

    old_status = []
    for s in STATUSES:
        if user_name in event[s]:
            if s == status:
                return # no net change
            event[s].remove(user_name)
            old_status = [s, event[s]] 

    if old_status:
        update_field(event_id, old_status[0], old_status[1], collection)

    if not old_status or (old_status and status != old_status[0]):
        attendance_status = event[status] + [user_name]
        update_field(event_id, status, attendance_status, collection)

    return "Set **{}'s** status to **{}** for **{}**.".format(user_name, status, event_name)


# ==== Helper Functions: Reminders ====

# string event_name: name of event to set reminder for
# string user: username#discriminator of user to set reminder for
# int/float time: minutes before event begins to send reminders
def set_reminder(event_name, user, time=REMINDER_TIME, collection=EVENTS):
    if not event_exists(event_name, collection):
        return pprint_event_not_found(event_name)
    
    if not isinstance(user, str):
        user_name = user_to_username(user)
    else:
        user_name = user

    event = get_event(event_name, collection)
    event_id = event['_id']

    metadata = event['Metadata']
    metadata['Reminders'][user_name] = time
    
    update_field(event_id, 'Metadata', metadata, collection)
    return "Set {} minutes reminder for **{}**.".format(time, event_name)

# event: event entry in mongodb
# string username: user.name#user.discriminator
def delete_reminder(event, username, collection=EVENTS):
    event_id = get_event_id(event['Name'], collection)
    metadata = event['Metadata']
    del metadata['Reminders'][username] 
    update_field(event_id, 'Metadata', metadata, collection)


# ==== Helper Functions: Event Linking ====
def set_link(event_name, key, collection):
    if not event_exists(event_name, collection):
        return pprint_event_not_found(event_name)

    # Update first event
    event = get_event(event_name, collection)
    event_id = event['_id']

    metadata = event['Metadata']
    metadata['Link'] = key

    update_field(event_id, 'Metadata', metadata, collection=collection)

    # Update second event
    event2_id, guild_id = key.split()
    key = "{} {}".format(event_id, collection.name)
    collection = get_collection(guild_id)
    event = collection.find_one({'_id': ObjectId(event2_id)})

    metadata = event['Metadata']
    metadata['Link'] = key

    update_field(ObjectId(event2_id), 'Metadata', metadata, collection=collection)

    return "Established link with key {}".format(key)

def get_linked_event(key):
    event_id, guild_id = key.split()
    collection = get_collection(guild_id)
    event = collection.find_one({'_id': ObjectId(event_id)})
    return event

def join_event(ctx, key):
    event = get_linked_event(key)
    name = event['Name']
    datetime = event['Time']
    description = event['Description']
    event_new = new_event(ctx, name, str(datetime), description)

    collection = get_collection(ctx.message.guild.id)
    set_link(name, key, collection)

    return pprint_event(name, collection=collection) + pprint_attendance_instructions() 


# ==== Discord specific helpers ====
async def send_temp_message(ctx, msg):
    temp_msg = await ctx.send(msg)
    await temp_msg.edit(content=msg, delete_after=TEMP_MESSAGE_DURATION)


# ==== Bot init ====


# Remove default help command
bot.remove_command('help')


# ==== Background tasks ====

async def send_reminders():
    await bot.wait_until_ready()

    while 1:
        for name in db.collection_names():
            if not name.isdigit():
                continue
            collection = get_collection(name)
            cursor = collection.find({})
            for event in cursor:
                reminders = event['Metadata']['Reminders']
                for user_name in list(event['Metadata']['Reminders'].keys()):
                    present = datetime.datetime.now(DEFAULT_TZ)
                    if present + datetime.timedelta(minutes=reminders[user_name]) >= event['Time']:
                        info("Sending reminder: {} {}".format(event['Name'], reminders))
                        event_name = event["Name"]
                        user = username_to_user(bot, user_name)
                        await user.send("Hey! Your event {} is starting within {} minutes!".format(event['Name'], reminders[user_name]))
                        delete_reminder(event, user_name, collection)
        await asyncio.sleep(REMINDER_CYCLE)


# ==== Events ====

@bot.event
async def on_ready():
    status = 'Say !help'#'DOWN FOR MAINT' #
    await bot.change_presence(activity=discord.Game(name=status))
    info('Logged in as: {}'.format(bot.user.name))
    info("Current time: {}".format(pprint_time(datetime.datetime.now(DEFAULT_TZ))))
    info("Currently active on servers:\n{}".format('\n'.join([guild.name for guild in bot.guilds])))
    print('-------------------')


@bot.event
async def on_raw_reaction_add(payload):
    guild = bot.get_guild(payload.guild_id)
    channel = guild.get_channel(payload.channel_id)
    user = bot.get_user(payload.user_id)
    message = await channel.get_message(payload.message_id)
    reaction = message.reactions[0]
    timezone = get_timezone(guild.id)
    collection = get_collection(payload.guild_id)

    listen_to_reactions = "by react" in message.content

    if listen_to_reactions:
        status = emoji_to_status(reaction.emoji)
        event_name = message.content.splitlines()[0].strip('_*')
        info("{} reacted {} to {}".format(user.name, reaction, event_name))

        if reaction.emoji == REMINDER_EMOJI:
            set_reminder(event_name, user, collection=collection)
            await user.send("Got it! You should get a reminder for {} {} minutes before it starts.".format(event_name, REMINDER_TIME))
        elif not status:
            msg = '**Not a valid reaction option.** Please try again using one of the specified emojis.'
            err_message = await channel.send(msg)
            await err_message.edit(content=msg, delete_after=TEMP_MESSAGE_DURATION)
        else:  
            set_attendance(event_name, user, status, collection)
            new_message = pprint_event(event_name, collection=collection) + pprint_attendance_instructions()
            await message.edit(content=new_message)

        await message.clear_reactions()


# ==== Config Commands ====
@bot.command()
async def timezone(ctx, timezone):
    guild_name = ctx.message.guild.name
    guild_id = ctx.message.guild.id
    if set_timezone(guild_id, timezone):
        new_timezone = get_timezone(guild_id)
        msg = "Set timezone for {} ({}) to {}.".format(guild_name, guild_id, new_timezone)
        await ctx.send(msg)
    else:
        msg = "**Valid timezones:** \n`{}`".format(', '.join(US_TZ))
        await ctx.send(msg)


# ==== Event Commands ====

@bot.command(aliases=['s', 'sh'])
async def show(ctx, *, name):
    log_command(ctx)
    msg = ''
    name = name.strip('\"')
    guild_id = ctx.message.guild.id
    collection = get_collection(guild_id)
    timezone = get_timezone(guild_id)

    if event_exists(name, collection):
        msg = pprint_event(name, collection=collection)
        msg += pprint_attendance_instructions()
    else:
        msg = pprint_event_not_found(name)

    await ctx.send(msg)

@bot.command(aliases=["sa"])
async def show_all(ctx):
    log_command(ctx)
    guild_id = ctx.message.guild.id
    msg = pprint_all_events(guild_id)
    await ctx.send(msg)

@bot.command(aliases=["sched", "sch"])
async def schedule(ctx, name, date, time, description='No description.'):
    log_command(ctx)
    datetime = date + ' ' + time
    msg = new_event(ctx, name, datetime, description)
    await ctx.send(msg)

@bot.command(aliases=["resched", "rs"])
async def reschedule(ctx, name, *, datetime):
    log_command(ctx)
    collection = get_collection(ctx.message.guild.id)

    if not event_exists(name, collection=collection):
        msg = pprint_event_not_found(name)
        await send_temp_message(ctx, msg)
    elif not (is_admin(ctx) or is_author(ctx, name)):
        msg = pprint_insufficient_privileges()
        await send_temp_message(ctx, msg)
    else:
        event_id = get_event_id(name, collection)
        time = input_to_datetime(datetime, get_timezone(ctx.message.guild.id))
        update_field(event_id, 'Time', time, collection=collection)
        msg = "Set {} to {}.".format(name, pprint_time(time))
        await ctx.send(msg)

@bot.command(aliases=["unsched", "us"])
async def unschedule(ctx, *, name):
    log_command(ctx)
    collection = get_collection(ctx.message.guild.id)

    if (is_admin(ctx) or is_author(ctx, name)):
        name = name.strip('\"')
        event = get_event(name, collection)
        msg = delete_event(name, collection)
        await ctx.send(msg)
    else:
        msg = pprint_insufficient_privileges()
        await send_temp_message(ctx, msg)

@bot.command(aliases=["usp"])
async def unschedule_past(ctx):
    log_command(ctx)

    guild_id = ctx.message.guild.id
    msg = delete_past_events(guild_id)
    await ctx.send(msg)
'''
@bot.command()
async def link(ctx, event_name, *, key):
    log_command(ctx)

    collection = get_collection(ctx.message.guild.id)
    msg = set_link(event_name, key, collection=EVENTS)
    await ctx.send(msg)
'''
@bot.command()
async def join(ctx, *, key):
    log_command(ctx)

    collection = get_collection(ctx.message.guild.id)
    msg = join_event(ctx, key)
    await ctx.send(msg)

# User can change value of a field which is a string.
@bot.command()
async def edit(ctx, name, key, value):
    log_command(ctx)

    guild_id = ctx.message.guild.id
    collection = get_collection(guild_id)

    msg = ''
    event_id = get_event_id(name, collection)
    event = get_event(name, collection)

    if not event_exists(name, collection):
        msg += pprint_event_not_found(name) + '\n'       

    if (
        (key in event and not isinstance(event[key], str)) or 
        (not (is_admin(ctx) or is_author(ctx, name))) or 
        ((key in RESTRICTED) and not is_admin(ctx))
        ):
        msg += "Error: the specified field cannot be changed using this command or you do not have permission."
        await send_temp_message(ctx, msg)
    else:
        update_field(event_id, key, value, collection=collection)
        msg = "Set {} to {}.".format(key, value)
        await ctx.send(msg)


# ==== Help ====

@bot.command()
async def help(ctx):
    title = "== eventbot v{} (by Meeow) ==".format(__version__)
    embed = discord.Embed(title=title, description="List of commands are:", color=0xeee657)

    embed.add_field(
        name="!schedule [name] [date (mm/dd) or (today/tomorrow)] [time] [description]", 
        value='''Create a new event. 
        Use quotes if your name or description parameter has spaces in it.
        Example: `!schedule "Scrim against SHD" "Descriptive description." 3/14 1:00PM`
        Aliases: `!sched, !sch`''', 
        inline=False)

    embed.add_field(
        name="!reschedule [name] [datetime] ", 
        value='''Edit the time of an existing event.  
        Use quotes if your name or description parameter has spaces in it.
        Can also be used to add a new field.
        Example: `!reschedule "Scrim against SHD" 4/1 13:30`
        Aliases: `!resched, !rs`''', 
        inline=False)

    embed.add_field(
        name="!unschedule [event_name]", 
        value='''Delete the specified event entirely. Usage restricted to author of the event and admins.
        Aliases: `!unsched, !us`''', 
        inline=False)

    embed.add_field(
        name="!unschedule_past", 
        value='''Delete ALL past events entirely.
        Aliases: `!usp`''', 
        inline=False)

    embed.add_field(
        name="!show_all", 
        value='''Show name and time for all upcoming events.
        Aliases: `!sa`''', 
        inline=False)

    embed.add_field(
        name="!show [event_name]", 
        value='''Show all details for the specified event.
        Aliases: `!s, !sh`''', 
        inline=False)

    embed.add_field(
        name="!edit [event_name] [field name] [new value]", 
        value='''Edit field with a string type value (not dates or attendance lists).
        Non-admins may not edit the `Author` field.
        Use quotes if your parameter has spaces in it. 
        `Example: !edit "Scrim against SHD" "Description" "Improved description."`''', 
        inline=False)

    embed.add_field(
        name="!timezone [timezone]", 
        value='''Set timezone for current server. Valid values include:
        US/Eastern
        US/Central
        US/Pacific''', 
        inline=False)

    embed.add_field(
        name="!join [link_key]", 
        value='''Create a linked duplicate event in another server (that has this bot).
        Linked events will display the attendance status of both teams.
        Link key is automatically displayed when scheduling an event. 
        Send the link key to the other team so they can run this command.
        ''', 
        inline=False)

    await ctx.send(embed=embed)


# ==== Undocumented Commands for Debugging/Admin ====
'''
@bot.command()
async def set_attend(ctx, event_name, user_name, status):
    if is_admin(ctx):
        msg = set_attendance(event_name, user_name, status)
        await ctx.send(msg)'''

@bot.command()
async def factory(ctx, num_events=5):
    if num_events > 9:
        num_events = 9

    for num in range(num_events):
        date = '10/{}'.format(num+1)
        time = str(1 + num) + ':00pm'
        name = '-test' + str(num)
        msg = new_event(ctx, name, datetime)
        await ctx.send(msg)
        info("Factory creating event on date {} at time {}".format(date, time))

    await ctx.send("Attempted to create {} test events".format(num_events))

@bot.command()
async def teardown(ctx):
    collection = get_collection(ctx.message.guild.id)

    cursor = collection.find({})
    for event in cursor:
        if event['Name'].startswith('-test'):
            delete_event(event['Name'], collection)
    await ctx.send('Deleted test events.')

@bot.command()
async def dump_roles(ctx):
    roles = ctx.message.guild.roles
    print (ctx.message.guild.roles)
    print (len(roles), "roles in server.")
    for role in roles:
        print(role.name, ' - position', role.position)
    await ctx.send('Logged roles in console.')


# ==== Run ====
bot.loop.create_task(send_reminders())
bot.run(BOT_TOKEN)




