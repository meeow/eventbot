import discord, datetime, asyncio
from discord.ext import commands
from pymongo import MongoClient
from bson.codec_options import CodecOptions

from os import environ

from pytz import timezone
from dateparser import parse

__python__ = 3.6
__author__ = "github.com/meeow" 
__version__ = "1.5" + "https://github.com/meeow/eventbot"

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

# Nice to have:
# - Chronological order !show_all 
# - Allow reactions to messages not in message cache
# - Destroy background tasks more cleanly
# - Auto-prune stale events

# Warnings:
# - May have unexpected behavior if another user reacts before the bot clears the previous user's reaction

# Current version history:
# - v1.1: 
#   * Add unschedule_past command
# - v1.2 (heroku build 121):  
#   * Save datetimes as timezone aware in mongodb
#   * More accurate datetime parsing and validations
#   * Basic factory, teardown commands for testing
#   * Improve code style
# - v1.3 (heroku build 131):
#   * Add basic permission system
#       + Configure minimum admin role (in .py file, command soon)
#       + Author may edit or delete own events
#       + Admin may edit or delete any events
#       + Anyone may delete all past events
#   * Make more error messages temporary
# - v1.3.1 (heroku build 143)
#   * Minor refactoring
#   * Begin implementing reminders
# - v1.4 (heroku build 163)
#   * Initial implementation of reminders
#       + React with ⏰ emoji to receive a reminder DM 20 mins before start of event
#       + Additional functionality coming soon
# - v1.4.1 (heroku build 164)
#   * Revised instructions to account for heroku dyno cycling clearing message cache
# - v1.4.2 (heroku build 178)
#   * Use raw reactions to handle reaction detection, to enable reaction functionaliy even if target message is not cached
#   * Revise instructions to account for this bugfix
# - v1.5 (heroku build 191)
#   * Add guild id to metadata, allowing for use in multiple servers
#   * Minor style changes to instructions message
#   * Add command aliases
#   * Improve !help  


# ==== Database and Context Setup ====

# Heroku environment variables 
BOT_TOKEN = environ['BOT_TOKEN'] 
MLAB_USER = environ['MONGOUSER']
MLAB_PASS = environ['MONGOPASS']

client = MongoClient("ds018498.mlab.com", 18498)
db = client.eventbot
db.authenticate(MLAB_USER, MLAB_PASS)

EVENTS = db.events.with_options(codec_options=CodecOptions(tz_aware=True))
CONFIG = db.config.with_options(codec_options=CodecOptions(tz_aware=True))


# ==== Bot config options ====

# Change seconds before deleting error messages 
ERR_MSG_DURATION = 5.0 

# Add more statuses to future events simply by changing this
STATUSES = {"Yes":"😃", "Partly":"😐", "Maybe":"🤔", "No":"😦"}

# By default, send reminders for events this number of minutes before start time
REMINDER_TIME = 20
# Emoji used to issue a shortcut reminder request
REMINDER_EMOJI = '⏰'
# Interval to check for reminders which need sending, in seconds
REMINDER_CYCLE = 10

# Interval to check for stale events, in seconds
STALE_CHECK_CYCLE = REMINDER_CYCLE

BOT_TZ = timezone('America/New_York')

# Top 'x' number of roles in the server's role hierarchy allowed to perform admin commands
ADMIN_ROLES = 1 


# ==== Helper Functions ====

# discord.Context ctx: context of command which calls this function
def is_admin(ctx):
    role_index = len(ctx.message.guild.roles) - ADMIN_ROLES
    if ctx.message.author.roles[-1].position >= role_index:
        return True
    else:
        return False

# Context ctx: context of command which calls this function
# string name: name of event to check authorship of
def is_author(ctx, name):
    if not event_exists(name): 
        return False
    event = get_event(name)
    msg_author = ctx.message.author.name + '#' + ctx.message.author.discriminator
    return msg_author == event['Author']

# Context ctx: context of command which calls this function
def pprint_insufficient_privileges(ctx):
    msg = "Error: You have insufficient privileges to perform this action."
    return msg

# string name: name of event to search for
def event_exists(name):
    return bool(EVENTS.find({"Name": name}).limit(1).count())

# dict event: dict representing event to check ownership
# Guild guild: guild to check for ownership of event
def event_belongs_to_guild(event, guild):
    return event['Metadata']['GuildID'] == guild.id

# Guild guild: guild to check for ownership of event
# string name: name of event to search for
def event_exists_and_belongs_to_guild(guild, name):
    exists = event_exists(name)
    if exists:
        event = get_event(name)
        belongs = event_belongs_to_guild(event, guild)
        return bool(belongs)
    else:
        return False

# datetime time: time to search for conflicts
def time_exists(time):
    return bool(EVENTS.find({"Time": time}).limit(1).count())

# datetime time: time to determine if it is in the past
def is_past(time):
    present = datetime.datetime.now(BOT_TZ)
    return time.astimezone(BOT_TZ) < present

# string name: name of event to return
def get_event(name):
    event = EVENTS.find_one({'Name': name})
    return event

# string name: name of event to find id of
def name_to_id(name):
    event = EVENTS.find_one({'Name': name})
    event_id = event['_id']
    return event_id

def get_utc_offset_hrs():
    bot_localtime = datetime.datetime.now(BOT_TZ)
    utc_offset = datetime.datetime.now(BOT_TZ).utcoffset().total_seconds()/60/60
    return utc_offset

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
        if STATUSES[status] == emoji:
            matched_status = status
            return matched_status

    return matched_status

def pprint_attendance_instructions():
    msg = '`Update your status by reacting to **this message** with the corresponding emoji.`'
    msg += '\n`Request a 20 minute heads-up via DM by additionally reacting {}. You must be able to receive DMs from non-friends.`'.format(REMINDER_EMOJI)
    return msg

# Datetime time: datetime object to convert to formatted string
def pprint_time(time):
    if time.tzinfo is None or time.tzinfo.utcoffset(time) is None: 
        print ("Localizing naive time...")  
        time = BOT_TZ.localize(time)
    else:
        time = time.astimezone(BOT_TZ)

    utc_offset = get_utc_offset_hrs
    msg = time.strftime("%A %-m/%-d %-I:%M%p %Z") 
    return msg

# string name: invalid search string
def pprint_event_not_found(name):
    msg = "Warning: Cannot find event called {}.".format(name)
    return msg

# int id: value of _id field of target mongodb document 
# * key: name of field to update
# * value: value to update field with
def update_field(id, key, value):
    result = EVENTS.update_one(
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

# string date: date in mm/dd format 
# string time: time in 24 hr or 12 hr format
def input_to_datetime(inp):
    time = parse(inp)

    bot_localtime = datetime.datetime.now(BOT_TZ)
    utc_offset = get_utc_offset_hrs()

    if time.tzinfo is None or time.tzinfo.utcoffset(time) is None:
        time = BOT_TZ.localize(time)
        if "in" in inp:
            time = time + datetime.timedelta(hours=utc_offset)

    return time


# ==== Internal Logic ====

# context ctx: used to get discord guild name
# string name: name of event to create
# string date: date in mm/dd format 
# string mil_time: time in 24 hr format
# string description: descrption of event
def new_event(ctx, name, author, date, time, description='No description.'):
    if event_exists(name):
        return name + " already exists in upcoming events."

    time = input_to_datetime(date + ' ' + time)

    if is_past(time):
        return "The specified date/time occurred in the past."
    if time_exists(time):
        return "There is already an event scheduled for {}".format(pprint_time(time))

    event = {}
    event["Name"] = name
    event["Author"] = author
    event["Time"] = time
    event["Description"] = description

    for status in STATUSES.keys():
        event[status] = []

    # hidden from view
    event["Metadata"] = {"Reminders": {}, "GuildID": ctx.message.guild.id}
    
    EVENTS.insert_one(event)

    msg = pprint_event(name) + pprint_attendance_instructions()
    
    return msg 


# string name: name of event to delete
def delete_event(name):
    if event_exists(name):
        result = EVENTS.remove({"Name": name})
        msg = "Removed {}.".format(name)
    else:
        msg = pprint_event_not_found(name)
    return msg

# Guild guild: guild whose events to delete
def delete_past_events(guild):
    msg = ''

    cursor = EVENTS.find({})
    for event in cursor:
        if is_past(event['Time']) and event_belongs_to_guild(event, guild):
            msg += "{} - {}\n".format(event['Name'], pprint_time(event['Time']))
            delete_event(event['Name'])

    if msg:
        msg = "The following past events were deleted: \n\n" + msg
    else:
        msg = "No past events were found."

    return msg


# string name: name of event to pretty print
# bool verbose: print only name and time if False
def pprint_event(name, verbose=True):
    if event_exists(name) == False:
        return pprint_event_not_found(name)

    event = get_event(name)
    msg = ''

    for field in event:
        val = event[field]
        if field == "Name":
            msg += "**{}**\n".format(val)
        elif field == "_id":
            msg += ''
        elif field == "Time":
            msg += "**{}:** {}\n".format(field, pprint_time(val)) 
        elif verbose:
            if field == 'Metadata':
                continue # do not show 
            elif field in STATUSES and isinstance(val, list):
                if val:
                    attendee_list = ', '.join(val)
                else:
                    attendee_list = 'None yet!'
                msg += "{} **{} ({}):** {}\n".format(STATUSES[field], field, len(val), attendee_list)
            elif not val:
                msg += "**{}:** {}\n".format(field, 'None')
            else:
                msg += "**{}:** {}\n".format(field, val)

    return msg + '\n'


# Guild guild: guild to print events for
def pprint_all_events(guild):
    msg = 'Showing all events for {}. Use command `!show [event name]` for detailed info.\n\n'.format(guild.name)
    found_events = ''

    cursor = EVENTS.find({})
    for event in cursor:
        if event_belongs_to_guild(event, guild): 
            found_events += pprint_event(event['Name'], verbose=False)

    if not found_events:
        msg = 'No upcoming events for {}.'.format(guild.name)
    else:
        msg += found_events
    
    return msg


# string event_name: name of event to change status of
# string user: username#discriminator of user to change status of
# string status: new status
def set_attendance(event_name, user, status):
    if not event_exists(event_name):
        return pprint_event_not_found(event_name)
    
    if not isinstance(user, str):
        user_name = user_to_username(user)
    else:
        user_name = user

    event = get_event(event_name)
    event_id = name_to_id(event_name)

    old_status = []
    for s in STATUSES:
        if user_name in event[s]:
            if s == status:
                return # no net change
            event[s].remove(user_name)
            old_status = [s, event[s]] 

    if old_status:
        update_field(event_id, old_status[0], old_status[1])

    if not old_status or (old_status and status != old_status[0]):
        attendance_status = event[status] + [user_name]
        update_field(event_id, status, attendance_status)

    return "Set **{}'s** status to **{}** for **{}**.".format(user_name, status, event_name)


# string event_name: name of event to set reminder for
# string user: username#discriminator of user to set reminder for
# int/float time: minutes before event begins to send reminders
def set_reminder(event_name, user, time=REMINDER_TIME):
    if not event_exists(event_name):
        return pprint_event_not_found(event_name)
    
    if not isinstance(user, str):
        user_name = user_to_username(user)
    else:
        user_name = user

    event = get_event(event_name)
    event_id = name_to_id(event_name)

    metadata = event['Metadata']
    metadata['Reminders'][user_name] = time
    
    update_field(event_id, 'Metadata', metadata)
    return "Set {} minutes reminder for **{}**.".format(time, event_name)

# event: event entry in mongodb
# string username: user.name#user.discriminator
def delete_reminder(event, username):
    event_id = name_to_id(event['Name'])
    metadata = event['Metadata']
    del metadata['Reminders'][username] 
    update_field(event_id, 'Metadata', metadata)


# ==== Discord specific helpers ====
async def send_temp_message(ctx, msg):
    temp_msg = await ctx.send(msg)
    await temp_msg.edit(content=msg, delete_after=ERR_MSG_DURATION)

'''
async def switch_collection(ctx):
    global db 
    guild = ctx.message.guild.name
    db = client[guild]
    db.authenticate(MLAB_USER, MLAB_PASS)
    print ("Swiched to", guild, "database")
'''
'''
def _prefix_callable(bot, msg):
    user_id = bot.user.id
    base = ['<@!{}> '.format(user_id), '<@{}> '.format(user_id)]
    if msg.guild is None:
        base.append('!')
    else:
        base.extend(bot.prefixes.get(msg.guild.id, ['?', '!']))
    return base
'''

# ==== Bot init ====

bot = commands.Bot(command_prefix='!')

# Remove default help command
bot.remove_command('help')


# ==== Background tasks ====

async def send_reminders():
    await bot.wait_until_ready()

    while 1:
        cursor = EVENTS.find({})
        for event in cursor:
            reminders = event['Metadata']['Reminders']
            for user_name in list(event['Metadata']['Reminders'].keys()):
                present = datetime.datetime.now(BOT_TZ)
                if present + datetime.timedelta(minutes=reminders[user_name]) >= event['Time']:
                    print("Sending reminder:", event['Name'], reminders)
                    event_name = event["Name"]
                    user = username_to_user(bot, user_name)
                    await user.send("Hey! Your event {} is starting within {} minutes!".format(event['Name'], reminders[user_name]))
                    delete_reminder(event, user_name)
        await asyncio.sleep(REMINDER_CYCLE)


# ==== Events ====

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name='Say !help'))
    print('Logged in as: {}'.format(bot.user.name))
    print("Current time: {}".format(pprint_time(datetime.datetime.now(BOT_TZ))))
    print("Currently active on servers:\n", '\n'.join([guild.name for guild in bot.guilds]))
    print('-------------------')


@bot.event
async def on_raw_reaction_add(payload):
    guild = bot.get_guild(payload.guild_id)
    channel = guild.get_channel(payload.channel_id)
    user = bot.get_user(payload.user_id)
    message = await channel.get_message(payload.message_id)
    reaction = message.reactions[0]
    print (message.reactions)

    listen_to_reactions = "by react" in message.content

    if listen_to_reactions:
        status = emoji_to_status(reaction.emoji)
        event_name = message.content.splitlines()[0].replace('*','')

        if reaction.emoji == REMINDER_EMOJI:
            set_reminder(event_name, user)
            await user.send("Got it! You should get a reminder for {} {} minutes before it starts.".format(event_name, REMINDER_TIME))
        elif not status:
            msg = '**Not a valid reaction option.** Please try again using one of the specified emojis.'
            err_message = await channel.send(msg)
            await err_message.edit(content=msg, delete_after=ERR_MSG_DURATION)
        else:  
            set_attendance(event_name, user, status)
            new_message = pprint_event(event_name) + pprint_attendance_instructions()
            await message.edit(content=new_message)

        await message.clear_reactions()


# ==== Commands ====

@bot.command()
async def show(ctx, *, name):
    msg = ''
    name = name.strip('\"')
    guild = ctx.message.guild

    if event_exists_and_belongs_to_guild(guild, name):
        msg = pprint_event(name)
        msg += pprint_attendance_instructions()
    else:
        msg = pprint_event_not_found(name)

    await ctx.send(msg)

@bot.command(aliases=["sa"])
async def show_all(ctx):
    guild = ctx.message.guild
    msg = pprint_all_events(guild)
    await ctx.send(msg)

@bot.command(aliases=["sched"])
async def schedule(ctx, name, date, time, description='No description.'):
    discord_tag = ctx.message.author.name + '#' + ctx.message.author.discriminator
    msg = new_event(ctx, name, discord_tag, date, time, description)
    await ctx.send(msg)

@bot.command(aliases=["resched", "rs"])
async def reschedule(ctx, name, *, datetime):
    if not event_exists(name):
        msg = pprint_event_not_found(name)
        await send_temp_message(ctx, msg)
    elif not (is_admin(ctx) or is_author(ctx, name)):
        msg = pprint_insufficient_privileges(ctx)
        await send_temp_message(ctx, msg)
    else:
        event_id = name_to_id(name)
        time = input_to_datetime(datetime)
        update_field(event_id, 'Time', time)
        msg = "Set {} to {}.".format(name, pprint_time(time))
        await ctx.send(msg)

@bot.command(aliases=["unsched", "us"])
async def unschedule(ctx, *, name):
    if is_admin(ctx) or is_author(ctx, name):
        name = name.strip('\"')
        msg = delete_event(name)
        await ctx.send(msg)
    else:
        msg = pprint_insufficient_privileges(ctx)
        await send_temp_message(ctx, msg)

@bot.command(aliases=["usp"])
async def unschedule_past(ctx):
    guild = ctx.message.guild
    msg = delete_past_events(guild)
    await ctx.send(msg)

# User can change value of a field which is a string.
@bot.command()
async def edit(ctx, name, key, value):
    msg = ''
    event_id = name_to_id(name)
    event = get_event(name)

    if not event_exists(name):
        msg += pprint_event_not_found(name) + '\n'       

    if (
        (key in event and not isinstance(event[key], str)) or 
        (not (is_admin(ctx) or is_author(ctx, name))) or 
        ((key == "Author" or key == "Metadata") and not is_admin(ctx))
        ):
        msg += "Error: the specified field cannot be changed using this command or you do not have permission."
        await send_temp_message(ctx, msg)
    else:
        update_field(event_id, key, value)
        msg = "Set {} to {}.".format(key, value)
        await ctx.send(msg)


# ==== Documentation ====

@bot.command()
async def help(ctx):
    title = "== eventbot v{} (by Meeow) ==".format(__version__)
    embed = discord.Embed(title=title, description="List of commands are:", color=0xeee657)

    embed.add_field(
        name="!schedule [name] [date (mm/dd)] [time] [description]", 
        value='''Create a new event. 
        Use quotes if your name or description parameter has spaces in it.
        Example: `!schedule "Scrim against SHD" "Descriptive description." 3/14 1:00PM`
        Aliases: !sched''', 
        inline=False)

    embed.add_field(
        name="!reschedule [name] [datetime] ", 
        value='''Edit the time of an existing event.  
        Use quotes if your name or description parameter has spaces in it.
        Example: `!reschedule "Scrim against SHD" 4/1 13:30`
        Aliases: !resched, !rs''', 
        inline=False)

    embed.add_field(
        name="!unschedule [event_name]", 
        value='''Delete the specified event entirely. Usage restricted to author of the event and admins.
        Aliases: !unsched, !us''', 
        inline=False)

    embed.add_field(
        name="!unschedule_past", 
        value='''Delete ALL past events entirely.
        Aliases: !usp''', 
        inline=False)

    embed.add_field(
        name="!show_all", 
        value='''Show name and time for all upcoming events.
        Aliases: !sa''', 
        inline=False)

    embed.add_field(
        name="!show [event_name]", 
        value="Show all details for the specified event.", 
        inline=False)

    embed.add_field(
        name="!edit [event_name] [field name] [new value]", 
        value='''Edit field with a string type value (not dates or attendance lists).
        Non-admins may not edit the `Author` field.
        Use quotes if your parameter has spaces in it. 
        `Example: !edit "Scrim against SHD" "Description" "Improved description."`''', 
        inline=False)


# ==== Undocumented Commands for Debugging/Admin ====
@bot.command()
async def set_attend(ctx, event_name, user_name, status):
    if is_admin(ctx):
        msg = set_attendance(event_name, user_name, status)
        await ctx.send(msg)

@bot.command()
async def factory(ctx, num_events=5):
    if num_events > 9:
        num_events = 9

    for num in range(num_events):
        date = '9/{}'.format(num+1)
        time = str(1 + num) + ':00pm'
        name = '-test' + str(num)
        msg = new_event(ctx, name, ctx.message.author.name, date, time)
        await ctx.send(msg)
        print ("Factory creating event on date {} at time {}".format(date, time))

    await ctx.send("Attempted to create {} test events".format(num_events))

@bot.command()
async def teardown(ctx):
    cursor = EVENTS.find({})
    for event in cursor:
        if event['Name'].startswith('-test'):
            delete_event(event['Name'])
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




