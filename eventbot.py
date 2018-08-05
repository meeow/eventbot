import discord, datetime, bisect
from discord.ext import commands

__python__ = 3.6
__author__ = "Meeow" + "github.com/meeow"
__version__ = "Alpha" + "https://github.com/meeow/eventbot"


# ==== Internal Logic ====

events = []
attendance = {}

# string name: name of event to create
# string date: date in mm/dd format 
# string mil_time: time in 24 hr format
# string description: descrption of event
def new_event(name, date, mil_time, description='No description.'):
    global events

    if name in attendance:
        return name + " already exists in upcoming events."

    time_format = '%m/%d-%H:%M'
    time = datetime.datetime.strptime(date + '-' + mil_time, time_format)

    new_event = [time, name, description]

    bisect.insort(events, new_event)
    attendance[name] = {}

    msg = pprint_event(name) + pprint_attendance_instructions()

    return msg 

# string name: name of event to get attendance of
def get_attendance(name):
    global attendance

    msg = ''
    if name not in attendance:
        return 'Unknown event name.'
        
    status = {}
    status['Attending'] = []
    status['Not attending'] = []
    status['Undecided'] = []

    for user in attendance[name]:
        if attendance[name][user] == "Attending":
            status['Attending'] += [user]
        elif attendance[name][user] == "Not attending":
            status['Not attending'] += [user]
        elif attendance[name][user] == "Undecided":
            status['Undecided'] += [user]

    return status

# string name: name of event to pretty print
def pprint_event(name):
    global events

    if name not in events:
        return "No event named {} found.".format(name)

    event = [_ for _ in events if _[1] == name][0]

    time = event[0].strftime("%A %-m/%-d %-I:%M%p")
    description = event[2]
    status = get_attendance(name)

    num_attending = len(status['Attending'])
    num_not_attending = len(status['Not attending'])
    num_undecided = len(status['Undecided'])

    for k in status.keys():
        if not status[k]:
            status[k] = ['None yet!']

    attending = ', '.join(status['Attending'])
    not_attending = ', '.join(status['Not attending'])
    undecided = ', '.join(status['Undecided'])

    msg = '''
**{}**
**Time:** {}
**Description:** {}
**Attending ({}):** {}
**Not attending ({}):** {}
**Undecided ({}):** {}
'''.format(name, time, description, num_attending, attending, num_not_attending, not_attending, num_undecided, undecided)

    return msg

def pprint_attendance_instructions():
    msg = '''\nIndicate or change your attendance plans by reacting to this message.
😃: Attending
😦: Not attending
🤔: Undecided
    '''
    return msg

def get_events():
    global events

    msg = ''
    if events == []:
        msg = 'No upcoming events.'
    else:
        for event in events:
            msg += pprint_event(event[1])

    return msg


# string event_name: name of event to change status of
# string user_name: name of user to change status of
# string status: new status
def change_attendance(event_name, user_name, status):
    global attendance

    if event_name not in attendance:
        return 'Unknown event name: {}'.format(event_name)
    
    attendance[event_name][user_name] = status

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
async def on_reaction_add(reaction, user):
    channel = reaction.message.channel
    status = emoji_to_status(reaction.emoji)
    event_name = reaction.message.content.splitlines()[0].replace('*','')

    if status == 'Unknown':
        msg = 'Not a valid reaction option. Please try again using one of the specified emojis.'
    else:  
        msg = change_attendance(event_name, user.name, status)

    await channel.send(msg)

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')

@bot.command()
async def show_events(ctx):
    msg = get_events()
    await ctx.send(msg)

@bot.command()
async def schedule(ctx, name, date, mil_time, description='No description.'):
    msg = new_event(name, date, mil_time, description)
    await ctx.send(msg)

@bot.command()
async def show_event(ctx, *, name):
    global events
    name = name.strip('\"')
    msg = pprint_event(name)

    if name in 
    await ctx.send(msg)

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="Schedule Bot", description="List of commands are:", color=0xeee657)

    embed.add_field(
        name="!schedule [name] [date (mm/dd)] [24-hr format time (hh:mm)] [description]", 
        value='''Create a new event. Use quotes if your name or description parameter has spaces in it.''', 
        inline=False)

    embed.add_field(
        name="!show_events", 
        value="Show details for all upcoming events.", 
        inline=False)

    embed.add_field(
        name="!show_event [event_name]", 
        value="Show details for the specified event.", 
        inline=False)

    await ctx.send(embed=embed)


# ==== Undocumented Commands for Debugging ====
@bot.command()
async def dump_attendance(ctx):
    global attendance
    await ctx.send(attendance)


# ==== Run Bot ====

bot.run('NDU5NDcyMDAxMzI1ODU4ODE2.Dg2wxg.aH5XVCGT0bxRM1NjF2jVHW8e7qI')




