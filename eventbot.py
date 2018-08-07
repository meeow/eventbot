import discord, datetime, bisect, copy
from discord.ext import commands
from pymongo import MongoClient

__python__ = 3.6
__author__ = "Meeow" + "github.com/meeow"
__version__ = "Alpha with MongoDB" + "https://github.com/meeow/eventbot"
bot_token = #insert here


# ==== Database Logic ====
client = MongoClient()
db = client.events
events = db.events

# ==== Internal Logic ====

#events = {}
statuses = ["Attending", "Not attending", "Undecided"]

# string name: name of event to search for
def event_exists(name):
    return bool(events.find({"Name": name}).limit(1).count())

# string name: name of event to create
# string date: date in mm/dd format 
# string mil_time: time in 24 hr format
# string description: descrption of event
def new_event(name, author, date, mil_time, description='No description.'):
    global events

    if event_exists(name):
        return name + " already exists in upcoming events."

    time_format = '%m/%d-%H:%M'
    time = datetime.datetime.strptime(date + '-' + mil_time, time_format)

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

def delete_event(name):
    global events

    result = events.remove({"Name": name})
    print (result)

    msg = "Successfully deleted {}.".format(name)
    return msg


# string name: name of event to get attendance of
def get_attendance(name):
    global events

    if name not in events:
        return 'Unknown event name.'
        
    msg = ''
    attendance = {}
    for status in statuses:
        attendance[status] = events[name][status]

    return attendance

# string name: name of event to pretty print
def pprint_event(name):
    global events

    if event_exists(name) == False:
        return "No event named {} found.".format(name)

    event = events.find_one({'Name': name})

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

    msg = '''
**{}**
**Time:** {}
**Scheduled By:** {}
**Description:** {}
**Attending ({}):** {}
**Not attending ({}):** {}
**Undecided ({}):** {}
'''.format(name, time, author, description, num_attending, attending, num_not_attending, not_attending, num_undecided, undecided)

    return msg

def pprint_attendance_instructions():
    msg = '''\n**Update your attendance plans by reacting to this message**.
😃: Attending
😦: Not attending
🤔: Undecided
    '''
    return msg

def get_events():
    global events

    msg = ''

    cursor = events.find({})
    for event in cursor:
        msg += pprint_event(event['Name'])

    if msg == '':
        msg = 'No upcoming events.'
    
    return msg

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

# string event_name: name of event to change status of
# string user_name: name of user to change status of
# string status: new status
def change_attendance(event_name, user_name, status):
    global events, statuses

    if not event_exists(event_name):
        return 'Unknown event name: {}'.format(event_name)
    
    event = events.find_one({'Name': event_name})
    event_id = event['_id']
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


# ==== User Interactions ====

bot = commands.Bot(command_prefix='!')

# Remove default help command
bot.remove_command('help')

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')

@bot.event
async def on_reaction_add(reaction, user):
    channel = reaction.message.channel
    status = emoji_to_status(reaction.emoji)
    event_name = reaction.message.content.splitlines()[0].replace('*','')

    if status == 'Unknown':
        msg = 'Not a valid reaction option. Please try again using one of the specified emojis.'
    else:  
        msg = change_attendance(event_name, user.name, status)

    await channel.send(msg)

# Commands

@bot.command()
async def show_all(ctx):
    msg = get_events()
    await ctx.send(msg)

@bot.command()
async def schedule(ctx, name, date, mil_time, description='No description.'):
    msg = new_event(name, ctx.message.author.name, date, mil_time, description)
    await ctx.send(msg)

@bot.command()
async def remove(ctx, name):
    msg = delete_event(name)
    await ctx.send(msg)

@bot.command()
async def show(ctx, *, name):
    global events
    name = name.strip('\"')
    msg = pprint_event(name)

    await ctx.send(msg)

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="== eventbot ==", description="List of commands are:", color=0xeee657)

    embed.add_field(
        name="!schedule [name] [date (mm/dd)] [24-hr format time (hh:mm)] [description]", 
        value='''Create a new event. Use quotes if your name or description parameter has spaces in it.
        Example: !schedule "Scrim against Shanghai Dragons" 4/20 16:20 "Descriptive description."''', 
        inline=False)

    embed.add_field(
        name="!show_all", 
        value="Show details for all upcoming events.", 
        inline=False)

    embed.add_field(
        name="!show [event_name]", 
        value="Show details for the specified event.", 
        inline=False)

    embed.add_field(
        name="!remove [event_name]", 
        value="Delete the specified event.", 
        inline=False)

    await ctx.send(embed=embed)


# ==== Undocumented Commands for Debugging ====
@bot.command()
async def dump_attendance(ctx):
    global attendance
    await ctx.send(attendance)

@bot.command()
async def dump_events(ctx):
    global events
    await ctx.send(events)


# ==== Run Bot ====

bot.run(bot_token)




