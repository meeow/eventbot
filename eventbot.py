import discord, datetime
from discord.ext import commands
from pymongo import MongoClient
from os import environ

__python__ = 3.6
__author__ = "Meeow" + "github.com/meeow"
__version__ = "Alpha with MongoDB" + "https://github.com/meeow/eventbot"
bot_token =  environ['BOT_TOKEN'] 

# TODO:
# - Add option to reschedule (edit time) existing events
# - Add option to add player to existing event via command, not reaction
# - Send reminders (DM or mentions) close to start time of event
# - Unit tests

# Nice to haves:
# - Role permissions to call certain commands


# ==== Database and Context Setup ====
mlab_user = environ['MONGOUSER']
mlab_pass = environ['MONGOPASS']

client = MongoClient("ds018498.mlab.com", 18498)
db = client.eventbot
db.authenticate(mlab_user, mlab_pass)
events = db.events

statuses = ["Attending", "Not attending", "Undecided"]

# ==== Helper Functions ====
# string name: name of event to search for
def event_exists(name):
    return bool(events.find({"Name": name}).limit(1).count())

# datetime time: time to search for conflicts
def time_exists(time):
    return bool(events.find({"Time": time}).limit(1).count())

# string name: name of event to return
def get_event(name):
    global events

    event = events.find_one({'Name': name})
    print ("Fetched " + str(event))

    return event

# string name: name of event to find id of
def name_to_id(name):
    event = events.find_one({'Name': name})
    event_id = event['_id']
    return event_id

# User user: User object to convert to user.name + user.discriminator
def user_to_username(user):
    return "{}#{}".format(user.name, user.discriminator)

# string emoji: reaction emoji from discord event
def emoji_to_status(emoji):
    status = 'Unknown'

    if emoji in (':smiley:', '😃'):
        status = 'Attending'
    elif emoji in (':frowning:', '😦'):
        status = 'Not attending'
    elif emoji in (':thinking:', '🤔'):
        status = 'Undecided'

    return status

def pprint_attendance_instructions():
    msg = '''\n**Update your attendance plans by reacting to this message**.
😃: Attending
😦: Not attending
🤔: Undecided
    '''
    return msg

# int id: value of _id field of target mongodb document 
# * key: name of field to update
# * value: value to update field with
def update_field(id, key, value):
    result = events.update_one(
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

# ==== Internal Logic ====
# string name: name of event to create
# string date: date in mm/dd format 
# string mil_time: time in 24 hr format
# string description: descrption of event
def new_event(name, author, date, mil_time, description='No description.'):
    global events

    if event_exists(name):
        return name + " already exists in upcoming events."

    year = str(datetime.datetime.now().year)

    time_format = '%m/%d/%Y-%H:%M'
    time = datetime.datetime.strptime(date + '/' + year + '-' + mil_time, time_format)

    if time_exists(time):
        return "There is already an event scheduled for {}".format(time.strftime("%A %-m/%-d %-I:%M%p"))

    event = {}
    event["Name"] = name
    event["Author"] = author
    event["Time"] = time
    event["Description"] = description
    for status in statuses:
        event[status] = []

    result = events.insert_one(event)
    print (result)

    msg = pprint_event(name) + pprint_attendance_instructions()

    return msg 

# string name: name of event to delete
def delete_event(name):
    global events

    result = events.remove({"Name": name})
    print (result)

    msg = "Successfully removed {}.".format(name)
    return msg

# string name: name of event to pretty print
# bool verbose: print only name and time if False
def pprint_event(name, verbose=True):
    if event_exists(name) == False:
        return "No event named {} found.".format(name)

    event = get_event(name)

    time = event["Time"].strftime("%A %-m/%-d %-I:%M%p")
    description = event["Description"]
    author = event["Author"]

    num_attending = len(event['Attending'])
    num_not_attending = len(event['Not attending'])
    num_undecided = len(event['Undecided'])

    for s in statuses:
        if not event[s]:
            event[s] = ['None yet!']

    attending = ', '.join(event['Attending'])
    not_attending = ', '.join(event['Not attending'])
    undecided = ', '.join(event['Undecided'])

    if verbose:
        msg = '''
**{}**
**Time:** {}
**Author:** {}
**Description:** {}
**Attending ({}):** {}
**Not attending ({}):** {}
**Undecided ({}):** {}
'''.format(name, time, author, description, num_attending, attending, 
    num_not_attending, not_attending, num_undecided, undecided)
    else:
        msg = '''
**{}**
**Time:** {}
'''.format(name, time)

    return msg

def get_events():
    global events

    msg = 'Showing all events. Use command `!show [event name]` for detailed info.\n'

    cursor = events.find({})
    for event in cursor:
        msg += pprint_event(event['Name'], verbose=False)

    if msg == '':
        msg = 'No upcoming events.'
    
    return msg

# string event_name: name of event to change status of
# string user: username#discriminator of user to change status of
# string status: new status
def change_attendance(event_name, user, status):
    global events, statuses

    if not event_exists(event_name):
        return 'Unknown event name: {}'.format(event_name)
    
    if not isinstance(user, str):
        user_name = user_to_username(user)
    else:
        user_name = user

    event = get_event(event_name)
    event_id = name_to_id(event_name)
    attendance_status = event[status] + [user_name]

    existing_status = ()
    for s in statuses:
        if user_name in event[s]:
            event[s].remove(user_name)
            existing_status = [s, event[s]]

    if existing_status:
        update_field(event_id, existing_status[0], existing_status[1])

    result = update_field(event_id, status, attendance_status)

    print (result)

    return "Set **{}'s** status to **{}** for **{}**.".format(user_name, status, event_name)


# ==== User Interactions ====

bot = commands.Bot(command_prefix='!')

# Remove default help command
bot.remove_command('help')

# Events 

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')

@bot.event
async def on_reaction_add(reaction, user):
    listen_to_reactions = "by reacting to this message" in reaction.message.content

    if listen_to_reactions:
        channel = reaction.message.channel
        status = emoji_to_status(reaction.emoji)
        event_name = reaction.message.content.splitlines()[0].replace('*','')

        if status == 'Unknown':
            msg = 'Not a valid reaction option. Please try again using one of the specified emojis.'
        else:  
            msg = change_attendance(event_name, user, status)

        await channel.send(msg)

# Commands

@bot.command()
async def show(ctx, *, name):
    name = name.strip('\"')
    msg = pprint_event(name) + pprint_attendance_instructions()
    await ctx.send(msg)

@bot.command()
async def show_all(ctx):
    msg = get_events()
    await ctx.send(msg)

@bot.command()
async def schedule(ctx, name, date, mil_time, description='No description.'):
    msg = new_event(name, ctx.message.author.name + '#' + ctx.message.author.discriminator, date, mil_time, description)
    await ctx.send(msg)

@bot.command()
async def remove(ctx, *, name):
    msg = delete_event(name)
    await ctx.send(msg)

# User can change value of a field which is a string.
@bot.command()
async def edit(ctx, name, key, value):
    global events 

    msg = ''
    event_id = name_to_id(name)
    event = get_event(name)

    if not (event and event_id):
        msg = 'Error: event name not found'        

    if key in event and not isinstance(event[key], str):
        msg = "Error: the specified field is not a string and cannot be changed using this command."
    else:
        update_field(event_id, key, value)
        msg = "Set {} to {}.".format(key, value)

    await ctx.send(msg)

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="== eventbot (by Meeow) ==", description="List of commands are:", color=0xeee657)

    embed.add_field(
        name="!schedule [name] [date (mm/dd)] [24-hr format time (hh:mm)] [description]", 
        value='''Create a new event. 
        Use quotes if your name or description parameter has spaces in it.
        Example: !schedule "Scrim against Shanghai Dragons" 4/20 16:20 "Descriptive description."''', 
        inline=False)

    embed.add_field(
        name="!show_all", 
        value="Show name and time for all upcoming events.", 
        inline=False)

    embed.add_field(
        name="!show [event_name]", 
        value="Show all details for the specified event.", 
        inline=False)

    embed.add_field(
        name="!remove [event_name]", 
        value="Delete the specified event.", 
        inline=False)

    embed.add_field(
        name="!edit [event_name] [field name] [new value]", 
        value='''Edit field with a string type value (not dates or attendance lists).
        Use quotes if your parameter has spaces in it.
        Example: !edit "Scrim against Shanghai Dragons" "Description" "Improved description."''', 
        inline=False)

    await ctx.send(embed=embed)


# ==== Undocumented Commands for Debugging/Admin Control ====
@bot.command()
async def dump_attendance(ctx):
    global attendance
    await ctx.send(attendance)

@bot.command()
async def dump_events(ctx):
    global events
    await ctx.send(events)

@bot.command()
async def change_attend(ctx, event_name, user_name, status):
    msg = change_attendance(event_name, user_name, status)
    await ctx.send(msg)

# ==== Run Bot ====

bot.run(bot_token)




